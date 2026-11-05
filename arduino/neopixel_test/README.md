# Test 1 — NeoPixel FeatherWing only

1. Keep the **6V motor supply disconnected**. Stack the 4×8 / 32-LED Wing on the
   original HUZZAH32 and plug the Feather into USB.
2. In Arduino IDE, install **Adafruit NeoPixel** from Library Manager if needed.
3. Open `neopixel_test.ino`, select **Adafruit ESP32 Feather**, choose its port,
   and upload.
4. The Wing automatically repeats **all red → all green → all blue → one moving
   pixel → four groups of eight → off**. Brightness is deliberately low.

This confirms all 32 pixels, colour order, and the four banks used by the combined
controller. No pump, motor driver, Python app, or serial command is needed to start.

Optional Serial Monitor controls, **115200 baud**, any line ending:

| Send | Result |
| --- | --- |
| `1`, `2`, `3`, `4` | Hold that eight-pixel bank: pink, amber, green, blue |
| `a` | Restart the automatic loop |
| `0` | All LEDs off |
| `?` | Print instructions again |

The default Wing data-jumper position maps to **GPIO 32 on this HUZZAH32**. The
`6` label in other Feather examples is not ESP32 GPIO 6. If your Wing's solder
jumper was moved, change `PIXEL_PIN` to the corresponding GPIO and also change it
in the combined controller later. Keep only one data jumper bridged. A completely
dark Wing calls for checking the jumper, stacked headers, selected board, and USB
power before changing anything else.

After it works, disconnect power and move on to the
[pump driver test](../pump_driver_test/README.md).

References: [Wing pinouts](https://learn.adafruit.com/adafruit-neopixel-featherwing/pinouts),
[HUZZAH32 pinouts](https://learn.adafruit.com/adafruit-huzzah32-esp32-feather/pinouts).
