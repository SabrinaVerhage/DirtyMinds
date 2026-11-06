"""Lights-only USB preview, used by the desktop test window.

The worker owns its serial connection. There is deliberately no real-run mode.
"""
import queue
import threading

from .pumps import PumpCancelled, PumpClient, PumpError, validate_durations

TEST_MS = 2000


def preview_durations(pump=None):
    if pump is None:
        return [TEST_MS] * 4
    if type(pump) is not int or not 1 <= pump <= 4:
        raise ValueError("Choose brine 1, 2, 3 or 4.")
    return [TEST_MS if i == pump else 0 for i in range(1, 5)]


def run_lights_preview(port, durations, *, cancelled, report, serial_factory=None):
    validate_durations(durations)
    if not port.strip():
        raise ValueError("Choose the Feather USB port first.")
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    with serial_factory(port, baudrate=115200, timeout=0.05, write_timeout=0.5) as connection:
        client = PumpClient(connection)
        # Never send a preview or motor command to an unidentified GSR board.
        client.hello(cancelled=cancelled)
        client.run(durations, preview=True, report=report, cancelled=cancelled)


class LightsWorker:
    def __init__(self):
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.thread = None

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, port, pump=None):
        return self.start_sequence(port, preview_durations(pump))

    def start_sequence(self, port, durations):
        validate_durations(durations)
        if not port.strip():
            raise ValueError("Choose the Feather USB port first.")
        return self._start_job(port, list(durations))

    def _start_job(self, port, durations):
        if self.busy:
            return False
        # Drop events from a completed test before starting another.
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        self.cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(port, durations), daemon=True)
        self.thread.start()
        return True

    def _run(self, port, durations):
        self.events.put(("status", "Connecting to the Feather… opening USB may reset it."))
        try:
            run_lights_preview(port, durations, cancelled=self.cancelled,
                               report=lambda message: self.events.put(("reply", message)))
            self.events.put(("done", "Test finished. All rows are off."))
        except PumpCancelled:
            self.events.put(("done", "Test cancelled; Stop requested. Each preview row is timed."))
        except ImportError:
            self.events.put(("error", "Run setup.cmd first to enable USB communication."))
        except (PumpError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("error", "USB connection failed. Check the cable/port and close Serial Monitor."))

    def stop(self):
        self.cancelled.set()

    def close(self):
        self.stop()
        if self.thread is not None:
            # A bounded read/write lets the worker send Stop and release the port.
            self.thread.join(timeout=0.8)
