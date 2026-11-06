"""USB client for the separate HUZZAH32 pump firmware (no automatic pouring)."""
import argparse
import math
import time

MAX_PUMP_MS = 180000
MAX_SEQUENCE_MS = 600000


class PumpError(Exception):
    pass


class PumpCancelled(PumpError):
    pass


def check_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise PumpCancelled("Lights test stopped.")


def seconds_to_ms(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValueError("Use a number of seconds.") from None
    if not math.isfinite(seconds) or seconds < 0 or seconds > 180:
        raise ValueError("Duration must be between 0 and 180 seconds.")
    milliseconds = round(seconds * 1000)
    if seconds != 0 and milliseconds < 100:
        raise ValueError("Use at least 0.1 seconds, or 0 to skip a pump.")
    return milliseconds


def validate_durations(durations):
    if len(durations) != 4:
        raise ValueError("Supply four durations, one for each pump.")
    if any(type(ms) is not int or (ms != 0 and not 100 <= ms <= MAX_PUMP_MS) for ms in durations):
        raise ValueError("Each pump needs 100–180000 milliseconds, or 0 to skip it.")
    if not 0 < sum(durations) <= MAX_SEQUENCE_MS:
        raise ValueError("Total run time must be greater than zero and at most 600 seconds.")


class PumpClient:
    def __init__(self, connection, *, clock=time.monotonic):
        self.connection = connection
        self.clock = clock
        self.pending = bytearray()

    def send(self, command):
        self.connection.write((command + "\n").encode("ascii"))

    def read_line(self):
        # Serial reads can time out halfway through a line. Preserve that fragment.
        chunk = self.connection.read_until(b"\n", size=256)
        self.pending.extend(chunk)
        if len(self.pending) > 1024:
            raise PumpError("Unexpected oversized response from the controller.")
        if not self.pending.endswith(b"\n"):
            return ""
        result = self.pending.decode("ascii", errors="replace").strip()
        self.pending.clear()
        return result

    def expect(self, prefix, timeout=3, *, cancelled=None):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            check_cancelled(cancelled)
            line = self.read_line()
            if line.startswith(prefix):
                return line
            if line.startswith(("ERR ", "STOPPED ")):
                raise PumpError(line)
        raise PumpError("Controller did not acknowledge the command.")

    def hello(self, *, cancelled=None):
        deadline, next_probe = self.clock() + 6, 0
        while self.clock() < deadline:
            check_cancelled(cancelled)
            if self.clock() >= next_probe:
                self.send("HELLO")
                next_probe = self.clock() + 0.5
            line = self.read_line()
            if line.startswith("DIRTYMINDS_PUMPS 1 "):
                return line
        raise PumpError("No Dirty Minds pump firmware found. Check COM port, upload, and baud rate.")

    def stop(self):
        # '!' is recognized immediately, even if an earlier line was incomplete.
        self.send("!")

    def run(self, durations, *, preview=False, report=print, cancelled=None):
        validate_durations(durations)
        completed = False
        try:
            check_cancelled(cancelled)
            if not preview:
                self.send("ARM")
                self.expect("OK ARM", cancelled=cancelled)
            check_cancelled(cancelled)
            command = "PREVIEW" if preview else "SEQ"
            self.send(command + " " + " ".join(str(ms) for ms in durations))
            self.expect("OK START", cancelled=cancelled)
            deadline = self.clock() + sum(durations) / 1000 + 8
            next_ping = self.clock()
            while self.clock() < deadline:
                check_cancelled(cancelled)
                if self.clock() >= next_ping:
                    self.send("PING")
                    next_ping = self.clock() + 1
                line = self.read_line()
                if line == "DONE":
                    completed = True
                    report("Finished. All pumps are off.")
                    return
                if line.startswith(("ERR ", "STOPPED ", "DIRTYMINDS_PUMPS ")):
                    raise PumpError("Controller stopped or reset: " + line)
                if line.startswith(("START ", "PUMP_DONE ")):
                    report(line)
            raise PumpError("Timed out waiting for completion.")
        finally:
            if not completed:
                try:
                    self.stop()
                except Exception:
                    pass  # The firmware's heartbeat timeout is the fallback.


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dirty Minds pump bench controls. Ctrl+C stops a run.")
    parser.add_argument("--port", help="Feather COM port, for example COM5")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ports", help="List available USB serial ports")
    commands.add_parser("status")
    commands.add_parser("stop")
    preview = commands.add_parser("preview", help="LED sequence only; motor outputs stay off")
    preview.add_argument("seconds", nargs="*", help="Optional four durations; default: 2 2 2 2")
    sequence = commands.add_parser("sequence", help="Run four pumps sequentially; 0 skips a pump")
    sequence.add_argument("seconds", nargs=4)
    run = commands.add_parser("run", help="Run a single pump for a measured time")
    run.add_argument("pump", type=int, choices=range(1, 5))
    run.add_argument("seconds")
    args = parser.parse_args(argv)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        parser.exit(1, "Run setup.cmd first to install pyserial.\n")
    if args.command == "ports":
        for port in list_ports.comports():
            print(f"{port.device}: {port.description}")
        return
    if not args.port:
        parser.error("--port COMx is required; use 'ports' to list devices")
    durations = None
    try:
        if args.command == "run":
            durations = [0] * 4
            durations[args.pump - 1] = seconds_to_ms(args.seconds)
        elif args.command in ("preview", "sequence"):
            durations = [seconds_to_ms(s) for s in (args.seconds or [2, 2, 2, 2])]
        if durations is not None:
            validate_durations(durations)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        with serial.Serial(args.port, baudrate=115200, timeout=0.05, write_timeout=0.5) as connection:
            client = PumpClient(connection)
            if args.command == "stop":
                # Do not wait for identification before sending an emergency stop.
                client.stop()
                client.expect("OK STOP")
                print("Stop acknowledged. All pumps are off.")
            else:
                client.hello()
                if args.command == "status":
                    client.send("STATUS")
                    print(client.expect("STATUS "))
                else:
                    print("Lights-only preview." if args.command == "preview" else "Running timed pump test. Press Ctrl+C to stop.")
                    client.run(durations, preview=args.command == "preview")
    except KeyboardInterrupt:
        parser.exit(130, "Stopped.\n")
    except (serial.SerialException, OSError, PumpError) as exc:
        parser.exit(1, f"Pump control: {exc}\n")
