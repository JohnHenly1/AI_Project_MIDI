import tkinter as tk
from tkinter import simpledialog, messagebox
import time
import threading


# ---------------- CONFIG ----------------
PITCHES = [
    "C6","B5","A#5","A5","G#5","G5","F#5","F5","E5","D#5","D5","C#5",
    "C5","B4","A#4","A4","G#4","G4","F#4","F4","E4","D#4","D4","C#4","C4"
]
ROW_H = 26
KEY_W = 70
GRID_STEP = 64
NOTE_MIN_W = 32
NOTE_H = ROW_H - 4
PLAY_BPM = 90   # fixed BPM (tempo control removed as requested)
SCENE_WIDTH = 4000


# ---------------- MAIN APP ----------------
class SingItClanker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sing it Clanker — AI Piano Roll")
        self.geometry("1100x650")
        self.config(bg="#1a1a1a")


        # Toolbar (play/stop only)
        toolbar = tk.Frame(self, bg="#111")
        toolbar.pack(side="top", fill="x")


        tk.Button(toolbar, text="Play", command=self.play).pack(side="left", padx=5)
        tk.Button(toolbar, text="Stop", command=self.stop).pack(side="left", padx=5)


        # Piano + Canvas frame
        frame = tk.Frame(self)
        frame.pack(side="top", fill="both", expand=True)


        self.piano = tk.Canvas(frame, width=KEY_W, bg="#e0e0e0", highlightthickness=0)
        self.piano.pack(side="left", fill="y")


        self.canvas = tk.Canvas(frame, bg="#1f1f1f",
                                scrollregion=(0,0,SCENE_WIDTH,len(PITCHES)*ROW_H))
        self.canvas.pack(side="left", fill="both", expand=True)


        vbar = tk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        hbar = tk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.config(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")


        # Bindings (notes and UI)
        self.canvas.bind("<Button-3>", self.add_note)                 # right-click add note
        self.canvas.bind("<Button-1>", self.on_left_down)            # left down (notes or playline)
        self.canvas.bind("<B1-Motion>", self.on_drag)                # left drag (notes or playline)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)       # left release
        self.canvas.bind("<Double-1>", self.edit_lyric)              # double-click edit lyric
        self.bind("<Delete>", self.delete_selected)                  # delete key


        # State
        self.notes = {}           # rect_id -> {"text": text_id, "row": row}
        self.selected = None
        self.drag_mode = None     # "move" or "resize"
        self.play_line = None
        self.playing = False
        self.play_thread = None
        self.play_x = 0.0
        self.play_dragging = False   # when user drags the playhead


        # Draw
        self.draw_piano()
        self.draw_grid()
        # create playline ready (visible)
        self.play_line = self.canvas.create_line(self.play_x, 0, self.play_x, len(PITCHES)*ROW_H,
                                                 fill="red", width=2, tags=("playhead",))


        # Info footer
        self.status = tk.Label(self, text="Right-click add note | Double-click edit lyric | Drag red line to move playhead",
                               bg="#111", fg="white", anchor="w")
        self.status.pack(side="bottom", fill="x")


    # ---------------- DRAWING ----------------
    def draw_piano(self):
        self.piano.delete("all")
        y = 0
        for p in PITCHES:
            color = "#fff" if "#" not in p else "#d0d0d0"
            self.piano.create_rectangle(0, y, KEY_W, y+ROW_H, fill=color, outline="#aaa")
            self.piano.create_text(KEY_W/2, y+ROW_H/2, text=p, font=("Arial",9))
            y += ROW_H


    def draw_grid(self):
        self.canvas.delete("grid")
        for i in range(len(PITCHES)):
            y = i * ROW_H
            fill = "#222" if i % 2 == 0 else "#242424"
            self.canvas.create_rectangle(0, y, SCENE_WIDTH, y+ROW_H, fill=fill, outline="", tags="grid")
        for x in range(0, SCENE_WIDTH, GRID_STEP):
            self.canvas.create_line(x, 0, x, len(PITCHES)*ROW_H, fill="#333", tags="grid")


    def snap_x(self, x):
        # snap to GRID_STEP
        return int(round(x / GRID_STEP)) * GRID_STEP


    def snap_y(self, y):
        return int(y // ROW_H) * ROW_H


    # ---------------- NOTES ----------------
    def add_note(self, event):
        x = self.snap_x(self.canvas.canvasx(event.x))
        y = self.snap_y(self.canvas.canvasy(event.y))
        rect = self.canvas.create_rectangle(x, y+2, x+GRID_STEP, y+NOTE_H+2,
                                            fill="#4fc3f7", outline="#003c46", width=2, tags=("note",))
        text = self.canvas.create_text(x + GRID_STEP/2, y+NOTE_H/2+2, text="", fill="#003c46", font=("Arial",10), tags=("note_text",))
        self.notes[rect] = {"text": text, "row": int(y//ROW_H)}
        self.select(rect)


    def select(self, rect):
        # visually indicate selection
        if self.selected and self.selected in self.canvas.find_all():
            try:
                self.canvas.itemconfig(self.selected, width=1)
            except Exception:
                pass
        self.selected = rect
        if rect:
            self.canvas.tag_raise(rect)
            self.canvas.itemconfig(rect, width=3)


    def edit_lyric(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        hits = self.canvas.find_overlapping(x, y, x, y)
        for item in hits:
            if item in self.notes:
                text_id = self.notes[item]["text"]
                cur_text = self.canvas.itemcget(text_id, "text")
                new = simpledialog.askstring("Edit Lyric", "Enter lyric:", initialvalue=cur_text, parent=self)
                if new is not None:
                    self.canvas.itemconfig(text_id, text=new)
                return


    # ---------------- DRAGGING NOTES ----------------
    def on_left_down(self, e):
        """
        Left button down: either start dragging playhead if clicked on it,
        or start note selection/move/resize.
        """
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)
        hits = self.canvas.find_overlapping(x, y, x, y)


        # 1) if playhead was clicked, start dragging playhead (priority)
        if self.play_line and self.play_line in hits:
            self.play_dragging = True
            # stop playback while dragging
            self.stop()
            return


        # 2) otherwise check for note hit (preserve full note adjust behavior)
        rect = next((i for i in hits if i in self.notes), None)
        if rect:
            self.select(rect)
            x1, y1, x2, y2 = self.canvas.coords(rect)
            # near right edge? treat as resize
            if (x2 - 8) <= x <= (x2 + 4):
                self.drag_mode = "resize"
            else:
                self.drag_mode = "move"
            self.start_x, self.start_y = x, y
            self.orig_coords = (x1, y1, x2, y2)
        else:
            # click empty space -> deselect
            self.select(None)


    def on_drag(self, e):
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)


        # if dragging playhead, update its x and visual immediately
        if self.play_dragging:
            self.play_x = max(0.0, min(SCENE_WIDTH, x))
            self.canvas.coords(self.play_line, self.play_x, 0, self.play_x, len(PITCHES)*ROW_H)
            # optionally update status
            self.status.config(text=f"Playhead px={int(self.play_x)}")
            return


        # else, handle note move/resize as before
        if not self.selected or not self.drag_mode:
            return


        dx = x - self.start_x
        dy = y - self.start_y
        x1, y1, x2, y2 = self.orig_coords
        rect = self.selected
        txt = self.notes[rect]["text"]


        if self.drag_mode == "move":
            new_x = self.snap_x(x1 + dx)
            new_y = self.snap_y(y1 + dy)
            w = x2 - x1
            new_x = max(0, min(SCENE_WIDTH - w, new_x))
            new_y = max(0, min(len(PITCHES)*ROW_H - NOTE_H, new_y))
            self.canvas.coords(rect, new_x, new_y, new_x + w, new_y + NOTE_H)
            self.canvas.coords(txt, new_x + w/2, new_y + NOTE_H/2)
        else:  # resize
            new_x2 = max(x1 + NOTE_MIN_W, self.snap_x(x2 + dx))
            new_x2 = min(SCENE_WIDTH, new_x2)
            self.canvas.coords(rect, x1, y1, new_x2, y2)
            self.canvas.coords(txt, (x1 + new_x2) / 2, y1 + NOTE_H/2)


    def on_left_up(self, e):
        # stop any note drag or playhead drag
        self.drag_mode = None
        if self.play_dragging:
            self.play_dragging = False
            # update status after dropping playhead
            self.status.config(text=f"Playhead set to px={int(self.play_x)}")


    def delete_selected(self, _=None):
        if not self.selected: return
        rect = self.selected
        text_id = self.notes[rect]["text"]
        self.canvas.delete(rect)
        self.canvas.delete(text_id)
        del self.notes[rect]
        self.selected = None


    # ---------------- PLAYBACK ----------------
    def play(self):
        if self.playing:
            return
        self.playing = True
        # ensure play line present
        if not self.play_line:
            self.play_line = self.canvas.create_line(self.play_x, 0, self.play_x, len(PITCHES)*ROW_H,
                                                     fill="red", width=2, tags=("playhead",))
        # run loop in background
        self.play_thread = threading.Thread(target=self.play_loop, daemon=True)
        self.play_thread.start()


    def stop(self):
        self.playing = False


    def play_loop(self):
        bpm = PLAY_BPM
        beat_time = 60.0 / bpm
        # compute start_time such that existing play_x positions correctly
        start_time = time.time() - (self.play_x / GRID_STEP) * beat_time
        while self.playing:
            elapsed = time.time() - start_time
            self.play_x = (elapsed / beat_time) * GRID_STEP
            if self.play_x > SCENE_WIDTH:
                self.playing = False
                break
            # update line on main thread via after
            px = self.play_x
            self.canvas.after(0, lambda p=px: self.canvas.coords(self.play_line, p, 0, p, len(PITCHES)*ROW_H))
            time.sleep(0.02)
        self.playing = False


# ---------------- RUN ----------------
if __name__ == "__main__":
    app = SingItClanker()
    app.mainloop()



