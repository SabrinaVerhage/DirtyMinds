"""Simulated input and a read-only Arduino USB serial input."""
import math
import queue
import random
import threading
import time


def parse_reading(line: bytes, maximum: float = 1023):
    try:
        text = line.decode("ascii").strip()
        if text.startswith("GSR:"):
            text = text[4:].strip()
        value = float(text)
        return value if math.isfinite(value) and 0 <= value <= maximum else None
    except (ValueError, UnicodeDecodeError):
        return None


class Simulator:
    def read(self, now, intensity, responding, maximum=1023):
        base = maximum * 0.42
        change = maximum * 0.30 * intensity if responding else 0
        ripple = math.sin(now * 1.4) * maximum * 0.008
        return min(maximum, max(0, base + change + ripple + random.uniform(-3, 3)))


class SerialInput:
    def __init__(self, port, baud=115200, maximum=1023):
        if not port.strip():
            raise ValueError("Select an Arduino COM port first.")
        try:
            import serial
            self.connection = serial.Serial(port, baudrate=baud, timeout=0.2)
        except ImportError:
            raise ValueError("Install requirements.txt to enable Arduino input.") from None
        except Exception:
            raise ValueError("Cannot open that COM port. Check the cable and close Arduino Serial Monitor.") from None
        self.maximum = maximum
        self.samples = queue.Queue(maxsize=100)
        self.error = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            # Opening the port resets many Arduino boards.
            if self.stop_event.wait(2):
                return
            self.connection.reset_input_buffer()
            pending = bytearray()
            discarding = False
            while not self.stop_event.is_set():
                chunk = self.connection.read_until(b"\n", size=64)
                for byte in chunk:
                    if byte == 10:
                        value = None if discarding else parse_reading(bytes(pending), self.maximum)
                        pending.clear()
                        discarding = False
                        if value is not None:
                            item = (time.monotonic(), value)
                            try:
                                self.samples.put_nowait(item)
                            except queue.Full:
                                try:
                                    self.samples.get_nowait()
                                except queue.Empty:
                                    pass  # UI may have drained it in the meantime.
                                self.samples.put_nowait(item)
                    elif not discarding:
                        pending.append(byte)
                        if len(pending) > 64:
                            pending.clear()
                            discarding = True
        except Exception:
            if not self.stop_event.is_set():
                self.error = "Arduino connection lost. Reconnect it and start a new session."
        finally:
            self.connection.close()

    def poll(self):
        readings = []
        while True:
            try:
                readings.append(self.samples.get_nowait())
            except queue.Empty:
                return readings

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=0.5)


def list_ports():
    try:
        from serial.tools import list_ports as serial_ports
        return [port.device for port in serial_ports.comports()]
    except ImportError:
        return []



class WirelessInput:
    """Read the Feather's newline-delimited TCP stream on the local network."""
    def __init__(self, host, maximum=1023, port=8765):
        import socket
        host = host.strip()
        if not host:
            raise ValueError("Enter the Feather's IP address.")
        self.maximum = maximum
        self.samples = queue.Queue(maxsize=100)
        self.error = None
        self.stop_event = threading.Event()
        try:
            self.connection = socket.create_connection((host, port), timeout=2)
            self.connection.settimeout(.2)
        except OSError:
            raise ValueError("Cannot reach Feather. Check its IP and Wi-Fi network.") from None
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        import socket
        pending = bytearray()
        discarding = False
        try:
            while not self.stop_event.is_set():
                try:
                    data = self.connection.recv(256)
                except socket.timeout:
                    continue
                if not data:
                    raise ConnectionError()
                for byte in data:
                    if byte == 10:
                        value = None if discarding else parse_reading(bytes(pending), self.maximum)
                        pending.clear()
                        discarding = False
                        if value is not None:
                            try:
                                self.samples.put_nowait((time.monotonic(), value))
                            except queue.Full:
                                try:
                                    self.samples.get_nowait()
                                except queue.Empty:
                                    pass
                                self.samples.put_nowait((time.monotonic(), value))
                    elif not discarding:
                        pending.append(byte)
                        if len(pending) > 64:
                            pending.clear()
                            discarding = True
        except OSError:
            if not self.stop_event.is_set():
                self.error = "Feather Wi-Fi connection lost. Start a new session after reconnecting."
        finally:
            self.connection.close()

    poll = SerialInput.poll

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=.5)
