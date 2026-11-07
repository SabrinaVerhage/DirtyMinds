# Dirty Minds · The Dirty Mind Diagnostic

**Department of Inappropriate Responses**

An experimental procedure for detecting inappropriate responses and prescribing
corrective cocktails. The patient listens through headphones and relaxes with
the sensor glove on. The installation maps skin-conductance changes to brine.

## Run an appointment

Run `setup.cmd` once, then open `run.cmd`. The app starts fullscreen on **Feather
USB** with the saved ports. It selects **Calibrated pumps** if a matching
calibration exists and **Uno water rehearsal** otherwise. Both modes use the Uno
hardware when you start a session. Uno water rehearsal uses timed pulses. **F11** toggles fullscreen. **Esc** stops active
speech, monitoring, or delivery. When idle in the operator view with the console
closed, Esc exits fullscreen.

Choose **Patient view** or press **F10** to cover the operator view with a black
screen with a terminal log driven by the appointment stages. It shows **Taking
baseline**, **Dirty 1 / 3** through **Dirty 3 / 3**, **Assessing responses**, and
the active brine during pumping, and the drink title at discharge. A live GSR
response trace and changing background follow the signal. Each two-second
**Recording response** screen shows that round’s normalized score. The final
bars show estimated calibrated volumes, or recipe targets alongside actual
pump times in Uno water rehearsal. The spoken lines stay in the headphones. Press
**F10** again to return to the operator view while the appointment continues.
The activity stream follows the current round while hidden and resumes in place
when reopened. Press **F8** to start a **New session** from either view when the
app is idle. The shortcut keeps the patient view open.
**Esc** still stops the active procedure from the patient display.

Select headphones as the Windows default audio output. Use **Three voices → Listen**
to audition each brine in Whisper mode. **Test headphones** plays the intake
jingle and a professor test line. Select **New session** when the patient is
ready. The live controls offer physical sensor and pump modes.

The procedure runs through patient intake, an eight-second baseline reading, three
character whispers with two-second response displays, the cocktail prescription,
delivery, and discharge. Each round scores signal change during playback and the following six
seconds. Each score's share of the sum becomes that brine's share of the 15 ml
total. For example, scores of 60, 30 and 10 give 9, 4.5 and 1.5 ml. If all three
scores are zero, each brine gets 5 ml. Add the base spirit and dry vermouth separately.

## Cast and prescription names

| Pump | Character | Default ElevenLabs voice |
| --- | --- | --- |
| 1 | The Olive · dry British understatement and impeccable manners | Trevor · British |
| 2 | The Jalapeño · playful dares that turn up the heat | Ernesto · Mexican-American English |
| 3 | The Pickled Onion · awkward intimacy, layers, and confessions | Kim from MindCastle · Dutch-accented English |

Daniel, a formal British voice, plays the dry professor at intake and discharge
and reads the clinic instructions. Set `VOICE_PROFESSOR` to change that voice.
The three brines keep their separate whisper voices. The original Australian
Trevor Whisper voice is available in the cast menu. Library voices require access in
your ElevenLabs account. Set `ELEVENLABS_API_KEY` in `.env` for speech. Save custom
IDs using `VOICE_ONION`, `VOICE_OLIVE`, and `VOICE_JALAPENO`. The app upgrades
previous bundled default IDs and preserves other custom IDs. Existing `.env`
files are preserved. With **Whisper delivery** and **Breaths and sighs** on, each
brine gets two breath or sigh cues and longer pauses between phrases. The professor
keeps the steady delivery.

Add `OPENAI_API_KEY` to `.env` and restart. With **Fresh script** enabled, each
**New session** requests a new deadpan professor opening and one new whisper for
each brine. The professor explains the three-voice test. The anonymous brines
each try to sell their own juice with slow, suggestive descriptions of liquid
through tubing, pump pulses, and what their brine adds to the glass. Fresh scripts
vary the selling angles. After the rounds, OpenAI uses the strongest-response pitch and the blend
to make a punny martini title. Recent session titles are checked for repeats.
If generation fails or runs past the show deadline, the appointment uses house
copy or a house title. Turn off
**Fresh script** and run `prepare_voices.py` with the chosen cast to cache the
fixed house audio. The name can still be generated when Fresh script is off.
The spoken title uses ElevenLabs when it is first announced.

The WAV files in `assets/` play locally. The intake jingle precedes the professor
and a soft tone cues each of the three whispers. Round scoring starts with the
spoken whisper. A short waiting tune plays during preparation, or as a brief
lead-in if preparation has already finished. The professor announces the title.

OpenAI receives the fictional cast briefs for the whispers and the leading pitch,
brine volumes and recent cocktail titles for the name. The app saves the prescription name, recipe,
character lines, aggregate responses, delivery mode and completion status to
`output/sessions/`. A screen or water rehearsal is identified by its mode.
The most recent Feather IP, sensor USB port and Uno USB port are remembered in
`output/connections.json`. Those files stay local.

## Operate the hardware

Open **Hardware console** to enter the Feather IP, monitor live GSR, choose the
Uno USB port and run **Check Uno**. Stop the live monitor before starting an
appointment. The console and the appointment share the Feather IP.

For bench work with water, the console starts at five seconds per channel.
Enable individual water tests to pulse a channel on demand. Channel 4 is
available for bench tests. Appointments use channels 1–3. Open **Pump
assignments** to change which brine is connected to each Uno channel. The
assignment is saved locally. Changing it disables calibrated pours until
you measure the new assignment.

**Uno water rehearsal** runs the chosen channels at their configured times.
For **Calibrated pumps**, choose the Uno USB port in **Hardware console**, then
open **Calibrate pumps**. Enable pump tests with a cup under the selected outlet.
Use **Prime 2 s** as needed to fill the tubing and get a steady flow. Empty the
cup, run a timed test, and enter the measured ml after the controller reports
completion. Start at five seconds and aim for a sample of several ml. Repeat for
each brine. For example, 8 ml in 5 seconds is 1.6 ml/s.

Use the show brine and tubing for the final measurements. **Save calibration**
stores the rates in `output/pump_calibration.json` and unlocks **Calibrated pumps**.
Choose that mode separately to use the measured rates. Calibrations are tied
to the pump assignments. Legacy `PUMP_ML_PER_SECOND` values in `.env` apply only
with the original onion, olive, jalapeño channel order. The controller runs
one pump at a time with a short gap. If a small share falls below the 100 ms minimum
pulse, the app redistributes enough volume to reach the minimum while keeping
the 15 ml total. The session log records the requested percentages, pump timings
and estimated calibrated volumes.

In both Uno modes, the app opens the controller at the reveal and starts the
sequence when reveal playback starts. In a silent run, the sequence starts when
the controller is ready. Discharge waits for both the reveal and the sequence
to finish. Close the separate pump test window or Serial Monitor before starting.

## Debug log and audio waits

Select **Open debug log** in the operator view or Hardware console. The console
shows live events and the file at `output/debug.log` keeps them between launches.
Search for `OpenAI /` to see requests for the professor intro, three whispers and
prescription title. Each result shows success, an HTTP error code, a network or
response problem, or a missed show deadline, along with any fallback.
Look for `UI / refresh delayed` to spot a stall and `Voice / playback started after`
to see how long the app waited for audio. Sensor connection timing, delivery
events and callback errors are also recorded.

Fresh lines need new ElevenLabs audio, so the wait before the first word can
be longer. For a live run with prepared audio, uncheck **Fresh script** and
run `prepare_voices.py` ahead of time using the show cast and settings.

## Current hardware

- **Feather HUZZAH32 + NeoPixel Wing:** GSR over USB serial or local Wi-Fi, with raw signal on the Wing.
- **Arduino Uno:** four L298N pump channels over USB; screen rehearsal is the default.

## Feather USB when Wi-Fi is unavailable

1. With the glove off the participant, connect the Feather with a USB data cable.
   Open [feather_gsr_serial.ino](arduino/feather_gsr_serial/feather_gsr_serial.ino)
   in Arduino IDE. Select **Adafruit ESP32 Feather** and the Feather COM port,
   then upload. The sketch uses the same A2 / GPIO34 input and NeoPixel Wing
   connection as the Wi-Fi sketch.
2. At **115200 baud**, Serial Monitor should show lines such as `GSR:512`.
   Close Serial Monitor, then select **Feather USB** under Signal input in the
   app. Choose the Feather COM port. Keep the pump Uno on its separate COM port.
   The serial sketch sends 10-bit readings, so use `GSR_MAX=1023`.
3. Bench-test with a suitable dummy input. Use a wired glove on a participant
   only if the complete setup has verified body-contact electrical isolation.

## Feather Wi-Fi test

1. Install the ESP32 board package and Adafruit NeoPixel library in Arduino IDE. Select the original **Adafruit ESP32 Feather**. In the sketch folder, create `wifi_secrets.h` with `#define WIFI_SSID "your network"` and `#define WIFI_PASSWORD "your password"` on separate lines. Use the same trusted 2.4 GHz local network as the PC with guest isolation disabled.
2. Upload `feather_gsr_wifi.ino`; open Serial Monitor at 115200 to read `Feather IP`. For a first test use a potentiometer between Feather **3V** and **GND**, wiper to **GPIO34 / A2**. Never apply more than 3.3 V to the ADC. The bar shows raw ADC value.
3. In the app select **Feather Wi-Fi**, enter that IP in the GSR field, select the Uno output mode, and begin. TCP port 8765 streams values at about 20 Hz. Set `GSR_MAX=1023` and calibrate `GSR_SPAN` for the actual circuit. The app stops a session on a missing stream; it does not substitute simulated readings. The connection is unencrypted and unauthenticated: use a trusted private network, not the public internet.
4. Your DIY GSR circuit still needs a suitable current-limited, battery-powered, electrically isolated body-contact design. This code alone does not make electrodes safe. Do not connect a participant to a USB-powered or mains-connected prototype.

## Uno pump bench

Upload `arduino/uno_pump_controller/uno_pump_controller.ino` with **Arduino Uno** selected. The firmware has not been tested on physical hardware. Uno D3, D5, D6, D9 go to the four driver ENA inputs; optional normally-open stop button D2 to GND. The motor sequence retains arming, timed limits, Stop and a 3-second heartbeat watchdog. PREVIEW never powers a motor.

For each L298N, remove its ENA jumper; ENA is driven by its Uno pin with an external 10 kΩ pull-down to GND to keep it off during reset. For a one-direction test, IN1 = Uno 5 V and IN2 = GND. The motor supply is 6 V, separately sized for startup current; its negative, all driver grounds and Uno GND must be common. Confirm the exact L298N board's regulator jumper and logic supply with its documentation; do not connect 6 V to the Uno's 5 V pin. L298N voltage drop may make 6 V pumps weak. Start with one pump and water, powered separately; keep liquids away from electronics. Test physical power cutoff.

Run `setup.cmd` in this copy, select its Uno COM port, and use water for initial bench checks. Use **Calibrate pumps** in the Hardware console to measure the show flow rates. Keep the physical power cutoff accessible.

---

## Previous four-character app and combined Feather setup · historical reference

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

## Uno pump test window

After running `setup.cmd`, upload `arduino/uno_pump_controller/uno_pump_controller.ino`
to the classic Uno R3. Close Arduino Serial Monitor, then open `start_pump_test.cmd`.
Select the Uno COM port. Each pump button runs for three seconds; Test all runs
pumps one at a time. Use water, verify each channel separately, and keep a motor
power disconnect accessible. The 10k enable pull-downs and correct 5V regulator
jumper configuration are required; see `arduino/uno_pump_test/README.md`.
The STOP button requests a stop; the firmware has a heartbeat timeout if USB fails.
The one-pump sketch is a separate test and is replaced when the main sketch uploads.
