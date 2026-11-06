"""Patient-facing phase and prescription display."""
from collections import deque
import tkinter as tk

from .core import REST_STAGES, ROUND_STAGES, Stage

DISPLAY_PHASES = {
    Stage.READY: "STANDBY",
    Stage.WELCOME: "INTAKE",
    Stage.BASELINE_PROMPT: "BASELINE SETUP",
    Stage.CALIBRATE: "TAKING BASELINE",
    Stage.REVEAL: "ASSESSING RESPONSES",
    Stage.DISPENSE: "PREPARING PRESCRIPTION",
    Stage.FAREWELL: "PRESCRIPTION",
    Stage.COMPLETE: "PROCEDURE COMPLETE",
    Stage.STOPPED: "PROCEDURE STOPPED",
    **{stage: f"DIRTY {i} / {len(ROUND_STAGES)}" for i, stage in enumerate(ROUND_STAGES, 1)},
    **{stage: f"RECORDING RESPONSE {i}" for i, stage in enumerate(REST_STAGES, 1)},
}


class PatientTimeline:
    def __init__(self):
        self.lines = deque(maxlen=10)
        self.counter = 0
        self.stage = None
        self.phase = ""
        self.title = ""

    def advance(self, stage, title="", activity=""):
        phase = activity or DISPLAY_PHASES[stage]
        if self.stage == stage and self.title == title and self.phase == phase:
            return False
        if self.stage != stage or self.phase != phase:
            self.stage = stage
            self.phase = phase
            self.counter += 1
            self.lines.append(f"{self.counter:04X}  >  {self.phase}")
        self.title = title
        return True


class PatientView:
    def __init__(self, root, timeline, close, stop, new_session):
        self.window = window = tk.Toplevel(root, background="black")
        window.withdraw()
        window.title("Dirty Minds · Patient display")
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", close)
        window.bind("<F10>", lambda event: close())
        window.bind("<F8>", new_session)
        window.bind("<Escape>", lambda event: stop())
        self.title = tk.Label(window, background="black", foreground="#dce8e0",
                              font=("Georgia", 36), wraplength=min(900, window.winfo_screenwidth() - 80))
        self.signoff = tk.Label(window, background="black", foreground="#8fa69a",
                                font=("Consolas", 13))
        frame = tk.Frame(window, background="black", padx=28, pady=24)
        frame.pack(side="bottom", anchor="w")
        self.heading = tk.Label(frame, background="black", foreground="#7e9789",
                                font=("Consolas", 22), anchor="w")
        self.heading.pack(fill="x", pady=(0, 10))
        self.stream = tk.Text(frame, height=10, width=53, state="disabled", background="black",
                              foreground="#658477", borderwidth=0, highlightthickness=0,
                              font=("Consolas", 12), takefocus=False, cursor="none", padx=0, pady=0)
        self.stream.pack(anchor="w")
        self.stream.tag_configure("latest", foreground="#a1b8a9")
        self.stream.bind("<Button-1>", lambda event: "break")
        self.render(timeline)
        window.deiconify()
        window.lift()
        window.focus_force()

    def render(self, timeline):
        self.heading.configure(text=f"D.I.R.   /   {timeline.phase}")
        if timeline.title:
            self.title.configure(text=timeline.title)
            self.title.place(relx=.5, rely=.40, anchor="center")
            self.signoff.configure(text="THANK YOU. PLEASE KEEP RESPONDING INAPPROPRIATELY.")
            self.signoff.place(relx=.5, rely=.54, anchor="center")
        else:
            self.title.place_forget()
            self.signoff.place_forget()
        self.stream.configure(state="normal")
        self.stream.delete("1.0", "end")
        self.stream.insert("1.0", "\n".join(timeline.lines))
        self.stream.tag_add("latest", f"{len(timeline.lines)}.0", "end-1c")
        self.stream.configure(state="disabled")

    def close(self):
        self.window.destroy()
