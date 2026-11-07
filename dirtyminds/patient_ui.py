"""Patient-facing phase, live response trace, and brine plan."""
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
TRACE_STAGES = (Stage.CALIBRATE, *ROUND_STAGES, *REST_STAGES)
TRACE_POINTS = 160
SIGNAL_COLOR = "#9ce2bd"
BAR_COLORS = ("#b9cb86", "#e5a06f", "#d8a4bf")
GRID_COLOR = "#526065"
MUTED_COLOR = "#9caeb0"


def signal_background(level):
    cool, warm = (7, 17, 27), (53, 16, 39)
    return "#%02x%02x%02x" % tuple(round(a + (b - a) * level) for a, b in zip(cool, warm))


class PatientTimeline:
    def __init__(self):
        self.lines = deque(maxlen=10)
        self.samples = deque(maxlen=TRACE_POINTS)
        self.counter = 0
        self.sample_count = 0
        self.stage = None
        self.phase = ""
        self.title = ""
        self.score = None
        self.blend = ()
        self.blend_heading = ""
        self.chart_revision = None

    def add_sample(self, level):
        self.samples.append(level)
        self.sample_count += 1

    def advance(self, stage, title="", activity="", *, score=None, blend=(), blend_heading=""):
        phase = activity or DISPLAY_PHASES[stage]
        revision = self.sample_count if stage in TRACE_STAGES else None
        if (self.stage, self.title, self.phase, self.score, self.blend,
                self.blend_heading, self.chart_revision) == (stage, title, phase, score, blend, blend_heading, revision):
            return False
        if self.stage != stage or self.phase != phase:
            self.stage = stage
            self.phase = phase
            self.counter += 1
            self.lines.append(f"{self.counter:04X}  >  {self.phase}")
        self.title, self.score = title, score
        self.blend, self.blend_heading = blend, blend_heading
        self.chart_revision = revision
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
        self.width = min(900, window.winfo_screenwidth() - 80)
        self.chart = tk.Canvas(window, width=self.width, height=176,
                               background="black", highlightthickness=0)
        self.response = tk.Label(window, background="black", foreground="#dce8e0", font=("Georgia", 36))
        self.title = tk.Label(window, background="black", foreground="#dce8e0",
                              font=("Georgia", 36), wraplength=self.width)
        self.signoff = tk.Label(window, background="black", foreground=MUTED_COLOR, font=("Consolas", 13))
        self.footer = tk.Frame(window, background="black", padx=28, pady=20)
        self.footer.pack(side="bottom", anchor="w")
        self.heading = tk.Label(self.footer, background="black", foreground=MUTED_COLOR,
                                font=("Consolas", 22), anchor="w")
        self.heading.pack(fill="x", pady=(0, 6))
        self.stream = tk.Text(self.footer, height=4, width=53, state="disabled", background="black",
                              foreground="#7d9b8d", borderwidth=0, highlightthickness=0,
                              font=("Consolas", 12), takefocus=False, cursor="none", padx=0, pady=0)
        self.stream.pack(anchor="w")
        self.stream.tag_configure("latest", foreground="#b7ccbe")
        self.stream.bind("<Button-1>", lambda event: "break")
        self.last_log = ()
        self.background = "black"
        self.render(timeline)
        window.deiconify()
        window.lift()
        window.focus_force()

    def render(self, timeline):
        trace_visible = timeline.stage in TRACE_STAGES
        level = timeline.score
        if level is None and timeline.samples:
            level = timeline.samples[-1]
        background = signal_background(level or 0) if trace_visible or timeline.blend else "black"
        if background != self.background:
            self.background = background
            for widget in (self.window, self.chart, self.response, self.title, self.signoff,
                           self.footer, self.heading, self.stream):
                widget.configure(background=background)

        if timeline.blend:
            self.chart.place(relx=.5, rely=.49, anchor="center")
            self.draw_blend(timeline.blend, timeline.blend_heading)
        elif trace_visible:
            self.chart.place(relx=.5, rely=.41, anchor="center")
            self.draw_trace(timeline.samples)
        else:
            self.chart.place_forget()

        if timeline.score is not None:
            self.response.configure(text=f"{timeline.score:.0%}  RESPONSE")
            self.response.place(relx=.5, rely=.62, anchor="center")
        else:
            self.response.place_forget()

        if timeline.title:
            self.title.configure(text=timeline.title)
            self.title.place(relx=.5, rely=.22 if timeline.blend else .40, anchor="center")
            self.signoff.configure(text="THANK YOU. PLEASE KEEP RESPONDING INAPPROPRIATELY.")
            self.signoff.place(relx=.5, rely=.68 if timeline.blend else .54, anchor="center")
        else:
            self.title.place_forget()
            self.signoff.place_forget()

        log = tuple(timeline.lines)
        if log != self.last_log:
            self.last_log = log
            self.heading.configure(text=f"D.I.R.   /   {timeline.phase}")
            self.stream.configure(state="normal")
            self.stream.delete("1.0", "end")
            self.stream.insert("1.0", "\n".join(log))
            self.stream.tag_add("latest", f"{len(log)}.0", "end-1c")
            self.stream.see("end")
            self.stream.configure(state="disabled")

    def draw_trace(self, samples):
        canvas = self.chart
        canvas.delete("all")
        left, right, top, bottom = 18, self.width - 18, 38, 155
        canvas.create_text(left, 15, text="GSR RESPONSE SIGNAL", fill=MUTED_COLOR,
                           font=("Consolas", 12), anchor="w")
        for y in (top, (top + bottom) / 2, bottom):
            canvas.create_line(left, y, right, y, fill=GRID_COLOR, dash=(3, 5))
        if len(samples) < 2:
            return
        spacing = (right - left) / (TRACE_POINTS - 1)
        points = [coordinate for i, sample in enumerate(samples)
                  for coordinate in (right - (len(samples) - 1 - i) * spacing,
                                     bottom - sample * (bottom - top))]
        canvas.create_line(*points, fill=SIGNAL_COLOR, width=3, tags="response-trace")

    def draw_blend(self, rows, heading):
        canvas = self.chart
        canvas.delete("all")
        left, bar_left, bar_right = 16, self.width * .25, self.width * .69
        canvas.create_text(left, 15, text=heading, fill=MUTED_COLOR,
                           font=("Consolas", 12), anchor="w")
        for i, ((label, ml, annotation), color) in enumerate(zip(rows, BAR_COLORS)):
            y = 48 + 39 * i
            canvas.create_text(left, y, text=label, fill="#dce8e0", font=("Segoe UI", 12), anchor="w")
            canvas.create_rectangle(bar_left, y - 7, bar_right, y + 7, outline=GRID_COLOR)
            if ml > 0:
                width = (bar_right - bar_left) * min(1, ml / 15)
                canvas.create_rectangle(bar_left, y - 7, bar_left + width, y + 7,
                                        outline="", fill=color, tags="blend-bar")
            canvas.create_text(bar_right + 12, y, text=annotation, fill="#dce8e0",
                               font=("Consolas", 11), anchor="w")

    def close(self):
        self.window.destroy()
