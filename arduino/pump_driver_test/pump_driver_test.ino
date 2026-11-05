// TEST 2: original HUZZAH32 + one L298N board + one or two 6V pumps.
// Read README.md first: this uses ENA/ENB, with fixed direction wiring.
// No NeoPixel library, Python app, or combined sketch is required.
#include <Arduino.h>
#include <string.h>

#if !defined(ARDUINO_FEATHER_ESP32)
#error Select the original "Adafruit ESP32 Feather" board.
#endif

// Start with 1. Change to 2 and re-upload after wiring the second channel.
#ifndef MOTOR_COUNT
#define MOTOR_COUNT 1
#endif
constexpr uint8_t ENABLE_PINS[] = {27, 33}; // ENA, optional ENB.
constexpr uint8_t UNUSED_ENABLE_PINS[] = {25, 26};
constexpr uint8_t STOP_BUTTON_PIN = 14;    // Optional button to GND.
constexpr uint32_t TEST_RUN_MS = 1000;     // One second per command.
static_assert(MOTOR_COUNT == 1 || MOTOR_COUNT == 2, "Use 1 or 2 motors.");
static_assert(TEST_RUN_MS >= 100 && TEST_RUN_MS <= 3000, "Keep tests 0.1-3 seconds.");

int8_t activeMotor = -1;
uint32_t startedAt = 0;

void say(const char* text) {
  // A closed/busy Serial Monitor must not delay turning a motor off.
  if (Serial.availableForWrite() >= int(strlen(text) + 2)) Serial.println(text);
}

void allOff() {
  for (uint8_t pin : ENABLE_PINS) digitalWrite(pin, LOW);
  activeMotor = -1;
}

void printHelp() {
  say("PUMP TEST: 1 = motor A; 0 / s / ! = STOP; ? = help.");
  say(MOTOR_COUNT == 2 ? "2 = motor B. Only one motor runs at a time."
                      : "Motor B disabled. Set MOTOR_COUNT to 2 to test it.");
  say("Each command runs one timed pulse. Nothing starts on boot.");
}

void startMotor(uint8_t index) {
  if (index >= MOTOR_COUNT) { say("Motor B disabled. Set MOTOR_COUNT to 2."); return; }
  if (digitalRead(STOP_BUTTON_PIN) == LOW) { say("Release Stop button first."); return; }
  if (activeMotor >= 0) { say("Busy. Wait for OFF, or send 0 to stop."); return; }
  allOff();
  activeMotor = index;
  startedAt = millis();
  digitalWrite(ENABLE_PINS[index], HIGH);
  say(index == 0 ? "Motor A ON" : "Motor B ON");
}

void checkStop() {
  if (digitalRead(STOP_BUTTON_PIN) == LOW) {
    bool wasRunning = activeMotor >= 0;
    allOff();
    if (wasRunning) say("OFF: Stop button.");
  } else if (activeMotor >= 0 && uint32_t(millis() - startedAt) >= TEST_RUN_MS) {
    allOff();
    say("OFF: timed pulse finished.");
  }
}

void setup() {
  // 10k pull-downs on ENA/ENB keep them low before setup runs / during reset.
  for (uint8_t pin : ENABLE_PINS) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  for (uint8_t pin : UNUSED_ENABLE_PINS) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  pinMode(STOP_BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  printHelp();
}

void loop() {
  checkStop();
  for (uint8_t budget = 0; budget < 32 && Serial.available(); ++budget) {
    checkStop();
    char command = Serial.read();
    if (command == '0' || command == 's' || command == 'S' || command == '!') {
      allOff();
      say("OFF: stopped.");
    } else if (command == '1' || command == '2') {
      startMotor(command - '1');
    } else if (command == '?') {
      printHelp();
    } else if (command != '\r' && command != '\n' && command != ' ' && command != '\t') {
      allOff();
      say("OFF: unknown command. Use 1, 2, 0 or ?.");
    }
  }
  checkStop();
  delay(1);
}
