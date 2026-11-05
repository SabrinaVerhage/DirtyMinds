from collections import deque
import math
import os
from pathlib import Path
import queue
import re
import time
import tkinter as tk
from tkinter import ttk

from .core import INGREDIENTS, LINES, Session, Stage, TEST_LINE
from .delivery import DeliveryWorker, SCREEN, LEDS, MOTORS, delivery_durations
from .sensors import SerialInput, WirelessInput, Simulator, list_ports
from .voice import ElevenVoice, VoiceWorker
from .lights_ui import LightsTestWindow
from .records import new_record_path, save_record

ROOT = Path(__file__).resolve().parent.parent
BG, PANEL, TEXT, MUTED = "#17151b", "#24212a", "#f3ece4", "#bcb3c1"
ACCENT, GREEN = "#dda2bc", "#bfd19c"
ROW_COLORS = ("#dda2bc", "#bfd19c", "#ff784e", "#70c9b5")


def load_config():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        if (ROOT / ".env").exists():
            raise ValueError("Run setup.cmd first so the app can read .env.") from None
    try:
        maximum, span = float(os.getenv("GSR_MAX", "1023")), float(os.getenv("GSR_SPAN", "200"))
        baud = int(os.getenv("SERIAL_BAUD", "115200"))
        if not all(math.isfinite(x) and x > 0 for x in (maximum, span, baud)):
            raise ValueError
    except ValueError:
        raise ValueError("GSR_MAX, GSR_SPAN and SERIAL_BAUD must be positive numbers in .env.") from None
    try:
        pause = int(os.getenv("ELEVENLABS_WHISPER_PAUSE_MS", "900"))
        if not 0 <= pause <= 3000:
            raise ValueError
    except ValueError:
        raise ValueError("ELEVENLABS_WHISPER_PAUSE_MS must be an integer from 0 to 3000.") from None
    enabled = os.getenv("ENABLE_REAL_PUMPS", "false").strip().lower() == "true"
    rates = ()
    if enabled:
        try:
            rates = tuple(float(x.strip()) for x in os.getenv("PUMP_ML_PER_SECOND", "").split(","))
            if len(rates) != 4 or not all(math.isfinite(x) and x > 0 for x in rates):
                raise ValueError
        except ValueError:
            raise ValueError("Real pumps need four positive, measured PUMP_ML_PER_SECOND rates in .env.") from None
    return {
        "maximum": maximum, "span": span, "baud": baud, "port": os.getenv("SERIAL_PORT", ""),
        "api_key": os.getenv("ELEVENLABS_API_KEY", "").strip(),
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID", "1ykC5GeLM4dP82qkyo91").strip(),
        "model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip(),
        "whisper": os.getenv("ELEVENLABS_WHISPER", "true").strip().lower() in ("true", "1", "yes"),
        "whisper_model_id": os.getenv("ELEVENLABS_WHISPER_MODEL_ID", "eleven_v3").strip(),
        "whisper_pause_ms": pause,
        "round_voices": [os.getenv(f"VOICE_{item.key.upper()}", item.voice_id).strip() or item.voice_id for item in INGREDIENTS],
        "pump_port": os.getenv("PUMP_PORT", "").strip(),
        "real_pumps": enabled, "pump_rates": rates,
    }


class App:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.session, self.simulator = Session(config["span"]), Simulator()
        self.serial = self.last_reading = self.lights_window = self.cast_window = None
        self.record_path = None
        self.record_error = ""
        self.session_source = self.session_mode = ""
        self.session_voices, self.durations = [], []
        self.history = deque(maxlen=300)
        self.delivery = DeliveryWorker()
        self.voice = VoiceWorker(ElevenVoice(
            config["api_key"], config["voice_id"], config["model_id"], ROOT / ".cache" / "voice",
            whisper=config.get("whisper", True), whisper_model_id=config.get("whisper_model_id", "eleven_v3"),
            whisper_pause_ms=config.get("whisper_pause_ms", 900)))
        self.source, self.port = tk.StringVar(value="Simulated"), tk.StringVar(value=config["port"])
        self.silent = tk.BooleanVar(value=not bool(config["api_key"]))
        self.whisper = tk.BooleanVar(value=config.get("whisper", True))
        self.voice_choices = {
            "Nora · Cozy ASMR": "1ykC5GeLM4dP82qkyo91",
            "Sarah · original voice": "EXAVITQu4vr4xnSDxMaL",
            "Trevor · Whisper app": "17JdVkQHD6PE3HPohzr2",
            "Shanni · sultry": "A6TsrDqI2qlO9AWAfZHY",
            "Marleen · Dutch": "AIFcvMreCoOxyPTbUrwe",
        }
        selected = next((name for name, ident in self.voice_choices.items() if ident == config["voice_id"]), "Voice from .env")
        self.voice_choices[selected] = config["voice_id"]
        self.voice_choice = tk.StringVar(value=selected)
        self.round_voices = list(config.get("round_voices", [item.voice_id for item in INGREDIENTS]))
        ports = list_ports()
        self.pump_port = tk.StringVar(value=config.get("pump_port") or (ports[0] if len(ports) == 1 else ""))
        self.mode = tk.StringVar(value=config.get("delivery_mode", SCREEN))
        self.intensity = tk.DoubleVar(value=40)
        self.stage_text = tk.StringVar(value="Four temptations. One dirty mind.")
        self.status = tk.StringVar(value="Feather: wireless GSR. Uno: pumps. Qnect: manual ring control.")
        self.reading_text = tk.StringVar(value="RAW —    BASELINE —    CHANGE —")
        self.line_text = tk.StringVar(value="A silver pearl. A classic temptation. A little heat. A Dutch secret.")
        self.recipe_text = tk.StringVar(value="Your personal blend appears after all four rounds.\nThe Feather Wing shows the live signal.")
        self.output_text = tk.StringVar(value="After the reveal: selected brine rows light in order.")
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.stop())
        self.after_id = root.after(100, self.tick)

    def _build(self):
        root = self.root
        root.title("Dirty Minds · four temptations")
        root.geometry("1060x820")
        root.minsize(960, 780)
        root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", MUTED)])
        style.configure("TButton", font=("Segoe UI", 10), padding=6, background=PANEL, foreground=TEXT)
        style.map("TButton", background=[("active", "#463b4b")], foreground=[("disabled", MUTED)])
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=ACCENT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL), ("disabled", PANEL)], foreground=[("disabled", MUTED), ("readonly", TEXT)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)
        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)
        shell = ttk.Frame(root, padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        ttk.Label(shell, text="DIRTY MINDS", font=("Segoe UI", 27, "bold"), foreground=ACCENT).grid(sticky="w", pady=(0, 12))
        body = ttk.Frame(shell)
        body.grid(row=1, sticky="nsew")
        body.columnconfigure(1, weight=1)
        controls = ttk.Frame(body, padding=(0, 0, 22, 0))
        controls.grid(row=0, column=0, sticky="nsw")
        controls.columnconfigure(0, weight=1)
        def label(text):
            ttk.Label(controls, text=text, foreground=GREEN).grid(sticky="w", pady=(8, 3))
        label("SIGNAL INPUT")
        self.source_box = ttk.Combobox(controls, textvariable=self.source, values=("Simulated", "Feather Wi-Fi", "Arduino USB"), state="readonly", width=25)
        self.source_box.grid(sticky="ew")
        self.source_box.bind("<<ComboboxSelected>>", lambda event: self._controls())
        label("GSR IP address or USB port")
        self.port_box = ttk.Combobox(controls, textvariable=self.port, values=list_ports(), width=25)
        self.port_box.grid(sticky="ew")
        label("Simulated response · change each round")
        self.slider = ttk.Scale(controls, from_=0, to=100, variable=self.intensity)
        self.slider.grid(sticky="ew", pady=4)
        label("HOST VOICE")
        self.voice_box = ttk.Combobox(controls, textvariable=self.voice_choice, values=tuple(self.voice_choices), state="readonly", width=25)
        self.voice_box.grid(sticky="ew")
        self.voice_box.bind("<<ComboboxSelected>>", lambda event: self.select_voice())
        self.whisper_box = ttk.Checkbutton(controls, text="Whisper · pauses between phrases", variable=self.whisper, command=self.set_voice_style)
        self.whisper_box.grid(sticky="w", pady=(5, 0))
        self.silent_box = ttk.Checkbutton(controls, text="Silent rehearsal", variable=self.silent)
        self.silent_box.grid(sticky="w")
        voice_actions = ttk.Frame(controls)
        voice_actions.grid(sticky="ew", pady=5)
        self.test_button = ttk.Button(voice_actions, text="Test host", command=self.test_voice)
        self.test_button.pack(side="left")
        self.cast_button = ttk.Button(voice_actions, text="Four voices…", command=self.edit_cast)
        self.cast_button.pack(side="left", padx=(6, 0))
        label("AFTER THE REVEAL")
        modes = (SCREEN, MOTORS) if self.config.get("real_pumps") else (SCREEN,)
        self.mode_box = ttk.Combobox(controls, textvariable=self.mode, values=modes, state="readonly", width=25)
        self.mode_box.grid(sticky="ew")
        self.mode_box.bind("<<ComboboxSelected>>", lambda event: self._controls())
        label("Uno pump USB port")
        self.pump_port_box = ttk.Combobox(controls, textvariable=self.pump_port, values=list_ports(), width=25)
        self.pump_port_box.grid(sticky="ew")
        self.refresh_button = ttk.Button(controls, text="Refresh USB ports", command=self.refresh_ports)
        self.refresh_button.grid(sticky="ew", pady=6)
        self.start_button = tk.Button(controls, text="Begin temptation", command=self.start, bg=ACCENT, fg=BG,
            activebackground=TEXT, font=("Segoe UI", 12, "bold"), relief="flat", pady=10)
        self.start_button.grid(sticky="ew", pady=(7, 5))
        tk.Button(controls, text="Stop / Esc", command=self.stop, bg=PANEL, fg=TEXT,
                  font=("Segoe UI", 11), relief="flat", pady=8).grid(sticky="ew")
        ttk.Label(controls, text="First voice generation takes longer.\nReplays reuse the local audio cache.", foreground=MUTED,
                  font=("Segoe UI", 9)).grid(sticky="w", pady=8)
        content = ttk.Frame(body)
        content.grid(row=0, column=1, sticky="nsew")
        ttk.Label(content, textvariable=self.stage_text, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(content, height=76, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="x", pady=(10, 4))
        ttk.Label(content, textvariable=self.reading_text, foreground=GREEN, font=("Consolas", 10)).pack(anchor="w")
        self.progress_bar = ttk.Progressbar(content, maximum=100)
        self.progress_bar.pack(fill="x", pady=7)
        self.script_label = ttk.Label(content, textvariable=self.line_text, wraplength=640, font=("Segoe UI", 12))
        self.script_label.pack(fill="x", pady=(4, 12))
        results = ttk.Frame(content)
        results.pack(fill="x", pady=(0, 10))
        results.columnconfigure(1, weight=1)
        self.result_texts = []
        for i, ingredient in enumerate(INGREDIENTS):
            ttk.Label(results, text=f"{i+1}  {ingredient.name}", foreground=ROW_COLORS[i]).grid(row=i, column=0, sticky="w", padx=(0, 15), pady=2)
            value = tk.StringVar(value="Waiting")
            self.result_texts.append(value)
            ttk.Label(results, textvariable=value).grid(row=i, column=1, sticky="w")
        ttk.Label(content, text="YOUR BLEND", foreground=ACCENT).pack(anchor="w")
        self.recipe_label = ttk.Label(content, textvariable=self.recipe_text, wraplength=640)
        self.recipe_label.pack(fill="x", pady=(4, 8))
        output = ttk.Frame(content)
        output.pack(fill="x", pady=(0, 6))
        self.led_canvas = tk.Canvas(output, width=150, height=70, bg=BG, highlightthickness=0)
        self.led_canvas.pack(side="left")
        self.cells = [[self.led_canvas.create_rectangle(2+x*18, 2+y*17, 16+x*18, 14+y*17,
                       fill="#38313e", outline="") for x in range(8)] for y in range(4)]
        ttk.Label(output, textvariable=self.output_text, wraplength=420, foreground=MUTED).pack(side="left", padx=10)
        actions = ttk.Frame(content)
        actions.pack(anchor="w")
        self.copy_button = ttk.Button(actions, text="Copy recipe", command=self.copy_recipe, state="disabled")
        self.copy_button.pack(side="left")
        self.lights_button = ttk.Button(actions, text="Test brine lights…", command=self.test_lights)
         # Legacy Feather pump-light test is hidden: the Wing is now the sensor display.
        self.status_label = ttk.Label(shell, textvariable=self.status, foreground=MUTED, wraplength=1000)
        self.status_label.grid(row=2, sticky="ew", pady=(10, 5))
        ttk.Label(shell, text="Signal change is a playful ingredient mapping, not a reading of thoughts or desire.",
                  foreground=MUTED, font=("Segoe UI", 9)).grid(row=3, sticky="w")
        content.bind("<Configure>", lambda event: self._wrap(event.width))
        self._controls()

    def _wrap(self, width):
        self.script_label.configure(wraplength=max(300, width))
        self.recipe_label.configure(wraplength=max(300, width))

    def _controls(self):
        locked = self.session.active or self.voice.busy or self.delivery.busy or self.lights_window is not None or self.cast_window is not None
        for widget in (self.source_box, self.voice_box, self.mode_box):
            widget.configure(state="disabled" if locked else "readonly")
        self.port_box.configure(state="normal" if not locked and self.source.get() in ("Arduino USB", "Feather Wi-Fi") else "disabled")
        self.pump_port_box.configure(state="normal" if not locked and self.mode.get() != SCREEN else "disabled")
        self.slider.configure(state="normal" if self.source.get() == "Simulated" else "disabled")
        for widget in (self.refresh_button, self.whisper_box, self.silent_box, self.test_button,
                       self.cast_button, self.lights_button, self.start_button):
            widget.configure(state="disabled" if locked else "normal")

    def refresh_ports(self):
        ports = list_ports()
        self.port_box.configure(values=ports)
        self.pump_port_box.configure(values=ports)
        if len(ports) == 1 and not self.pump_port.get():
            self.pump_port.set(ports[0])
        self.status.set("Ports refreshed." if ports else "No USB ports found. Connect the Feather and try again.")

    def start(self):
        if self.session.active or self.voice.busy or self.delivery.busy or self.lights_window or self.cast_window:
            return
        self.voice.stop()
        try:
            mode = self.mode.get()
            if mode not in (SCREEN, LEDS, MOTORS) or (mode == MOTORS and not self.config.get("real_pumps")):
                raise ValueError("Choose Screen rehearsal or enabled calibrated pumps.")
            if mode != SCREEN and not self.pump_port.get().strip():
                raise ValueError("Choose the Uno COM port, or select Screen rehearsal.")
            if self.source.get() == "Feather Wi-Fi":
                self.serial = WirelessInput(self.port.get(), maximum=self.config["maximum"])
            elif self.source.get() == "Arduino USB":
                if mode != SCREEN and self.port.get().strip().upper() == self.pump_port.get().strip().upper():
                    raise ValueError("GSR and Feather need separate boards/COM ports. Use simulated GSR for the LED test.")
                self.serial = SerialInput(self.port.get(), self.config["baud"], self.config["maximum"])
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.started, self.last_reading = time.monotonic(), None
        self.history.clear()
        self.durations = []
        self.record_path = new_record_path(ROOT / "output" / "sessions")
        self.record_error = ""
        self.session_source, self.session_mode = self.source.get(), mode
        self.session_voices = list(self.round_voices)
        self.session.start(self.started, spoken=not self.silent.get())
        self.copy_button.configure(state="disabled")
        self.recipe_text.set("Four temptations are waiting. Your blend comes after the last round.")
        self._set_row(None)
        self.output_text.set(f"{mode} · waiting for the recipe reveal")
        self._stage_changed()

    def _stage_changed(self):
        self.stage_text.set(self.session.stage.value)
        line = self.session.line()
        self.line_text.set(line)
        self._show_results()
        if self.session.recipe:
            self.recipe_text.set(self.session.recipe.display())
            self.copy_button.configure(state="normal")
            self._close_sensor()
        self._save()
        if self.session.stage == Stage.DISPENSE:
            try:
                self.durations = delivery_durations(self.session.recipe, self.session_mode,
                    self.config.get("pump_rates", ()), real_enabled=self.config.get("real_pumps", False))
                self._save()
                self.line_text.set("Your selected brines run one at a time. The final whisper follows completion.")
                if not self.delivery.start_delivery(self.pump_port.get(), self.durations, self.session_mode,
                                                   real_enabled=self.config.get("real_pumps", False)):
                    raise ValueError("The previous delivery is still stopping. Start a fresh session.")
                self.status.set("Starting the selected brine sequence…")
            except ValueError as exc:
                self.stop(str(exc))
        elif self.session.stage == Stage.COMPLETE:
            self.status.set("Session complete. Results saved locally." + (" " + self.record_error if self.record_error else ""))
        elif self.session.voice_pending:
            index = self.session.round_index
            voice_id = self.session_voices[index] if index is not None else self.voice.backend.voice_id
            if not self.voice.speak(line, voice_id=voice_id):
                self.stop("Voice was still busy. Start a fresh session.")
            else:
                self.status.set("Preparing voice… scoring starts when this round's playback begins.")
        elif self.silent.get():
            self.status.set("Silent rehearsal · move the slider differently in each round.")
        else:
            self.status.set("A quiet pause. Keep your fingers still.")
        self._controls()

    def _show_results(self):
        for i, value in enumerate(self.result_texts):
            if i < len(self.session.results):
                result = self.session.results[i]
                value.set(f"{result.score:.0%} response · saved")
            elif i == self.session.round_index:
                value.set("Listening…" if self.session.collecting else "Preparing voice…")
            else:
                value.set("Waiting")

    def _save(self):
        if self.record_path is None:
            return
        try:
            save_record(self.record_path, self.session, source=self.session_source, mode=self.session_mode,
                        durations=self.durations, voices=self.session_voices)
        except OSError:
            self.record_error = "Could not save the local results file; results remain visible in the window."

    def test_voice(self):
        if not self.session.active and not self.voice.busy:
            self.voice.speak(TEST_LINE)
            self.status.set("Testing the host through Windows default audio output…")
            self._controls()

    def edit_cast(self):
        if self.session.active or self.voice.busy or self.cast_window:
            return
        window = self.cast_window = tk.Toplevel(self.root)
        window.title("Four temptations · voice cast")
        window.configure(bg=BG)
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Choose a voice or paste a voice ID. Test plays a short excerpt.", wraplength=570).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        variables = []
        for i, item in enumerate(INGREDIENTS):
            name = next((n for n, ident in self.voice_choices.items() if ident == self.round_voices[i]), self.round_voices[i])
            var = tk.StringVar(value=name)
            variables.append(var)
            ttk.Label(frame, text=f"{i+1} · {item.name}").grid(row=i+1, column=0, sticky="w", padx=(0, 12), pady=7)
            ttk.Combobox(frame, textvariable=var, values=tuple(self.voice_choices), width=30).grid(row=i+1, column=1)
            def audition(index=i, variable=var):
                if self.voice.busy:
                    self.status.set("Wait for this voice, or use Stop before testing another.")
                    return
                ident = self.voice_choices.get(variable.get(), variable.get().strip())
                if ident:
                    excerpt = ". ".join(INGREDIENTS[index].pitch.split(". ")[:2]) + "."
                    self.voice.speak(excerpt, voice_id=ident)
            ttk.Button(frame, text="Listen", command=audition).grid(row=i+1, column=2, padx=(10, 0))
        ttk.Label(frame, text="Marleen is Dutch; the accent in English and the whisper need auditioning.\nChanges here last until restart. Permanent IDs: VOICE_ONION / OLIVE / JALAPENO / PICKLE in .env.",
                  wraplength=610, foreground=MUTED).grid(row=5, column=0, columnspan=3, sticky="w", pady=12)
        def finish():
            ids = [self.voice_choices.get(var.get(), var.get().strip()) for var in variables]
            if all(ids):
                self.round_voices = ids
            self.voice.stop()
            window.grab_release()
            window.destroy()
            self.cast_window = None
            self._controls()
        ttk.Button(frame, text="Use this cast", command=finish).grid(row=6, column=0, columnspan=3, sticky="e")
        window.protocol("WM_DELETE_WINDOW", finish)
        window.bind("<Escape>", lambda event: self.voice.stop())
        self._controls()

    def test_lights(self):
        if self.session.active or self.voice.busy or self.delivery.busy:
            return
        if self.lights_window is None:
            self.lights_window = LightsTestWindow(self.root, on_close=self._lights_closed)
            self.lights_window.port.set(self.pump_port.get())
        self._controls()

    def _lights_closed(self):
        self.lights_window = None
        self._controls()

    def set_voice_style(self):
        self.voice.backend.whisper = self.whisper.get()

    def select_voice(self):
        self.voice.backend.voice_id = self.voice_choices[self.voice_choice.get()]

    def _close_sensor(self):
        if self.serial:
            self.serial.close()
            self.serial = None

    def stop(self, reason="Stopped. Start again for a fresh baseline and four new rounds."):
        self.voice.stop()
        self.delivery.stop()
        self._close_sensor()
        self.session.stop()
        self._save()
        self.stage_text.set(Stage.STOPPED.value)
        self._set_row(None)
        self.output_text.set("Stopped · no automatic delivery retry")
        self.status.set(reason)
        self._controls()

    def _set_row(self, pump):
        for i, row in enumerate(self.cells, 1):
            for cell in row:
                self.led_canvas.itemconfigure(cell, fill=ROW_COLORS[i-1] if pump == i else "#38313e")

    def _delivery_events(self, now):
        while True:
            try:
                kind, message = self.delivery.events.get_nowait()
            except queue.Empty:
                break
            if self.session.stage != Stage.DISPENSE:
                continue
            if kind in ("error", "cancelled"):
                self.stop(message)
            elif kind == "done":
                self._set_row(None)
                self.output_text.set("Brine delivery complete." if self.session_mode == MOTORS else "Light rehearsal complete · no liquid dispensed")
                if self.session.finish_delivery(now):
                    self._stage_changed()
            elif kind == "reply":
                match = re.match(r"START pump=([1-4])\b", message)
                if match:
                    pump = int(match[1])
                    self._set_row(pump)
                    self.output_text.set(f"{pump} · {INGREDIENTS[pump-1].name}\n{self.session_mode}")
                elif message.startswith("PUMP_DONE "):
                    self._set_row(None)
            else:
                self.status.set(message)

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
                    self.stop(message + " Check Four voices, or rehearse silently.")
                else:
                    self.status.set(message)
            elif kind == "playing":
                self.session.playback_started()
                self._show_results()
            elif kind == "done":
                self.session.voice_finished(now)
                self.status.set("A quiet moment to sense the response…" if self.session.collecting else message)
            else:
                self.status.set(message)
        self._delivery_events(now)
        if self.session.needs_sensor:
            if self.serial:
                readings = self.serial.poll()
                if self.serial.error:
                    self.stop(self.serial.error)
            else:
                readings = [(now, self.simulator.read(now, self.intensity.get()/100,
                                                      self.session.collecting, self.config["maximum"]))]
            for timestamp, raw in readings:
                if not self.session.needs_sensor or now - timestamp > 1:
                    continue
                self.last_reading = timestamp
                self.session.sample(raw)
                self.history.append(self.session.smoothed)
                baseline = "—" if self.session.baseline is None else f"{self.session.baseline:.0f}"
                self.reading_text.set(f"RAW {raw:.0f}    BASELINE {baseline}    CHANGE {self.session.signal:.0%}")
            if self.serial and ((self.last_reading is None and now-self.started > 6) or (self.last_reading is not None and now-self.last_reading > 3)):
                self.stop("No valid GSR readings. Check the sensor connection, address and network.")
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
        width, height = max(2, self.canvas.winfo_width()), self.canvas.winfo_height()
        for fraction in (.25, .5, .75):
            self.canvas.create_line(0, height*fraction, width, height*fraction, fill="#38313e")
        maximum = self.config["maximum"]
        if self.session.baseline is not None:
            y = height - self.session.baseline / maximum * (height-16) - 8
            self.canvas.create_line(0, y, width, y, fill=GREEN, dash=(4, 4))
        if len(self.history) > 1:
            points = []
            for i, value in enumerate(self.history):
                points.extend((i/299*width, height-value/maximum*(height-16)-8))
            self.canvas.create_line(*points, fill=ACCENT, width=2)

    def copy_recipe(self):
        if self.session.recipe:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.session.recipe.display())
            self.status.set("Recipe copied.")

    def close(self):
        self.root.after_cancel(self.after_id)
        if self.lights_window:
            self.lights_window.close()
        if self.session.active:
            self.stop("Closing")
        self.delivery.close()
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
