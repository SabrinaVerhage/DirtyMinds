# Test 2 — one L298N, one pump, then optionally two

Start with **one pump on channel A**. The NeoPixel Wing can be removed for this
test. The sketch needs no extra Arduino library and never runs a motor on boot.

## Wire one pump

Disconnect USB and motor power while wiring. This is the **ENA-control** wiring
used by the combined controller, not the earlier IN1/IN2 GPIO test.

| L298N connection | Connect to |
| --- | --- |
| Motor supply terminal (`VS`, `VIN`, sometimes labelled `12V`) | Separate **6V supply +** |
| GND | Supply − **and** Feather GND |
| 5V logic terminal | Feather **USB** pin; **remove the 5V-EN regulator jumper first** |
| IN1 | Feather **3V** |
| IN2 | Common GND |
| ENA | Feather **GPIO 27**; **remove the ENA jumper** |
| ENA to GND | **10kΩ pull-down** resistor to keep the pump off during reset |
| OUT1 / OUT2 | Pump A's two wires |
| Unused B channel | Remove ENB jumper; tie ENB, IN3 and IN4 to GND |

The **5V-EN** and **ENA** jumpers are different. USB powers the Feather and driver
logic; the separate 6V supply powers the pump. Never connect 6V to Feather USB,
BAT, 3V or a GPIO. Check the labels on your actual L298N module before power-on.
Keep a physical way to disconnect motor power within reach.

## Upload and test

1. Leave `MOTOR_COUNT` at **1** near the top of `pump_driver_test.ino`.
2. With motor power disconnected, upload using **Adafruit ESP32 Feather** and its
   USB port. No NeoPixel library or Python helper is needed.
3. Open Serial Monitor at **115200 baud**. Send `?` to see instructions.
4. Put the tubing in a water-test setup with a waste container, then connect 6V.
5. Send **`1`**: pump A runs for **one second**, then switches off. Repeat as needed.
6. Send **`0`**, **`s`**, or **`!`** to stop early. It accepts any line-ending setting.

There is no repeating pump loop and no queued sequence. Further start commands
while a pulse is running are ignored. No heartbeat is required: each pulse ends
locally after one second even if the PC disconnects. You can change `TEST_RUN_MS`
at the top; the sketch limits it to 100–3000 ms. An optional normally-open button
between **GPIO 14 and GND** also stops the pulse; releasing it does not restart it.

Use water and discard it, as discussed for the supplied tubing. One second may
show motor movement before water reaches the outlet; repeat short tests to prime.
If direction is wrong, power off and swap the two pump wires. If the pump stalls,
check supply/current and wiring: an L298 drops voltage, so a nominal 6V supply
delivers less at the pump. Do not compensate by connecting a 12V supply.

## Optional second pump on the SAME L298N

Disconnect both power sources. Keep channel A as above, and change channel B:

| Connection | Second-channel wiring |
| --- | --- |
| ENB | **Remove its direct GND wire and its jumper**, then connect Feather **GPIO 33** |
| ENB to GND | Add a **10kΩ pull-down** resistor |
| IN3 | Remove its GND wire, then connect Feather **3V** |
| IN4 | Keep connected to common GND |
| OUT3 / OUT4 | Pump B's two wires |

Change **`#define MOTOR_COUNT 1` to `#define MOTOR_COUNT 2`**, then upload again
with motor power disconnected. Reconnect power and send `1` for A or `2` for B.
**Only one runs at a time**; wait for `OFF` before testing the other. Sending `2`
in the one-motor build reports that B is disabled.

To test two separate driver boards instead, wire channel A on both as in the first
table, with board 1 ENA on GPIO 27 and board 2 ENA on GPIO 33; keep both B channels
disabled. The two-motor sketch works with either arrangement.

## Then use the combined sketch

The same GPIO 27/33 map to pumps 1/2, and the LED test uses GPIO 32, so their pins
already agree with [pump_controller](../pump_controller/README.md). Upload that
sketch after these individual tests pass; no code copying or merging is needed.

Its wiring guide uses **four separate driver boards, channel A on each**, matching
your inventory. If you tested B on the first board, move that pump to channel A of
board 2 and connect GPIO 33 to board 2 ENA to follow that guide; disable the now
unused B channel again. Add pumps 3/4 on GPIO 25/26 as documented there. Run its
`PREVIEW` first. Its real-run commands and heartbeat are different from this test:
use the combined controller's instructions/Python helper then.

References: [L298 datasheet](https://www.st.com/resource/en/datasheet/l298.pdf),
[HUZZAH32 pinouts](https://learn.adafruit.com/adafruit-huzzah32-esp32-feather/pinouts).
