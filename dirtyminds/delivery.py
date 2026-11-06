"""Screen rehearsal and timed delivery through the controller protocol."""
import math
import threading

from .core import DEFAULT_PUMP_ORDER, INGREDIENTS
from .lights import LightsWorker, run_lights_preview
from .pumps import PumpCancelled, PumpClient, PumpError, check_cancelled, seconds_to_ms, validate_durations

SCREEN = "Screen rehearsal"
LEDS = "Feather LEDs"
MOTORS = "Calibrated pumps"
WATER = "Uno water rehearsal"
MOTOR_MODES = (WATER, MOTORS)
UNO_CHECK = "Uno status"
PUMP_CHANNELS = 4
MAX_WATER_MS = 10_000
MIN_PUMP_MS = 100


def water_test_ms(value):
    milliseconds = seconds_to_ms(value)
    if not 100 <= milliseconds <= MAX_WATER_MS:
        raise ValueError("Enter a water-test duration between 0.1 and 10 seconds.")
    return milliseconds


def _calibrated_durations(amounts, rates):
    """Give every used pump a legal pulse without increasing the total dose."""
    durations = [0] * len(amounts)
    remaining = [i for i, ml in enumerate(amounts) if ml > 0]
    volume_left = math.fsum(amounts)
    while remaining:
        weight = math.fsum(amounts[i] for i in remaining)
        shares = {i: volume_left * (amounts[i] / weight) for i in remaining}
        short = [i for i in remaining if shares[i] < rates[i] * (MIN_PUMP_MS / 1000) - 1e-12]
        if not short:
            for i, ml in shares.items():
                ms = ml / rates[i] * 1000
                if not math.isfinite(ms):
                    raise ValueError("A pump duration exceeds the controller's range. Check its flow rate.")
                durations[i] = max(MIN_PUMP_MS, math.floor(ms + 1e-8))
            break
        for i in short:
            volume_left -= rates[i] * (MIN_PUMP_MS / 1000)
            durations[i] = MIN_PUMP_MS
        if volume_left < -1e-12:
            raise ValueError("The pump minimum pulses exceed 15 ml. Check the measured flow rates.")
        remaining = [i for i in remaining if i not in short]
    return durations


def delivery_durations(recipe, mode, rates=(), *, real_enabled=False, water_ms=(),
                       pump_order=DEFAULT_PUMP_ORDER):
    if mode not in (SCREEN, LEDS, *MOTOR_MODES):
        raise ValueError("Choose a delivery mode.")
    count = len(INGREDIENTS)
    if mode == MOTORS:
        if not real_enabled:
            raise ValueError("Calibrated pumps are disabled. Use Uno water rehearsal for timed tests.")
        if len(rates) not in (count, PUMP_CHANNELS) or not all(
                math.isfinite(rate) and rate > 0 for rate in rates[:count]):
            raise ValueError("Set three measured PUMP_ML_PER_SECOND rates before running pumps.")
        durations = _calibrated_durations(recipe.amounts, rates)
    elif mode == WATER:
        if len(water_ms) not in (count, PUMP_CHANNELS) or any(
                type(ms) is not int or not 100 <= ms <= MAX_WATER_MS for ms in water_ms[:count]):
            raise ValueError("Enter a water-test duration for each of the three brine pumps.")
        times_by_ingredient = dict(zip(pump_order, water_ms))
        durations = [times_by_ingredient[item.key] if ml else 0
                     for item, ml in zip(INGREDIENTS, recipe.amounts)]
    else:
        durations = [max(MIN_PUMP_MS, round(ml / recipe.brine_ml * 6000)) if ml else 0
                     for ml in recipe.amounts]
    # Preserve the controller protocol. The fourth channel is bench-only.
    by_ingredient = {item.key: ms for item, ms in zip(INGREDIENTS, durations)}
    channels = [by_ingredient[key] for key in pump_order] + [0]
    validate_durations(channels)
    return channels


class DeliveryWorker(LightsWorker):
    def check_uno(self, port):
        if self.busy:
            return False
        if not port.strip():
            raise ValueError("Choose the Uno USB port.")
        self.mode = UNO_CHECK
        return self._start_job(port, None)

    def start_delivery(self, port, durations, mode, *, real_enabled=False, on_cue=False):
        if self.busy:
            return False
        if mode not in (SCREEN, LEDS, *MOTOR_MODES) or (mode == MOTORS and not real_enabled):
            raise ValueError("Calibrated pumps are disabled. Choose Uno water rehearsal or Screen rehearsal.")
        if mode == WATER and any(type(ms) is int and ms > MAX_WATER_MS for ms in durations):
            raise ValueError("Water tests are limited to 10 seconds per pump.")
        self.cue = threading.Event() if mode in MOTOR_MODES and on_cue else None
        self.mode = mode
        self.real_enabled = real_enabled
        return self.start_sequence("screen" if mode == SCREEN else port, durations)

    def cue_motors(self):
        if self.busy and self.cue is not None:
            self.cue.set()

    def _run(self, port, durations):
        report = lambda line: self.events.put(("reply", line))
        try:
            if self.mode == SCREEN:
                for pump, ms in enumerate(durations, 1):
                    if not ms:
                        continue
                    check_cancelled(self.cancelled)
                    report(f"START pump={pump} ms={ms} preview=1")
                    if self.cancelled.wait(ms / 1000):
                        raise PumpCancelled("Stopped")
                    report(f"PUMP_DONE pump={pump}")
                    if self.cancelled.wait(.3):
                        raise PumpCancelled("Stopped")
            elif self.mode == LEDS:
                self.events.put(("status", "Connecting to the Feather for the brine light sequence…"))
                run_lights_preview(port, durations, cancelled=self.cancelled, report=report)
            else:
                if self.mode == MOTORS and not self.real_enabled:
                    raise ValueError("Real pumps are disabled.")
                self.events.put(("status", f"Opening Uno on {port}…"))
                import serial
                with serial.Serial(port, baudrate=115200, timeout=.05, write_timeout=.5) as connection:
                    client = PumpClient(connection)
                    report(client.hello(cancelled=self.cancelled))
                    if self.mode == UNO_CHECK:
                        check_cancelled(self.cancelled)
                        client.send("STATUS")
                        report(client.expect("STATUS ", cancelled=self.cancelled))
                    else:
                        if self.cue is not None:
                            self.events.put(("ready", "Uno ready. Waiting for the reveal cue."))
                            while not self.cue.wait(.05):
                                check_cancelled(self.cancelled)
                        client.run(durations, preview=False, cancelled=self.cancelled, report=report)
            check_cancelled(self.cancelled)
            message = "Uno responded to STATUS." if self.mode == UNO_CHECK else "Brine sequence finished."
            self.events.put(("done", message))
        except PumpCancelled:
            self.events.put(("cancelled", "Delivery cancelled. Stop requested."))
        except ImportError:
            self.events.put(("error", "Run setup.cmd to enable USB communication."))
        except (PumpError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("error", "USB delivery failed. Check the cable/port and close Serial Monitor. No automatic retry."))
