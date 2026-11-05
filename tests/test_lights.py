import threading
import unittest
from unittest.mock import patch

from dirtyminds.lights import LightsWorker, preview_durations, run_lights_preview
from dirtyminds.pumps import PumpCancelled, PumpClient, PumpError


class FakeConnection:
    def __init__(self, cancelled=None, cancel_after=None, wrong=False):
        self.commands = []
        self.replies = []
        self.closed = False
        self.now = 0
        self.cancelled = cancelled
        self.cancel_after = cancel_after
        self.wrong = wrong

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def clock(self):
        return self.now

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        if command == "HELLO":
            self.replies.append(b"512\n" if self.wrong else b"DIRTYMINDS_PUMPS 1 pumps=4\n")
        elif command.startswith("PREVIEW "):
            self.replies.append(b"OK START\n")
            for pump, duration in enumerate(command.split()[1:], 1):
                if duration != "0":
                    self.replies += [f"START pump={pump} ms={duration} preview=1\n".encode(),
                                     f"PUMP_DONE pump={pump}\n".encode()]
            self.replies.append(b"DONE\n")
        elif command == "PING":
            self.replies.append(b"PONG\n")
        if self.cancel_after and command.startswith(self.cancel_after):
            self.cancelled.set()

    def read_until(self, *args, **kwargs):
        self.now += 0.2
        return self.replies.pop(0) if self.replies else b""


class LightsTests(unittest.TestCase):
    def run_preview(self, connection, pump=None, cancelled=None):
        reports = []
        # The production serial client, with only its clock replaced for fast tests.
        with patch("dirtyminds.lights.PumpClient", side_effect=lambda c: PumpClient(c, clock=c.clock)):
            run_lights_preview("COM7", preview_durations(pump),
                               cancelled=cancelled or threading.Event(), report=reports.append,
                               serial_factory=lambda *a, **k: connection)
        return reports

    def test_all_four_buttons_send_matching_preview_only_and_close_port(self):
        for pump in range(1, 5):
            with self.subTest(pump=pump):
                connection = FakeConnection()
                reports = self.run_preview(connection, pump)
                expected = ["0"] * 4
                expected[pump-1] = "2000"
                self.assertIn("PREVIEW " + " ".join(expected), connection.commands)
                self.assertTrue(any(line.startswith(f"START pump={pump} ") for line in reports))
                self.assertFalse(any(c.startswith(("ARM", "SEQ", "RUN")) for c in connection.commands))
                self.assertTrue(connection.closed)

    def test_all_four_sequence_reports_rows_in_order(self):
        connection = FakeConnection()
        reports = self.run_preview(connection)
        starts = [line.split()[1] for line in reports if line.startswith("START ")]
        self.assertEqual(starts, [f"pump={n}" for n in range(1, 5)])
        self.assertIn("PREVIEW 2000 2000 2000 2000", connection.commands)

    def test_cancel_waiting_for_preview_ack_sends_stop_and_closes(self):
        cancel = threading.Event()
        connection = FakeConnection(cancel, cancel_after="PREVIEW")
        with self.assertRaises(PumpCancelled):
            self.run_preview(connection, cancelled=cancel)
        self.assertEqual(connection.commands[-1], "!")
        self.assertTrue(connection.closed)

    def test_cancel_during_identification_does_not_start_preview(self):
        cancel = threading.Event()
        connection = FakeConnection(cancel, cancel_after="HELLO", wrong=True)
        with self.assertRaises(PumpCancelled):
            self.run_preview(connection, cancelled=cancel)
        self.assertEqual(connection.commands, ["HELLO"])
        self.assertTrue(connection.closed)

    def test_wrong_firmware_does_not_receive_a_preview(self):
        connection = FakeConnection(wrong=True)
        with self.assertRaises(PumpError):
            self.run_preview(connection)
        self.assertTrue(all(c == "HELLO" for c in connection.commands))
        self.assertTrue(connection.closed)

    def test_invalid_pump_and_empty_port_do_not_open_usb(self):
        for invalid in (0, 5, True, "1"):
            with self.assertRaises(ValueError):
                preview_durations(invalid)
        with patch("dirtyminds.lights.run_lights_preview") as run:
            with self.assertRaises(ValueError):
                LightsWorker().start("", 1)
            run.assert_not_called()

    def test_worker_rejects_overlapping_tests_and_close_cancels(self):
        entered = threading.Event()
        def wait_for_cancel(*args, cancelled, **kwargs):
            entered.set()
            cancelled.wait(1)
            raise PumpCancelled("Stopped")
        worker = LightsWorker()
        with patch("dirtyminds.lights.run_lights_preview", side_effect=wait_for_cancel):
            self.assertTrue(worker.start("COM7", 1))
            self.assertTrue(entered.wait(1))
            self.assertFalse(worker.start("COM7", 2))
            worker.close()
        self.assertFalse(worker.busy)
        self.assertTrue(worker.cancelled.is_set())
