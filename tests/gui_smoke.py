"""Real Tk event-loop check; no key, sound, or physical hardware used."""
from pathlib import Path
import json
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dirtyminds.app import App, IDLE_CELL
from dirtyminds.core import INGREDIENTS, LINES, PROFESSOR_VOICE_ID, ROUND_STAGES, Stage, make_recipe
from dirtyminds.delivery import LEDS, MOTORS, WATER, delivery_durations
from dirtyminds.records import load_pump_calibration, load_pump_order


class FakeDelivery:
    def __init__(self):
        self.events, self.calls = queue.Queue(), []
        self.busy = False
        self.cues = 0
        self.on_cue = False

    def start_delivery(self, port, durations, mode, **kwargs):
        self.busy = True
        self.calls.append((port, durations, mode))
        self.on_cue = kwargs.get("on_cue", False)
        return True

    def cue_motors(self):
        self.cues += 1

    def stop(self):
        self.busy = False

    close = stop


class FakeVoice:
    def __init__(self, backend):
        self.backend = backend
        self.events, self.calls = queue.Queue(), []
        self.generation, self.busy = 0, False
        self.options = []
        self.loops = []

    def play_loop(self, path):
        self.loops.append(path.name)
        return True

    def speak(self, text, *, voice_id=None, cue=None, steady=False, lead_in=None):
        self.busy = True
        self.calls.append((text, voice_id))
        self.options.append((steady, lead_in.name if lead_in else None))
        self.events.put((self.generation, 'playing', 'playing'))
        return True

    def stop(self):
        self.generation += 1
        self.busy = False

    close = stop


with tempfile.TemporaryDirectory() as directory, patch('dirtyminds.app.ROOT', Path(directory)):
    root = tk.Tk()
    app = App(root, {'span': 200, 'maximum': 1023, 'baud': 115200, 'port': '',
                     'api_key': '', 'model_id': 'test', 'delivery_mode': LEDS})
    try:
        app.voice.close()
        app.voice = FakeVoice(app.voice.backend)
        app.delivery = FakeDelivery()
        app.pump_port.set('COM7')
        # Exercise layout at the advertised minimum, including a long pitch and recipe.
        root.update()
        assert root.attributes('-fullscreen')
        assert app.cast_art.width() > 0
        app.toggle_fullscreen()
        root.geometry('960x750')
        app.line_text.set(LINES[Stage.WELCOME])
        root.update()
        assert app.status_label.winfo_rooty() + app.status_label.winfo_height() < root.winfo_rooty() + root.winfo_height()
        assert app.start_button.winfo_rooty() + app.start_button.winfo_height() < app.status_label.winfo_rooty()
        assert app.hardware_button.winfo_rooty() + app.hardware_button.winfo_height() < app.status_label.winfo_rooty()
        assert app.copy_button.winfo_rooty() + app.copy_button.winfo_height() < app.status_label.winfo_rooty(), (
            root.winfo_width(), root.winfo_height(), app.copy_button.winfo_rooty(),
            app.copy_button.winfo_height(), app.status_label.winfo_rooty(), app.script_label.winfo_width(),
            app.script_label.winfo_height(), app.script_label.cget('wraplength'),
        )
        app.open_hardware()
        hardware = app.hardware_window
        root.update()
        assert hardware.pulses[-1].instate(["disabled"])
        assert [field.get() for field in app.water_times] == ["5.0"] * 4
        assert [label["text"] for label in hardware.pump_labels[:3]] == [
            "1  Olive", "2  Jalapeño", "3  Pickled Onion"]
        hardware.pulse(4)
        assert not app.delivery.calls
        hardware.armed.set(True)
        hardware.update()
        app.water_times[-1].set('1.5')
        hardware.pulses[-1].invoke()
        assert app.delivery.calls[-1] == ('COM7', [0, 0, 0, 1500], WATER)
        app.stop()
        assert not hardware.armed.get() and not app.delivery.busy
        app.feather_host.set('127.0.0.1')
        with patch('dirtyminds.hardware_ui.WirelessInput') as sensor:
            sensor.return_value.error = None
            sensor.return_value.poll.return_value = [(time.monotonic(), 512)]
            hardware.toggle_feather()
            hardware.opening.thread.join(1)
            hardware.poll(time.monotonic())
            assert 'raw 512' in hardware.feather_status.get()
            assert app.start_button['state'] == 'disabled'
            hardware.toggle_feather()
            sensor.return_value.close.assert_called_once()
        assert 'receiving valid GSR samples' in hardware.log.get('1.0', 'end')
        hardware.open_calibration()
        calibration = hardware.calibration
        root.update()
        assert calibration.save_button.instate(["disabled"])
        before = len(app.delivery.calls)
        calibration.run(0, prime=True)
        assert len(app.delivery.calls) == before
        assert app.new_session_shortcut() == "break" and not app.session.active
        calibration.armed.set(True)
        calibration.run(0, prime=True)
        assert app.delivery.calls[-1] == ('COM7', [2000, 0, 0, 0], WATER)
        app.delivery.busy = False
        app.delivery.events.put(('done', 'Prime complete'))
        app._delivery_events(time.monotonic())
        assert calibration.completed_ms[0] is None
        calibration.run(0)
        calibration.stop()
        app.delivery.events.put(('cancelled', 'Stopped'))
        app._delivery_events(time.monotonic())
        assert calibration.completed_ms[0] is None
        assert calibration.save_button.instate(["disabled"])
        calibration.armed.set(True)
        for i, ml in enumerate(("8", "6", "10")):
            calibration.run(i)
            assert app.delivery.calls[-1][1] == [5000 if ch == i else 0 for ch in range(4)]
            app.delivery.busy = False
            app.delivery.events.put(('done', 'Timed run complete'))
            app._delivery_events(time.monotonic())
            calibration.volumes[i].set(ml)
        calibration.times[0].set("10")
        assert calibration.rate_labels[0]["text"] == "1.600"  # The completed run used 5 seconds.
        calibration.save_button.invoke()
        assert hardware.calibration is None and app.config["pump_rates"] == (2.0, 1.6, 1.2)
        assert load_pump_calibration(Path(directory) / "output" / "pump_calibration.json") == (2.0, 1.6, 1.2)
        assert MOTORS in app.mode_box["values"] and app.mode.get() == LEDS
        hardware.close()
        connections = json.loads(app.connection_path.read_text(encoding='utf-8'))
        assert connections == {'feather_ip': '127.0.0.1', 'gsr_usb': '', 'pump_usb': 'COM7'}
        # A slow connection can be cancelled without starting a simulated session.
        app.source.set("Feather Wi-Fi")
        release = threading.Event()
        with patch('dirtyminds.app.WirelessInput') as sensor:
            connected = sensor.return_value
            def connect(*args, **kwargs):
                release.wait(2)
                return connected
            sensor.side_effect = connect
            app.start()
            opening = app.input_opening
            assert opening is not None and not app.session.active
            app.stop()
            release.set()
            opening.thread.join(1)
            connected.close.assert_called_once()
            assert app.input_opening is None and not app.session.active
        app.source.set("Feather USB")
        app.port.set("COM7")
        app.mode.set(WATER)
        app.start()
        assert app.input_opening is None and "separate ports" in app.status.get()
        app.port.set("COM8")
        app.mode.set(LEDS)
        with patch('dirtyminds.app.SerialInput') as sensor:
            app.start()
            app.input_opening.thread.join(1)
            app._poll_input_opening(time.monotonic())
            sensor.assert_called_once_with("COM8", 115200, 1023)
            assert app.session_source == "Feather USB" and app.session.active
            app.stop()
        app.source.set("Simulated")
        app.toggle_patient_view()
        root.update()
        patient = app.patient_window
        patient.window.event_generate("<F8>")
        root.update()
        assert app.session.stage == Stage.WELCOME and app.patient_window is patient
        current_path = app.record_path
        patient.window.event_generate("<F8>")
        root.update()
        assert app.record_path == current_path
        app.stop()
        app.close_patient_view()
        for spoken in (False, True):
            app.silent.set(not spoken)
            app.start()
            if spoken:
                app.toggle_patient_view()
                root.update()
                patient = app.patient_window
                assert patient.window.attributes('-fullscreen')
                assert patient.window.winfo_viewable()
                assert patient.window.cget('background') == 'black'
                assert 'INTAKE' in patient.stream.get('1.0', 'end')
                assert LINES[Stage.WELCOME] not in patient.stream.get('1.0', 'end')
                voice_count = len(app.voice.calls)
                timeline = app.patient_timeline
                position = timeline.counter
                app.toggle_patient_view()
                assert app.patient_window is None and app.session.active
                assert len(app.voice.calls) == voice_count and app.voice.busy
            seen, delivered = [], False
            deadline = time.monotonic() + 18
            while app.session.active and time.monotonic() < deadline:
                stage = app.session.stage
                if not seen or seen[-1] != stage:
                    seen.append(stage)
                if spoken and stage == Stage.ROUND_2 and app.patient_window is None:
                    app.toggle_patient_view()
                    assert app.patient_timeline is timeline and timeline.counter > position
                    assert 'DIRTY 2 / 3' in app.patient_window.heading['text']
                    assert app.voice.busy or app.session.playback_has_started
                index = app.session.round_index
                if index is not None:
                    app.intensity.set((15, 30, 95)[index])
                # Keep the real 10 Hz sensor path; shorten only pauses after enough readings.
                sufficient = ((stage == Stage.CALIBRATE and len(app.session.calibration) >= 12)
                              or (index is not None and len(app.session.responses) >= 12)
                              or (stage != Stage.CALIBRATE and index is None))
                if sufficient and app.session.voice_pending and app.session.playback_has_started:
                    app.voice.busy = False
                    app.voice.events.put((app.voice.generation, 'done', 'done'))
                if sufficient and not app.session.voice_pending and stage != Stage.DISPENSE:
                    app.session.ready_at = time.monotonic()
                if stage == Stage.DISPENSE and not delivered:
                    assert app.delivery.calls[-1] == ('COM7', delivery_durations(app.session.recipe, LEDS), LEDS)
                    assert not app.session.delivery_complete
                    assert not app.session.tick(time.monotonic() + 100000)
                    if spoken:
                        assert app.voice.calls[-1][0] == LINES[Stage.REVEAL]
                    for pump, brine in enumerate(("OLIVE", "JALAPEÑO", "PICKLED ONION"), 1):
                        app.delivery.events.put(('reply', f'START pump={pump} ms=500 preview=1'))
                        app._delivery_events(time.monotonic())
                        assert app.patient_timeline.phase == f"PUMPING {brine}"
                        if app.patient_window:
                            assert f"PUMPING {brine}" in app.patient_window.heading["text"]
                        assert app.led_canvas.itemcget(app.cells[pump - 1][0], 'fill') != IDLE_CELL
                        app.delivery.events.put(('reply', f'PUMP_DONE pump={pump}'))
                        app._delivery_events(time.monotonic())
                        assert app.patient_timeline.phase == "PREPARING PRESCRIPTION"
                    assert app.session.stage == Stage.DISPENSE
                    app.delivery.busy = False
                    app.delivery.events.put(('done', 'done'))
                    delivered = True
                root.update()
                time.sleep(.01)
            assert app.session.stage == Stage.COMPLETE, (app.session.stage, app.status.get(), list(app.events)[-14:])
            assert len(app.session.results) == 3
            assert app.session.delivery_complete
            assert all(app.led_canvas.itemcget(row[0], 'fill') == IDLE_CELL for row in app.cells)
            record = json.loads(app.record_path.read_text(encoding='utf-8'))
            assert len(record['rounds']) == 3 and record['delivery_complete']
            assert len(record['round_scripts']) == 3
            assert abs(sum(record['recipe']['amounts']) - 15) < .001
            assert len(record['recipe']['brines_ml']) == 3
            if spoken:
                app.close_patient_view()
                assert app.voice.calls[0] == (LINES[Stage.WELCOME], PROFESSOR_VOICE_ID)
                assert app.voice.options[0] == (True, 'intake-jingle.wav')
                first_round = app.voice.calls.index((LINES[Stage.ROUND_1], INGREDIENTS[0].voice_id))
                assert app.voice.options[first_round] == (False, 'test-ready.wav')
                assert all(app.voice.options[app.voice.calls.index((LINES[stage], item.voice_id))] == (False, 'test-ready.wav')
                           for stage, item in zip(ROUND_STAGES, INGREDIENTS))
                assert app.voice.loops == ['prescription-wait.wav']
                assert app.session.recipe.name in app.voice.calls[-1][0]
                assert app.voice.calls[-1][1] == PROFESSOR_VOICE_ID and app.voice.options[-1] == (True, None)
                round_calls = [voice for text, voice in app.voice.calls if text in [LINES[stage] for stage in ROUND_STAGES]]
                assert round_calls == [item.voice_id for item in INGREDIENTS]
                assert app.voice.calls[-1][0].endswith(LINES[Stage.FAREWELL])
        # A failed delivery must stop without speaking the farewell or marking success.
        app.session._enter(Stage.DISPENSE, time.monotonic())
        app.session.delivery_complete = False
        call_count = len(app.voice.calls)
        app.delivery.events.put(('error', 'USB removed'))
        app._delivery_events(time.monotonic())
        assert app.session.stage == Stage.STOPPED
        assert not app.session.delivery_complete
        assert len(app.voice.calls) == call_count
        app.start()
        assert app.session.results == [] and app.session.recipe is None
        app.stop()
        assert app.session.stage == Stage.STOPPED
        # Real output handshakes first, starts on audio playback and waits for both
        # the reveal and DONE, regardless of which finishes first.
        app.mode.set(WATER)
        for done_first in (True, False):
            app.start()
            app.voice.stop()
            now = time.monotonic()
            app.session.recipe = make_recipe([0, .6, .8])
            app.water_times[3].set('10.1')  # The spare channel is bench-only.
            app.session._enter(Stage.REVEAL, now)
            voice_count, cue_count = len(app.voice.calls), app.delivery.cues
            app._stage_changed()
            assert app.delivery.calls[-1] == ('COM7', [5000, 5000, 0, 0], WATER)
            assert app.delivery.on_cue and len(app.voice.calls) == voice_count
            call_count = len(app.delivery.calls)
            app.delivery.events.put(('ready', 'Uno ready'))
            app._delivery_events(now)
            assert app.voice.calls[-1][0] == LINES[Stage.REVEAL]
            assert app.delivery.cues == cue_count
            root.after_cancel(app.after_id)
            app.tick()
            assert app.delivery.cues == cue_count + 1
            if done_first:
                app.delivery.busy = False
                app.delivery.events.put(('done', 'Done'))
                app._delivery_events(now)
                assert app.session.stage == Stage.REVEAL and app.session.delivery_complete
            app.voice.busy = False
            app.session.voice_finished(now)
            assert app.session.tick(now + 2)
            app._stage_changed()
            if not done_first:
                assert app.session.stage == Stage.DISPENSE and not app.session.delivery_complete
                app.delivery.busy = False
                app.delivery.events.put(('done', 'Done'))
                app._delivery_events(now)
            assert app.session.stage == Stage.FAREWELL and app.session.delivery_complete
            assert app.voice.calls[-1][0] == app.session.line()
            assert len(app.delivery.calls) == call_count
            app.stop()
        # A new session requests a fresh introduction and three brine whispers.
        app.mode.set(LEDS)
        app.silent.set(False)
        app.fresh_scripts.set(True)
        app.config['openai_key'] = 'test'
        with patch('dirtyminds.app.generate_intro', return_value='Peer-reviewed and lightly stirred.') as intro, \
                patch('dirtyminds.app.generate_lines', return_value={item.key: item.pitch for item in INGREDIENTS}) as lines:
            previous = app.patient_timeline
            app.start_button.invoke()
            assert app.patient_timeline is not previous and app.patient_timeline.counter == 1
            app.intro_request.thread.join(1)
            app.script_request.thread.join(1)
            app._poll_intro(time.monotonic())
            intro.assert_called_once()
            lines.assert_called_once()
            assert app.voice.calls[-1] == ('Peer-reviewed and lightly stirred.', PROFESSOR_VOICE_ID)
        app.stop()
        app.fresh_scripts.set(False)
        # A completed name becomes the display and the existing session log.
        app.mode.set(LEDS)
        app.silent.set(True)
        app.config['openai_key'] = 'test'
        app.start()
        now = time.monotonic()
        app.session.recipe = make_recipe([.8, .6, 0])
        app.session._enter(Stage.REVEAL, now)
        app.session_scripts = [{"text": "My juice is dangerously silky."}, {"text": "A salty finish."}]
        with patch('dirtyminds.app.generate_name', return_value='A Second Onion Opinion') as generate_name:
            app._stage_changed()
            app.name_request.thread.join(1)
        assert generate_name.call_args.args[3] == "My juice is dangerously silky."
        root.after_cancel(app.after_id)
        app.tick()
        assert app.session.recipe.name == 'A Second Onion Opinion'
        assert 'A Second Onion Opinion' in app.recipe_text.get()
        record = json.loads(app.record_path.read_text(encoding='utf-8'))
        assert record['recipe']['name'] == 'A Second Onion Opinion'
        assert abs(record['recipe']['brines_ml']['onion'] - 15 * .8 / 1.4) < .001
        app.toggle_patient_view()
        assert not app.patient_window.title.winfo_manager()
        app.session._enter(Stage.FAREWELL, time.monotonic())
        app._stage_changed()
        assert app.patient_window.title.cget('text') == 'A Second Onion Opinion'
        assert app.patient_window.title.winfo_manager() == 'place'
        app.close_patient_view()
        app.stop()
        app.open_hardware()
        hardware = app.hardware_window
        hardware.open_assignments()
        root.update()
        assignments = hardware.assignment_window.winfo_children()[0]
        choices = [widget for widget in assignments.winfo_children() if isinstance(widget, ttk.Combobox)]
        save = next(widget for widget in assignments.winfo_children()
                    if isinstance(widget, ttk.Button) and widget["text"] == "Save assignments")
        choices[0].set("Jalapeño")
        save.invoke()
        assert hardware.assignment_window is not None  # Duplicate pump assignment.
        choices[1].set("Olive")
        app.mode.set(MOTORS)
        save.invoke()
        assert hardware.assignment_window is None
        assert app.mode.get() != MOTORS and not app.config["real_pumps"]
        assert [label["text"] for label in hardware.pump_labels[:3]] == [
            "1  Jalapeño", "2  Olive", "3  Pickled Onion"]
        assert load_pump_order(Path(directory) / "output" / "pump_channels.json") == app.pump_order
        assert not load_pump_calibration(Path(directory) / "output" / "pump_calibration.json", app.pump_order)
        hardware.close()
        log = app.debug.path.read_text(encoding='utf-8')
        assert "Display / patient view opened" in log
        assert "Display / returned to operator view" in log
        assert "Voice / playback started after" in log
        assert "Signal / connection cancelled" in log
        assert "Session / Patient intake" in log
        assert "Session / Assessing responses" in log
        assert "OpenAI / prescription title succeeded" in log
        assert "OpenAI / professor intro succeeded" in log
        assert "The app encountered an error" not in log
        assert LINES[Stage.WELCOME] not in log
        print('PASS: Tk rehearsals, patient F8, measured calibration, debug log, hardware controls, real-output cue, DONE/farewell in either order, Stop/restart and layout.')
    finally:
        app.close()
