# Test each part first

Upload **one sketch at a time**. Uploading replaces the previous sketch on that
board; keep all the folders here so you can return to any test. The standalone LED,
pump and GSR tests work without Python; the USB lights test uses the desktop app.

| Order | Open in Arduino IDE | What it tests |
| --- | --- | --- |
| 1 | [neopixel_test.ino](neopixel_test/neopixel_test.ino) | USB + HUZZAH32 + 32-LED Wing only |
| 2 | [pump_controller.ino](pump_controller/pump_controller.ino), app's **Test brine lights…** | Python → USB → full LED rows; no motor driver |
| 3 | [pump_driver_test.ino](pump_driver_test/pump_driver_test.ino) | One L298N channel and one pump; optional second channel/pump |
| Separate sensor test | [gsr_reader.ino](gsr_reader/gsr_reader.ino) | Existing standalone analog/USB reader, on a separate board |
| Once the parts work | [pump_controller.ino](pump_controller/pump_controller.ino) | Combined four-pump controller with LED progress |

For the two new sketches, select **Adafruit ESP32 Feather**, the original
HUZZAH32, and its USB port. They use Serial Monitor at **115200 baud**. The tests
accept single characters, so any Serial Monitor line-ending setting works.

Start with the [LED instructions](neopixel_test/README.md), then the Python lights
test below, then the [pump wiring and instructions](pump_driver_test/README.md).
After those pass, follow the [combined controller guide](pump_controller/README.md).
There is no need to paste sketches together: the combined controller already
contains both functions.

## Python to Feather: lights only

1. Connect **only the HUZZAH32 + NeoPixel Wing to USB**. No motor controller or
   6V supply is needed for this test.
2. Upload the **updated combined `pump_controller` sketch**, with all its `.h`
   files in the same folder. Select **Adafruit ESP32 Feather**. Its `PREVIEW`
   commands keep every motor enable LOW.
3. Close Arduino Serial Monitor, restart `run.cmd`, and click **Test brine lights…**.
4. Select the Feather COM port. Click **Brine 1**, then 2, 3, 4. Each selected
   physical row of eight pixels lights fully for two seconds, then goes dark.
   **Test all four** runs all rows in order; **Stop / Esc** cancels. Closing the
   window also requests Stop and releases USB.

| App button | Meaning | Wing row / zero-based pixel indices | Colour |
| --- | --- | --- | --- |
| Brine 1 | Brine pump 1 | Row 1 / 0–7 | Pink |
| Brine 2 | Brine pump 2 | Row 2 / 8–15 | Amber |
| Brine 3 | Brine pump 3 | Row 3 / 16–23 | Green |
| Brine 4 | Brine pump 4 | Row 4 / 24–31 | Blue |

These groups follow the physical rows in the
[Adafruit PCB data chain](https://github.com/adafruit/Adafruit-NeoPixel-FeatherWing-PCB).
If you turn the Wing upside down, row 1 will appear at the opposite edge; use the
individual buttons to label your mounted orientation. The PC picture follows
the board's reported active row; inspect the physical Wing to confirm the LEDs.

Example: button 3 sends `PREVIEW 0 0 2000 0`. The board acknowledges `OK START`,
reports `START pump=3 ms=2000 preview=1`, then `PUMP_DONE pump=3` and `DONE`.
The helper also sends `PING`. It opens/checks/closes the port for each test, so the
Feather may reset briefly between tests. No ARM or real motor-run command is sent.
The standalone LED animation sketch is a different test and will not respond to
this protocol. If the app says no pump firmware was found, check that the combined
sketch is uploaded and the right COM port selected.

An unplugged cable may prevent Stop arriving, but this lights-only preview is
bounded: one row lasts two seconds; all four finish in about nine seconds.
The real motor-run mode separately has the three-second heartbeat stop.

The four channels are different brines. Names and automatic GSR-to-brine selection
are not assigned yet; first verify these four manual choices. The existing recipe
generator still calculates an olive-brine amount independently.

## Existing GSR / analog test

`gsr_reader` already is a small, separate test sketch. Choose the board you actually
use for GSR in Arduino IDE. It sends one `analogRead(A0)` value every 50 ms at
115200 baud; open Serial Plotter to see it change. For a bench check, connect a
potentiometer's outer terminals to that board's **3V/3.3V and GND**, and its centre
terminal to **A0**. An ESP32 input must not receive 5V. Use an appropriate GSR
module's analog output later; this sketch does not specify a body-contact circuit.

On the original HUZZAH32, A0 is GPIO 26 and readings are normally 0–4095; set
`GSR_MAX=4095` in the app for that board. A 10-bit Arduino normally uses 0–1023.
Keep GSR on a **separate board/port** from the combined pump controller: its GPIO
26 is assigned to pump 4. Close Serial Plotter before connecting the app.

## Checks performed

The NeoPixel test and both `MOTOR_COUNT=1` / `MOTOR_COUNT=2` pump-test builds are
compiled for `esp32:esp32:featheresp32`. Physical LEDs, wiring and pump movement
still need the bench tests above. Compiling never uploads or starts a pump.
