from collections import deque
from dataclasses import replace
import math
import os
from pathlib import Path
import queue
import re
import time
import traceback
import tkinter as tk
from tkinter import ttk

from .core import (DEFAULT_PUMP_ORDER, INGREDIENTS, INGREDIENT_BY_KEY, LEGACY_PUMP_ORDER,
                   PROFESSOR_VOICE_ID, REST_STAGES, ROUND_STAGES, SOUND_CUES, VOICE_CUES, WAITING_TUNE,
                   Session, Stage, TEST_LINE)
from .delivery import DeliveryWorker, SCREEN, LEDS, MOTORS, MOTOR_MODES, PUMP_CHANNELS, WATER, delivery_durations, water_test_ms
from .debug_log import DebugLog
from .hardware_ui import HardwareWindow
from .patient_ui import PatientTimeline, PatientView
from .sensors import InputOpening, SerialInput, WirelessInput, Simulator, list_ports
from .scripts import DEFAULT_MODEL, WritingRequest, choose_tactics, generate_intro, generate_lines, generate_name
from .voice import ElevenVoice, VoiceWorker
from .records import (load_connections, load_pump_calibration, load_pump_order, new_record_path,
                      recent_recipe_names, save_connections, save_pump_calibration, save_pump_order,
                      save_record)

ROOT = Path(__file__).resolve().parent.parent
BG, PANEL, TEXT, MUTED = "#111814", "#1b2620", "#f6efe1", "#b0bdb0"
ACCENT, GREEN = "#e1ed9a", "#a6bf9e"
ROW_COLORS = ("#f3c8bf", "#e7ca72", "#d9e893")
ASSETS = ROOT / "assets"
CAST_ART = ASSETS / "diagnostic-cast.png"
IDLE_CELL = "#314138"
USB_SENSOR_SOURCES = ("Feather USB", "Arduino USB")


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
    pump_order = load_pump_order(ROOT / "output" / "pump_channels.json")
    calibration_path = ROOT / "output" / "pump_calibration.json"
    rates = load_pump_calibration(calibration_path, pump_order)
    legacy_enabled = os.getenv("ENABLE_REAL_PUMPS", "false").strip().lower() == "true"
    calibration_status = ""
    if not rates and calibration_path.exists():
        calibration_status = "Pump calibration is unavailable for this assignment. Calibrate in Hardware console."
    elif not rates and legacy_enabled and pump_order == LEGACY_PUMP_ORDER:
        try:
            rates = tuple(float(x.strip()) for x in os.getenv("PUMP_ML_PER_SECOND", "").split(","))
            if len(rates) not in (len(INGREDIENTS), PUMP_CHANNELS) or not all(
                    math.isfinite(x) and x > 0 for x in rates[:len(INGREDIENTS)]):
                raise ValueError
        except ValueError:
            rates = ()
            calibration_status = "Pump rates need calibration. Open the Hardware console."
    elif not rates and legacy_enabled:
        calibration_status = "Pump assignments changed. Recalibrate before dispensing."
    previous_defaults = {
        "onion": ("1ykC5GeLM4dP82qkyo91",),
        "olive": ("EXAVITQu4vr4xnSDxMaL", "PB6BdkFkZLbI39GHdnbQ"),
        "jalapeno": ("A6TsrDqI2qlO9AWAfZHY",),
    }
    cast = []
    for item in INGREDIENTS:
        ident = os.getenv(f"VOICE_{item.key.upper()}", "").strip()
        cast.append(item.voice_id if not ident or ident in previous_defaults[item.key] else ident)
    return {
        "maximum": maximum, "span": span, "baud": baud, "port": os.getenv("SERIAL_PORT", ""),
        "api_key": os.getenv("ELEVENLABS_API_KEY", "").strip(),
        "model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip(),
        "whisper": os.getenv("ELEVENLABS_WHISPER", "true").strip().lower() in ("true", "1", "yes"),
        "whisper_model_id": os.getenv("ELEVENLABS_WHISPER_MODEL_ID", "eleven_v4").strip() or "eleven_v4",
        "whisper_pause_ms": pause,
        "voice_effects": os.getenv("ELEVENLABS_VOICE_EFFECTS", "true").strip().lower() in ("true", "1", "yes"),
        "round_voices": cast,
        "professor_voice": os.getenv("VOICE_PROFESSOR", "").strip() or PROFESSOR_VOICE_ID,
        "openai_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "openai_model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "feather_host": os.getenv("FEATHER_HOST", "").strip(),
        "pump_port": os.getenv("PUMP_PORT", "").strip(),
        "real_pumps": bool(rates), "pump_rates": rates, "calibration_status": calibration_status,
        "pump_order": pump_order,
    }


class App:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.session, self.simulator = Session(config["span"]), Simulator()
        self.serial = self.last_reading = self.cast_window = self.hardware_window = None
        self.patient_window = self.input_opening = None
        self.pump_order = config.get("pump_order", DEFAULT_PUMP_ORDER)
        self.active_pump = None
        self.patient_timeline = PatientTimeline()
        self.patient_timeline.advance(self.session.stage)
        self.recent_names = deque(recent_recipe_names(ROOT / "output" / "sessions"), maxlen=24)
        self.waiting_tune_started = False
        self.voice_requested_at = None
        self.last_tick = time.monotonic()
        self.graph_state = None
        self.debug = DebugLog(ROOT / "output" / "debug.log")
        root.report_callback_exception = self._callback_error
        self.record_path = None
        self.record_error = ""
        self.session_source = self.session_mode = ""
        self.session_voices, self.durations = [], []
        self.session_scripts, self.previous_tactics = [], ()
        self.script_request = self.generated_lines = self.name_request = self.intro_request = None
        self.accept_script = False
        self.history = deque(maxlen=300)
        self.events = deque(maxlen=180)
        self.delivery = DeliveryWorker()
        self.round_voices = list(config.get("round_voices", [item.voice_id for item in INGREDIENTS]))
        self.connection_path = ROOT / "output" / "connections.json"
        self.saved_connections = load_connections(self.connection_path)
        self.professor_voice = config.get("professor_voice", PROFESSOR_VOICE_ID)
        self.voice = VoiceWorker(ElevenVoice(
            config["api_key"], self.professor_voice, config["model_id"], ROOT / ".cache" / "voice",
            whisper=config.get("whisper", True), whisper_model_id=config.get("whisper_model_id", "eleven_v4"),
            whisper_pause_ms=config.get("whisper_pause_ms", 900)))
        self.source = tk.StringVar(value="Feather USB")
        old_port = config["port"]
        old_host = old_port if "." in old_port or ":" in old_port else ""
        self.port = tk.StringVar(value=self.saved_connections.get("gsr_usb", "" if old_host else old_port))
        self.feather_host = tk.StringVar(value=self.saved_connections.get(
            "feather_ip", config.get("feather_host") or old_host))
        self.silent = tk.BooleanVar(value=False)
        self.whisper = tk.BooleanVar(value=config.get("whisper", True))
        self.effects = tk.BooleanVar(value=config.get("voice_effects", True))
        self.fresh_scripts = tk.BooleanVar(value=bool(config.get("openai_key")))
        self.voice_choices = {
            **{item.voice_name: item.voice_id for item in INGREDIENTS},
            "Nora · Cozy ASMR": "1ykC5GeLM4dP82qkyo91",
            "Natasha · playful whisper": "PB6BdkFkZLbI39GHdnbQ",
            "Emily · soft whisper": "1cxc5c3E9K6F1wlqOJGV",
            "AImee · ASMR whisper": "GL7nHO5mDrxcHlJPJK5T",
            "Matthew · deep whisper": "uCAKWh24Y93ESUjKwRGP",
            "Trevor Whisper · Australian": "17JdVkQHD6PE3HPohzr2",
            "Shanni · sultry": "A6TsrDqI2qlO9AWAfZHY",
            "Marleen · Dutch": "AIFcvMreCoOxyPTbUrwe",
        }
        self.ports = list_ports()
        default_pump = config.get("pump_port") or (self.ports[0] if len(self.ports) == 1 else "")
        self.pump_port = tk.StringVar(value=self.saved_connections.get("pump_usb", default_pump))
        default_mode = MOTORS if config.get("real_pumps") else WATER
        self.mode = tk.StringVar(value=config.get("delivery_mode", default_mode))
        self.water_times = [tk.StringVar(value="5.0") for _ in range(PUMP_CHANNELS)]
        self.session_water_ms = ()
        self.intensity = tk.DoubleVar(value=40)
        self.stage_text = tk.StringVar(value=Stage.READY.value)
        self.status = tk.StringVar(value=config.get("calibration_status")
                                   or f"{self.source.get()} · {self.mode.get()}")
        self.reading_text = tk.StringVar(value="RAW —    BASELINE —    CHANGE —")
        self.line_text = tk.StringVar(value="An experimental procedure for detecting inappropriate responses and prescribing corrective cocktails.")
        self.recipe_text = tk.StringVar(value="Your prescription will appear after the three diagnostic stimuli.")
        self.output_text = tk.StringVar(value="Awaiting your prescription")
        self.note("App / started")
        self.note(self.status.get())
        self.status.trace_add("write", lambda *_: self.note(self.status.get()))
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", self.escape)
        root.bind("<F11>", self.toggle_fullscreen)
        root.bind("<F10>", self.toggle_patient_view)
        root.bind("<F8>", self.new_session_shortcut)
        self.after_id = root.after(100, self.tick)

    def _build(self):
        root = self.root
        root.title("Dirty Minds · The Dirty Mind Diagnostic")
        root.attributes("-fullscreen", True)
        root.geometry("1060x790")
        root.minsize(960, 750)
        root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Kicker.TLabel", foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", foreground=TEXT, font=("Georgia", 23))
        style.configure("Card.TFrame", background=PANEL)
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Quote.TLabel", background=PANEL, foreground=TEXT, font=("Georgia", 14))
        style.configure("TLabelframe", background=BG, bordercolor=GREEN)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", MUTED)])
        style.configure("TButton", font=("Segoe UI", 10), padding=6, background=PANEL, foreground=TEXT)
        style.map("TButton", background=[("active", "#304437")], foreground=[("disabled", MUTED)])
        style.configure("Stop.TButton", background="#452b27", foreground="#ffdbcd")
        style.map("Stop.TButton", background=[("active", "#633e35")])
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=ACCENT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL), ("disabled", PANEL)], foreground=[("disabled", MUTED), ("readonly", TEXT)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)
        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)
        shell = ttk.Frame(root, padding=(24, 12))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        header = ttk.Frame(shell)
        header.grid(row=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="DEPARTMENT OF INAPPROPRIATE RESPONSES", style="Kicker.TLabel").grid(sticky="w")
        ttk.Label(header, text="DIRTY MINDS", foreground=TEXT, font=("Georgia", 38)).grid(row=1, sticky="w")
        ttk.Label(header, text="3 STIMULI   /   1 PRESCRIPTION", style="Kicker.TLabel").grid(row=1, column=1, sticky="se", pady=(0, 8))
        ttk.Separator(header).grid(row=2, columnspan=2, sticky="ew", pady=(6, 0))
        body = ttk.Frame(shell)
        body.grid(row=1, sticky="nsew")
        body.columnconfigure(1, weight=1)
        controls = ttk.Frame(body, padding=(0, 0, 22, 0))
        controls.grid(row=0, column=0, sticky="nsw")
        controls.columnconfigure(0, weight=1)
        def label(text):
            ttk.Label(controls, text=text, style="Kicker.TLabel").grid(sticky="w", pady=(7, 3))
        label("01   SIGNAL INPUT")
        self.source_box = ttk.Combobox(controls, textvariable=self.source, values=(*USB_SENSOR_SOURCES, "Feather Wi-Fi"), state="readonly", width=25)
        self.source_box.grid(sticky="ew")
        self.source_box.bind("<<ComboboxSelected>>", lambda event: self._controls())
        self.input_label = ttk.Label(controls, text="Input address", style="Muted.TLabel")
        self.input_label.grid(sticky="w", pady=(5, 2))
        self.port_box = ttk.Combobox(controls, textvariable=self.port, values=self.ports, width=25)
        self.port_box.grid(sticky="ew")
        self.port_source = None
        label("02   VOICE & SCRIPT")
        self.whisper_box = ttk.Checkbutton(controls, text="Whisper delivery", variable=self.whisper, command=self.set_voice_style)
        self.whisper_box.grid(sticky="w", pady=(5, 0))
        self.effects_box = ttk.Checkbutton(controls, text="Breaths and sighs", variable=self.effects)
        self.effects_box.grid(sticky="w")
        self.script_box = ttk.Checkbutton(controls, text="Fresh script · OpenAI" if self.config.get("openai_key")
                                        else "Fresh script · needs API key", variable=self.fresh_scripts)
        self.script_box.grid(sticky="w")
        voice_actions = ttk.Frame(controls)
        voice_actions.grid(sticky="ew", pady=5)
        self.test_button = ttk.Button(voice_actions, text="Test headphones", command=self.test_voice)
        self.test_button.pack(side="left")
        self.cast_button = ttk.Button(voice_actions, text="Three voices…", command=self.edit_cast)
        self.cast_button.pack(side="left", padx=(6, 0))
        label("03   BRINE OUTPUT")
        modes = (WATER, MOTORS) if self.config.get("real_pumps") else (WATER,)
        self.mode_box = ttk.Combobox(controls, textvariable=self.mode, values=modes, state="readonly", width=25)
        self.mode_box.grid(sticky="ew")
        self.mode_box.bind("<<ComboboxSelected>>", lambda event: self._controls())
        self.hardware_button = ttk.Button(controls, text="Hardware console…", command=self.open_hardware)
        self.hardware_button.grid(sticky="ew", pady=(5, 0))
        self.start_button = tk.Button(controls, text="New session · F8", command=self.start, bg=ACCENT, fg=BG,
            activebackground=TEXT, font=("Segoe UI", 12, "bold"), relief="flat", pady=10)
        self.start_button.grid(sticky="ew", pady=(7, 5))
        ttk.Button(controls, text="Stop / Esc", command=self.stop, style="Stop.TButton").grid(sticky="ew")
        ttk.Button(controls, text="Patient view · F10", command=self.toggle_patient_view).grid(sticky="ew", pady=(5, 0))
        ttk.Button(controls, text="Open debug log", command=self.open_debug_log).grid(sticky="ew", pady=(4, 0))
        ttk.Label(controls, text="F11 · toggle fullscreen", style="Muted.TLabel").grid(sticky="w", pady=(5, 0))
        content = ttk.Frame(body)
        content.grid(row=0, column=1, sticky="nsew")
        ttk.Label(content, text="THE DIRTY MIND DIAGNOSTIC", style="Kicker.TLabel").pack(anchor="w")
        ttk.Label(content, textvariable=self.stage_text, style="Title.TLabel").pack(anchor="w", pady=(2, 0))
        self.progress_bar = ttk.Progressbar(content, maximum=100)
        self.progress_bar.pack(fill="x", pady=(8, 10))
        quote = ttk.Frame(content, style="Card.TFrame", padding=(14, 8))
        quote.pack(fill="x")
        self.script_label = ttk.Label(quote, textvariable=self.line_text, wraplength=620, style="Quote.TLabel")
        self.script_label.pack(fill="x")
        self.canvas = tk.Canvas(content, height=52, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="x", pady=(10, 4))
        ttk.Label(content, textvariable=self.reading_text, foreground=GREEN, font=("Consolas", 10)).pack(anchor="w")
        results = ttk.Frame(content)
        results.pack(fill="x", pady=(8, 10))
        results.columnconfigure(1, weight=1)
        if CAST_ART.is_file():
            self.cast_art = tk.PhotoImage(file=str(CAST_ART)).subsample(9)
            ttk.Label(results, image=self.cast_art).grid(
                row=0, column=2, rowspan=len(INGREDIENTS), padx=(16, 0))
        self.result_texts = []
        for i, ingredient in enumerate(INGREDIENTS):
            ttk.Label(results, text=f"0{i+1}   {ingredient.name}", foreground=ROW_COLORS[i],
                      font=("Segoe UI", 10, "bold")).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=2)
            value = tk.StringVar(value="Waiting")
            self.result_texts.append(value)
            ttk.Label(results, textvariable=value).grid(row=i, column=1, sticky="w")
        ttk.Separator(content).pack(fill="x", pady=(0, 8))
        ttk.Label(content, text="COCKTAIL PRESCRIPTION", style="Kicker.TLabel").pack(anchor="w")
        self.recipe_label = ttk.Label(content, textvariable=self.recipe_text, wraplength=640)
        self.recipe_label.pack(fill="x", pady=(4, 8))
        output = ttk.Frame(content)
        output.pack(fill="x", pady=(0, 6))
        self.led_canvas = tk.Canvas(output, width=150, height=52, bg=BG, highlightthickness=0)
        self.led_canvas.pack(side="left")
        self.cells = [[self.led_canvas.create_rectangle(2+x*18, 2+y*12, 16+x*18, 11+y*12,
                       fill=IDLE_CELL, outline="") for x in range(8)] for y in range(len(INGREDIENTS))]
        ttk.Label(output, textvariable=self.output_text, wraplength=300, foreground=MUTED).pack(side="left", padx=10)
        self.copy_button = ttk.Button(output, text="Copy recipe", command=self.copy_recipe, state="disabled")
        self.copy_button.pack(side="right")
        self.status_label = ttk.Label(shell, textvariable=self.status, foreground=MUTED, wraplength=1000)
        self.status_label.grid(row=2, sticky="ew", pady=(10, 5))
        shell.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(300, event.width - 48)))
        ttk.Label(shell, text="The signal is part of the performance. It maps skin-conductance changes to a brine recipe.",
                  foreground=MUTED, font=("Segoe UI", 9)).grid(row=3, sticky="w")
        content.bind("<Configure>", lambda event: self._wrap(event.width))
        self._controls()

    def toggle_patient_view(self, event=None):
        if self.patient_window:
            self.close_patient_view()
        elif not self.cast_window:
            self._update_patient_view()
            self.patient_window = PatientView(self.root, self.patient_timeline, self.close_patient_view, self.stop,
                                              self.new_session_shortcut)
            self.note("Display / patient view opened")
        return "break"

    def new_session_shortcut(self, event=None):
        self.start()
        return "break"

    def _update_patient_view(self):
        stage = self.session.stage
        title = ""
        if self.session.recipe and (stage == Stage.COMPLETE or
                                    (stage == Stage.FAREWELL and self.session.playback_has_started)):
            title = self.session.recipe.name
        activity = ""
        if self.active_pump and stage in (Stage.REVEAL, Stage.DISPENSE):
            activity = f"PUMPING {self.pump_ingredients[self.active_pump - 1].name.upper()}"
        score = None
        if stage in REST_STAGES:
            index = REST_STAGES.index(stage)
            if index < len(self.session.results):
                score = self.session.results[index].score
        heading, blend = self._patient_blend()
        changed = self.patient_timeline.advance(stage, title, activity, score=score,
                                                blend=blend, blend_heading=heading)
        if changed and self.patient_window:
            self.patient_window.render(self.patient_timeline)

    def _patient_blend(self):
        recipe = self.session.recipe
        if not recipe or not self.durations or self.session.stage not in (
                Stage.REVEAL, Stage.DISPENSE, Stage.FAREWELL, Stage.COMPLETE):
            return "", ()
        rates = self.config.get("pump_rates", ())
        rows = []
        for pump, item in enumerate(self.pump_ingredients):
            index = INGREDIENTS.index(item)
            seconds = self.durations[pump] / 1000
            if self.session_mode == MOTORS:
                ml = seconds * rates[index]
                annotation = f"{ml:.1f} ml"
            else:
                ml = recipe.amounts[index]
                annotation = f"{ml:.1f} ml"
                if self.session_mode == WATER:
                    annotation += f" target · {seconds:g} s"
            rows.append((item.name, ml, annotation))
        heading = {MOTORS: "ESTIMATED BRINE BY PUMP", WATER: "BRINE TARGETS · PUMP TIME"}.get(
            self.session_mode, "BRINE TARGETS")
        return heading, tuple(rows)

    def close_patient_view(self):
        if self.patient_window:
            self.patient_window.close()
            self.patient_window = None
            self.root.lift()
            self.root.focus_force()
            self.note("Display / returned to operator view")

    def open_debug_log(self):
        try:
            os.startfile(self.debug.path)
        except OSError:
            self.status.set(f"Debug log is unavailable at {self.debug.path}")

    def _callback_error(self, exc_type, exc, tb):
        frames = " > ".join(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}"
                            for frame in traceback.extract_tb(tb))
        self.note(f"UI / {exc_type.__name__} at {frames}")
        self.stop("The app encountered an error. Open the debug log for details.")

    def toggle_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))
        return "break"

    def escape(self, event=None):
        if (self.session.active or self.input_opening or self.voice.busy or self.delivery.busy
                or self.hardware_window is not None):
            self.stop()
        else:
            self.root.attributes("-fullscreen", False)
        return "break"

    def remember_connections(self):
        values = {"feather_ip": self.feather_host.get().strip(),
                  "gsr_usb": self.port.get().strip(), "pump_usb": self.pump_port.get().strip()}
        if values == self.saved_connections or not any(values.values()) and not self.saved_connections:
            return
        try:
            save_connections(self.connection_path, values)
        except OSError:
            self.note("Could not remember the connection settings.")
        else:
            self.saved_connections = values

    def _wrap(self, width):
        self.script_label.configure(wraplength=max(300, width - 28))
        self.recipe_label.configure(wraplength=max(300, width))

    def _controls(self):
        hardware = self.hardware_window
        monitoring = bool(hardware and (hardware.monitoring or hardware.pump_setup_open))
        locked = bool(self.input_opening or self.session.active or self.voice.busy or self.delivery.busy
                      or self.cast_window is not None)
        for widget in (self.source_box, self.mode_box):
            widget.configure(state="disabled" if locked else "readonly")
        source = self.source.get()
        if source != self.port_source:
            self.port_source = source
            self.port_box.configure(textvariable=self.feather_host if source == "Feather Wi-Fi" else self.port,
                                    values=() if source == "Feather Wi-Fi" else self.ports)
            labels = {"Feather Wi-Fi": "Feather IP address", "Feather USB": "Feather USB port",
                      "Arduino USB": "Sensor USB port"}
            self.input_label.configure(text=labels.get(source, "No device needed"))
        edit_input = not locked and source != "Simulated" and not (monitoring and source == "Feather Wi-Fi")
        self.port_box.configure(state="normal" if edit_input else "disabled")
        for widget in (self.whisper_box, self.effects_box, self.test_button, self.cast_button):
            widget.configure(state="disabled" if locked else "normal")
        self.script_box.configure(state="normal" if not locked and self.config.get("openai_key") else "disabled")
        self.start_button.configure(state="disabled" if locked or monitoring else "normal")
        if self.hardware_window:
            self.hardware_window.update()

    def note(self, message):
        line = f"{time.strftime('%H:%M:%S')}  {message}"
        if self.events and self.events[-1].split("  ", 1)[1] == message:
            return
        self.events.append(line)
        self.debug.write(message)
        if self.hardware_window:
            self.hardware_window.append(line)

    def open_hardware(self):
        if self.hardware_window is None:
            self.hardware_window = HardwareWindow(self)
        self.hardware_window.window.lift()

    def refresh_ports(self):
        self.ports = list_ports()
        if self.source.get() != "Feather Wi-Fi":
            self.port_box.configure(values=self.ports)
        if len(self.ports) == 1 and not self.pump_port.get():
            self.pump_port.set(self.ports[0])
        self.status.set("USB ports refreshed." if self.ports else "No USB serial ports found.")
        self._controls()

    @property
    def pump_ingredients(self):
        return tuple(INGREDIENT_BY_KEY[key] for key in self.pump_order)

    def apply_pump_order(self, order):
        if order == self.pump_order:
            return
        save_pump_order(ROOT / "output" / "pump_channels.json", order)
        self.pump_order = order
        self.config["pump_rates"] = ()
        self.config["real_pumps"] = False
        if self.mode.get() == MOTORS:
            self.mode.set(WATER)
        self.mode_box.configure(values=(WATER,))
        self.status.set("Pump assignments saved. Calibrate the new assignment before dispensing.")
        if self.hardware_window:
            self.hardware_window.refresh_pump_labels()

    def apply_pump_calibration(self, rates):
        save_pump_calibration(ROOT / "output" / "pump_calibration.json", rates, self.pump_order)
        self.config["pump_rates"] = rates
        self.config["real_pumps"] = True
        self.mode_box.configure(values=(WATER, MOTORS))
        self.status.set("Calibration saved. Select Calibrated pumps when ready to dispense.")

    def start(self):
        if self.input_opening or self.session.active or self.voice.busy or self.delivery.busy or self.cast_window:
            return
        if self.hardware_window and (self.hardware_window.monitoring or self.hardware_window.pump_setup_open):
            return
        self.voice.stop()
        self.remember_connections()
        try:
            mode = self.mode.get()
            if mode not in (SCREEN, LEDS, *MOTOR_MODES) or (mode == MOTORS and not self.config.get("real_pumps")):
                raise ValueError("Choose Uno water rehearsal or calibrated pumps.")
            if mode != SCREEN and not self.pump_port.get().strip():
                raise ValueError("Choose the Uno USB port in the hardware console.")
            self.session_water_ms = tuple(water_test_ms(value.get()) for value in self.water_times[:len(INGREDIENTS)]) if mode == WATER else ()
            source = self.source.get()
            if source == "Feather Wi-Fi":
                self.input_opening = InputOpening(WirelessInput, self.feather_host.get(), maximum=self.config["maximum"])
            elif source in USB_SENSOR_SOURCES:
                if mode != SCREEN and self.port.get().strip().upper() == self.pump_port.get().strip().upper():
                    raise ValueError("The USB sensor and pump controller need separate ports.")
                self.input_opening = InputOpening(SerialInput, self.port.get(), self.config["baud"], self.config["maximum"])
        except ValueError as exc:
            self.status.set(str(exc))
            return
        if self.input_opening:
            self.input_started = time.monotonic()
            self.input_mode = mode
            self.status.set(f"Connecting to {source}…")
            self._controls()
        else:
            self._begin_session(mode)

    def _poll_input_opening(self, now):
        if self.input_opening:
            result = self.input_opening.poll()
            if result is not None:
                self.input_opening = None
                self.serial, error = result
                self.note(f"Signal / connection {'failed' if error else 'opened'} after {now - self.input_started:.2f} s")
                if error:
                    self.status.set(error)
                else:
                    self._begin_session(self.input_mode)

    def _begin_session(self, mode):
        self.started, self.last_reading = time.monotonic(), None
        self.history.clear()
        self.reading_text.set("RAW —    BASELINE —    CHANGE —")
        self.durations = []
        self.waiting_tune_started = False
        self.record_path = new_record_path(ROOT / "output" / "sessions")
        self.record_error = ""
        self.session_source, self.session_mode = self.source.get(), mode
        self.session_voices = list(self.round_voices)
        self.session_scripts = []
        self.generated_lines = None
        self.accept_script = False
        self.note(f"Session / {self.session_source} → {mode}")
        key = self.config.get("openai_key")
        if self.fresh_scripts.get() and key:
            model = self.config.get("openai_model", DEFAULT_MODEL)
            self.intro_request = WritingRequest(generate_intro, key, model)
            self.intro_deadline = time.monotonic() + 4
            self.note(f"OpenAI / professor intro requested ({model})")
            self.previous_tactics = choose_tactics(self.previous_tactics)
            self.script_request = WritingRequest(generate_lines, key, model, self.previous_tactics)
            self.note(f"OpenAI / three whispers requested ({model})")
            self.accept_script = True
        else:
            reason = "Fresh script is off" if key else "no OpenAI key configured"
            self.note(f"OpenAI / house script selected ({reason})")
        self.patient_timeline = PatientTimeline()
        self.session.start(self.started, spoken=not self.silent.get())
        self.copy_button.configure(state="disabled")
        self.recipe_text.set("The department will issue your prescription after the third stimulus.")
        self._set_row(None)
        self.output_text.set(f"{mode} · waiting for the recipe reveal")
        self._stage_changed()

    def _stage_changed(self, *, request_name=True):
        self._update_patient_view()
        self.stage_text.set(self.session.stage.value)
        self.note(f"Session / {self.session.stage.value}")
        key = self.config.get("openai_key")
        if self.session.stage == Stage.REVEAL and request_name:
            self._close_sensor()
            if key:
                amounts = self.session.recipe.amounts
                lead = max(range(len(amounts)), key=amounts.__getitem__)
                pitch = (self.session_scripts[lead]["text"] if lead < len(self.session_scripts)
                         else INGREDIENTS[lead].pitch)
                model = self.config.get("openai_model", DEFAULT_MODEL)
                self.name_request = WritingRequest(generate_name, key, model, amounts, pitch, tuple(self.recent_names))
                self.name_deadline = time.monotonic() + 4
                self.note(f"OpenAI / prescription title requested ({model})")
                self.line_text.set("The department is assessing your responses.")
                self.status.set("Preparing your martini name…")
                self._show_results()
                self._save()
                return
            self._set_prescription_name()
        line = self.session.line()
        index = self.session.round_index
        if index == 0 and self.accept_script:
            self.accept_script = False
            try:
                self.generated_lines, outcome = self.script_request.result.get_nowait()
            except queue.Empty:
                outcome = "still pending at round one"
            fallback = "" if self.generated_lines else " · using house whispers"
            self.note(f"OpenAI / three whispers {outcome}{fallback}")
        if index is not None:
            approach = "house script"
            if self.generated_lines:
                line = self.generated_lines[INGREDIENTS[index].key]
                approach = self.previous_tactics[index]
            self.session_scripts.append({"approach": approach, "text": line})
        self.line_text.set(line)
        self._show_results()
        if self.session.recipe:
            self.recipe_text.set(self.session.recipe.display())
            self.copy_button.configure(state="normal")
            self._close_sensor()
        self._save()
        if self.session.stage == Stage.REVEAL and self.session_mode in MOTOR_MODES:
            if self.session.spoken:
                self.line_text.set("Connecting to the Uno for your prescription…")
            self._start_delivery(on_cue=self.session.spoken)
        elif self.session.stage == Stage.DISPENSE:
            self.line_text.set("Preparing your prescription. The pumps run one at a time.")
            if self.session_mode not in MOTOR_MODES:
                self._start_delivery()
            if self.session.stage == Stage.DISPENSE and self.session.spoken:
                self.waiting_tune_started = self.voice.play_loop(ASSETS / WAITING_TUNE)
                if self.waiting_tune_started:
                    self.note("Audio / prescription waiting tune started")
        elif self.session.stage == Stage.COMPLETE:
            self.status.set("Appointment complete. Prescription saved locally." + (" " + self.record_error if self.record_error else ""))
        elif self.session.stage == Stage.WELCOME and self.intro_request:
            self.status.set("Preparing the professor’s introduction…")
        elif self.session.voice_pending:
            self._speak(line)
        elif self.silent.get():
            self.status.set("Silent rehearsal · move the slider during each round." if self.session_source == "Simulated"
                            else "Silent rehearsal · using the selected sensor.")
        else:
            self.status.set("A quiet pause. Keep your fingers still.")
        self._controls()

    def _poll_intro(self, now):
        if not self.intro_request:
            return
        try:
            intro, outcome = self.intro_request.result.get_nowait()
        except queue.Empty:
            if now < self.intro_deadline:
                return
            intro, outcome = None, "passed the 4 s show deadline"
        self.intro_request = None
        fallback = "" if intro else " · using the house introduction"
        self.note(f"OpenAI / professor intro {outcome}{fallback}")
        line = intro or self.session.line()
        self.line_text.set(line)
        if self.session.voice_pending:
            self._speak(line)
        else:
            self.session.ready_at = max(self.session.ready_at, now + 4)
            self.status.set("Silent rehearsal · professor introduction.")

    def _set_prescription_name(self, proposed=None):
        used = {name.casefold() for name in self.recent_names}
        base = proposed if proposed and proposed.casefold() not in used else self.session.recipe.name
        name = base
        batch = 2
        while name.casefold() in used:
            name = f"{base} No. {batch}"
            batch += 1
        self.session.recipe = replace(self.session.recipe, name=name)
        self.recent_names.appendleft(name)
        if proposed and name != proposed:
            self.note("OpenAI / title repeated · using a fresh house title")

    def _speak(self, line):
        index = self.session.round_index
        voice_id = self.professor_voice if index is None else self.session_voices[index]
        cue = VOICE_CUES.get(self.session.stage) if self.effects.get() else None
        filename = SOUND_CUES.get(self.session.stage)
        if self.session.stage == Stage.FAREWELL and not self.waiting_tune_started:
            filename = WAITING_TUNE
        lead_in = ASSETS / filename if filename else None
        if not self.voice.speak(line, voice_id=voice_id, cue=cue, steady=index is None, lead_in=lead_in):
            self.stop("Voice was still busy. Start a fresh session.")
        else:
            self.voice_requested_at = time.monotonic()
            self.status.set("Preparing voice…")

    def _start_delivery(self, *, on_cue=False):
        try:
            enabled = self.config.get("real_pumps", False)
            self.durations = delivery_durations(self.session.recipe, self.session_mode,
                self.config.get("pump_rates", ()), real_enabled=enabled, water_ms=self.session_water_ms,
                pump_order=self.pump_order)
            if self.session_mode == MOTORS:
                rates = self.config["pump_rates"]
                if any(abs(self.durations[self.pump_order.index(item.key)] * rate / 1000 - ml) > .05
                       for item, rate, ml in zip(INGREDIENTS, rates, self.session.recipe.amounts)):
                    self.note("Delivery / minimum pulse adjustment applied; estimates saved with recipe")
            self._save()
            if not self.delivery.start_delivery(self.pump_port.get().strip(), self.durations, self.session_mode,
                                                real_enabled=enabled, on_cue=on_cue):
                raise ValueError("The previous delivery is still stopping. Start a fresh session.")
            self.status.set("Connecting to the Uno…" if on_cue else "Starting the selected output sequence…")
        except ValueError as exc:
            self.stop(str(exc))

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
                        durations=self.durations, voices=self.session_voices, scripts=self.session_scripts,
                        pump_rates=self.config.get("pump_rates", ()) if self.session_mode == MOTORS else (),
                        pump_order=self.pump_order)
        except OSError:
            self.record_error = "Could not save the local results file; results remain visible in the window."

    def test_voice(self):
        if not self.session.active and not self.voice.busy:
            self.voice.speak(TEST_LINE, voice_id=self.professor_voice, steady=True,
                             lead_in=ASSETS / SOUND_CUES[Stage.WELCOME])
            self.voice_requested_at = time.monotonic()
            self.status.set("Testing the professor and jingle through Windows default audio output…")
            self._controls()

    def edit_cast(self):
        if self.session.active or self.voice.busy or self.cast_window:
            return
        window = self.cast_window = tk.Toplevel(self.root)
        window.title("Dirty Minds · diagnostic cast")
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
                    item = INGREDIENTS[index]
                    excerpt = ". ".join(item.pitch.split(". ")[:2]).rstrip(".") + "."
                    if self.voice.speak(excerpt, voice_id=ident, cue=VOICE_CUES[ROUND_STAGES[index]] if self.effects.get() else None):
                        self.voice_requested_at = time.monotonic()
            ttk.Button(frame, text="Listen", command=audition).grid(row=i+1, column=2, padx=(10, 0))
        ttk.Label(frame, text="The professor handles the clinic announcements. Audition each voice with Whisper delivery on.\nSave your choices with the VOICE_ settings in .env.",
                  wraplength=610, foreground=MUTED).grid(row=4, column=0, columnspan=3, sticky="w", pady=12)
        def finish():
            ids = [self.voice_choices.get(var.get(), var.get().strip()) for var in variables]
            if all(ids):
                self.round_voices = ids
            self.voice.stop()
            window.grab_release()
            window.destroy()
            self.cast_window = None
            self._controls()
        ttk.Button(frame, text="Use this cast", command=finish).grid(row=5, column=0, columnspan=3, sticky="e")
        window.protocol("WM_DELETE_WINDOW", finish)
        window.bind("<Escape>", lambda event: self.voice.stop())
        self._controls()

    def set_voice_style(self):
        self.voice.backend.whisper = self.whisper.get()

    def _close_sensor(self):
        if self.serial:
            self.serial.close()
            self.serial = None

    def stop(self, reason="Appointment stopped. Begin again for a fresh baseline."):
        if self.input_opening:
            self.input_opening.cancel()
            self.input_opening = None
            self.note("Signal / connection cancelled")
        self.voice_requested_at = None
        self.voice.stop()
        self.delivery.stop()
        self.name_request = self.intro_request = None
        self.accept_script = False
        if self.hardware_window:
            if self.hardware_window.calibration:
                self.hardware_window.calibration.stop()
            self.hardware_window.armed.set(False)
            if self.hardware_window.monitoring:
                self.hardware_window.stop_feather()
        if not self.session.active:
            self.status.set("Stop requested. Bench tests and audio are cancelled.")
            self._controls()
            return
        self._close_sensor()
        self.session.stop()
        self._update_patient_view()
        self._save()
        self.stage_text.set(Stage.STOPPED.value)
        self._set_row(None)
        self.output_text.set("Stopped · no automatic delivery retry")
        self.status.set(reason)
        self._controls()

    def _set_row(self, pump):
        self.active_pump = pump
        for i, row in enumerate(self.cells, 1):
            color = ROW_COLORS[INGREDIENTS.index(self.pump_ingredients[i - 1])] if pump == i else IDLE_CELL
            for cell in row:
                self.led_canvas.itemconfigure(cell, fill=color)
        self._update_patient_view()

    def _delivery_events(self, now):
        while True:
            try:
                kind, message = self.delivery.events.get_nowait()
            except queue.Empty:
                break
            at_reveal = self.session.stage == Stage.REVEAL and self.session_mode in MOTOR_MODES
            delivering = at_reveal or self.session.stage == Stage.DISPENSE
            prefix = "Delivery" if delivering else "Uno"
            self.note(f"{prefix} / {message}")
            if self.hardware_window:
                self.hardware_window.uno_status.set(message)
                if self.hardware_window.calibration:
                    self.hardware_window.calibration.handle_event(kind, message)
            if not delivering:
                continue
            if kind in ("error", "cancelled"):
                self.stop(message)
            elif kind == "ready" and at_reveal and self.session.voice_pending:
                line = self.session.line()
                self.line_text.set(line)
                self._speak(line)
            elif kind == "done":
                self._set_row(None)
                self.output_text.set({MOTORS: "Brine delivery complete.", WATER: "Water rehearsal complete."}
                                     .get(self.session_mode, "Screen or light rehearsal complete"))
                if self.session.finish_delivery(now):
                    self._stage_changed()
                else:
                    self._save()
            elif kind == "reply":
                match = re.match(r"START pump=([1-3])\b", message)
                if match:
                    pump = int(match[1])
                    self._set_row(pump)
                    self.output_text.set(f"{pump} · {self.pump_ingredients[pump - 1].name}\n{self.session_mode}")
                elif message.startswith("PUMP_DONE "):
                    self._set_row(None)
            else:
                self.status.set(message)

    def tick(self):
        now = time.monotonic()
        gap = now - self.last_tick
        self.last_tick = now
        if gap >= .5:
            self.note(f"UI / refresh delayed {gap:.2f} s")
        self._poll_input_opening(now)
        while True:
            try:
                generation, kind, message = self.voice.events.get_nowait()
            except queue.Empty:
                break
            if generation != self.voice.generation:
                continue
            if kind in ("error", "playing") and self.voice_requested_at is not None:
                outcome = "failed" if kind == "error" else "playback started"
                self.note(f"Voice / {outcome} after {max(0, now - self.voice_requested_at):.2f} s")
                self.voice_requested_at = None
            if kind == "error":
                if self.session.stage == Stage.FAREWELL:
                    self.voice.stop()
                    self.session.playback_started()
                    self.session.voice_finished(now)
                    self.status.set("Prescription audio failed. The title is on screen. " + message)
                elif self.session.active:
                    self.stop(message + " Check Three voices, or rehearse silently.")
                else:
                    self.status.set(message)
            elif kind == "playing":
                self.session.playback_started()
                if self.session.stage == Stage.REVEAL and self.session_mode in MOTOR_MODES:
                    self.delivery.cue_motors()
                self._show_results()
            elif kind == "done":
                self.session.voice_finished(now)
                self.status.set("A quiet moment to sense the response…" if self.session.collecting else message)
            else:
                self.status.set(message)
        if (self.voice_requested_at is not None and now - self.voice_requested_at >= 8
                and self.status.get() == "Preparing voice…"):
            self.status.set("Still waiting for voice audio. Open the debug log for timing.")
        self._delivery_events(now)
        if self.hardware_window:
            self.hardware_window.poll(now)
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
                if self.serial and not self.history:
                    self.note("Signal / receiving valid sensor readings")
                self.session.sample(raw)
                self.history.append(self.session.smoothed)
                if self.session.baseline is not None:
                    self.patient_timeline.add_sample(self.session.signal)
                elif self.session.calibration:
                    change = abs(self.session.smoothed - self.session.calibration[0]) / self.session.span
                    self.patient_timeline.add_sample(min(1.0, change))
                baseline = "—" if self.session.baseline is None else f"{self.session.baseline:.0f}"
                self.reading_text.set(f"RAW {raw:.0f}    BASELINE {baseline}    CHANGE {self.session.signal:.0%}")
            if self.serial and ((self.last_reading is None and now-self.started > 6) or (self.last_reading is not None and now-self.last_reading > 3)):
                self.stop("No valid GSR readings. Check the sensor connection, address and network.")
        try:
            self._poll_intro(now)
            if self.name_request:
                try:
                    name, outcome = self.name_request.result.get_nowait()
                except queue.Empty:
                    name, outcome = None, "passed the 4 s show deadline"
                    waiting = now < self.name_deadline
                else:
                    waiting = False
                if not waiting:
                    self.name_request = None
                    fallback = "" if name else " · using a house title"
                    self.note(f"OpenAI / prescription title {outcome}{fallback}")
                    self._set_prescription_name(name)
                    if self.session.ready_at is not None:
                        self.session.ready_at = max(self.session.ready_at, now + 2)
                    self._stage_changed(request_name=False)
            elif not self.intro_request and self.session.tick(now, self.voice.busy):
                self._stage_changed()
        except ValueError as exc:
            self.stop(str(exc))
        self.progress_bar["value"] = self.session.progress(now)
        self._update_patient_view()
        if not self.patient_window:
            self._draw()
        self._controls()
        self.after_id = self.root.after(100, self.tick)

    def _draw(self):
        width, height = max(2, self.canvas.winfo_width()), self.canvas.winfo_height()
        state = width, height, self.last_reading, self.session.baseline
        if state == self.graph_state:
            return
        self.graph_state = state
        self.canvas.delete("all")
        for fraction in (.25, .5, .75):
            self.canvas.create_line(0, height*fraction, width, height*fraction, fill=IDLE_CELL)
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
        self.close_patient_view()
        self.remember_connections()
        if self.hardware_window:
            self.hardware_window.close()
        if self.session.active or self.input_opening:
            self.stop("Closing")
        self.delivery.close()
        self.voice.close()
        self._close_sensor()
        self.note("App / closed")
        self.debug.close()
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
