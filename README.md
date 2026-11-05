# Dirty Minds — hardware update (working copy)

**This working copy changes the hardware plan.** The original guide below describes the previous combined Feather pump/LED setup and is retained for historical reference only; its pump and LED wiring instructions no longer apply.

- **Feather HUZZAH32 + NeoPixel Wing:** GSR input over local Wi-Fi, live raw signal on the Wing.
- **Arduino Uno:** four L298N pump channels over USB; screen rehearsal is the default.
- **Qnect plug:** switch the complete ring device on/off manually with its app or button. Python control is not implemented; exact model and local integration remain to be confirmed. The plug does not reverse the motor.

## Feather Wi-Fi test

1. Install the ESP32 board package and Adafruit NeoPixel library in Arduino IDE. Select the original **Adafruit ESP32 Feather**. Copy `arduino/feather_gsr_wifi/wifi_secrets.example.h` to `wifi_secrets.h` in that folder and fill in your Wi-Fi name/password. Never share or commit this file. Use the same trusted 2.4 GHz local network as the PC; guest isolation must be off.
2. Upload `feather_gsr_wifi.ino`; open Serial Monitor at 115200 to read `Feather IP`. For a first test use a potentiometer between Feather **3V** and **GND**, wiper to **GPIO34 / A2**. Never apply more than 3.3 V to the ADC. The bar shows raw ADC value.
3. In the app select **Feather Wi-Fi**, enter that IP in the GSR field, select **Screen rehearsal**, and begin. TCP port 8765 streams values at about 20 Hz. Set `GSR_MAX=1023` and calibrate `GSR_SPAN` for the actual circuit. The app stops a session on a missing stream; it does not substitute simulated readings. The connection is unencrypted and unauthenticated: use a trusted private network, not the public internet.
4. Your DIY GSR circuit still needs a suitable current-limited, battery-powered, electrically isolated body-contact design. This code alone does not make electrodes safe. Do not connect a participant to a USB-powered or mains-connected prototype.

## Uno pump bench

Upload `arduino/uno_pump_controller/uno_pump_controller.ino` with **Arduino Uno** selected. The firmware has not been tested on physical hardware. Uno D3, D5, D6, D9 go to the four driver ENA inputs; optional normally-open stop button D2 to GND. The motor sequence retains arming, timed limits, Stop and a 3-second heartbeat watchdog. PREVIEW never powers a motor.

For each L298N, remove its ENA jumper; ENA is driven by its Uno pin with an external 10 kΩ pull-down to GND to keep it off during reset. For a one-direction test, IN1 = Uno 5 V and IN2 = GND. The motor supply is 6 V, separately sized for startup current; its negative, all driver grounds and Uno GND must be common. Confirm the exact L298N board's regulator jumper and logic supply with its documentation; do not connect 6 V to the Uno's 5 V pin. L298N voltage drop may make 6 V pumps weak. Start with one pump and water, powered separately; keep liquids away from electronics. Test physical power cutoff.

Run `setup.cmd` in this copy, select its Uno COM port, and use the existing bench commands in the older guide below. After measuring each pump's actual ml/s with water, add `PUMP_ML_PER_SECOND` and `ENABLE_REAL_PUMPS=true` to this copy's `.env`. Calibration and a physical power cutoff are still required.

## Qnect ring

For now switch on/off in the Qnect app, separately from the experience. Confirm the ring device is safe and stable, its heaters are not unintentionally active, and that its original controls resume as expected after power is restored. A smart plug is not an emergency stop. Keep its mains electrics away from liquid.

---

## Previous guide — historical reference

# Dirty Minds

A local Windows experience: four whispered brine temptations, four individual
signal responses, one personalised dirty martini. Python 3.10+ and Tkinter; no
hosted website, browser, microphone, server or language model required.

## Try the complete experience with the NeoPixel Wing

1. If already installed, close the old window and double-click **run.cmd**.
   For a new installation, run **setup.cmd** first. It creates `.venv`, installs
   `python-dotenv` and `pyserial`, and creates `.env` only if it does not exist.
2. Keep signal input on **Simulated**. Choose **Feather LEDs** under
   **After the reveal**, then choose the Feather COM port. Close Arduino Serial
   Monitor. The Feather needs the existing combined `pump_controller` sketch;
   the standalone NeoPixel animation does not speak the USB protocol.
3. Select headphones as the Windows default output. Use **Test host** and
   **Four voices… → Listen** to audition the cast. **Whisper** applies to all voices.
   **Silent rehearsal** runs the same sequence with on-screen text and no TTS calls.
   The Listen/Test buttons deliberately play real speech even in silent rehearsal.
4. Click **Begin temptation**. Change the simulated response slider differently in
   each round. The baseline ignores the slider. Each finished score appears beside
   its brine, and the recipe appears after the fourth round.
5. After the reveal, the selected LED row(s) run in order. The final voice waits
   until the Feather reports `DONE`. **Stop / Esc** cancels speech and delivery.

**Feather LEDs never arms or runs motors.** The combined firmware keeps motor
enables LOW during `PREVIEW`. Only connect USB + the Wing for today's test.
**Screen rehearsal** shows the same sequence on screen without opening a Feather
port. The main window also retains **Test brine lights…** for manual row testing.

If using fresh voices, prepare the audio before a live visitor session:

```powershell
cd C:\Users\sabri\Documents\_GITHUB\DirtyMinds
.\.venv\Scripts\python.exe prepare_voices.py
.\.venv\Scripts\python.exe app.py
```

Preparation caches all eight scripted lines using the cast and settings in `.env`.
Uncached phrases use ElevenLabs credit; cached phrases are reused. It does not play
audio and has no automatic paid retries. First generation can take several minutes.
Changing voices only in the window does not change `.env` or the preparation script.

## The experience

Introduction → baseline invitation → 8 seconds of quiet baseline → four rounds,
with a 4-second quiet break between rounds → reveal → brine delivery → final whisper.
Each round measures during the actual voice playback and for 6 seconds afterwards.
Time waiting for ElevenLabs to generate audio is excluded. Silent rounds show the
pitch for 14 seconds and allow the same 6-second response tail. Speech never overlaps.
The silent sequence is about two minutes; spoken timing depends on each recording.

| Round / LED row / pump | Ingredient | Default voice | Personality |
| --- | --- | --- | --- |
| 1 | Silver onion / zilveruitje | Nora | A pale pearl, a sweet secret, a sharp little kiss |
| 2 | Classic olive | Sarah | Velvet salt and a classic temptation |
| 3 | Jalapeño | Shanni | Cool glass, hot intentions |
| 4 | Dutch augurk | Marleen | You call it naughty; I call it lekker |

The host introduces the experience and closes it: “Thank you for sharing your dirty
mind. You deserve a dirty drink.” Edit the copy and ingredient names in
`dirtyminds/core.py`. The four cast members and host can be changed independently.
Marleen is a native Dutch voice speaking the English script; the resulting accent
and whisper are creative choices to audition, not guaranteed by an accent tag.

## How the scores choose the drink

The baseline is the median of smoothed readings during the quiet calibration.
Smoothing uses an exponential moving average (0.22). Each round separately averages
`abs(smoothed - baseline) / GSR_SPAN`, clipped to 0–100%. It also saves the peak and
sample count. Both rising and falling sensor signals count as change. At least ten
readings are required for baseline and for every round.

The highest response selects the brine. If the runner-up scores at least 75% of
the winner, the two share **15 ml total brine** in proportion to their scores.
Otherwise the winner gets all 15 ml. If every response is below 10%, classic olive
is the fallback. Ties prefer olive, then onion, jalapeño, augurk. Example: onion 80%
and olive 60% gives 8.6 ml onion + 6.4 ml olive. Only the strongest two can be mixed.

Every recipe keeps **50 ml gin or vodka + 10 ml dry vermouth** fixed. The controller
dispenses only brines; the base spirit, vermouth, chilling and garnish are manual.
These are prototype recipe quantities: taste and tune the brines before serving.
GSR is an artistic input mapping, not a measurement of thoughts, desire or arousal.
Contact changes, movement and responses carrying over between rounds can influence
the scores; the short breaks are theatrical timing, not a validated experiment.

**Anonymous aggregate results** are saved locally under `output/sessions/` after
each stage, including each finished round, the recipe, output mode and completion
status. A stopped run retains its partial results; restarting makes a new record.
No names, raw sample traces or API keys are saved. The UI states when a file could
not be saved. The live trace itself stays in memory.

## Voices, pauses and secrets

Put `ELEVENLABS_API_KEY` in `.env` with TTS permission. Existing `.env` contents are
preserved by updates. Missing new settings automatically use defaults. An empty
key selects silent rehearsal. API headers and raw service errors are not logged.
Only scripted text and voice settings go to ElevenLabs; sensor data stays local.

| Setting | Default for new installs |
| --- | --- |
| `ELEVENLABS_VOICE_ID` (host) | Nora: `1ykC5GeLM4dP82qkyo91` |
| `VOICE_ONION` | Nora: `1ykC5GeLM4dP82qkyo91` |
| `VOICE_OLIVE` | Sarah: `EXAVITQu4vr4xnSDxMaL` |
| `VOICE_JALAPENO` | Shanni: `A6TsrDqI2qlO9AWAfZHY` |
| `VOICE_PICKLE` | Marleen: `AIFcvMreCoOxyPTbUrwe` |

The **Four voices…** window accepts a menu choice or a pasted voice ID; changes
there last until restart. To keep a cast, set the four IDs above in `.env`.
The host menu also retains Trevor (`17JdVkQHD6PE3HPohzr2`), but Nora's previous
samples had quieter gaps. New library voices depend on account access. If one is
unavailable, choose an accessible voice in the cast window or change its `.env` ID.

Whisper mode uses `eleven_v3`, starts **each short phrase** with `[whispering]`, and
inserts **900 ms of actual silence** between phrases (at most ten words per phrase).
Set `ELEVENLABS_WHISPER_PAUSE_MS=0..3000` to change the gap. Changing only the gap
reuses phrase clips. Ordinary speech uses `ELEVENLABS_MODEL_ID`, default
`eleven_multilingual_v2`. Generation is scripted TTS, not a live voice agent.
See the [ElevenLabs TTS guidance](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices).

Playback keeps the earlier **20 ms fade-in / 120 ms fade-out** per phrase and a
**90 Hz high-pass filter** in whisper mode to reduce low rumble. It does not remove
every generated noise. Raw WAV phrases stay intact in `.cache/voice/`; cleaned
playback is separately cached in `.cache/voice/playback/`. A full prepared cast can
play offline. Missing phrases require internet and credit.

Stop immediately stops local playback. A request already sent may still finish and
be charged/cached, but its result will not play. Cancelled generation stops before
requesting another phrase. A subsequent job may wait for the outstanding request's
25-second network timeout. Each job keeps its own voice/settings snapshot.

`.env`, `.venv`, caches and `output/` are Git-ignored. Commit only `.env.example`.
Never paste keys into source, screenshots, chat or issues. Environment variables
take precedence over `.env`. Python `winsound` uses Windows default audio output.

## Adding real GSR

Upload `arduino/gsr_reader/gsr_reader.ino` to a separate Arduino. It reads A0 at
20 Hz and sends ASCII `512\n` or `GSR:512\n` at 115200 baud. Use a suitable sensor
module; that sketch is not a body-contact circuit design. A potentiometer is useful
for testing. Close Serial Monitor, select **Arduino USB**, and choose its port.

Default `.env` settings: `SERIAL_BAUD=115200`, `GSR_MAX=1023`, `GSR_SPAN=200`.
For a 12-bit ADC use `GSR_MAX=4095` and tune the span. Match the board's baud rate.
Invalid, non-finite, overlong and out-of-range input is ignored; fragments are
buffered. A missing first reading after six seconds, or a three-second dropout,
stops the session. The app never substitutes simulation for a disconnected sensor.

The GSR board and Feather controller need separate ports. The app rejects using
the same port for both. The GSR reader does not receive motor commands.

## Pump hardware, when the wires arrive

Follow [the Arduino test order](arduino/README.md): standalone
[NeoPixel test](arduino/neopixel_test/README.md), then
[one/two motor driver test](arduino/pump_driver_test/README.md), then the
[combined controller wiring guide](arduino/pump_controller/README.md).
The original HUZZAH32, four L298N boards, 6 V pumps and 32-pixel Wing retain the
existing pin assignments. The Python update does not require a firmware change
if your current combined sketch already responds to the app's row tests.

For today's **Feather LEDs** mode, the recipe becomes a six-second visual sequence,
split according to the chosen brine amounts. These durations are **not pump flow
calibration**. USB uses `HELLO` then `PREVIEW t1 t2 t3 t4`. The on-screen row follows
the controller's `START`/`PUMP_DONE` replies, and the session waits for `DONE`.
Replies confirm controller state, not measured light or liquid output.

After water tests, measure every pump's ml/second. Set `PUMP_PORT` and four measured
`PUMP_ML_PER_SECOND` values in onion, olive, jalapeño, pickle order, then explicitly
set `ENABLE_REAL_PUMPS=true`. This exposes **Calibrated pumps** in the output menu;
the startup selection remains **Feather LEDs**. Real mode sends `ARM` then `SEQ`
and calculates each duration as `ml / measured_ml_per_second`. No assumed flow
rates are supplied. Positive durations must be at least 100 ms and at most 180 s
per pump, with at most 600 s total, matching firmware limits.

Only one pump runs at once, with a 300 ms inter-pump gap. Python sends heartbeats;
the combined firmware stops real motors after three seconds without one. Stop
attempts `!`, and cancellation/failure never triggers the final voice or an automatic
retry. Opening USB may reset the Feather. Keep a physical way to cut motor power.

Bench controls remain available:

```powershell
.\.venv\Scripts\python.exe pump_control.py ports
.\.venv\Scripts\python.exe pump_control.py --port COM3 preview
.\.venv\Scripts\python.exe pump_control.py --port COM3 run 1 2
```

The last command is a real two-second motor test, only for the wired/calibrated bench.

## Checks and troubleshooting

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\gui_smoke.py
```

The tests require no API key or hardware. They cover separate scores, generation
exclusion, recipe bounds, voice cancellation and per-job cast, audio processing,
serial parsing, motor/preview protocol, delivery cancellation and local records.
The GUI check runs silent and mocked-voice sessions through the real Tk event loop,
including the delivery gate, failure, Stop/restart and layout. Physical hardware,
voice character and liquid flow still require hands-on checks.

| Problem | Check |
| --- | --- |
| No sound | Windows default headphones, app/system volume, Test host. |
| Long first pause | Run `prepare_voices.py` before the session; fresh phrases take time. |
| One voice fails | Its cast ID, account access and TTS credit; swap it in Four voices. |
| Click/hum | Restart for fades/filter; audition Nora. Stop intentionally cuts audio immediately. |
| USB busy/no reply | Close Serial Monitor; choose the Feather port and upload combined firmware. |
| No valid GSR | Separate port, matching baud, newline values, suitable `GSR_MAX`. |
| Always high response | Lower slider or increase `GSR_SPAN`; recalibrate with still contact. |
| Recipe shown but sequence failed | Check cable/port and start a fresh session; there is no automatic repour. |

Python + Tkinter keeps USB, audio and the window in one small process. Node could
do this too, especially with an existing web UI, but a browser would add a local
bridge/server and Electron adds packaging. For this two-day local prototype,
Python avoids those extra moving parts. The audio player is currently Windows-only.
