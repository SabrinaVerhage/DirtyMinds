# Uno: one-pump test

This sketch is for a classic Arduino Uno R3 (ATmega328P), one L298N module and
one pump. It runs one 1-second pulse when you send `1`; `0` or `s` stops early.
No Python, LEDs or network is needed. It does not start a pump on boot. Uploading
replaces the sketch currently on the Uno; re-upload the main sketch afterwards.

## Wiring: power off first

Unplug both Uno USB and the motor supply. This is for the common L298N module,
using channel A; confirm the exact board's labels and regulator circuit first.

| Connection | Wire |
| --- | --- |
| Uno D3 | L298N ENA, with its ENA jumper removed |
| 10 kΩ resistor | Between ENA and GND (in addition to the D3 wire) |
| Uno 5V | L298N IN1 |
| Uno GND | L298N IN2 and GND |
| Motor supply 6 V negative | L298N GND (common with Uno GND) |
| Motor supply 6 V positive | L298N motor input, often labelled 12V, VS or VIN |
| Pump's two wires | L298N OUT1 and OUT2 |

The L298N also needs 5 V logic power. Module designs differ: identify its exact
5V terminal and regulator jumper before connecting them. On a module documented
to accept external 5 V on its 5V terminal with the regulator jumper removed, a
USB-powered Uno's 5V output can supply logic for this single module, provided
its current needs fit the USB supply. Never connect motor 6 V to the Uno 5V pin
or connect two 5 V supplies together. Do not guess jumper positions.

For an unused channel B, remove its ENB jumper and tie ENB, IN3 and IN4 to GND
if the module exposes these signals. An accessible switch or disconnect on the
motor supply is required for immediate physical cutoff. Keep electronics dry.

## Test

1. With motor power disconnected, open `uno_pump_test.ino` in Arduino IDE.
2. Select **Arduino Uno** (classic R3) and the Uno's USB port; upload.
3. Open Serial Monitor at **115200 baud**. Nothing should run at startup.
4. After checking the wiring and the module's logic supply, connect motor power.
   Use water in a waste container and keep the motor disconnect within reach.
5. Type `1` and send. The pump runs for one second and stops. Send `0` or `s`
   to stop early. The timer runs on the Uno, even if the USB cable disconnects.
6. Turn off motor power and USB before changing wiring. If direction is wrong,
   swap the pump wires at OUT1 and OUT2 with power disconnected.

An L298N drops voltage, so a 6 V motor on a 6 V supply may run slowly or stall;
do not simply substitute a 12 V supply. The supply needs adequate startup current.
This test has not been verified with your physical hardware.
