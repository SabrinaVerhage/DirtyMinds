"""Real Tk event-loop check; no key, sound, or physical hardware used."""
from pathlib import Path
import json
import queue
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dirtyminds.app import App
from dirtyminds.core import INGREDIENTS, LINES, Session, Stage
from dirtyminds.delivery import LEDS


class FakeDelivery:
    def __init__(self):
        self.events, self.calls = queue.Queue(), []
        self.busy = False

    def start_delivery(self, port, durations, mode, **kwargs):
        self.busy = True
        self.calls.append((port, durations, mode))
        return True

    def stop(self):
        self.busy = False

    close = stop


class FakeVoice:
    def __init__(self, backend):
        self.backend = backend
        self.events, self.calls = queue.Queue(), []
        self.generation, self.busy = 0, False

    def speak(self, text, *, voice_id=None):
        self.busy = True
        self.calls.append((text, voice_id))
        self.events.put((self.generation, 'playing', 'playing'))
        return True

    def stop(self):
        self.generation += 1
        self.busy = False

    close = stop


with tempfile.TemporaryDirectory() as directory, patch('dirtyminds.app.ROOT', Path(directory)):
    root = tk.Tk()
    app = App(root, {'span': 200, 'maximum': 1023, 'baud': 115200, 'port': '',
                     'api_key': '', 'voice_id': 'test-host', 'model_id': 'test', 'delivery_mode': LEDS})
    try:
        app.voice.close()
        app.voice = FakeVoice(app.voice.backend)
        app.delivery = FakeDelivery()
        app.pump_port.set('COM7')
        # Exercise layout at the advertised minimum, including a long pitch and recipe.
        root.geometry('960x780')
        app.line_text.set(INGREDIENTS[3].pitch)
        root.update()
        assert app.status_label.winfo_rooty() + app.status_label.winfo_height() < root.winfo_rooty() + root.winfo_height()
        assert app.start_button.winfo_rooty() + app.start_button.winfo_height() < app.status_label.winfo_rooty()
        assert app.lights_button.winfo_rooty() + app.lights_button.winfo_height() < app.status_label.winfo_rooty()
        for spoken in (False, True):
            app.silent.set(not spoken)
            app.start()
            seen, delivered = [], False
            deadline = time.monotonic() + 18
            while app.session.active and time.monotonic() < deadline:
                stage = app.session.stage
                if not seen or seen[-1] != stage:
                    seen.append(stage)
                index = app.session.round_index
                if index is not None:
                    app.intensity.set((15, 30, 95, 10)[index])
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
                    assert app.delivery.calls[-1] == ('COM7', [0, 0, 6000, 0], LEDS), app.delivery.calls
                    assert not app.session.delivery_complete
                    assert not app.session.tick(time.monotonic() + 100000)
                    if spoken:
                        assert app.voice.calls[-1][0] == LINES[Stage.REVEAL]
                    app.delivery.events.put(('reply', 'START pump=3 ms=6000 preview=1'))
                    app._delivery_events(time.monotonic())
                    assert app.led_canvas.itemcget(app.cells[2][0], 'fill') != '#38313e'
                    assert app.session.stage == Stage.DISPENSE
                    app.delivery.busy = False
                    app.delivery.events.put(('done', 'done'))
                    delivered = True
                root.update()
                time.sleep(.01)
            assert app.session.stage == Stage.COMPLETE, (app.session.stage, app.status.get())
            assert len(app.session.results) == 4
            assert app.session.delivery_complete
            assert all(app.led_canvas.itemcget(row[0], 'fill') == '#38313e' for row in app.cells)
            record = json.loads(app.record_path.read_text(encoding='utf-8'))
            assert len(record['rounds']) == 4 and record['delivery_complete']
            assert record['recipe']['amounts'] == [0, 0, 15, 0]
            if spoken:
                round_calls = [voice for text, voice in app.voice.calls if text in [item.pitch for item in INGREDIENTS]]
                assert round_calls == [item.voice_id for item in INGREDIENTS]
                assert app.voice.calls[-1][0] == LINES[Stage.FAREWELL]
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
        print('PASS: silent and voiced four-round Tk sessions; independent scores, cast, LED/DONE gate, failure, Stop/restart, records and layout.')
    finally:
        app.close()
