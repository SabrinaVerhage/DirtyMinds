import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dirtyminds.core import Session, RoundResult, make_recipe
from dirtyminds.delivery import DeliveryWorker, delivery_durations, water_test_ms, LEDS, SCREEN, MOTORS, WATER
from dirtyminds.pumps import PumpCancelled, PumpClient, PumpError
from dirtyminds.records import new_record_path, save_record
from test_lights import FakeConnection


class DeliveryTests(unittest.TestCase):
    def test_water_rehearsal_uses_timers_only_for_selected_channels(self):
        recipe = make_recipe([.8, .6, 0])
        self.assertEqual(delivery_durations(recipe, WATER, water_ms=(2300, 500, 100, 300)), [2300, 0, 100, 0])
        self.assertEqual(water_test_ms("2.3"), 2300)
        for value in ("0", "10.1", "nan", "abc"):
            with self.assertRaises(ValueError):
                water_test_ms(value)

    def test_uno_waits_for_reveal_cue_and_stop_while_waiting_never_arms(self):
        class MotorConnection(FakeConnection):
            def write(self, data):
                super().write(data)
                if data == b"ARM\n":
                    self.replies.append(b"OK ARM\n")
                elif data.startswith(b"SEQ "):
                    self.replies.extend([b"OK START\n", b"DONE\n"])

        for cue in (False, True):
            with self.subTest(cue=cue), patch("serial.Serial") as serial:
                connection = serial.return_value = MotorConnection()
                worker = DeliveryWorker()
                try:
                    self.assertTrue(worker.start_delivery("COM7", [1000, 0, 0, 0], WATER, on_cue=True))
                    events = [worker.events.get(timeout=1) for _ in range(3)]
                    self.assertEqual(events[-1][0], "ready")
                    self.assertEqual(connection.commands, ["HELLO"])
                    if cue:
                        worker.cue_motors()
                    else:
                        worker.stop()
                    worker.thread.join(2)
                    self.assertFalse(worker.busy)
                    self.assertEqual("ARM" in connection.commands, cue)
                    self.assertEqual("SEQ 1000 0 0 0" in connection.commands, cue)
                    self.assertEqual(list(worker.events.queue)[-1][0], "done" if cue else "cancelled")
                finally:
                    worker.close()

    def test_uno_status_only_identifies_and_queries(self):
        class StatusConnection(FakeConnection):
            def write(self, data):
                super().write(data)
                if data == b"STATUS\n":
                    self.replies.append(b"STATUS armed=0 running=0\n")

        connection = StatusConnection()
        worker = DeliveryWorker()
        with patch("serial.Serial", return_value=connection):
            self.assertTrue(worker.check_uno("COM7"))
            worker.thread.join(2)
        self.assertEqual(connection.commands, ["HELLO", "STATUS"])
        self.assertIn(("reply", "STATUS armed=0 running=0"), list(worker.events.queue))
        self.assertTrue(connection.closed)

    def test_recipe_rows_and_real_calibration(self):
        recipe = make_recipe([.8, .6, 0])
        self.assertEqual(delivery_durations(recipe, LEDS), [2571, 0, 3429, 0])
        self.assertEqual(delivery_durations(recipe, SCREEN), [2571, 0, 3429, 0])
        self.assertEqual(delivery_durations(recipe, MOTORS, [2, 1, 2, 2], real_enabled=True), [6428, 0, 4285, 0])
        self.assertEqual(delivery_durations(recipe, MOTORS, [2, 1, 2], real_enabled=True), [6428, 0, 4285, 0])
        with self.assertRaisesRegex(ValueError, "disabled"):
            delivery_durations(recipe, MOTORS, [2]*4)
        for rates in ([], [0]*4, [float('nan')]*4, [.001]*4, [100000]*4):
            with self.assertRaises(ValueError):
                delivery_durations(recipe, MOTORS, rates, real_enabled=True)

    def test_custom_order_applies_to_calibration_and_physical_test_timers(self):
        recipe = make_recipe([.8, .6, 0])
        order = ("jalapeno", "onion", "olive")
        self.assertEqual(delivery_durations(recipe, WATER, water_ms=(1000, 2000, 3000),
                                            pump_order=order), [0, 2000, 3000, 0])
        self.assertEqual(delivery_durations(recipe, MOTORS, [2, 1, 2], real_enabled=True,
                                            pump_order=order), [0, 4285, 6428, 0])

    def test_tiny_shares_use_minimum_pulses_without_exceeding_total(self):
        recipe = make_recipe([.001, .4, .599])
        rates = (2.0, 1.0, 1.5)
        durations = delivery_durations(recipe, MOTORS, rates, real_enabled=True)
        self.assertEqual(durations[2], 100)
        self.assertEqual(durations[3], 0)
        self.assertTrue(all(ms >= 100 for ms in durations[:3]))
        ingredient_durations = (durations[2], durations[0], durations[1])
        doses = [ms * rate / 1000 for ms, rate in zip(ingredient_durations, rates)]
        self.assertLessEqual(sum(doses), 15.0)
        self.assertAlmostEqual(sum(doses), 15.0, places=2)
        self.assertAlmostEqual(doses[1] / doses[2], .4 / .599, places=3)

    def test_led_delivery_uses_actual_client_preview_and_waits_for_done(self):
        connection = FakeConnection()
        worker = DeliveryWorker()
        with patch('serial.Serial', return_value=connection), patch('dirtyminds.lights.PumpClient', side_effect=lambda c: PumpClient(c, clock=c.clock)):
            worker.start_delivery('COM7', [3000, 0, 0, 3000], LEDS)
            worker.thread.join(2)
        self.assertFalse(worker.busy)
        self.assertIn('PREVIEW 3000 0 0 3000', connection.commands)
        self.assertFalse(any(c.startswith(('ARM', 'SEQ', 'RUN')) for c in connection.commands))
        events = list(worker.events.queue)
        self.assertEqual(events[-1][0], 'done')
        self.assertTrue(connection.closed)

    def test_failure_or_cancel_never_reports_completion(self):
        for failure, expected in ((PumpCancelled('Stopped'), 'cancelled'), (PumpError('USB failed'), 'error')):
            worker = DeliveryWorker()
            with patch('dirtyminds.delivery.run_lights_preview', side_effect=failure):
                worker.start_delivery('COM7', [6000, 0, 0, 0], LEDS)
                worker.thread.join(2)
            kinds = [kind for kind, _ in list(worker.events.queue)]
            self.assertIn(expected, kinds)
            self.assertNotIn('done', kinds)

    def test_screen_stop_is_fast_and_cannot_overlap(self):
        worker = DeliveryWorker()
        worker.start_delivery('', [6000, 0, 0, 0], SCREEN)
        self.assertFalse(worker.start_delivery('', [0, 6000, 0, 0], SCREEN))
        worker.close()
        self.assertFalse(worker.busy)
        self.assertEqual(list(worker.events.queue)[-1][0], 'cancelled')
        with self.assertRaises(ValueError):
            worker.start_delivery('COM7', [6000, 0, 0, 0], MOTORS)

    def test_partial_and_complete_records_keep_results_without_raw_trace(self):
        session = Session()
        session.start(0)
        session.baseline = 400
        session.results = [RoundResult('onion', .8, .9, 100)]
        with tempfile.TemporaryDirectory() as directory:
            path = new_record_path(Path(directory))
            save_record(path, session, source='Simulated', mode=LEDS, durations=[], voices=['id']*3)
            first = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(first['rounds'][0]['score'], .8)
            self.assertIsNone(first['recipe'])
            self.assertNotIn('responses', first)
            self.assertNotIn('api_key', first)
            session.recipe = make_recipe([.8, .2, .1])
            session.stop()
            save_record(path, session, source='Simulated', mode=LEDS, durations=[6000, 0, 0, 0], voices=['id']*3)
            final = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(final['stage'], 'Stopped')
            self.assertFalse(final['delivery_complete'])
            self.assertEqual(len(final['rounds']), 1)
            self.assertEqual(set(final['recipe']['brines_ml']), {'onion', 'olive', 'jalapeno'})
            self.assertAlmostEqual(sum(final['recipe']['brine_percentages'].values()), 100, places=2)
            self.assertAlmostEqual(sum(final['recipe']['amounts']), 15)
            self.assertFalse(path.with_suffix('.tmp').exists())
