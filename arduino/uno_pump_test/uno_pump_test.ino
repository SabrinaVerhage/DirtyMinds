// One-pump bench test for the classic Arduino Uno. See README.md before wiring.
#include <Arduino.h>

#if !defined(ARDUINO_AVR_UNO)
#error Select Arduino Uno (classic Uno R3) in the Arduino IDE.
#endif

const byte PUMP_PIN = 3;  // Driver ENA; 10k resistor from ENA to GND.
const unsigned long RUN_MS = 3000;
bool running = false;
unsigned long started = 0;

void stopPump() {
  digitalWrite(PUMP_PIN, LOW);
  running = false;
}

void setup() {
  digitalWrite(PUMP_PIN, LOW);
  pinMode(PUMP_PIN, OUTPUT);
  Serial.begin(115200);
  Serial.println(F("Uno pump test: send 1 for one second; 0 stops."));
}

void loop() {
  if (running && (unsigned long)(millis() - started) >= RUN_MS) {
    stopPump();
    if (Serial.availableForWrite() >= 5) Serial.println(F("OFF"));
  }
  if (Serial.available()) {
    char command = Serial.read();
    if (command == '0' || command == 's' || command == 'S') {
      stopPump();
      if (Serial.availableForWrite() >= 9) Serial.println(F("STOPPED"));
    } else if (command == '1' && !running) {
      started = millis();
      running = true;
      digitalWrite(PUMP_PIN, HIGH);
      if (Serial.availableForWrite() >= 17) Serial.println(F("ON for 1 second"));
    }
  }
}
