import math
import queue
import threading
import unittest

from dirtyminds.core import Session, Stage, SEQUENCE, ROUND_STAGES, make_recipe
from dirtyminds.sensors import parse_reading, Simulator, SerialInput


class SessionTests(unittest.TestCase):
    def test_complete_session_uses_baseline_and_yields_recipe(self):
        session = Session(span=200)
        session.start(0)
        for stage in SEQUENCE:
            self.assertEqual(session.stage, stage)
            if stage == Stage.DISPENSE:
                self.assertFalse(session.tick(100000))
                self.assertTrue(session.finish_delivery(1000))
                continue
            for _ in range(100):
                session.sample(600 if stage == Stage.ROUND_3 else 400)
            self.assertTrue(session.tick(session.ready_at))
        self.assertEqual(session.stage, Stage.COMPLETE)
        self.assertEqual(session.baseline, 400)
        self.assertEqual(len(session.results), 4)
        self.assertGreater(session.results[2].score, .9)
        self.assertLess(session.results[3].score, .01)
        self.assertEqual(session.recipe.amounts, (0, 0, 15, 0))
        self.assertTrue(session.delivery_complete)
        self.assertEqual(session.progress(100000), 100)

    def test_voice_blocks_transition(self):
        session = Session()
        session.start(0, spoken=True)
        self.assertFalse(session.tick(100, voice_busy=True))
        self.assertEqual(session.stage, Stage.WELCOME)
        self.assertFalse(session.tick(100))
        session.playback_started()
        self.assertFalse(session.tick(100))
        session.voice_finished(100)
        self.assertTrue(session.tick(101))

    def test_generation_time_does_not_count_as_a_round_response(self):
        session = Session(span=100)
        session.start(0, spoken=True)
        session.baseline = 400
        session._enter(Stage.ROUND_1, 10)
        for _ in range(100):
            session.sample(400)
        self.assertEqual(session.responses, [])
        session.playback_started()
        for _ in range(50):
            session.sample(500)
        session.voice_finished(200)
        self.assertFalse(session.tick(205.9))
        self.assertTrue(session.tick(206))
        self.assertGreater(session.results[0].score, .9)
        self.assertEqual(session.responses, [])

    def test_missing_calibration_cannot_make_recipe(self):
        session = Session()
        session._enter(Stage.CALIBRATE, 0)
        with self.assertRaisesRegex(ValueError, "baseline"):
            session.tick(8)
        self.assertIsNone(session.recipe)

    def test_missing_response_cannot_make_recipe(self):
        session = Session()
        session._enter(Stage.ROUND_1, 0)
        with self.assertRaisesRegex(ValueError, "round 1"):
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
        session._enter(Stage.ROUND_1, 0)
        session.baseline = 500
        session.sample(400)
        self.assertEqual(session.signal, 1)
        session.sample(math.nan)
        self.assertEqual(len(session.responses), 1)

    def test_recipe_is_bounded_and_alcohol_fixed(self):
        recipes = [make_recipe([x / 100, .2, .3, .4]) for x in range(-10, 111)]
        for recipe in recipes:
            self.assertAlmostEqual(recipe.brine_ml, 15)
            self.assertEqual((recipe.gin_ml, recipe.vermouth_ml), (50, 10))
            self.assertLessEqual(sum(x > 0 for x in recipe.amounts), 2)
        with self.assertRaises(ValueError):
            make_recipe([math.nan, 0, 0, 0])

    def test_blend_threshold_fallback_and_ties(self):
        self.assertEqual(make_recipe([0, 0, 0, 0]).amounts, (0, 15, 0, 0))
        self.assertEqual(make_recipe([.8, .1, .1, .1]).amounts, (15, 0, 0, 0))
        self.assertEqual(make_recipe([.8, .8, .8, .8]).amounts, (7.5, 7.5, 0, 0))
        self.assertEqual(make_recipe([.8, .6, .1, 0]).amounts, (8.6, 6.4, 0, 0))
        self.assertEqual(make_recipe([.8, .59, .1, 0]).amounts, (15, 0, 0, 0))

    def test_bad_settings_and_premature_delivery(self):
        for value in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                Session(time_scale=value)
        session = Session()
        session.start(0)
        self.assertFalse(session.finish_delivery(1))
        self.assertFalse(session.delivery_complete)


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

