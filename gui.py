import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
import os
import struct
import time
import threading
try:
    import winsound
except Exception:
    winsound = None
try:
    import simpleaudio as sa
except Exception:
    sa = None
import math
from array import array


def pitch_to_freq(name: str) -> float:
    """Convert note name like C4 or A#3 to frequency (Hz)."""
    name = name.strip()
    if not name:
        return 440.0
    # split note letters and octave digits
    i = len(name) - 1
    while i >= 0 and name[i].isdigit():
        i -= 1
    note = name[: i+1]
    octave = name[i+1:]
    try:
        oct_i = int(octave)
    except Exception:
        oct_i = 4
    semis = {
        'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4,
        'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9,
        'A#': 10, 'B': 11
    }
    if note not in semis:
        # try normalize (e.g., use flat -> sharp) minimal support
        note = note.replace('Bb', 'A#').replace('Db', 'C#').replace('Eb', 'D#').replace('Gb', 'F#').replace('Ab', 'G#')
    semitone = semis.get(note, 9)
    midi = (oct_i + 1) * 12 + semitone
    freq = 440.0 * (2 ** ((midi - 69) / 12.0))
    return freq


def play_tone(freq_hz: float, duration_ms: float):
    """Play a tone (non-blocking wrapper will spawn a thread)."""
    # Prefer simpleaudio sine/harmonic synthesis for a piano-like timbre
    if sa is not None:
        try:
            sample_rate = 44100
            duration_s = max(0.01, duration_ms / 1000.0)
            n_samples = int(sample_rate * duration_s)
            max_amp = 32767
            buf = array('h')
            # harmonic coefficients to approximate a piano-ish tone
            h = [1.0, 0.6, 0.3, 0.15]
            for i in range(n_samples):
                t = i / sample_rate
                s = 0.0
                for idx, coef in enumerate(h, start=1):
                    s += coef * math.sin(2.0 * math.pi * freq_hz * idx * t)
                # simple amplitude envelope: quick attack, exponential decay
                env = (1.0 - math.exp(-12.0 * t)) * math.exp(-4.0 * t)
                val = int(max(-max_amp, min(max_amp, s * env * 0.25 * max_amp)))
                buf.append(val)
            play_obj = sa.play_buffer(buf.tobytes(), 1, 2, sample_rate)
            play_obj.wait_done()
            return
        except Exception:
            # if synthesis fails, fall back to winsound if available
            pass

    if winsound:
        try:
            f = int(max(37, min(32767, round(freq_hz))))
            d = int(max(1, round(duration_ms)))
            winsound.Beep(f, d)
        except Exception:
            # ignore sound errors
            pass
    else:
        # no-op on non-Windows or missing sound backends
        return


# ---------------- CONFIG ----------------
PITCHES = [
    "C6","B5","A#5","A5","G#5","G5","F#5","F5","E5","D#5","D5","C#5",
    "C5","B4","A#4","A4","G#4","G4","F#4","F4","E4","D#4","D4","C#4",
    "C4","B3","A#3","A3","G#3","G3","F#3","F3","E3","D#3","D3","C#3",
    "C3","B2","A#2","A2","G#2","G2","F#2","F2","E2","D#2","D2","C#2","C2",
]
ROW_H = 26
KEY_W = 70
GRID_STEP = 64
NOTE_MIN_W = 32
NOTE_H = ROW_H - 4
PLAY_BPM = 145   # fixed BPM
SCENE_WIDTH = 4000

# Zoom base values (we keep base copies so zoom math is stable)
BASE_ROW_H = ROW_H
BASE_GRID_STEP = GRID_STEP
BASE_NOTE_MIN_W = NOTE_MIN_W
BASE_KEY_W = KEY_W

# Zoom limits
MIN_ZOOM = 0.25
MAX_ZOOM = 4.0
DEFAULT_ZOOM = 1.0


class SingItClanker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sing it Clanker — AI Piano Roll")
        self.geometry("1100x650")

        # Toolbar
        toolbar = tk.Frame(self)
        toolbar.pack(side="top", fill="x")
        tk.Button(toolbar, text="Play", command=self.play).pack(side="left", padx=4, pady=4)
        tk.Button(toolbar, text="Stop", command=self.stop).pack(side="left", padx=4, pady=4)
        # Stop and reset playhead to start
        tk.Button(toolbar, text="Stop+Reset", command=lambda: self.stop(True)).pack(side="left", padx=4, pady=4)
        # Tempo control (BPM)
        tk.Label(toolbar, text="Tempo:").pack(side="left", padx=(8,2))
        self.tempo_var = tk.IntVar(value=PLAY_BPM)
        self.tempo_spin = tk.Spinbox(toolbar, from_=20, to=300, textvariable=self.tempo_var, width=5)
        self.tempo_spin.pack(side="left", padx=2, pady=4)

        # Render Audio button (placeholder)
        tk.Button(toolbar, text="Render Audio", command=self.render_audio).pack(side="left", padx=4, pady=4)

        # Lyrics input and assign button
        tk.Label(toolbar, text="Lyrics:").pack(side="left", padx=(8,2))
        self.lyric_var = tk.StringVar(value="")
        self.lyric_entry = tk.Entry(toolbar, textvariable=self.lyric_var, width=30)
        self.lyric_entry.pack(side="left", padx=2, pady=4)
        tk.Button(toolbar, text="Assign Lyrics", command=self.assign_lyrics).pack(side="left", padx=4, pady=4)

    # Zoom UI removed per user request

        # Main frame with piano and canvas
        frame = tk.Frame(self)
        frame.pack(side="top", fill="both", expand=True)

        self.piano = tk.Canvas(frame, width=KEY_W, bg="#e0e0e0", highlightthickness=0)
        self.piano.pack(side="left", fill="y")

        self.canvas = tk.Canvas(frame, bg="#1f1f1f",
                                scrollregion=(0, 0, SCENE_WIDTH, len(PITCHES)*ROW_H))
        self.canvas.pack(side="left", fill="both", expand=True)

        # Scrollbars that synchronize both canvases
        vbar = tk.Scrollbar(frame, orient="vertical", command=self._on_vscroll)
        hbar = tk.Scrollbar(self, orient="horizontal", command=self._on_hscroll)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")
        self.canvas.config(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.piano.config(yscrollcommand=vbar.set)

        # Bindings
        self.canvas.bind("<Button-3>", self.add_note)
        self.canvas.bind("<Button-1>", self.on_left_down)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_up)
        self.canvas.bind("<Double-1>", self.edit_lyric)
        self.bind("<Delete>", self.delete_selected)

        # Make mouse wheel scroll both piano and main canvas vertically
        try:
            self.canvas.bind("<MouseWheel>", self._on_mousewheel)
            self.piano.bind("<MouseWheel>", self._on_mousewheel)
            # X11 / Linux support
            self.canvas.bind("<Button-4>", self._on_mousewheel)
            self.canvas.bind("<Button-5>", self._on_mousewheel)
            self.piano.bind("<Button-4>", self._on_mousewheel)
            self.piano.bind("<Button-5>", self._on_mousewheel)
        except Exception:
            pass

        # State
        self.notes = {}  # rect_id -> {"text": text_id, "row": row, "start_x": steps, "width_steps": steps}
        self.selected = None
        self.drag_mode = None
        self.orig_coords = None
        self.start_x = self.start_y = 0

        self.play_line = None
        self.playing = False
        self.play_thread = None
        self.play_x = 0.0
        self.play_dragging = False
        # playback sound state
        self._played_notes = set()
        self._prev_play_x = 0.0

        # zoom state
        self.current_h_zoom = DEFAULT_ZOOM
        self.current_v_zoom = DEFAULT_ZOOM

        # Draw initial
        self.draw_piano()
        self.draw_grid()
        self.play_line = self.canvas.create_line(self.play_x, 0, self.play_x, len(PITCHES)*ROW_H,
                                                 fill="red", width=2, tags=("playhead",))

        self.status = tk.Label(self, text="Right-click add note | Double-click edit lyric | Drag playhead to move", anchor="w")
        self.status.pack(side="bottom", fill="x")

        # shutdown flag
        self.shutting_down = False

        # protocol handler for safe shutdown
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def draw_piano(self):
        self.piano.delete("all")
        y = 0
        for p in PITCHES:
            color = "#fff" if "#" not in p else "#d0d0d0"
            self.piano.create_rectangle(0, y, KEY_W, y+ROW_H, fill=color, outline="#aaa")
            self.piano.create_text(KEY_W/2, y+ROW_H/2, text=p, font=("Arial", 9))
            y += ROW_H

    def draw_grid(self):
        self.canvas.delete("grid")
        height = len(PITCHES) * ROW_H
        for i in range(len(PITCHES)):
            y = i * ROW_H
            fill = "#222" if i % 2 == 0 else "#242424"
            self.canvas.create_rectangle(0, y, SCENE_WIDTH, y+ROW_H, fill=fill, outline="", tags="grid")
        for x in range(0, SCENE_WIDTH, GRID_STEP):
            self.canvas.create_line(x, 0, x, height, fill="#333", tags="grid")
        # draw ruler alongside grid
        try:
            self.draw_ruler()
        except Exception:
            pass

    def draw_ruler(self):
        """Draw a horizontal ruler where each GRID_STEP == a 16th note.
        Labels show bar numbers (every 16 steps = 1 bar in 4/4)."""
        self.ruler.delete("all")
        rh = int(self.ruler['height']) if 'height' in self.ruler.keys() else 24
        # ensure scrollregion matches scene width
        self.ruler.config(scrollregion=(0, 0, SCENE_WIDTH, rh))
        steps = int(SCENE_WIDTH // GRID_STEP) + 1
        for s in range(steps):
            x = s * GRID_STEP
            # major tick and label every 16 steps (one bar of 16 16th-notes)
            if s % 16 == 0:
                bar = s // 16 + 1
                # longer tick
                self.ruler.create_line(x, rh, x, 4, fill="#666", width=2)
                # label slightly inset
                self.ruler.create_text(x + 4, rh/2, text=str(bar), anchor="w", fill="#ddd", font=("Arial", 9))
            else:
                # short tick for other steps
                self.ruler.create_line(x, rh, x, rh-8, fill="#444")

    def snap_x(self, x):
        return int(round(x / GRID_STEP)) * GRID_STEP

    def snap_y(self, y):
        return int(y // ROW_H) * ROW_H

    # Notes
    def add_note(self, event):
        x = self.snap_x(self.canvas.canvasx(event.x))
        y = self.snap_y(self.canvas.canvasy(event.y))
        rect = self.canvas.create_rectangle(x, y+2, x+GRID_STEP, y+NOTE_H+2,
                                            fill="#4fc3f7", outline="#003c46", width=2, tags=("note",))
        text = self.canvas.create_text(x + GRID_STEP/2, y+NOTE_H/2+2, text="", fill="#003c46", font=("Arial", 10), tags=("note_text",))
        # store grid-based positions so zoom/redraw can recompute pixels
        self.notes[rect] = {"text": text, "row": int(y // ROW_H), "start_x": int(x // GRID_STEP), "width_steps": 1}
        self.select(rect)

    def select(self, rect):
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
    def text_to_phonemes(self, text: str):
        """Convert input text to a list of phoneme tokens using G2P.

        Preference order:
        1. `g2p_en` (best if installed)
        2. `pronouncing` (CMUdict lookup)
        3. fallback to simple grapheme split (characters)
        """
        if not text:
            return []
        words = text.strip().split()

        # Try g2p_en first
        try:
            from g2p_en import G2p
            g2p = G2p()
            phonemes = []
            for w in words:
                toks = g2p(w)
                # g2p returns a list; filter empty/space tokens
                toks = [t for t in toks if t and not t.isspace()]
                if toks:
                    phonemes.extend(toks)
                else:
                    phonemes.extend(list(w))
            return phonemes
        except Exception:
            pass

        # Next try pronouncing (CMUdict) as a lighter-weight fallback
        try:
            import pronouncing
            phonemes = []
            for w in words:
                phones = pronouncing.phones_for_word(w.lower())
                if phones:
                    phonemes.extend(phones[0].split())
                else:
                    phonemes.extend(list(w))
            return phonemes
        except Exception:
            # Final fallback: split into characters (graphemes)
            out = []
            for w in words:
                out.extend(list(w))
            return out

    def assign_lyrics(self):
        """Assign phoneme tokens from the lyrics entry to notes.

        Mapping rules:
        - Phonemes are assigned to consecutive notes ordered by start_x (then row).
        - If a note is selected, assignment starts from that note; otherwise from first note.
        - If phonemes exceed remaining notes, assignment stops when notes run out.
        """
        lyrics = self.lyric_var.get().strip()
        if not lyrics:
            messagebox.showinfo("Assign Lyrics", "No lyrics provided.")
            return
        phonemes = self.text_to_phonemes(lyrics)
        if not phonemes:
            messagebox.showinfo("Assign Lyrics", "No phonemes generated from input.")
            return

        # If the extracted token count is suspiciously low (e.g. one token per word),
        # try a per-word expansion to get finer-grained tokens.
        words = lyrics.split()
        try:
            if len(phonemes) <= len(words):
                alt = []
                # try pronouncing per-word expansion
                try:
                    import pronouncing
                    for w in words:
                        phones = pronouncing.phones_for_word(w.lower())
                        if phones:
                            alt.extend(phones[0].split())
                        else:
                            alt.extend(list(w))
                except Exception:
                    # try g2p per-word
                    try:
                        from g2p_en import G2p
                        g2p = G2p()
                        for w in words:
                            toks = [t for t in g2p(w) if t and not t.isspace()]
                            if toks:
                                alt.extend(toks)
                            else:
                                alt.extend(list(w))
                    except Exception:
                        # final fallback to characters
                        for w in words:
                            alt.extend(list(w))

                if len(alt) > len(phonemes):
                    phonemes = alt
        except Exception:
            pass

        # Debug: show tokens to the user so they can see what will be assigned
        try:
            dbg = ", ".join(str(p) for p in phonemes[:200])
            messagebox.showinfo("Assign Lyrics - Tokens", f"First tokens: {dbg}")
        except Exception:
            pass

        # Sort notes by start_x then row to get chronological ordering
        notes_sorted = sorted(self.notes.items(), key=lambda it: (it[1]["start_x"], it[1]["row"]))
        if not notes_sorted:
            messagebox.showinfo("Assign Lyrics", "No notes available to assign lyrics to.")
            return

        rects = [r for r, _ in notes_sorted]
        start_idx = 0
        if self.selected and self.selected in rects:
            start_idx = rects.index(self.selected)

        assigned = 0
        for i, ph in enumerate(phonemes):
            idx = start_idx + i
            if idx >= len(rects):
                break
            rect_id, info = notes_sorted[idx]
            text_id = info["text"]
            try:
                self.canvas.itemconfig(text_id, text=ph)
                assigned += 1
            except Exception:
                pass

        messagebox.showinfo("Assign Lyrics", f"Assigned {assigned} phoneme(s) starting at note #{start_idx+1}.")

    # Dragging
    def on_left_down(self, e):
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)
        hits = self.canvas.find_overlapping(x, y, x, y)

        # check playhead first
        for item in hits:
            if "playhead" in self.canvas.gettags(item):
                self.play_dragging = True
                self.stop()
                return

        rect = next((i for i in hits if i in self.notes), None)
        if rect:
            self.select(rect)
            x1, y1, x2, y2 = self.canvas.coords(rect)
            if (x2 - 8) <= x <= (x2 + 4):
                self.drag_mode = "resize"
            else:
                self.drag_mode = "move"
            self.start_x, self.start_y = x, y
            self.orig_coords = (x1, y1, x2, y2)
        else:
            self.select(None)

    def on_drag(self, e):
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)

        if self.play_dragging:
            self.play_x = max(0.0, min(SCENE_WIDTH, x))
            self.canvas.coords(self.play_line, self.play_x, 0, self.play_x, len(PITCHES)*ROW_H)
            self.status.config(text=f"Playhead px={int(self.play_x)}")
            return

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
            # update stored grid positions
            self.notes[rect]["start_x"] = int(new_x // GRID_STEP)
            self.notes[rect]["row"] = int(new_y // ROW_H)
        else:
            new_x2 = max(x1 + NOTE_MIN_W, self.snap_x(x2 + dx))
            new_x2 = min(SCENE_WIDTH, new_x2)
            self.canvas.coords(rect, x1, y1, new_x2, y2)
            self.canvas.coords(txt, (x1 + new_x2) / 2, y1 + NOTE_H/2)
            # update width in grid steps
            self.notes[rect]["width_steps"] = max(1, int((new_x2 - x1) // GRID_STEP))

    def on_left_up(self, e):
        self.drag_mode = None
        if self.play_dragging:
            self.play_dragging = False
            self.status.config(text=f"Playhead set to px={int(self.play_x)}")
        else:
            # finalize storing grid-aligned positions for selected note
            if self.selected and self.selected in self.notes:
                x1, y1, x2, y2 = self.canvas.coords(self.selected)
                self.notes[self.selected]["start_x"] = int(x1 // GRID_STEP)
                self.notes[self.selected]["width_steps"] = max(1, int((x2 - x1) // GRID_STEP))
                self.notes[self.selected]["row"] = int(y1 // ROW_H)

    def delete_selected(self, _=None):
        if not self.selected:
            return
        rect = self.selected
        text_id = self.notes[rect]["text"]
        self.canvas.delete(rect)
        self.canvas.delete(text_id)
        del self.notes[rect]
        self.selected = None

    # Playback
    def play(self):
        if self.playing:
            return
        self.playing = True
        # reset playback note history for this run
        self._played_notes = set()
        self._prev_play_x = self.play_x
        if not self.play_line:
            self.play_line = self.canvas.create_line(self.play_x, 0, self.play_x, len(PITCHES)*ROW_H,
                                                     fill="red", width=2, tags=("playhead",))
        self.play_thread = threading.Thread(target=self.play_loop, daemon=True)
        self.play_thread.start()

    def stop(self):
        # Stop playback without resetting playhead by default.
        # Pass reset=True to also move the playhead back to start (x=0)
        self.playing = False

    def stop(self, reset: bool = False):
        # Backwards-compatible stop that can optionally reset playhead
        self.playing = False
        if reset:
            try:
                self.play_x = 0.0
                self._prev_play_x = 0.0
                # clear played-note history so notes will play again on next run
                try:
                    self._played_notes.clear()
                except Exception:
                    self._played_notes = set()
                if self.play_line:
                    # update on the main thread
                    try:
                        self.canvas.after(0, lambda: self.canvas.coords(self.play_line, 0.0, 0, 0.0, len(PITCHES)*ROW_H))
                    except Exception:
                        pass
                try:
                    self.status.config(text="Stopped — playhead reset to start")
                except Exception:
                    pass
            except Exception:
                pass

    def render_audio(self):
        """Export the piano-roll as a MIDI file plus a Stylesinger-compatible
        lyric timing file. The user picks a destination .mid path; a matching
        .lab (text) file is written alongside it containing lines:

            <start_seconds> <duration_seconds> <lyric>

        Times are computed using the current tempo (BPM) and the grid mapping
        where 1 grid step == 1 beat (quarter note) as used by playback.
        """
        # collect notes
        notes_sorted = sorted(self.notes.items(), key=lambda it: (it[1]["start_x"], it[1]["row"]))
        if not notes_sorted:
            messagebox.showinfo("Render Audio", "No notes to export.")
            return

        # ask for output path
        out_mid = filedialog.asksaveasfilename(defaultextension='.mid', filetypes=[('MIDI files','*.mid')], title='Save MIDI as')
        if not out_mid:
            return
        base, _ = os.path.splitext(out_mid)
        out_lab = base + '.lab'

        # tempo and timing
        try:
            tempo = int(self.tempo_var.get())
        except Exception:
            tempo = PLAY_BPM
        if tempo <= 0:
            tempo = PLAY_BPM
        beat_time = 60.0 / float(tempo)  # seconds per beat

        # helper: convert note name to MIDI number
        def note_name_to_midi(name: str) -> int:
            name = name.strip()
            if not name:
                return 60
            i = len(name) - 1
            while i >= 0 and name[i].isdigit():
                i -= 1
            note = name[: i+1]
            octave = name[i+1:]
            try:
                oct_i = int(octave)
            except Exception:
                oct_i = 4
            semis = {
                'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4,
                'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9,
                'A#': 10, 'B': 11
            }
            note = note.replace('Bb', 'A#').replace('Db', 'C#').replace('Eb', 'D#').replace('Gb', 'F#').replace('Ab', 'G#')
            semitone = semis.get(note, 9)
            midi = (oct_i + 1) * 12 + semitone
            return int(midi)

        # build event list: (tick, type, channel, note, velocity)
        PPQ = 480
        events = []
        for rect_id, info in notes_sorted:
            start_beats = info.get('start_x', 0)
            dur_beats = info.get('width_steps', 1)
            start_tick = int(start_beats * PPQ)
            dur_tick = int(dur_beats * PPQ)
            row = info.get('row', 0)
            if 0 <= row < len(PITCHES):
                note_name = PITCHES[row]
                midi_note = note_name_to_midi(note_name)
                velocity = 100
                events.append((start_tick, 'on', midi_note, velocity, rect_id))
                events.append((start_tick + dur_tick, 'off', midi_note, 0, rect_id))

        # sort events by tick
        events.sort(key=lambda e: e[0])

        # helper to write variable length quantity
        def write_varlen(n: int) -> bytes:
            buf = bytearray()
            val = n & 0x0fffffff
            stack = []
            stack.append(val & 0x7f)
            val >>= 7
            while val:
                stack.append((val & 0x7f) | 0x80)
                val >>= 7
            return bytes(reversed(stack))

        # assemble MIDI track data
        track_data = bytearray()
        # set tempo meta (microseconds per quarter)
        us_per_q = int(60.0 / tempo * 1_000_000)
        track_data += b'\x00' + b'\xff\x51\x03' + struct.pack('>I', us_per_q)[1:]

        last_tick = 0
        for ev in events:
            tick, kind, midi_note, vel, rid = ev
            delta = tick - last_tick
            track_data += write_varlen(delta)
            if kind == 'on':
                track_data += bytes([0x90, midi_note & 0x7f, vel & 0x7f])
            else:
                track_data += bytes([0x80, midi_note & 0x7f, vel & 0x7f])
            last_tick = tick

        # End of track
        track_data += write_varlen(0)
        track_data += b'\xff\x2f\x00'

        # write MIDI file (header + single track)
        with open(out_mid, 'wb') as f:
            # Header: MThd, length 6, format 0, ntrks 1, division PPQ
            f.write(b'MThd')
            f.write(struct.pack('>I', 6))
            f.write(struct.pack('>H', 0))
            f.write(struct.pack('>H', 1))
            f.write(struct.pack('>H', PPQ))
            # Track chunk
            f.write(b'MTrk')
            f.write(struct.pack('>I', len(track_data)))
            f.write(track_data)

        # write label file: start_seconds duration_seconds lyric_token
        with open(out_lab, 'w', encoding='utf-8') as lf:
            for rect_id, info in notes_sorted:
                start_beats = info.get('start_x', 0)
                dur_beats = info.get('width_steps', 1)
                start_s = start_beats * beat_time
                dur_s = dur_beats * beat_time
                text_id = info.get('text')
                lyric = ''
                try:
                    lyric = self.canvas.itemcget(text_id, 'text') or ''
                except Exception:
                    lyric = ''
                lf.write(f"{start_s:.4f} {dur_s:.4f} {lyric}\n")

        messagebox.showinfo("Render Audio", f"Exported MIDI to:\n{out_mid}\nand labels to:\n{out_lab}")

    def play_loop(self):
        # incremental playhead update using live tempo (supports tempo changes during playback)
        last_time = time.time()
        prev = self._prev_play_x
        while self.playing:
            now = time.time()
            dt = now - last_time
            last_time = now

            try:
                tempo = int(self.tempo_var.get())
            except Exception:
                tempo = PLAY_BPM
            if tempo <= 0:
                tempo = PLAY_BPM
            beat_time = 60.0 / float(tempo)

            # advance playhead by dt relative to beat_time: GRID_STEP pixels per beat
            delta_px = (dt / beat_time) * GRID_STEP
            self.play_x += delta_px

            # detect notes crossed by the playhead between prev and current
            lower = min(prev, self.play_x)
            upper = max(prev, self.play_x)
            for rect_id, note_info in list(self.notes.items()):
                try:
                    start_px = note_info.get("start_x", 0) * GRID_STEP
                    if rect_id in self._played_notes:
                        continue
                    if lower <= start_px <= upper:
                        row = note_info.get("row", 0)
                        if 0 <= row < len(PITCHES):
                            pitch_name = PITCHES[row]
                            freq = pitch_to_freq(pitch_name)
                            duration_ms = note_info.get("width_steps", 1) * beat_time * 1000.0
                            threading.Thread(target=play_tone, args=(freq, duration_ms), daemon=True).start()
                        self._played_notes.add(rect_id)
                except Exception:
                    pass

            prev = self.play_x
            self._prev_play_x = self.play_x

            if self.play_x > SCENE_WIDTH:
                self.playing = False
                break
            px = self.play_x
            try:
                self.canvas.after(0, lambda p=px: self.canvas.coords(self.play_line, p, 0, p, len(PITCHES)*ROW_H))
            except Exception:
                pass
            time.sleep(0.02)
        self.playing = False

    # Scroll synchronization handlers
    def _on_vscroll(self, *args):
        self.canvas.yview(*args)
        try:
            self.piano.yview(*args)
        except Exception:
            pass

    def _on_hscroll(self, *args):
        self.canvas.xview(*args)
        try:
            self.piano.xview(*args)
        except Exception:
            pass

    def _on_mousewheel(self, event):
        """Handle vertical mouse wheel scrolling for both canvases.

        Works on Windows (event.delta), and X11 (Button-4/5) fallbacks.
        """
        try:
            delta = 0
            if hasattr(event, 'delta') and event.delta:
                # Windows: event.delta is multiple of 120
                delta = int(event.delta)
            else:
                # X11: Button-4 = up, Button-5 = down
                if getattr(event, 'num', None) == 4:
                    delta = 120
                elif getattr(event, 'num', None) == 5:
                    delta = -120
            lines = -int(delta / 120)
            if lines == 0:
                return
            try:
                self.canvas.yview_scroll(lines, 'units')
                self.piano.yview_scroll(lines, 'units')
            except Exception:
                pass
        except Exception:
            pass

    # Zoom & redraw helpers
    def update_measurements(self):
        """Update module measurements based on current zoom levels"""
        global ROW_H, KEY_W, GRID_STEP, NOTE_MIN_W, NOTE_H
        ROW_H = int(BASE_ROW_H * self.current_v_zoom)
        KEY_W = BASE_KEY_W  # piano width left constant for now
        GRID_STEP = max(1, int(BASE_GRID_STEP * self.current_h_zoom))
        NOTE_MIN_W = max(4, int(BASE_NOTE_MIN_W * self.current_h_zoom))
        NOTE_H = max(4, ROW_H - 4)

    def redraw_notes(self):
        """Redraw all notes using stored grid units"""
        for rect_id, note_info in list(self.notes.items()):
            start_x = note_info.get("start_x")
            width_steps = note_info.get("width_steps", 1)
            row = note_info.get("row", 0)
            if start_x is None:
                x1, _, x2, _ = self.canvas.coords(rect_id)
                start_x = int(x1 // GRID_STEP)
                width_steps = max(1, int((x2 - x1) // GRID_STEP))
                note_info["start_x"] = start_x
                note_info["width_steps"] = width_steps
            new_x1 = start_x * GRID_STEP
            new_x2 = new_x1 + (width_steps * GRID_STEP)
            new_y = row * ROW_H
            new_h = NOTE_H
            try:
                self.canvas.coords(rect_id, new_x1, new_y + 2, new_x2, new_y + new_h + 2)
                text_id = note_info["text"]
                self.canvas.coords(text_id, (new_x1 + new_x2) / 2, new_y + new_h/2 + 2)
            except Exception:
                pass

    def _zoom_h_in(self):
        new_zoom = min(self.current_h_zoom + 0.25, MAX_ZOOM)
        self.h_zoom_set(new_zoom)

    def _zoom_h_out(self):
        new_zoom = max(self.current_h_zoom - 0.25, MIN_ZOOM)
        self.h_zoom_set(new_zoom)

    def _zoom_v_in(self):
        new_zoom = min(self.current_v_zoom + 0.25, MAX_ZOOM)
        self.v_zoom_set(new_zoom)

    def _zoom_v_out(self):
        new_zoom = max(self.current_v_zoom - 0.25, MIN_ZOOM)
        self.v_zoom_set(new_zoom)

    def h_zoom_set(self, value):
        old_zoom = self.current_h_zoom
        self.current_h_zoom = float(value)
        self.update_measurements()
        xview = self.canvas.xview()
        center = (xview[0] + xview[1]) / 2
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        self.canvas.xview_moveto(center)

    def v_zoom_set(self, value):
        old_zoom = self.current_v_zoom
        self.current_v_zoom = float(value)
        self.update_measurements()
        yview = self.canvas.yview()
        center = (yview[0] + yview[1]) / 2
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        self.canvas.yview_moveto(center)
        self.piano.yview_moveto(center)

    def on_close(self):
        """Safely stop playback and close the app."""
        if self.shutting_down:
            return
        self.shutting_down = True
        # stop playback
        self.stop()
        # join thread briefly
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=1.0)
        try:
            self.destroy()
        except Exception:
            pass


# ---------------- RUN ----------------
if __name__ == "__main__":
    app = SingItClanker()
    app.mainloop()
    def update_measurements(self):
        """Update measurements based on current zoom levels"""
        global ROW_H, KEY_W, GRID_STEP, NOTE_MIN_W, NOTE_H
        
        ROW_H = int(BASE_ROW_H * self.current_v_zoom)
        KEY_W = BASE_KEY_W  # Piano width stays constant
        GRID_STEP = int(BASE_GRID_STEP * self.current_h_zoom)
        NOTE_MIN_W = int(BASE_NOTE_MIN_W * self.current_h_zoom)
        NOTE_H = ROW_H - 4

    def _on_horizontal_zoom(self, value):
        """Handle horizontal zoom changes"""
        old_zoom = self.current_h_zoom
        self.current_h_zoom = float(value)
        self.update_measurements()
        
        # Get current view fractions for maintaining position
        xview = self.canvas.xview()
        center = (xview[0] + xview[1]) / 2
        
        # Redraw everything
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        
        # Update scroll regions
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        
        # Maintain view center
        self.canvas.xview_moveto(center - (self.current_h_zoom / old_zoom - 1) / 2)

    def _on_vertical_zoom(self, value):
        """Handle vertical zoom changes"""
        old_zoom = self.current_v_zoom
        self.current_v_zoom = float(value)
        self.update_measurements()
        
        # Get current view fractions for maintaining position
        yview = self.canvas.yview()
        center = (yview[0] + yview[1]) / 2
        
        # Redraw everything
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        
        # Update scroll regions
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        
        # Maintain view center
        self.canvas.yview_moveto(center - (self.current_v_zoom / old_zoom - 1) / 2)

    def redraw_notes(self):
        """Redraw all notes with current zoom levels"""
        for rect_id, note_info in self.notes.items():
            # Always use stored grid positions for x and width
            start_x = note_info.get("start_x")
            width_steps = note_info.get("width_steps", 1)
            row = note_info["row"]
            if start_x is None:
                # If missing, calculate from current position
                x1, _, x2, _ = self.canvas.coords(rect_id)
                start_x = x1 / GRID_STEP
                width_steps = max(1, (x2 - x1) / GRID_STEP)
                note_info["start_x"] = start_x
                note_info["width_steps"] = width_steps
            new_x1 = start_x * GRID_STEP
            new_x2 = new_x1 + (width_steps * GRID_STEP)
            new_y = row * ROW_H
            new_h = NOTE_H
            self.canvas.coords(rect_id, new_x1, new_y + 2, new_x2, new_y + new_h + 2)
            text_id = note_info["text"]
            self.canvas.coords(text_id, (new_x1 + new_x2) / 2, new_y + new_h/2 + 2)

    def _zoom_h_in(self):
        new_zoom = min(self.current_h_zoom + 0.25, MAX_ZOOM)
        self.h_zoom_set(new_zoom)
    def _zoom_h_out(self):
        new_zoom = max(self.current_h_zoom - 0.25, MIN_ZOOM)
        self.h_zoom_set(new_zoom)
    def _zoom_v_in(self):
        new_zoom = min(self.current_v_zoom + 0.25, MAX_ZOOM)
        self.v_zoom_set(new_zoom)
    def _zoom_v_out(self):
        new_zoom = max(self.current_v_zoom - 0.25, MIN_ZOOM)
        self.v_zoom_set(new_zoom)
    def h_zoom_set(self, value):
        self.current_h_zoom = float(value)
        self.update_measurements()
        xview = self.canvas.xview()
        center = (xview[0] + xview[1]) / 2
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        self.canvas.xview_moveto(center)
    def v_zoom_set(self, value):
        self.current_v_zoom = float(value)
        self.update_measurements()
        yview = self.canvas.yview()
        center = (yview[0] + yview[1]) / 2
        self.draw_piano()
        self.draw_grid()
        self.redraw_notes()
        height = len(PITCHES) * ROW_H
        self.canvas.config(scrollregion=(0, 0, SCENE_WIDTH, height))
        self.piano.config(scrollregion=(0, 0, KEY_W, height))
        self.canvas.yview_moveto(center)
        self.piano.yview_moveto(center)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app = SingItClanker()
    app.mainloop()




