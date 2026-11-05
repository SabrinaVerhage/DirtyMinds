"""Small hardware test window; no GSR/recipe-to-pump mapping yet."""
import queue
import re
import tkinter as tk
from tkinter import ttk

from .lights import LightsWorker
from .sensors import list_ports

COLORS = ("#ff2378", "#ff9600", "#32ff23", "#1482ff")


class LightsTestWindow:
    def __init__(self, parent, *, on_close=lambda: None, worker=None):
        self.worker = worker or LightsWorker()
        self.on_close = on_close
        self.window = tk.Toplevel(parent)
        self.window.title("Dirty Minds · Brine lights test")
        self.window.configure(bg="#17151b")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="Connect only the Feather + NeoPixel Wing over USB.")
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="BRINE LIGHTS TEST", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Lights only · no motor driver needed\nUpload the updated pump_controller sketch and close Serial Monitor.",
                  wraplength=520).pack(anchor="w", pady=(6, 14))
        ports = ttk.Frame(frame)
        ports.pack(fill="x")
        ttk.Label(ports, text="Feather USB port").pack(side="left", padx=(0, 10))
        self.port_box = ttk.Combobox(ports, textvariable=self.port, width=15)
        self.port_box.pack(side="left")
        self.refresh_button = ttk.Button(ports, text="Refresh", command=self.refresh)
        self.refresh_button.pack(side="left", padx=8)
        self.canvas = tk.Canvas(frame, width=500, height=160, bg="#24212a", highlightthickness=0)
        self.canvas.pack(fill="x", pady=14)
        self.cells = []
        for row in range(4):
            self.canvas.create_text(12, 20+row*39, text=f"Brine {row+1}", fill="#f3ece4", anchor="w")
            self.cells.append([self.canvas.create_rectangle(104+col*47, 7+row*39,
                               140+col*47, 32+row*39, fill="#38313e", outline="") for col in range(8)])
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self.test_buttons = []
        for pump in range(1, 5):
            button = ttk.Button(buttons, text=f"Brine {pump}", command=lambda p=pump: self.start(p))
            button.pack(side="left", expand=True, fill="x", padx=3)
            self.test_buttons.append(button)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(10, 12))
        self.all_button = ttk.Button(actions, text="Test all four", command=self.start)
        self.all_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop / Esc", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=self.close).pack(side="right")
        ttk.Label(frame, textvariable=self.status, wraplength=520).pack(anchor="w")
        ttk.Label(frame, text="Each row lights for 2 seconds. The screen follows board replies; check the real Wing too.",
                  wraplength=520, font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
        self.refresh()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.stop())
        self.window.grab_set()
        self.after_id = self.window.after(50, self.poll)

    def refresh(self):
        ports = list_ports()
        self.port_box.configure(values=ports)
        if ports and self.port.get() not in ports:
            self.port.set(ports[0])

    def show_row(self, pump=None):
        for index, cells in enumerate(self.cells, start=1):
            for cell in cells:
                self.canvas.itemconfigure(cell, fill=COLORS[index-1] if pump == index else "#38313e")

    def start(self, pump=None):
        try:
            if self.worker.start(self.port.get(), pump):
                self.show_row()
                self.status.set("Connecting to the Feather…")
        except ValueError as exc:
            self.status.set(str(exc))
        self.controls()

    def stop(self):
        if self.worker.busy:
            self.worker.stop()
            self.status.set("Stopping the lights test…")

    def controls(self):
        busy = self.worker.busy
        for button in (*self.test_buttons, self.all_button, self.refresh_button):
            button.configure(state="disabled" if busy else "normal")
        self.port_box.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")

    def poll(self):
        while True:
            try:
                kind, message = self.worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == "reply":
                match = re.match(r"START pump=([1-4])(?:\s|$)", message)
                if match:
                    self.show_row(int(match[1]))
                    self.status.set(f"Feather reports brine {match[1]} preview active · lights only.")
                elif message.startswith("PUMP_DONE "):
                    self.show_row()
            else:
                self.status.set(message)
                if kind in ("done", "error"):
                    self.show_row()
        self.controls()
        self.after_id = self.window.after(50, self.poll)

    def close(self):
        self.window.after_cancel(self.after_id)
        self.worker.close()
        self.window.grab_release()
        self.window.destroy()
        self.on_close()
