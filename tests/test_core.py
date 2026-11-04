import math
import queue
import threading
import unittest

from dirtyminds.core import Session, Stage, SEQUENCE, DURATIONS, make_recipe
from dirtyminds.sensors import parse_reading, Simulator, SerialInput


class SessionTests(unittest.TestCase):
    def test_complete_session_uses_baseline_and_yields_recipe(self):
        session = Session(span=200)
        now = 0
        session.start(now)
        for stage, duration in zip(SEQUENCE, DURATIONS):
            self.assertEqual(session.stage, stage)
            for _ in range(30):
                session.sample(400 if stage in (Stage.WELCOME, Stage.CALIBRATE) else 600)
            now += duration
            self.assertTrue(session.tick(now))
        self.assertEqual(session.stage, Stage.COMPLETE)
        self.assertEqual(session.baseline, 400)
        self.assertGreater(session.score, 0.8)
        self.assertEqual(session.recipe.brine_ml, 25)
        self.assertEqual(session.progress(now), 100)

    def test_voice_blocks_transition(self):
        session = Session()
        session.start(0)
        self.assertFalse(session.tick(100, voice_busy=True))
        self.assertEqual(session.stage, Stage.WELCOME)
        self.assertTrue(session.tick(100))

    def test_missing_calibration_cannot_make_recipe(self):
        session = Session()
        session.start(0)
        session.tick(7)
        with self.assertRaisesRegex(ValueError, "calibrate"):
            session.tick(15)
        self.assertIsNone(session.recipe)

    def test_missing_response_cannot_make_recipe(self):
        session = Session()
        session.stage = Stage.SETTLE
        with self.assertRaisesRegex(ValueError, "recipe"):
            session.tick(50)

    def test_stop_and_restart_reset_measurements(self):
        session = Session()
        session.start(0)
        session.sample(100)
        session.baseline = 100
        session.responses = [1]
        session.stop()
        self.assertFalse(session.tick(100))
        self.assertIsNone(session.recipe)
        session.start(101)
        self.assertEqual(session.responses, [])
        self.assertIsNone(session.smoothed)
        self.assertIsNone(session.baseline)

    def test_inverted_signal_is_valid_absolute_change(self):
        session = Session(span=100)
        session.stage = Stage.EXPLORE
        session.baseline = 500
        session.sample(400)
        self.assertEqual(session.signal, 1)
        session.sample(math.nan)
        self.assertEqual(len(session.responses), 1)

    def test_recipe_is_bounded_monotonic_and_alcohol_fixed(self):
        recipes = [make_recipe(x / 100) for x in range(-10, 111)]
        self.assertEqual(sorted(r.brine_ml for r in recipes), [r.brine_ml for r in recipes])
        for recipe in recipes:
            self.assertIn(recipe.brine_ml, (5, 10, 15, 20, 25))
            self.assertEqual((recipe.gin_ml, recipe.vermouth_ml), (50, 10))
            self.assertIn(recipe.olives, (1, 2, 3))
        with self.assertRaises(ValueError):
            make_recipe(math.nan)


class SensorTests(unittest.TestCase):
    def test_protocol_accepts_numbers_and_optional_prefix(self):
        for data, expected in [(b"512\r\n", 512), (b"GSR: 0\n", 0), (b"1023", 1023), (b"42.5", 42.5)]:
            self.assertEqual(parse_reading(data), expected)

    def test_protocol_rejects_noise_and_out_of_range(self):
        for data in (b"", b"booting", b"nan", b"inf", b"-1", b"1024", b"512,12", b"\xff"):
            self.assertIsNone(parse_reading(data))
        self.assertEqual(parse_reading(b"4095", 4095), 4095)

    def test_simulator_baseline_independent_of_slider(self):
        simulator = Simulator()
        for level in (0, 0.5, 1):
            self.assertTrue(415 < simulator.read(0, level, False) < 445)
        self.assertGreater(simulator.read(0, 1, True), 700)

    def test_serial_fragmentation_noise_and_disconnect(self):
        class ImmediateEvent(threading.Event):
            def wait(self, timeout=None):
                return self.is_set()

        class Connection:
            closed = False
            chunks = iter([b"5", b"12\njunk\n", b"9" * 65, b"\nGSR:27\n", b"400", b".5\n"])

            def reset_input_buffer(self):
                pass

            def read_until(self, ending, size):
                try:
                    return next(self.chunks)
                except StopIteration:
                    raise OSError("USB removed")

            def close(self):
                self.closed = True

        sensor = SerialInput.__new__(SerialInput)
        sensor.connection = Connection()
        sensor.maximum = 1023
        sensor.stop_event = ImmediateEvent()
        sensor.samples = queue.Queue(maxsize=100)
        sensor.error = None
        sensor._read()
        self.assertEqual([value for _, value in sensor.poll()], [512, 27, 400.5])
        self.assertIn("connection lost", sensor.error)
        self.assertTrue(sensor.connection.closed)


if __name__ == "__main__":
    unittest.main()

