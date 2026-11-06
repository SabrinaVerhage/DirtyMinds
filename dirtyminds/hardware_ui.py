"""Operator console for independent sensor and pump checks."""
import time
import tkinter as tk
from tkinter import ttk

from .core import INGREDIENTS
from .delivery import WATER, water_test_ms
from .sensors import WirelessInput, list_ports

class HardwareWindow:
    def __init__(self, app):
        self.app = app
        self.sensor = None
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
        self.arm_button = ttk.Checkbutton(uno, text="Enable individual water tests", variable=self.armed,
                                          command=self.update)
        self.arm_button.pack(anchor="w", pady=(7, 0))
        self.pulses = []
        self.durations = []
        channels = ttk.Frame(uno)
        channels.pack(fill="x", pady=(4, 0))
        channels.columnconfigure(0, weight=1)
        ttk.Label(channels, text="Pump", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(channels, text="Seconds", style="Muted.TLabel").grid(row=0, column=1, padx=6)
        for item, duration in zip(INGREDIENTS, app.water_times):
            ttk.Label(channels, text=f"{item.pump}  {item.name}").grid(row=item.pump, column=0, sticky="w")
            entry = ttk.Entry(channels, textvariable=duration, width=7)
            entry.grid(row=item.pump, column=1, padx=6)
            self.durations.append(entry)
            button = ttk.Button(channels, text="Test", width=7,
                                command=lambda pump=item.pump: self.pulse(pump))
            button.grid(row=item.pump, column=2, sticky="e")
            self.pulses.append(button)
        ttk.Label(uno, textvariable=self.uno_status, wraplength=275).pack(anchor="w", pady=(8, 0))
        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(12, 4))
        ttk.Label(controls, text="EVENT LOG", style="Kicker.TLabel").pack(side="left")
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

    def toggle_feather(self):
        if self.sensor:
            self.stop_feather()
            return
        if self.app.session.active:
            return
        host = self.app.feather_host.get().strip()
        self.app.note(f"Feather / opening monitor at {host or '(no address)'}")
        try:
            self.sensor = WirelessInput(host, maximum=self.app.config["maximum"])
        except ValueError as exc:
            self.feather_status.set(str(exc))
            self.app.note(f"Feather / {exc}")
            return
        self.opened_at = time.monotonic()
        self.count, self.latest_at = 0, None
        self.feather_status.set("Connected · waiting for readings")
        self.app.note("Feather / connected, waiting for data")
        self.app._controls()

    def stop_feather(self, status="Monitor off"):
        if self.sensor:
            self.sensor.close()
            self.sensor = None
            self.app.note(f"Feather / {status}")
        self.feather_status.set(status)
        self.app._controls()

    def poll(self, now):
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
        durations = [ms if item.pump == pump else 0 for item in INGREDIENTS]
        self._run(lambda port: self.app.delivery.start_delivery(port, durations, WATER),
                  f"Pump {pump} · {ms / 1000:g}-second water test")

    def _run(self, action, label):
        if self.app.session.active or self.app.delivery.busy:
            return
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
        active = self.app.session.active
        busy = self.app.delivery.busy
        if active:
            self.armed.set(False)
        if active and self.app.session_source == "Feather Wi-Fi":
            self.feather_status.set(self.app.reading_text.get() if self.app.serial else "Session input closed")
        elif not self.sensor and self.feather_status.get().startswith(("RAW", "Session input closed")):
            self.feather_status.set("Monitor off")
        self.host.configure(state="disabled" if active or self.sensor else "normal")
        self.monitor_button.configure(text="Stop monitor" if self.sensor else "Start monitor",
                                      state="disabled" if active else "normal")
        for widget in (self.port, self.check_button, self.refresh_button, *self.durations):
            widget.configure(state="disabled" if active or busy else "normal")
        self.arm_button.configure(state="disabled" if active or busy else "normal")
        for button in self.pulses:
            button.configure(state="normal" if self.armed.get() and not active and not busy else "disabled")

    def close(self):
        if self.app.delivery.busy and not self.app.session.active:
            self.app.delivery.stop()
            self.app.note("Uno / Stop requested on console close")
        self.stop_feather()
        self.app.hardware_window = None
        self.window.destroy()
        self.app._controls()
