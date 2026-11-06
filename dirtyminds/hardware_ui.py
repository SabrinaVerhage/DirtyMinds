"""Operator console for independent sensor and pump checks."""
import time
import tkinter as tk
from tkinter import ttk

from .calibration_ui import CalibrationWindow
from .core import INGREDIENTS
from .delivery import WATER, water_test_ms
from .sensors import InputOpening, WirelessInput, list_ports

class HardwareWindow:
    def __init__(self, app):
        self.app = app
        self.sensor = self.opening = self.calibration = self.assignment_window = None
        self.latest_at = None
        self.count = 0
        self.armed = tk.BooleanVar(master=app.root)
        self.feather_status = tk.StringVar(master=app.root, value="Monitor off")
        self.uno_status = tk.StringVar(master=app.root, value="Idle")
        self.window = window = tk.Toplevel(app.root)
        window.title("Dirty Minds / Hardware console")
        window.geometry("740x680")
        window.minsize(680, 640)
        window.transient(app.root)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda event: app.stop())
        window.bind("<F10>", app.toggle_patient_view)
        shell = ttk.Frame(window, padding=20)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Hardware console", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="Bench checks and live session events", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        devices = ttk.Frame(shell)
        devices.pack(fill="x")
        devices.columnconfigure((0, 1), weight=1, uniform="device")
        feather = ttk.Labelframe(devices, text="01   FEATHER  /  GSR", padding=12)
        feather.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(feather, text="Feather IP address").pack(anchor="w")
        self.host = ttk.Entry(feather, textvariable=app.feather_host)
        self.host.pack(fill="x", pady=(4, 8))
        self.monitor_button = ttk.Button(feather, text="Start monitor", command=self.toggle_feather)
        self.monitor_button.pack(anchor="w")
        ttk.Label(feather, textvariable=self.feather_status, wraplength=275).pack(anchor="w", pady=(8, 0))

        uno = ttk.Labelframe(devices, text="02   UNO  /  PUMPS", padding=12)
        uno.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(uno, text="Uno USB port").pack(anchor="w")
        self.port = ttk.Combobox(uno, textvariable=app.pump_port, values=list_ports())
        self.port.pack(fill="x", pady=(4, 8))
        buttons = ttk.Frame(uno)
        buttons.pack(fill="x")
        self.check_button = ttk.Button(buttons, text="Check Uno", command=self.check_uno)
        self.check_button.pack(side="left")
        self.refresh_button = ttk.Button(buttons, text="Refresh ports", command=self.refresh)
        self.refresh_button.pack(side="left", padx=5)
        setup = ttk.Frame(uno)
        setup.pack(fill="x", pady=(6, 0))
        self.calibrate_button = ttk.Button(setup, text="Calibrate pumps…", command=self.open_calibration)
        self.calibrate_button.pack(side="left")
        self.assign_button = ttk.Button(setup, text="Pump assignments…", command=self.open_assignments)
        self.assign_button.pack(side="left", padx=(5, 0))
        self.arm_button = ttk.Checkbutton(uno, text="Enable individual water tests", variable=self.armed,
                                          command=self.update)
        self.arm_button.pack(anchor="w", pady=(7, 0))
        self.pulses = []
        self.pump_labels = []
        self.durations = []
        channels = ttk.Frame(uno)
        channels.pack(fill="x", pady=(4, 0))
        channels.columnconfigure(0, weight=1)
        ttk.Label(channels, text="Pump", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(channels, text="Seconds", style="Muted.TLabel").grid(row=0, column=1, padx=6)
        labels = [item.name for item in app.pump_ingredients] + ["Spare · bench only"]
        for pump, (name, duration) in enumerate(zip(labels, app.water_times), 1):
            label = ttk.Label(channels, text=f"{pump}  {name}")
            label.grid(row=pump, column=0, sticky="w")
            self.pump_labels.append(label)
            entry = ttk.Entry(channels, textvariable=duration, width=7)
            entry.grid(row=pump, column=1, padx=6)
            self.durations.append(entry)
            button = ttk.Button(channels, text="Test", width=7,
                                command=lambda pump=pump: self.pulse(pump))
            button.grid(row=pump, column=2, sticky="e")
            self.pulses.append(button)
        ttk.Label(uno, textvariable=self.uno_status, wraplength=275).pack(anchor="w", pady=(8, 0))
        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(12, 4))
        ttk.Label(controls, text="EVENT LOG", style="Kicker.TLabel").pack(side="left")
        ttk.Button(controls, text="Open debug log", command=app.open_debug_log).pack(side="left", padx=12)
        ttk.Button(controls, text="Stop all / Esc", style="Stop.TButton", command=app.stop).pack(side="right")
        log_area = ttk.Frame(shell)
        log_area.pack(fill="both", expand=True)
        self.log = tk.Text(log_area, height=8, wrap="word", state="disabled", relief="flat", padx=8, pady=8,
                           bg="#141c18", fg="#e5ebe0", font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_area, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)
        for line in app.events:
            self.append(line)
        self.update()

    def append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > self.app.events.maxlen + 1:
            self.log.delete("1.0", "2.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh(self):
        self.app.refresh_ports()
        self.port.configure(values=self.app.ports)

    @property
    def monitoring(self):
        return self.sensor is not None or self.opening is not None

    def toggle_feather(self):
        if self.monitoring:
            self.stop_feather()
            return
        if self.app.session.active or self.app.input_opening:
            return
        self.app.remember_connections()
        host = self.app.feather_host.get().strip()
        self.app.note(f"Feather / opening monitor at {host or '(no address)'}")
        self.connect_started = time.monotonic()
        self.opening = InputOpening(WirelessInput, host, maximum=self.app.config["maximum"])
        self.feather_status.set("Connecting…")
        self.app._controls()

    def stop_feather(self, status="Monitor off"):
        if self.monitoring:
            if self.opening:
                self.opening.cancel()
                self.opening = None
            if self.sensor:
                self.sensor.close()
                self.sensor = None
            self.app.note(f"Feather / {status}")
        self.feather_status.set(status)
        self.app._controls()

    def poll(self, now):
        if self.opening:
            result = self.opening.poll()
            if result is not None:
                self.opening = None
                self.sensor, error = result
                elapsed = now - self.connect_started
                self.app.note(f"Feather / monitor {'failed' if error else 'connected'} after {elapsed:.2f} s")
                self.feather_status.set(error or "Connected · waiting for readings")
                self.opened_at = now
                self.count, self.latest_at = 0, None
        if self.sensor:
            readings = self.sensor.poll()
            if readings:
                if not self.count:
                    self.app.note("Feather / receiving valid GSR samples")
                self.count += len(readings)
                self.latest_at, raw = readings[-1]
                self.feather_status.set(f"Live · raw {raw:.0f} · {self.count:,} samples")
            if self.sensor.error:
                self.stop_feather(self.sensor.error)
            elif self.latest_at is None and now - self.opened_at > 6:
                self.stop_feather("No valid samples in six seconds.")
            elif self.latest_at is not None and now - self.latest_at > 3:
                self.stop_feather("Feather stream stalled.")
        self.update()

    @property
    def pump_setup_open(self):
        return self.calibration is not None or self.assignment_window is not None

    def refresh_pump_labels(self):
        for pump, item in enumerate(self.app.pump_ingredients, 1):
            self.pump_labels[pump - 1].configure(text=f"{pump}  {item.name}")

    def open_assignments(self):
        if self.pump_setup_open or self.app.session.active or self.app.input_opening or self.app.delivery.busy:
            return
        self.armed.set(False)
        window = self.assignment_window = tk.Toplevel(self.window)
        window.title("Dirty Minds · Pump assignments")
        window.transient(self.window)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        names = {item.name: item.key for item in INGREDIENTS}
        ttk.Label(frame, text="Match each physical Uno channel to its brine.",
                  style="Muted.TLabel").grid(row=0, columnspan=2, sticky="w", pady=(0, 8))
        variables = []
        for pump, item in enumerate(self.app.pump_ingredients, 1):
            choice = tk.StringVar(master=window, value=item.name)
            variables.append(choice)
            ttk.Label(frame, text=f"Pump {pump}").grid(row=pump, column=0, sticky="w", padx=(0, 12))
            ttk.Combobox(frame, textvariable=choice, values=tuple(names), state="readonly",
                         width=18).grid(row=pump, column=1, sticky="ew", pady=3)
        status = tk.StringVar(master=window, value="Changing assignments requires a new calibration.")
        ttk.Label(frame, textvariable=status, wraplength=345).grid(
            row=4, columnspan=2, sticky="w", pady=(8, 10))

        def save():
            try:
                self.app.apply_pump_order(tuple(names[choice.get()] for choice in variables))
            except ValueError as exc:
                status.set(str(exc))
            except OSError:
                status.set("Could not save pump assignments.")
            else:
                self.close_assignments()

        ttk.Button(frame, text="Cancel", command=self.close_assignments).grid(row=5, column=0, sticky="w")
        ttk.Button(frame, text="Save assignments", command=save).grid(row=5, column=1, sticky="e")
        window.protocol("WM_DELETE_WINDOW", self.close_assignments)
        window.bind("<Escape>", lambda event: self.close_assignments())
        window.grab_set()
        window.focus_set()
        self.app._controls()

    def close_assignments(self):
        if self.assignment_window:
            self.assignment_window.grab_release()
            self.assignment_window.destroy()
            self.assignment_window = None
            self.app._controls()

    def open_calibration(self):
        if self.pump_setup_open or self.app.session.active or self.app.input_opening or self.app.delivery.busy:
            return
        if not self.app.pump_port.get().strip():
            self.uno_status.set("Choose the Uno USB port before calibrating.")
            return
        self.armed.set(False)
        self.app.remember_connections()
        self.calibration = CalibrationWindow(self)
        self.app._controls()

    def check_uno(self):
        self._run(self.app.delivery.check_uno, "Status check")

    def pulse(self, pump):
        if not self.armed.get():
            return
        try:
            ms = water_test_ms(self.app.water_times[pump - 1].get())
        except ValueError as exc:
            self.uno_status.set(str(exc))
            return
        durations = [ms if i == pump else 0 for i in range(1, len(self.app.water_times) + 1)]
        self._run(lambda port: self.app.delivery.start_delivery(port, durations, WATER),
                  f"Pump {pump} · {ms / 1000:g}-second water test")

    def _run(self, action, label):
        if self.app.session.active or self.app.input_opening or self.app.delivery.busy or self.pump_setup_open:
            return
        self.app.remember_connections()
        port = self.app.pump_port.get().strip()
        try:
            if not port:
                raise ValueError("Choose the Uno USB port.")
            if action(port):
                self.app.note(f"Uno / {label} on {port}")
                self.uno_status.set(label)
        except ValueError as exc:
            self.app.note(f"Uno / {exc}")
            self.uno_status.set(str(exc))
        self.app._controls()

    def update(self):
        active = self.app.session.active or self.app.input_opening is not None
        busy = self.app.delivery.busy or self.pump_setup_open
        if active:
            self.armed.set(False)
        if self.app.session.active and self.app.session_source in ("Feather Wi-Fi", "Feather USB"):
            self.feather_status.set(self.app.reading_text.get() if self.app.serial else "Session input closed")
        elif not self.sensor and self.feather_status.get().startswith(("RAW", "Session input closed")):
            self.feather_status.set("Monitor off")
        self.host.configure(state="disabled" if active or self.monitoring else "normal")
        self.monitor_button.configure(text="Stop monitor" if self.monitoring else "Start monitor",
                                      state="disabled" if active else "normal")
        for widget in (self.port, self.check_button, self.refresh_button, self.calibrate_button, self.assign_button, *self.durations):
            widget.configure(state="disabled" if active or busy else "normal")
        self.arm_button.configure(state="disabled" if active or busy else "normal")
        for button in self.pulses:
            button.configure(state="normal" if self.armed.get() and not active and not busy else "disabled")

        if self.calibration:
            self.calibration.update()

    def close(self):
        self.close_assignments()
        if self.calibration:
            self.calibration.close()
        if self.app.delivery.busy and not self.app.session.active:
            self.app.delivery.stop()
            self.app.note("Uno / Stop requested on console close")
        self.stop_feather()
        self.app.hardware_window = None
        self.window.destroy()
        self.app._controls()
