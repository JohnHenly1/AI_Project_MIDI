import tkinter as tk
from tkinter import messagebox, filedialog

# ------------------ GLOBALS ------------------
note_positions = {}
active_notes = {}
note_length = 120
grid_step = 100
current_time_x = 0
playing = False
tempo_bpm = 90

dragging_note = None
resizing_note = None
drag_start_x = 0
note_original_coords = None
note_y_fixed = None
dragging_playhead = False

note_colors = {}
base_colors = [
    "#4CAF50", "#2196F3", "#FF9800",
    "#9C27B0", "#E91E63", "#00BCD4", "#8BC34A"
]

selected_note = None

# ------------------ FUNCTIONS ------------------

def generate_song():
    lyrics = lyrics_box.get("1.0", tk.END).strip()
    if not lyrics:
        messagebox.showwarning("No Lyrics", "Please enter or load some lyrics first.")
        return
    messagebox.showinfo("AI Singing", f"AI will sing these lyrics:\n\n{lyrics[:200]}...")

def load_lyrics():
    file_path = filedialog.askopenfilename(
        title="Open Lyrics File",
        filetypes=(("Text Files", "*.txt"), ("All Files", "*.*"))
    )
    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            lyrics_box.delete("1.0", tk.END)
            lyrics_box.insert(tk.END, f.read())

def get_note_color(note):
    if note not in note_colors:
        idx = len(note_colors) % len(base_colors)
        note_colors[note] = base_colors[idx]
    return note_colors[note]

def create_or_move_note(note):
    global current_time_x
    pressed_note_label.config(text=f"🎹 You pressed: {note}")

    y = note_positions[note]
    grid_x = (current_time_x // grid_step) * grid_step
    key = (note, grid_x)

    if key in active_notes:
        return

    color = get_note_color(note)
    rect = piano_roll.create_rectangle(
        grid_x, y - 8, grid_x + note_length, y + 8,
        fill=color, outline="black", tags=("note", note)
    )
    active_notes[key] = rect
    bind_note_events(rect, note)
    current_time_x += note_length // 2
    draw_playhead()

def bind_note_events(rect, note):
    piano_roll.tag_bind(rect, "<Button-1>", lambda e, r=rect, n=note: start_drag(e, r, n))
    piano_roll.tag_bind(rect, "<B1-Motion>", lambda e, r=rect: do_drag(e, r))
    piano_roll.tag_bind(rect, "<ButtonRelease-1>", lambda e, r=rect: stop_drag(e, r))
    piano_roll.tag_bind(rect, "<Button-3>", lambda e, r=rect: start_resize(e, r))
    piano_roll.tag_bind(rect, "<B3-Motion>", lambda e, r=rect: do_resize(e, r))
    piano_roll.tag_bind(rect, "<ButtonRelease-3>", lambda e, r=rect: stop_resize(e, r))
    piano_roll.tag_bind(rect, "<Double-Button-3>", lambda e, r=rect: delete_note(r))

def start_drag(event, rect, note):
    global dragging_note, drag_start_x, note_original_coords, note_y_fixed, selected_note
    dragging_note = rect
    selected_note = rect
    highlight_selected(rect)
    drag_start_x = event.x
    note_original_coords = piano_roll.coords(rect)
    note_y_fixed = (note_original_coords[1] + note_original_coords[3]) / 2  # lock Y center

def do_drag(event, rect):
    if not dragging_note:
        return
    dx = event.x - drag_start_x
    x1, y1, x2, y2 = note_original_coords
    piano_roll.coords(rect, x1 + dx, note_y_fixed - 8, x2 + dx, note_y_fixed + 8)

def stop_drag(event, rect):
    global dragging_note
    dragging_note = None

def start_resize(event, rect):
    global resizing_note, resize_start_x, note_original_coords
    resizing_note = rect
    resize_start_x = event.x
    note_original_coords = piano_roll.coords(rect)

def do_resize(event, rect):
    if not resizing_note:
        return
    dx = event.x - resize_start_x
    x1, y1, x2, y2 = note_original_coords
    new_x2 = max(x1 + 20, x2 + dx)
    piano_roll.coords(rect, x1, y1, new_x2, y2)

def stop_resize(event, rect):
    global resizing_note
    resizing_note = None

def delete_note(rect):
    """Delete selected note."""
    piano_roll.delete(rect)
    for key, val in list(active_notes.items()):
        if val == rect:
            del active_notes[key]
            break

def highlight_selected(rect):
    """Show visual highlight for selected note."""
    for _, r in active_notes.items():
        piano_roll.itemconfig(r, width=1)
    piano_roll.itemconfig(rect, width=3)

def draw_piano_keys():
    piano_canvas.delete("all")
    note_positions.clear()

    white_notes = ["C", "D", "E", "F", "G", "A", "B"]
    all_notes = []
    for octave in range(6, 3, -1):  # B6 down to E4
        for n in white_notes:
            all_notes.append(f"{n}{octave}")
            if n in ["C", "D", "F", "G", "A"]:
                all_notes.append(f"{n}#{octave}")

    y_pos = 0
    for note in all_notes:
        is_black = "#" in note
        color = "black" if is_black else "white"
        text_color = "white" if is_black else "black"
        h = 20
        piano_canvas.create_rectangle(0, y_pos, 80, y_pos + h, fill=color, outline="gray")
        piano_canvas.create_text(40, y_pos + h / 2, text=note, fill=text_color, font=("Arial", 9))
        rect = piano_canvas.create_rectangle(0, y_pos, 80, y_pos + h, outline="", fill="", tags="key")
        piano_canvas.tag_bind(rect, "<Button-1>", lambda e, n=note: create_or_move_note(n))
        note_positions[note] = y_pos + h / 2
        y_pos += h

def draw_grid():
    piano_roll.delete("grid")
    for x in range(0, 4000, grid_step):
        piano_roll.create_line(x, 0, x, 2000, fill="#eee", tags="grid")
    for y in note_positions.values():
        piano_roll.create_line(0, y, 4000, y, fill="#f2f2f2", tags="grid")

def draw_playhead():
    piano_roll.delete("playhead")
    playhead = piano_roll.create_line(current_time_x, 0, current_time_x, 2000, fill="red", width=2, tags="playhead")
    piano_roll.tag_bind(playhead, "<Button-1>", start_playhead_drag)
    piano_roll.tag_bind(playhead, "<B1-Motion>", do_playhead_drag)
    piano_roll.tag_bind(playhead, "<ButtonRelease-1>", stop_playhead_drag)

def start_playhead_drag(event):
    global dragging_playhead
    dragging_playhead = True
    update_playhead_position(event.x)

def do_playhead_drag(event):
    if dragging_playhead:
        update_playhead_position(event.x)

def stop_playhead_drag(event):
    global dragging_playhead
    dragging_playhead = False

def update_playhead_position(x):
    global current_time_x
    current_time_x = x
    draw_playhead()

def toggle_play():
    global playing
    playing = not playing
    play_btn.config(text="Stop" if playing else "Play")
    if playing:
        move_playhead()

def move_playhead():
    global current_time_x
    if not playing:
        return
    current_time_x += 5
    draw_playhead()
    root.after(int(60000 / tempo_bpm / 4), move_playhead)

def delete_selected(event=None):
    """Delete selected note with Delete key."""
    global selected_note
    if selected_note:
        delete_note(selected_note)
        selected_note = None

# ------------------ MAIN WINDOW ------------------

root = tk.Tk()
root.title("🎵 AI Singing — Piano Roll Editor")
root.geometry("1200x700")
root.configure(bg="#f5f5f5")

root.bind("<Delete>", delete_selected)

# Header
tk.Label(root, text="AI Singing — Piano Roll Editor", font=("Arial", 16, "bold"), bg="#f5f5f5").pack(pady=5)

lyrics_box = tk.Text(root, wrap="word", font=("Arial", 12), height=4)
lyrics_box.pack(fill="x", padx=20, pady=10)

controls = tk.Frame(root, bg="#f5f5f5")
controls.pack()

play_btn = tk.Button(controls, text="Play", width=10, command=toggle_play)
play_btn.pack(side="left", padx=5)

tk.Label(controls, text="Tempo (BPM):", bg="#f5f5f5").pack(side="left")
tempo_spin = tk.Spinbox(controls, from_=60, to=200, width=5)
tempo_spin.pack(side="left", padx=5)

tk.Button(controls, text="Load Lyrics", command=load_lyrics, width=12).pack(side="left", padx=5)
tk.Button(controls, text="Generate Song", command=generate_song, width=15, bg="#0078D7", fg="white").pack(side="left", padx=10)

pressed_note_label = tk.Label(root, text="🎹 Press a piano key", font=("Arial", 11, "italic"), bg="#f5f5f5")
pressed_note_label.pack(pady=5)

main_frame = tk.Frame(root)
main_frame.pack(expand=True, fill="both", padx=10, pady=10)

piano_canvas = tk.Canvas(main_frame, width=80, bg="#dcdcdc")
piano_canvas.pack(side="left", fill="y")

roll_frame = tk.Frame(main_frame)
roll_frame.pack(side="left", fill="both", expand=True)

x_scroll = tk.Scrollbar(roll_frame, orient="horizontal")
y_scroll = tk.Scrollbar(roll_frame, orient="vertical")

piano_roll = tk.Canvas(
    roll_frame, bg="white",
    scrollregion=(0, 0, 4000, 2000),
    xscrollcommand=x_scroll.set,
    yscrollcommand=y_scroll.set
)
x_scroll.config(command=piano_roll.xview)
y_scroll.config(command=piano_roll.yview)
x_scroll.pack(side="bottom", fill="x")
y_scroll.pack(side="right", fill="y")
piano_roll.pack(side="left", fill="both", expand=True)

# Init
draw_piano_keys()
draw_grid()
draw_playhead()

root.mainloop()
