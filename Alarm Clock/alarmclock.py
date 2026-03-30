"""
alarm_clock.py  —  a simple tkinter alarm clock
author: Aditee

Needs nothing outside the standard library. Audio works via winsound on Windows,
afplay on macOS, or aplay/paplay on Linux. If none of those exist it just beeps
the terminal — good enough for a clock that lives in a console window.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime, json, math, io, os, struct, subprocess, sys, tempfile
import threading, time, wave


SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alarms.json")

# ── palette ───────────────────────────────────────────────────────────────────
BG      = "#0d0d1a"
BG2     = "#13132b"
PANEL   = "#16162e"
PANEL2  = "#1c1c38"
BORDER  = "#252545"
TEAL    = "#00e5c0"
TEAL_DK = "#009e86"
PINK    = "#ff2d78"
PURPLE  = "#8b5cf6"
AMBER   = "#f59e0b"
TEXT    = "#e8e8ff"
MUTED   = "#6060a0"
MID     = "#9090c0"

DAYS   = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
          "Jul","Aug","Sep","Oct","Nov","Dec"]


# ── sound ─────────────────────────────────────────────────────────────────────
# Build a raw WAV in memory so we never touch the filesystem for the sound data
# itself — only when the OS player requires a file path.
def _synthesise(freq_hz: int, duration_ms: int) -> bytes:
    rate     = 44100
    n        = int(rate * duration_ms / 1000)
    buf      = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(n):
            # short fade at both ends to kill the click you'd otherwise get
            envelope = min(i, n - i, 500) / 500
            sample   = int(0.4 * envelope * 32767
                           * math.sin(2 * math.pi * freq_hz * i / rate))
            wf.writeframes(struct.pack("<h", sample))
    return buf.getvalue()


def _play_wav(data: bytes):
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY)
        return

    # every other OS needs a real file
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        player = (
            ["afplay", path]                                    if sys.platform == "darwin"
            else ["aplay", "-q", path]                         if not subprocess.run(
                                                                    ["which", "aplay"],
                                                                    capture_output=True).returncode
            else ["paplay", path]                              if not subprocess.run(
                                                                    ["which", "paplay"],
                                                                    capture_output=True).returncode
            else None
        )
        if player:
            subprocess.run(player, timeout=5, check=False)
        else:
            print("\a", end="", flush=True)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def ring():
    """Three-tone beep pattern, repeated four times. Runs on a daemon thread."""
    tones = [(880, 100), (880, 100), (1100, 130), (880, 100)]
    for _ in range(4):
        for hz, ms in tones:
            _play_wav(_synthesise(hz, ms))
            time.sleep(0.05)
        time.sleep(0.3)


# ── app ───────────────────────────────────────────────────────────────────────
class AlarmClock(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Alarm Clock")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("500x820")

        self.alarms: list[dict]   = []
        self.ringing_id: int|None = None
        self._colon_visible       = True   # blinks every second
        self._ring_flash          = False

        self._load_alarms()
        self._apply_styles()
        self._build_ui()
        self._tick()

    # ── data ──────────────────────────────────────────────────────────────────
    def _load_alarms(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE) as f:
                    self.alarms = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass   # corrupted file — start fresh

    def _save_alarms(self):
        with open(SAVE_FILE, "w") as f:
            json.dump(self.alarms, f, indent=2)

    # ── ttk theming ───────────────────────────────────────────────────────────
    def _apply_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Dark.TCombobox",
                    fieldbackground=PANEL2, background=PANEL2,
                    foreground=TEXT, bordercolor=BORDER,
                    arrowcolor=TEAL, selectbackground=PANEL2,
                    selectforeground=TEXT, padding=6)
        s.map("Dark.TCombobox",
              fieldbackground=[("readonly", PANEL2)],
              selectbackground=[("readonly", PANEL2)])

    # ── top-level scaffold ────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_titlebar()
        tk.Frame(self, bg=TEAL, height=2).pack(fill="x")   # accent stripe
        self._build_clock_panel()
        tk.Frame(self, bg=BG2,  height=1).pack(fill="x")   # divider
        self._build_form()
        self._build_alarm_list()

        # ringing banner — unpacked until needed
        self.banner = tk.Frame(self, bg=PINK, height=46)
        self.banner_text = tk.Label(self.banner, text="", bg=PINK,
                                     fg="white", font=("Segoe UI", 11, "bold"))
        self.banner_text.pack(expand=True)

    def _build_titlebar(self):
        bar = tk.Frame(self, bg=BG, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="⏰", bg=BG, fg=TEAL,
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(18, 6), pady=8)
        tk.Label(bar, text="ALARM CLOCK", bg=BG, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        tk.Label(bar, text="LIVE", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))
        self.live_dot = tk.Label(bar, text="●", bg=BG, fg=TEAL,
                                  font=("Segoe UI", 8))
        self.live_dot.pack(side="right", padx=(18, 2))

    # ── analog + digital clock ────────────────────────────────────────────────
    def _build_clock_panel(self):
        panel = tk.Frame(self, bg=BG2)
        panel.pack(fill="x")

        # analog dial — drawn once, hands updated every second
        DIAL = 180
        self.dial = tk.Canvas(panel, width=DIAL, height=DIAL,
                               bg=BG2, bd=0, highlightthickness=0)
        self.dial.pack(side="left", padx=(24, 16), pady=20)
        self._init_dial(DIAL)

        # digital readout on the right
        right = tk.Frame(panel, bg=BG2)
        right.pack(side="left", fill="both", expand=True, pady=16, padx=(0, 24))

        # day-of-week strip (MON–SUN), today's badge lights up
        day_strip = tk.Frame(right, bg=BG2)
        day_strip.pack(anchor="w", pady=(4, 10))
        self.day_badges = []
        for label in DAYS:
            cell = tk.Frame(day_strip, bg=BORDER, width=32, height=22)
            cell.pack(side="left", padx=2)
            cell.pack_propagate(False)
            lbl = tk.Label(cell, text=label, bg=BORDER, fg=MUTED,
                           font=("Segoe UI", 7, "bold"))
            lbl.pack(expand=True)
            self.day_badges.append((cell, lbl))

        # HH:MM in big digits
        row = tk.Frame(right, bg=BG2)
        row.pack(anchor="w")
        self.dg_hour   = tk.Label(row, text="12", font=("Segoe UI", 48, "bold"),
                                   bg=BG2, fg=TEXT)
        self.dg_colon  = tk.Label(row, text=":",  font=("Segoe UI", 48, "bold"),
                                   bg=BG2, fg=TEAL)
        self.dg_minute = tk.Label(row, text="00", font=("Segoe UI", 48, "bold"),
                                   bg=BG2, fg=TEXT)
        for w in (self.dg_hour, self.dg_colon, self.dg_minute):
            w.pack(side="left")

        sub = tk.Frame(right, bg=BG2)
        sub.pack(anchor="w")
        self.dg_sec  = tk.Label(sub, text=":00", font=("Segoe UI", 20),
                                 bg=BG2, fg=MUTED)
        self.dg_ampm = tk.Label(sub, text="AM",  font=("Segoe UI", 14, "bold"),
                                 bg=BG2, fg=TEAL)
        self.dg_sec.pack(side="left")
        self.dg_ampm.pack(side="left", padx=(10, 0))

        self.dg_date = tk.Label(right, text="", font=("Segoe UI", 10),
                                 bg=BG2, fg=MID)
        self.dg_date.pack(anchor="w", pady=(6, 0))

    def _init_dial(self, size):
        cx = cy = size // 2
        r  = cx - 8
        c  = self.dial

        c.create_oval(4, 4, size-4, size-4, fill=PANEL2, outline=BORDER, width=2)
        c.create_oval(10, 10, size-10, size-10, fill=PANEL, outline="")

        for i in range(60):
            angle = math.radians(i * 6 - 90)
            if i % 5 == 0:
                inner, col, w = r - 12, MID, 2
            else:
                inner, col, w = r - 7,  BORDER, 1
            x1 = cx + r     * math.cos(angle)
            y1 = cy + r     * math.sin(angle)
            x2 = cx + inner * math.cos(angle)
            y2 = cy + inner * math.sin(angle)
            c.create_line(x1, y1, x2, y2, fill=col, width=w)

        for i, num in enumerate([12,1,2,3,4,5,6,7,8,9,10,11]):
            angle = math.radians(i * 30 - 90)
            x = cx + (r - 22) * math.cos(angle)
            y = cy + (r - 22) * math.sin(angle)
            c.create_text(x, y, text=str(num), fill=MID,
                          font=("Segoe UI", 7, "bold"))

        # hands — coords updated every tick, created here as placeholders
        self._hand_h = c.create_line(cx, cy, cx, cy, fill=TEXT,  width=4, capstyle="round")
        self._hand_m = c.create_line(cx, cy, cx, cy, fill=TEXT,  width=3, capstyle="round")
        self._hand_s = c.create_line(cx, cy, cx, cy, fill=PINK,  width=1, capstyle="round")
        self._arc    = c.create_arc(14, 14, size-14, size-14,
                                     start=90, extent=0,
                                     style="arc", outline=TEAL, width=3)
        c.create_oval(cx-4, cy-4, cx+4, cy+4, fill=TEAL, outline="")
        self._dial_cx = cx
        self._dial_cy = cy
        self._dial_r  = r

    def _update_dial(self, now):
        cx, cy, r = self._dial_cx, self._dial_cy, self._dial_r
        h12 = now.hour % 12
        m   = now.minute
        s   = now.second

        def move_hand(tag, angle_deg, length):
            a  = math.radians(angle_deg - 90)
            xe = cx + length * math.cos(a)
            ye = cy + length * math.sin(a)
            self.dial.coords(tag, cx, cy, xe, ye)

        move_hand(self._hand_h, h12 * 30 + m * 0.5,   r - 28)
        move_hand(self._hand_m, m  * 6  + s * 0.1,    r - 18)
        move_hand(self._hand_s, s  * 6,                r - 10)
        self.dial.itemconfig(self._arc, extent=-(s / 60) * 360)

    # ── new-alarm form ────────────────────────────────────────────────────────
    def _build_form(self):
        wrapper = tk.Frame(self, bg=BG)
        wrapper.pack(fill="x", padx=20, pady=(16, 8))

        self._section_header(wrapper, "＋", "NEW ALARM")

        card = tk.Frame(wrapper, bg=PANEL, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="x")

        fields = tk.Frame(card, bg=PANEL)
        fields.pack(fill="x", padx=16, pady=14)
        fields.columnconfigure(0, weight=2)
        fields.columnconfigure(1, weight=1)
        fields.columnconfigure(2, weight=1)

        # time input
        tk.Label(fields, text="🕐  TIME  (24 h)", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
        self.entry_time = tk.Entry(fields, font=("Segoe UI", 14, "bold"),
                                    bg=PANEL2, fg=TEXT, insertbackground=TEAL,
                                    relief="flat", bd=0, justify="center",
                                    highlightthickness=1, highlightbackground=BORDER,
                                    highlightcolor=TEAL)
        self.entry_time.grid(row=1, column=0, sticky="ew", padx=(0,10), ipady=8)
        self.entry_time.insert(0, datetime.datetime.now().strftime("%H:%M"))
        self.entry_time.bind("<FocusIn>",
            lambda _: self.entry_time.config(highlightbackground=TEAL))
        self.entry_time.bind("<FocusOut>",
            lambda _: self.entry_time.config(highlightbackground=BORDER))

        # repeat picker
        tk.Label(fields, text="🔁  REPEAT", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", pady=(0,4))
        self.repeat_var = tk.StringVar(value="once")
        ttk.Combobox(fields, textvariable=self.repeat_var,
                     values=["once", "daily", "weekdays", "weekends"],
                     state="readonly", style="Dark.TCombobox",
                     font=("Segoe UI", 10), justify="center"
                     ).grid(row=1, column=1, sticky="ew", padx=(0,10), ipady=4)

        # sound toggle — a plain button that flips its own colour
        tk.Label(fields, text="🔔  SOUND", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", pady=(0,4))
        self.sound_on = True
        self.sound_btn = tk.Button(fields, text="ON", bg=TEAL, fg=BG,
                                    font=("Segoe UI", 9, "bold"),
                                    relief="flat", cursor="hand2",
                                    padx=14, pady=6,
                                    command=self._flip_sound)
        self.sound_btn.grid(row=1, column=2, sticky="ew")

        # label
        lbl_area = tk.Frame(card, bg=PANEL)
        lbl_area.pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(lbl_area, text="✏️  LABEL  (optional)", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.entry_label = tk.Entry(lbl_area, font=("Segoe UI", 10),
                                     bg=PANEL2, fg=TEXT, insertbackground=TEAL,
                                     relief="flat", bd=0,
                                     highlightthickness=1, highlightbackground=BORDER,
                                     highlightcolor=PURPLE)
        self.entry_label.pack(fill="x", pady=(4, 0), ipady=7)
        self.entry_label.bind("<FocusIn>",
            lambda _: self.entry_label.config(highlightbackground=PURPLE))
        self.entry_label.bind("<FocusOut>",
            lambda _: self.entry_label.config(highlightbackground=BORDER))

        # action buttons live in the same card so they feel connected to the form
        btn_area = tk.Frame(card, bg=PANEL)
        btn_area.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_add = tk.Button(btn_area, text="＋  ADD ALARM",
                                  bg=TEAL, fg=BG,
                                  font=("Segoe UI", 10, "bold"),
                                  relief="flat", cursor="hand2",
                                  pady=10, activebackground=TEAL_DK,
                                  command=self._add_alarm)
        self.btn_add.pack(fill="x")

        # dismiss only appears when something is ringing
        self.btn_dismiss = tk.Button(btn_area, text="⏹  DISMISS",
                                      bg=PINK, fg="white",
                                      font=("Segoe UI", 10, "bold"),
                                      relief="flat", cursor="hand2",
                                      pady=10, activebackground="#cc1055",
                                      command=self._dismiss)

    def _flip_sound(self):
        self.sound_on = not self.sound_on
        if self.sound_on:
            self.sound_btn.config(text="ON", bg=TEAL, fg=BG)
        else:
            self.sound_btn.config(text="OFF", bg=BORDER, fg=MUTED)

    def _section_header(self, parent, icon, title):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 10))
        tk.Label(row, text=icon,  bg=BG, fg=TEAL,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(row, text=f"  {title}", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x",
                                                 expand=True, padx=(10, 0), pady=6)

    # ── alarm list ────────────────────────────────────────────────────────────
    def _build_alarm_list(self):
        wrapper = tk.Frame(self, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        hdr = tk.Frame(wrapper, bg=BG)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(hdr, text="⏰", bg=BG, fg=PURPLE,
                 font=("Segoe UI Emoji", 11)).pack(side="left")
        tk.Label(hdr, text="  SCHEDULED ALARMS", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_count = tk.Label(hdr, text="", bg=BG, fg=MUTED,
                                   font=("Segoe UI", 9))
        self.lbl_count.pack(side="right")
        tk.Frame(hdr, bg=BORDER, height=1).pack(side="left", fill="x",
                                                  expand=True, padx=(10, 10), pady=6)

        outer = tk.Frame(wrapper, bg=BG)
        outer.pack(fill="both", expand=True)

        self.list_canvas = tk.Canvas(outer, bg=BG, bd=0, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical",
                          command=self.list_canvas.yview,
                          bg=BG, troughcolor=BG2, activebackground=PURPLE)
        self.list_frame = tk.Frame(self.list_canvas, bg=BG)
        self.list_frame.bind("<Configure>", lambda _:
            self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_canvas.configure(yscrollcommand=sb.set)
        self.list_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._redraw_list()

    # ── clock tick ────────────────────────────────────────────────────────────
    def _tick(self):
        now  = datetime.datetime.now()
        h12  = now.hour % 12 or 12
        ampm = "PM" if now.hour >= 12 else "AM"

        self._colon_visible = not self._colon_visible
        self.dg_colon.config(fg=TEAL if self._colon_visible else BG2)
        self.live_dot.config(fg=TEAL if self._colon_visible else BG)

        self.dg_hour.config(text=f"{h12:02d}")
        self.dg_minute.config(text=f"{now.minute:02d}")
        self.dg_sec.config(text=f":{now.second:02d}")
        self.dg_ampm.config(text=ampm)
        self.dg_date.config(
            text=f"{DAYS[now.weekday()]}  ·  "
                 f"{now.day:02d} {MONTHS[now.month-1]} {now.year}")

        for i, (cell, lbl) in enumerate(self.day_badges):
            today = i == now.weekday()
            cell.config(bg=TEAL   if today else BORDER)
            lbl.config( bg=TEAL   if today else BORDER,
                        fg=BG     if today else MUTED)

        self._update_dial(now)

        if now.second == 0 and self.ringing_id is None:
            self._check_alarms(now)

        self.after(1000, self._tick)

    # ── alarm firing ──────────────────────────────────────────────────────────
    def _check_alarms(self, now):
        h, m, weekday = now.hour, now.minute, now.weekday()
        for alarm in self.alarms:
            if not alarm.get("active"):
                continue
            ah, am = map(int, alarm["time"].split(":"))
            if ah != h or am != m:
                continue
            rule = alarm["repeat"]
            if (rule in ("once", "daily")
                    or (rule == "weekdays" and weekday < 5)
                    or (rule == "weekends" and weekday >= 5)):
                self._fire(alarm["id"])
                break

    def _fire(self, alarm_id):
        self.ringing_id = alarm_id
        alarm = next(a for a in self.alarms if a["id"] == alarm_id)
        name  = alarm.get("label") or "Alarm"

        self.banner_text.config(text=f"⚡  {name.upper()}  —  RINGING  ⚡")
        self.banner.pack(fill="x", before=self.winfo_children()[2])
        self.btn_add.pack_forget()
        self.btn_dismiss.pack(fill="x", pady=(6, 0))

        self._blink_banner()
        self._redraw_list()

        if alarm.get("sound", True):
            threading.Thread(target=ring, daemon=True).start()

    def _blink_banner(self):
        if self.ringing_id is None:
            return
        self._ring_flash = not self._ring_flash
        colour = PINK if self._ring_flash else "#8b0033"
        self.banner.config(bg=colour)
        self.banner_text.config(bg=colour)
        self.after(600, self._blink_banner)

    def _dismiss(self):
        if self.ringing_id is None:
            return
        alarm = next((a for a in self.alarms if a["id"] == self.ringing_id), None)
        # one-shot alarms disable themselves after they fire
        if alarm and alarm["repeat"] == "once":
            alarm["active"] = False
        self.ringing_id = None
        self._save_alarms()
        self.banner.pack_forget()
        self.btn_dismiss.pack_forget()
        self.btn_add.pack(fill="x")
        self._redraw_list()

    # ── adding / removing alarms ──────────────────────────────────────────────
    def _add_alarm(self):
        raw = self.entry_time.get().strip()
        try:
            t = datetime.datetime.strptime(raw, "%H:%M")
        except ValueError:
            messagebox.showerror("Bad time", "Format is HH:MM  e.g. 07:30")
            return

        self.alarms.append({
            "id":     int(time.time() * 1000),
            "time":   t.strftime("%H:%M"),
            "label":  self.entry_label.get().strip(),
            "repeat": self.repeat_var.get(),
            "sound":  self.sound_on,
            "active": True,
        })
        self._save_alarms()
        self.entry_label.delete(0, tk.END)
        self._redraw_list()

    def _remove_alarm(self, alarm_id):
        if self.ringing_id == alarm_id:
            self._dismiss()
        self.alarms = [a for a in self.alarms if a["id"] != alarm_id]
        self._save_alarms()
        self._redraw_list()

    def _toggle_alarm(self, alarm_id):
        alarm = next((a for a in self.alarms if a["id"] == alarm_id), None)
        if alarm:
            alarm["active"] = not alarm["active"]
            self._save_alarms()
            self._redraw_list()

    # ── list rendering ────────────────────────────────────────────────────────
    def _redraw_list(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        active_count = sum(1 for a in self.alarms if a.get("active"))
        if self.alarms:
            self.lbl_count.config(
                text=f"{active_count} active · {len(self.alarms)} total")
        else:
            self.lbl_count.config(text="")

        if not self.alarms:
            self._empty_state()
            return

        for alarm in sorted(self.alarms, key=lambda a: a["time"]):
            self._alarm_card(alarm)

    def _empty_state(self):
        box = tk.Frame(self.list_frame, bg=BG)
        box.pack(fill="x", pady=30)
        tk.Label(box, text="🔕", bg=BG, fg=MUTED,
                 font=("Segoe UI Emoji", 28)).pack()
        tk.Label(box, text="No alarms set", bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(pady=(6, 0))
        tk.Label(box, text="Add one above ↑", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack()

    def _alarm_card(self, alarm):
        ringing = alarm["id"] == self.ringing_id
        active  = alarm.get("active", True)

        card_bg   = "#2a0010" if ringing else (PANEL  if active else BG2)
        bar_color = PINK      if ringing else (TEAL   if active else MUTED)
        border    = PINK      if ringing else (PURPLE if active else BORDER)

        card = tk.Frame(self.list_frame, bg=card_bg,
                        highlightthickness=1, highlightbackground=border)
        card.pack(fill="x", pady=5)

        # coloured left stripe — gives each card a quick at-a-glance status
        tk.Frame(card, bg=bar_color, width=4).pack(side="left", fill="y")

        body = tk.Frame(card, bg=card_bg)
        body.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        h, m = map(int, alarm["time"].split(":"))
        h12  = h % 12 or 12
        ampm = "PM" if h >= 12 else "AM"

        top = tk.Frame(body, bg=card_bg)
        top.pack(fill="x")

        tk.Label(top, text=f"{h12:02d}:{m:02d}",
                 font=("Segoe UI", 26, "bold"),
                 bg=card_bg, fg=TEXT if active else MUTED).pack(side="left")
        tk.Label(top, text=f" {ampm}", font=("Segoe UI", 12),
                 bg=card_bg, fg=TEAL if active else MUTED).pack(
                 side="left", anchor="s", pady=(0, 4))

        # badges on the right: repeat mode + sound indicator
        badges = tk.Frame(top, bg=card_bg)
        badges.pack(side="right", anchor="n", pady=4)

        repeat_icons = {"once": "↺", "daily": "∞", "weekdays": "☀", "weekends": "⛾"}
        rep  = alarm.get("repeat", "once")
        icon = repeat_icons.get(rep, "↺")
        tk.Label(badges, text=f" {icon}  {rep.upper()} ",
                 bg=PURPLE if active else BORDER,
                 fg="white" if active else MUTED,
                 font=("Segoe UI", 8, "bold"), padx=4, pady=2).pack(side="left", padx=(0,4))

        if alarm.get("sound", True) and active:
            tk.Label(badges, text=" 🔔 ",
                     bg=PANEL2, fg=AMBER,
                     font=("Segoe UI Emoji", 9), padx=2, pady=2).pack(side="left")

        if alarm.get("label"):
            tk.Label(body, text=f"  {alarm['label']}",
                     font=("Segoe UI", 9), bg=card_bg, fg=MID).pack(anchor="w", pady=(2, 0))

        if ringing:
            tk.Label(body, text="⚡ RINGING NOW",
                     font=("Segoe UI", 8, "bold"),
                     bg=card_bg, fg=PINK).pack(anchor="w", pady=(4, 0))

        # controls: toggle + delete on the right edge of the card
        ctrl = tk.Frame(card, bg=card_bg)
        ctrl.pack(side="right", fill="y", padx=12)

        tog_text = "ON " if active else "OFF"
        tog_bg   = TEAL if active else BORDER
        tog_fg   = BG   if active else MUTED
        tk.Button(ctrl, text=tog_text, bg=tog_bg, fg=tog_fg,
                  font=("Segoe UI", 8, "bold"),
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  activebackground=TEAL_DK,
                  command=lambda aid=alarm["id"]: self._toggle_alarm(aid)
                  ).pack(pady=(14, 6))

        tk.Button(ctrl, text="🗑", bg=card_bg, fg=MUTED,
                  font=("Segoe UI Emoji", 12), relief="flat", cursor="hand2",
                  activebackground=card_bg, activeforeground=PINK,
                  command=lambda aid=alarm["id"]: self._remove_alarm(aid)
                  ).pack(pady=(0, 14))


if __name__ == "__main__":
    app = AlarmClock()
    app.mainloop()