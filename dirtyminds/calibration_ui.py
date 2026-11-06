"""Operator-guided pump calibration using timed pours confirmed by the Uno."""
import math
import tkinter as tk
from tkinter import ttk

from .core import INGREDIENTS
from .delivery import PUMP_CHANNELS, WATER, water_test_ms

PRIME_MS = 2000


def measured_rate(volume, duration_ms):
    try:
        ml = float(volume)
    except (TypeError, ValueError):
        raise ValueError("Enter the measured volume in ml.") from None
    if not math.isfinite(ml) or ml < 1 or not 1000 <= duration_ms <= 10_000:
        raise ValueError("Measure at least 1 ml in a 1–10 second run.")
    return ml / (duration_ms / 1000)


class CalibrationWindow:
    def __init__(self, hardware):
        self.hardware = hardware
        self.app = app = hardware.app
        self.port = app.pump_port.get().strip()
        self.ingredients = app.pump_ingredients
        self.pending = None
        self.completed_ms = [None] * len(INGREDIENTS)
        self.rates = ()
        self.window = window = tk.Toplevel(hardware.window)
        window.title("Dirty Minds · Calibrate pumps")
        window.transient(hardware.window)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda event: self.stop())
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Calibrate pumps", style="Title.TLabel").grid(
            row=0, columnspan=6, sticky="w")
        ttk.Label(frame, text=(
            f"Uno on {self.port}. Place the selected outlet over a cup. Prime until flow is steady, "
            "then empty the cup and start a timed run. Use a graduated cup and enter the collected ml. "
            "Aim for several ml per run. Use the brine and tubing you will serve with."
        ), wraplength=600, justify="left").grid(row=1, columnspan=6, sticky="w", pady=(6, 12))
        self.armed = tk.BooleanVar(master=window)
        self.arm_button = ttk.Checkbutton(frame, text="Enable pump tests", variable=self.armed,
                                          command=self.update)
        self.arm_button.grid(row=2, columnspan=6, sticky="w", pady=(0, 8))
        for column, label in enumerate(("Pump", "Seconds", "", "", "Collected ml", "ml/s")):
            ttk.Label(frame, text=label, style="Kicker.TLabel").grid(row=3, column=column, sticky="w", padx=4)
        self.times, self.volumes, self.rate_labels = [], [], []
        self.time_boxes, self.volume_boxes, self.pump_buttons = [], [], []
        for index, item in enumerate(self.ingredients):
            row = index + 4
            ttk.Label(frame, text=f"{index + 1}  {item.name}").grid(row=row, column=0, sticky="w", padx=4)
            seconds = tk.StringVar(master=window, value="5")
            volume = tk.StringVar(master=window)
            self.times.append(seconds)
            self.volumes.append(volume)
            time_box = ttk.Entry(frame, textvariable=seconds, width=7)
            time_box.grid(row=row, column=1, padx=4, pady=4)
            self.time_boxes.append(time_box)
            for column, label, prime in ((2, "Prime 2 s", True), (3, "Run test", False)):
                button = ttk.Button(frame, text=label, command=lambda i=index, p=prime: self.run(i, prime=p))
                button.grid(row=row, column=column, padx=4)
                self.pump_buttons.append(button)
            volume_box = ttk.Entry(frame, textvariable=volume, width=10)
            volume_box.grid(row=row, column=4, padx=4)
            self.volume_boxes.append(volume_box)
            rate = ttk.Label(frame, text="—", width=10)
            rate.grid(row=row, column=5, padx=4)
            self.rate_labels.append(rate)
            volume.trace_add("write", lambda *_: self.update())
        self.status = tk.StringVar(master=window, value="Enable pump tests when the outlet is ready.")
        ttk.Label(frame, textvariable=self.status, wraplength=600).grid(
            row=7, columnspan=6, sticky="w", pady=(12, 8))
        ttk.Button(frame, text="Stop / Esc", command=self.stop, style="Stop.TButton").grid(
            row=8, columnspan=2, sticky="w")
        self.save_button = ttk.Button(frame, text="Save calibration", command=self.save)
        self.save_button.grid(row=8, column=3, columnspan=2, sticky="e")
        ttk.Button(frame, text="Close", command=self.close).grid(row=8, column=5, sticky="e")
        self.update()
        window.grab_set()
        window.focus_set()

    def update(self):
        locked = self.pending is not None or self.app.delivery.busy
        self.arm_button.configure(state="disabled" if locked else "normal")
        for button in self.pump_buttons:
            button.configure(state="normal" if self.armed.get() and not locked else "disabled")
        rates = []
        for i, duration in enumerate(self.completed_ms):
            self.time_boxes[i].configure(state="disabled" if locked else "normal")
            self.volume_boxes[i].configure(state="normal" if duration and not locked else "disabled")
            rate = None
            if duration is not None:
                try:
                    rate = measured_rate(self.volumes[i].get(), duration)
                except ValueError:
                    pass
            self.rate_labels[i].configure(text=f"{rate:.3f}" if rate else "—")
            rates.append(rate)
        self.rates = tuple(rates) if all(rate is not None for rate in rates) else ()
        self.save_button.configure(state="normal" if self.rates and not locked else "disabled")

    def run(self, index, *, prime=False):
        if not self.armed.get() or self.pending or self.app.delivery.busy or self.app.session.active:
            return
        try:
            ms = PRIME_MS if prime else water_test_ms(self.times[index].get())
            if ms < 1000:
                raise ValueError("Choose a test duration from 1 to 10 seconds.")
            item = self.ingredients[index]
            durations = [0] * PUMP_CHANNELS
            durations[index] = ms
            if not self.app.delivery.start_delivery(self.port, durations, WATER):
                return
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.pending = index, ms, prime
        if not prime:
            self.completed_ms[index] = None
            self.volumes[index].set("")
        action = "Priming" if prime else "Measuring"
        self.status.set(f"{action} {item.name} for {ms / 1000:g} seconds…")
        self.app.note(f"Calibration / {action.lower()} pump {index + 1} for {ms} ms")
        self.update()

    def handle_event(self, kind, message):
        if not self.pending or kind not in ("done", "error", "cancelled"):
            return
        index, ms, prime = self.pending
        self.pending = None
        if kind != "done":
            self.armed.set(False)
            self.status.set(message)
        elif prime:
            self.status.set("Prime finished. Repeat if needed, then empty the measuring cup.")
        else:
            self.completed_ms[index] = ms
            self.status.set(f"Enter the ml collected from {self.ingredients[index].name} in {ms / 1000:g} seconds.")
        self.update()

    def save(self):
        self.update()
        if not self.rates or self.pending or self.app.delivery.busy:
            return
        try:
            rates_by_key = {item.key: rate for item, rate in zip(self.ingredients, self.rates)}
            self.app.apply_pump_calibration(tuple(rates_by_key[item.key] for item in INGREDIENTS))
        except OSError:
            self.status.set("Could not save calibration. Check the output folder.")
            return
        self.close()

    def stop(self):
        if self.pending:
            self.pending = None
            self.app.delivery.stop()
            self.app.note("Calibration / stop requested")
        self.armed.set(False)
        self.status.set("Pump tests disabled. Enable again when ready.")
        self.update()

    def close(self):
        self.stop()
        self.window.grab_release()
        self.window.destroy()
        self.hardware.calibration = None
        self.app._controls()
