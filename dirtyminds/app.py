from collections import deque
import math
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import ttk

from .core import Session, Stage, TEST_LINE
from .sensors import SerialInput, Simulator, list_ports
from .voice import ElevenVoice, VoiceWorker

ROOT = Path(__file__).resolve().parent.parent
BG = "#17151b"
PANEL = "#24212a"
TEXT = "#f3ece4"
MUTED = "#bcb3c1"
ACCENT = "#dda2bc"
GREEN = "#bfd19c"


def load_config():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        if (ROOT / ".env").exists():
            raise ValueError("Run setup.cmd first so the app can read .env.") from None
    try:
        maximum = float(os.getenv("GSR_MAX", "1023"))
        span = float(os.getenv("GSR_SPAN", "200"))
        baud = int(os.getenv("SERIAL_BAUD", "115200"))
        if not all(math.isfinite(x) and x > 0 for x in (maximum, span, baud)):
            raise ValueError
    except ValueError:
        raise ValueError("GSR_MAX, GSR_SPAN and SERIAL_BAUD must be positive numbers in .env.") from None
    return {
        "maximum": maximum, "span": span, "baud": baud,
        "port": os.getenv("SERIAL_PORT", ""),
        "api_key": os.getenv("ELEVENLABS_API_KEY", "").strip(),
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL").strip(),
        "model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip(),
    }


class App:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.session = Session(config["span"])
        self.simulator = Simulator()
        self.serial = None
        self.last_reading = None
        self.started = 0
        self.history = deque(maxlen=300)
        self.voice = VoiceWorker(ElevenVoice(
            config["api_key"], config["voice_id"], config["model_id"], ROOT / ".cache" / "voice"
        ))
        self.source = tk.StringVar(value="Simulated")
        self.port = tk.StringVar(value=config["port"])
        self.silent = tk.BooleanVar(value=not bool(config["api_key"]))
        self.intensity = tk.DoubleVar(value=40)
        self.stage_text = tk.StringVar(value="Ready when you are")
        self.status = tk.StringVar(value="Choose headphones in Windows sound settings, then test the voice.")
        self.reading_text = tk.StringVar(value="RAW —     BASELINE —     CHANGE —")
        self.line_text = tk.StringVar(value="A thought. A ripple. A martini.")
        self.recipe_text = tk.StringVar(value="Your recipe appears here after the session.\n\nStart with a silent rehearsal; move the slider during the imagination prompt.")
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.stop())
        self.after_id = root.after(100, self.tick)

    def _build(self):
        root = self.root
        root.title("Dirty Minds · local prototype")
        root.geometry("1020x800")
        root.minsize(920, 740)
        root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", MUTED)])
        style.configure("TButton", font=("Segoe UI", 10), padding=8, background=PANEL, foreground=TEXT, bordercolor="#463b4b")
        style.map("TButton", background=[("active", "#463b4b")], foreground=[("disabled", MUTED)])
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=ACCENT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL), ("disabled", PANEL)], foreground=[("disabled", MUTED), ("readonly", TEXT)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)
        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)
        shell = ttk.Frame(root, padding=20)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)
        ttk.Label(shell, text="DIRTY MINDS", font=("Segoe UI", 28, "bold"), foreground=ACCENT).grid(sticky="w")
        ttk.Label(shell, text="An intimate little experiment in imagination & olives", foreground=MUTED).grid(sticky="w", pady=(0, 12))
        body = ttk.Frame(shell)
        body.grid(row=2, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        controls = ttk.Frame(body, padding=(0, 0, 24, 0))
        controls.grid(row=0, column=0, rowspan=4, sticky="nsw")
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, text="INPUT", foreground=GREEN, font=("Segoe UI", 10, "bold")).grid(sticky="w")
        self.source_box = ttk.Combobox(controls, textvariable=self.source, values=("Simulated", "Arduino USB"), state="readonly", width=23)
        self.source_box.grid(sticky="ew", pady=(8, 16))
        self.source_box.bind("<<ComboboxSelected>>", lambda event: self._controls())
        ttk.Label(controls, text="Arduino port").grid(sticky="w")
        self.port_box = ttk.Combobox(controls, textvariable=self.port, values=list_ports(), width=23)
        self.port_box.grid(sticky="ew", pady=8)
        self.refresh_button = ttk.Button(controls, text="Refresh ports", command=self.refresh_ports)
        self.refresh_button.grid(sticky="ew", pady=(0, 12))
        ttk.Label(controls, text="SIMULATED RESPONSE", foreground=GREEN, font=("Segoe UI", 10, "bold")).grid(sticky="w")
        self.slider = ttk.Scale(controls, from_=0, to=100, variable=self.intensity)
        self.slider.grid(sticky="ew", pady=8)
        ttk.Label(controls, text="Subtle                         Extra dirty", foreground=MUTED).grid(sticky="w")
        ttk.Label(controls, text="Applies after baseline calibration.", foreground=MUTED, font=("Segoe UI", 9)).grid(sticky="w", pady=(4, 12))
        self.silent_box = ttk.Checkbutton(controls, text="Silent rehearsal", variable=self.silent)
        self.silent_box.grid(sticky="w", pady=(0, 8))
        ttk.Label(controls, text="Voice uses Windows default output.\nUncheck for ElevenLabs playback.", foreground=MUTED, font=("Segoe UI", 9)).grid(sticky="w", pady=(0, 12))
        self.test_button = ttk.Button(controls, text="Test ElevenLabs voice", command=self.test_voice)
        self.test_button.grid(sticky="ew", pady=(0, 12))
        self.start_button = tk.Button(controls, text="Begin extraction", command=self.start, bg=ACCENT, fg=BG, activebackground=TEXT, font=("Segoe UI", 12, "bold"), relief="flat", padx=12, pady=12)
        self.start_button.grid(sticky="ew", pady=6)
        tk.Button(controls, text="Stop / Esc", command=self.stop, bg=PANEL, fg=TEXT, activebackground=ACCENT, font=("Segoe UI", 11), relief="flat", padx=12, pady=10).grid(sticky="ew", pady=6)
        ttk.Label(controls, text="~45–70 seconds per session\nNo sensor required in simulation.", foreground=MUTED, font=("Segoe UI", 9)).grid(sticky="w", pady=14)
        ttk.Label(body, textvariable=self.stage_text, font=("Segoe UI", 19, "bold")).grid(row=0, column=1, sticky="w")
        monitor = ttk.Frame(body)
        monitor.grid(row=1, column=1, sticky="ew", pady=(12, 16))
        self.canvas = tk.Canvas(monitor, height=110, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="x")
        ttk.Label(monitor, textvariable=self.reading_text, foreground=GREEN, font=("Consolas", 10)).pack(anchor="w", pady=(8, 6))
        self.progress_bar = ttk.Progressbar(monitor, maximum=100)
        self.progress_bar.pack(fill="x")
        script = ttk.Frame(body)
        script.grid(row=2, column=1, sticky="ew")
        ttk.Label(script, text="THE VOICE", foreground=ACCENT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.script_label = ttk.Label(script, textvariable=self.line_text, wraplength=615, font=("Segoe UI", 12), padding=(0, 8, 0, 12))
        self.script_label.pack(fill="x")
        recipe = ttk.Frame(body)
        recipe.grid(row=3, column=1, sticky="nsew")
        ttk.Label(recipe, text="YOUR RECIPE", foreground=ACCENT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.recipe_label = ttk.Label(recipe, textvariable=self.recipe_text, wraplength=615, font=("Segoe UI", 10), padding=(0, 8, 0, 8))
        self.recipe_label.pack(fill="x")
        self.copy_button = ttk.Button(recipe, text="Copy recipe", command=self.copy_recipe, state="disabled")
        self.copy_button.pack(anchor="w")
        self.status_label = ttk.Label(shell, textvariable=self.status, foreground=MUTED, wraplength=950)
        self.status_label.grid(row=3, sticky="ew", pady=(14, 6))
        ttk.Label(shell, text="Signal change is a playful ingredient mapping, not a reading of thoughts or desire.", foreground=MUTED, font=("Segoe UI", 9)).grid(row=4, sticky="w")
        body.bind("<Configure>", lambda event: self._wrap(event.width))
        self._controls()

    def _wrap(self, width):
        available = max(300, width - 285)
        self.script_label.configure(wraplength=available)
        self.recipe_label.configure(wraplength=available)

    def _controls(self):
        locked = self.session.active or self.voice.busy
        self.source_box.configure(state="disabled" if locked else "readonly")
        serial_enabled = not locked and self.source.get() == "Arduino USB"
        self.port_box.configure(state="normal" if serial_enabled else "disabled")
        self.refresh_button.configure(state="normal" if serial_enabled else "disabled")
        self.slider.configure(state="normal" if self.source.get() == "Simulated" else "disabled")
        for widget in (self.silent_box, self.test_button, self.start_button):
            widget.configure(state="disabled" if locked else "normal")

    def refresh_ports(self):
        ports = list_ports()
        self.port_box.configure(values=ports)
        if ports and not self.port.get():
            self.port.set(ports[0])
        self.status.set("Ports refreshed." if ports else "No ports found. Connect an Arduino; run setup.cmd if needed.")

    def start(self):
        if self.session.active or self.voice.busy:
            return
        self.voice.stop()
        try:
            if self.source.get() == "Arduino USB":
                self.serial = SerialInput(self.port.get(), self.config["baud"], self.config["maximum"])
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.started = time.monotonic()
        self.last_reading = None
        self.history.clear()
        self.session.start(self.started)
        self.copy_button.configure(state="disabled")
        self.recipe_text.set("Listening for a little inspiration…")
        self._stage_changed()

    def _stage_changed(self):
        self.stage_text.set(self.session.stage.value)
        line = self.session.line()
        self.line_text.set(line)
        if self.session.recipe:
            self.recipe_text.set(self.session.recipe.display())
            self.copy_button.configure(state="normal")
            self._close_sensor()
        if self.silent.get():
            self.status.set("Silent rehearsal · no speech request sent.")
        elif line:
            self.voice.speak(line)
            self.status.set("Preparing voice…")
        self._controls()

    def test_voice(self):
        if not self.session.active and not self.voice.busy:
            self.voice.speak(TEST_LINE)
            self.status.set("Testing ElevenLabs through Windows default audio output…")
            self._controls()

    def _close_sensor(self):
        if self.serial:
            self.serial.close()
            self.serial = None

    def stop(self, reason="Stopped. You can begin a fresh session when ready."):
        self.voice.stop()
        self._close_sensor()
        self.session.stop()
        self.stage_text.set(Stage.STOPPED.value)
        self.recipe_text.set("Session stopped. No recipe generated.")
        self.copy_button.configure(state="disabled")
        self.status.set(reason)
        self._controls()

    def tick(self):
        now = time.monotonic()
        while True:
            try:
                generation, kind, message = self.voice.events.get_nowait()
            except queue.Empty:
                break
            if generation != self.voice.generation:
                continue
            if kind == "error":
                if self.session.active:
                    self.stop(message + " Start again with Silent rehearsal if needed.")
                else:
                    self.status.set(message)
            else:
                self.status.set(message)
        if self.session.active:
            readings = []
            if self.serial:
                readings = self.serial.poll()
                if self.serial.error:
                    self.stop(self.serial.error)
            else:
                responding = self.session.stage in (Stage.EXPLORE, Stage.RESPOND, Stage.SETTLE)
                readings = [(now, self.simulator.read(now, self.intensity.get() / 100, responding, self.config["maximum"]))]
            for timestamp, raw in readings:
                if not self.session.active or now - timestamp > 1:
                    continue
                self.last_reading = timestamp
                self.session.sample(raw)
                self.history.append(self.session.smoothed)
                baseline = "—" if self.session.baseline is None else f"{self.session.baseline:.0f}"
                self.reading_text.set(f"RAW {raw:.0f}     BASELINE {baseline}     CHANGE {self.session.signal:.0%}")
            if self.serial and ((self.last_reading is None and now - self.started > 6) or (self.last_reading is not None and now - self.last_reading > 3)):
                self.stop("No valid Arduino readings. Check port, baud rate, and newline-delimited sensor values.")
            try:
                if self.session.tick(now, self.voice.busy):
                    self._stage_changed()
            except ValueError as exc:
                self.stop(str(exc))
        self.progress_bar["value"] = self.session.progress(now)
        self._draw()
        self._controls()
        self.after_id = self.root.after(100, self.tick)

    def _draw(self):
        self.canvas.delete("all")
        width = max(2, self.canvas.winfo_width())
        height = self.canvas.winfo_height()
        for fraction in (0.25, 0.5, 0.75):
            self.canvas.create_line(0, height * fraction, width, height * fraction, fill="#38313e")
        maximum = self.config["maximum"]
        if self.session.baseline is not None:
            y = height - self.session.baseline / maximum * (height - 16) - 8
            self.canvas.create_line(0, y, width, y, fill=GREEN, dash=(4, 4))
        if len(self.history) > 1:
            points = []
            for i, value in enumerate(self.history):
                points.extend((i / 299 * width, height - value / maximum * (height - 16) - 8))
            self.canvas.create_line(*points, fill=ACCENT, width=2)
        self.canvas.create_text(10, 10, text=f"{self.source.get()} · raw signal / smoothed trace", fill=MUTED, anchor="nw", font=("Segoe UI", 9))

    def copy_recipe(self):
        if self.session.recipe:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.session.recipe.display())
            self.status.set("Recipe copied.")

    def close(self):
        self.root.after_cancel(self.after_id)
        self.voice.close()
        self._close_sensor()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        config = load_config()
    except ValueError as exc:
        from tkinter import messagebox
        root.withdraw()
        messagebox.showerror("Dirty Minds setup", str(exc), parent=root)
        root.destroy()
        return
    App(root, config)
    root.mainloop()

