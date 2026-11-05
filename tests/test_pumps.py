import unittest

from dirtyminds.pumps import PumpClient, PumpError, seconds_to_ms, validate_durations


class FakeSerial:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.commands = []
        self.now = 0

    def clock(self):
        return self.now

    def write(self, data):
        self.commands.append(data.decode().strip())

    def read_until(self, ending, size):
        self.now += 0.4
        item = next(self.replies, b"")
        if isinstance(item, BaseException):
            raise item
        return item


class PumpClientTests(unittest.TestCase):
    def test_duration_limits_and_nan(self):
        self.assertEqual(seconds_to_ms("2.5"), 2500)
        self.assertEqual(seconds_to_ms(0), 0)
        for bad in ("nan", "inf", "-1", "181", "0.0001", "text"):
            with self.assertRaises(ValueError):
                seconds_to_ms(bad)
        for bad in ([0, 0, 0, 0], [100, 100], [180000] * 4, [100, 0, -1, 0]):
            with self.assertRaises(ValueError):
                validate_durations(bad)

    def test_preview_never_arms_and_sends_heartbeats(self):
        serial = FakeSerial([b"OK START\n", b"START pump=1\n"] + [b""] * 6 + [b"DONE\n"])
        client = PumpClient(serial, clock=serial.clock)
        client.run([2000, 2000, 0, 0], preview=True, report=lambda _: None)
        self.assertEqual(serial.commands[0], "PREVIEW 2000 2000 0 0")
        self.assertNotIn("ARM", serial.commands)
        self.assertGreaterEqual(serial.commands.count("PING"), 2)
        self.assertNotIn("!", serial.commands)

    def test_real_sequence_requires_arm_ack(self):
        serial = FakeSerial([b"OK ARM\n", b"OK START\n", b"DONE\n"])
        client = PumpClient(serial, clock=serial.clock)
        client.run([1000, 0, 1000, 0], report=lambda _: None)
        self.assertEqual(serial.commands[:2], ["ARM", "SEQ 1000 0 1000 0"])
        rejected = FakeSerial([b"ERR STOP_BUTTON\n"])
        with self.assertRaises(PumpError):
            PumpClient(rejected, clock=rejected.clock).run([1000, 0, 0, 0])
        self.assertEqual(rejected.commands, ["ARM", "!"])

    def test_ctrl_c_disconnect_and_reset_attempt_immediate_stop(self):
        for interrupted in (KeyboardInterrupt(), OSError("USB removed"), b"DIRTYMINDS_PUMPS 1 pumps=4\n", b"STOPPED LINK_LOST\n"):
            serial = FakeSerial([b"OK ARM\n", b"OK START\n", interrupted])
            with self.assertRaises((KeyboardInterrupt, OSError, PumpError)):
                PumpClient(serial, clock=serial.clock).run([2000, 0, 0, 0], report=lambda _: None)
            self.assertEqual(serial.commands[-1], "!")

    def test_completion_timeout_attempts_stop(self):
        serial = FakeSerial([b"OK START\n"])
        with self.assertRaisesRegex(PumpError, "Timed out"):
            PumpClient(serial, clock=serial.clock).run([100, 0, 0, 0], preview=True)
        self.assertEqual(serial.commands[-1], "!")

    def test_partial_serial_lines_and_wrong_firmware(self):
        serial = FakeSerial([b"DIRTYMINDS_", b"PUMPS 1 pumps=4\r\n"])
        PumpClient(serial, clock=serial.clock).hello()
        unknown = FakeSerial([b"512\n"] * 20)
        with self.assertRaisesRegex(PumpError, "No Dirty Minds pump firmware"):
            PumpClient(unknown, clock=unknown.clock).hello()
        self.assertTrue(all(c == "HELLO" for c in unknown.commands))


if __name__ == "__main__":
    unittest.main()
