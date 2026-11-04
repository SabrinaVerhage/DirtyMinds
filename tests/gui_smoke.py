"""Run separately on a Windows desktop: python tests/gui_smoke.py.

Exercises the real Tk window and timer through completion and Stop/restart.
No API key, network, audio, or Arduino required.
"""
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dirtyminds.app import App
from dirtyminds.core import Stage

root = tk.Tk()
root.withdraw()
app = App(root, {
    "span": 200, "maximum": 1023, "baud": 115200, "port": "",
    "api_key": "", "voice_id": "test", "model_id": "test",
})
try:
    app.session.time_scale = 0.2
    app.start()
    deadline = time.monotonic() + 15
    while app.session.active and time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    assert app.session.stage == Stage.COMPLETE, (app.session.stage, app.status.get())
    assert app.session.recipe is not None
    assert "ml olive brine" in app.recipe_text.get()
    assert app.voice.generation == 1  # Start cancelled any old voice jobs.
    assert not app.voice.busy
    app.start()
    assert app.session.stage == Stage.WELCOME
    app.stop()
    assert app.session.stage == Stage.STOPPED
    assert app.session.recipe is None
    print("PASS: real Tk session completed; recipe, Stop, and restart work.")
finally:
    app.close()

