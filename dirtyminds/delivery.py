"""Recipe delivery through the existing controller protocol. LEDs by default."""
import math

from .lights import LightsWorker, run_lights_preview
from .pumps import PumpCancelled, PumpClient, PumpError, check_cancelled, validate_durations

SCREEN = "Screen rehearsal"
LEDS = "Feather LEDs"
MOTORS = "Calibrated pumps"


def delivery_durations(recipe, mode, rates=(), *, real_enabled=False):
    if mode not in (SCREEN, LEDS, MOTORS):
        raise ValueError("Choose a delivery mode.")
    if mode == MOTORS:
        if not real_enabled:
            raise ValueError("Real pumps are disabled. Use Feather LEDs for now.")
        if len(rates) != 4 or not all(math.isfinite(rate) and rate > 0 for rate in rates):
            raise ValueError("Set all four measured PUMP_ML_PER_SECOND rates before running pumps.")
        durations = [round(ml / rate * 1000) for ml, rate in zip(recipe.amounts, rates)]
    else:
        durations = [round(ml / recipe.brine_ml * 6000) for ml in recipe.amounts]
    if any(ml > 0 and ms < 100 for ml, ms in zip(recipe.amounts, durations)):
        raise ValueError("A selected brine needs at least 100 ms. Check the measured pump rates.")
    validate_durations(durations)
    return durations


class DeliveryWorker(LightsWorker):
    def start_delivery(self, port, durations, mode, *, real_enabled=False):
        if self.busy:
            return False
        if mode not in (SCREEN, LEDS, MOTORS) or (mode == MOTORS and not real_enabled):
            raise ValueError("Real pumps are disabled. Choose Feather LEDs or Screen rehearsal.")
        self.mode = mode
        self.real_enabled = real_enabled
        return self.start_sequence("screen" if mode == SCREEN else port, durations)

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
                if not self.real_enabled:
                    raise ValueError("Real pumps are disabled.")
                import serial
                with serial.Serial(port, baudrate=115200, timeout=.05, write_timeout=.5) as connection:
                    client = PumpClient(connection)
                    client.hello(cancelled=self.cancelled)
                    client.run(durations, preview=False, cancelled=self.cancelled, report=report)
            check_cancelled(self.cancelled)
            self.events.put(("done", "Brine sequence finished."))
        except PumpCancelled:
            self.events.put(("cancelled", "Delivery cancelled. Stop requested."))
        except ImportError:
            self.events.put(("error", "Run setup.cmd to enable USB communication."))
        except (PumpError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("error", "USB delivery failed. Check the cable/port and close Serial Monitor. No automatic retry."))
