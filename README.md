# Dirty Minds

A local Windows installation prototype: press **Begin extraction**, hear a scripted
ElevenLabs voice, watch a simulated or Arduino GSR signal, and receive a dirty
martini recipe. Python 3.10+ and Tkinter. No hosted page, browser, Node, server,
microphone, or language model is needed.

## Start here

1. Double-click **setup.cmd**. It creates `.venv`, installs two small dependencies,
   and copies `.env.example` to `.env` only if `.env` does not already exist.
   Python must include Tcl/Tk; the python.org Windows installer normally does.
2. Double-click **run.cmd**.
3. Leave **Simulated** and **Silent rehearsal** selected. Click **Begin extraction**.
   During *A little imagination*, move the response slider. A recipe appears after
   roughly 45 seconds. **Stop / Esc** cancels; start again for a fresh baseline.
4. To add speech, open `.env` locally in your editor and set `ELEVENLABS_API_KEY`.
   Use a key with Text to Speech permission. Set `ELEVENLABS_VOICE_ID` to a voice
   available in your account, if needed; the example defaults to Sarah.
5. Restart the app. Select your headphones as the **Windows default sound output**
   and set a comfortable volume. Click **Test ElevenLabs voice**. Uncheck
   **Silent rehearsal**, then begin. The test button always tests real playback,
   even when rehearsal is checked.

PowerShell equivalent (no virtual-environment activation needed):

```powershell
cd C:\Users\sabri\Documents\_GITHUB\DirtyMinds
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe app.py
```

An empty `.env` key selects silent rehearsal by default. Without dependencies or
an `.env` file, `python app.py` can also run the silent simulator immediately.
The Windows `py` launcher is optional; these scripts use `python`.

## What happens during a session

Welcome → 8-second baseline → imagination prompt → a signal-dependent reply → recipe.
The complete sequence has 42 seconds of scheduled stages; fresh voice generation
can extend it. Stages wait for their voice clip to finish and never overlap speech.
All lines are visible on screen. Edit the short script in `dirtyminds/core.py`.
The voice is intimate and theatrical, with three response/ending variants.

The monitor shows raw ADC counts, a smoothed trace, baseline, and absolute change.
The baseline is the median of the calibration samples. Smoothing is an exponential
moving average (0.22). Change is `abs(smoothed - baseline) / GSR_SPAN`, clipped to
0–100%; the recipe uses the average during the imagination and response stages.
This accepts sensors whose output rises **or** falls with conductance. It is an
artistic input mapping, not a calibrated conductance measurement, emotion detector,
or measurement of sexual arousal. Motion/contact changes can affect it.

Every recipe contains **50 ml gin or vodka + 10 ml dry vermouth**. Only olive brine
(5–25 ml, in 5 ml steps) and garnish (1–3 olives) vary. Instructions and a **Copy
recipe** button are included. Mixing is manual in this version.

## Arduino when you're ready

1. Open `arduino/gsr_reader/gsr_reader.ino` in the Arduino IDE. It reads A0 and sends
   one value per line at 115200 baud, 20 times a second. Use a suitable GSR sensor
   module's analog output; the sketch is not a body-contact circuit design. A
   potentiometer works for a bench test of the software path.
2. Upload it and **close Serial Monitor/Plotter** so the port is free.
3. Choose **Arduino USB**, **Refresh ports**, and the right COM port. You can also
   type a port or set `SERIAL_PORT=COM3` in `.env`.
4. Begin with steady contact during baseline. Tune `GSR_SPAN` for your sensor's
   typical raw change. For a 12-bit ADC, set `GSR_MAX=4095` and tune the span too.

Protocol: ASCII `512\n` or `GSR:512\n`; decimals are accepted. Invalid, non-finite,
overlong and out-of-range lines are ignored. Partial lines are buffered. Defaults:
`SERIAL_BAUD=115200`, `GSR_MAX=1023`, `GSR_SPAN=200`. Set matching baud rates on both
ends. The app waits up to six seconds for the first reading (Arduino reset included)
and stops if valid readings disappear for three seconds. It never silently replaces
a lost physical sensor with simulated values. It sends no serial commands to motors
or pumps; opening the port may reset the Arduino.

## Voice, offline use, and secrets

The app calls the [ElevenLabs text-to-speech endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
directly from Python, requesting 24 kHz PCM, wrapping it in WAV, and playing it with
Windows audio. No FFmpeg or extra audio package is needed. The model defaults to
`eleven_multilingual_v2`; change `ELEVENLABS_MODEL_ID` and restart to try another
compatible TTS model. Voice availability depends on your account.

- First-time speech needs internet and ElevenLabs credit. Each uncached line makes
  one request; there are no automatic paid retries. A normal session has six lines.
- WAV clips are cached under `.cache/voice/`, keyed by voice, model, settings and
  text. Repeated lines use the cache. To cover all variants offline, rehearse low,
  medium and high slider responses with voice enabled first. Missing cached lines
  still need the service. Silent rehearsal always works offline.
- Stop immediately stops local playback and prevents pending results from playing.
  A request already sent may still finish and be charged/cached. A new voice job
  can wait for that request to finish (25-second network timeout).
- Only scripted text and voice settings go to ElevenLabs. Raw sensor samples stay
  in memory; they are not uploaded or logged. A selected response variant reflects
  the signal band. There is no session database or telemetry.
- `.env`, `.venv`, caches and output folders are Git-ignored. Commit only
  `.env.example`. Never paste a real key into source, chat, screenshots or issues.
  API headers and raw error bodies are not logged. Existing environment variables
  take precedence over `.env`.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `python` not found / Store opens | Install Python 3.10+ from python.org with Tcl/Tk and Add Python to PATH. Reopen the terminal. |
| `.env` isn't being loaded | Run setup.cmd, then restart. |
| No sound | Select headphones in Windows sound settings; check app/system volume; click Test ElevenLabs voice. |
| Key/voice/access error | Check your key's TTS permission, credit, and the voice/model IDs; restart after editing `.env`. |
| Network failure | Retry when connected, or restart the session with Silent rehearsal selected. |
| No COM port / port busy | Connect Arduino, install requirements, refresh ports, close Arduino Serial Monitor. |
| No valid readings | Match baud rates, send newline-delimited numbers, check `GSR_MAX`. |
| Always maximum change | Reduce simulated slider or increase `GSR_SPAN`; recalibrate with steady contact. |

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\gui_smoke.py
```

Unit tests cover session completion, calibration/data failures, Stop/restart,
recipe bounds, serial parsing, PCM-to-WAV conversion, caching, redacted errors,
and cancellation during an API call. The separate GUI check runs an accelerated
silent session through the real Tk event loop. These require neither a key nor
hardware. Real headphone output, an authenticated ElevenLabs request, and physical
Arduino input still need their corresponding manual checks.

## Why this stack

Python + Tkinter puts the window, USB serial, recipe logic and HTTP calls in one
small process. The two dependencies are `python-dotenv` and `pyserial`; the rest is
standard-library code. A background worker handles speech and another reads USB,
keeping Stop and the window responsive.

Node can do the same work, particularly with an existing web interface. A browser
UI would add a local server/bridge for serial and audio lifecycle handling; Electron
would add packaging. A web UI may be useful later for a polished kiosk or a second
screen, but the native window gets this two-day prototype running sooner. This
version is Windows-specific because it uses `winsound`, and playback uses the
Windows default output rather than an in-app device selector.

For the two-day build: get silent simulation working, add voice, then connect GSR.
Keep cocktail preparation manual until that loop is dependable. Motor and liquid
hardware integration are separate next steps.
