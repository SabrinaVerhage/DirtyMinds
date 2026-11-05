// Dirty Minds: HUZZAH32 + four L298N channels + 32-pixel NeoPixel FeatherWing.
// Read README.md in this folder before wiring. No automatic motor run on boot.
#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include "pump_engine.h"

#if !defined(ARDUINO_AVR_UNO)
#error Select Arduino Uno.
#endif

PumpEngine engine;
char inputLine[96];
size_t inputLength = 0;
bool discardingLine = false;
uint32_t lastPixelUpdate = 0;
int8_t reportedActive = -1;
bool reportedRunning = false;
const char* reportedStop = nullptr;

void sendLine(const char* text) {
  // Never allow an unconsumed serial response to delay switching a motor off.
  if (Serial.availableForWrite() >= int(strlen(text) + 2)) Serial.println(text);
}

void applyOutputs() {
  // First lower all inactive channels, then raise the one selected channel.
  const int8_t selected = engine.motorOutput();
  for (uint8_t i = 0; i < PUMP_COUNT; ++i)
    if (i != selected) digitalWrite(PUMP_ENABLE_PINS[i], LOW);
  if (selected >= 0) digitalWrite(PUMP_ENABLE_PINS[selected], HIGH);
}

void reportChanges(uint32_t now) {
  char message[112];
  if (reportedActive != engine.active) {
    if (reportedActive >= 0 && (engine.completed & (1U << reportedActive))) {
      snprintf(message, sizeof(message), "PUMP_DONE pump=%d", reportedActive + 1);
      sendLine(message);
    }
    if (engine.active >= 0) {
      snprintf(message, sizeof(message), "START pump=%d ms=%lu preview=%d",
               engine.active + 1, (unsigned long)engine.remaining(now), engine.preview);
      sendLine(message);
    }
    reportedActive = engine.active;
  }
  if (engine.stopped && engine.stopped != reportedStop) {
    snprintf(message, sizeof(message), "STOPPED %s", engine.stopped);
    sendLine(message);
  } else if (reportedRunning && !engine.running && !engine.stopped) {
    sendLine("DONE");
  }
  reportedStop = engine.stopped;
  reportedRunning = engine.running;
}

void stopNow(const char* reason) {
  engine.stop(reason);
  applyOutputs();
}

bool parseUnsigned(const char* text, uint32_t* result) {
  if (!text || !*text) return false;
  uint32_t value = 0;
  for (const char* p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    const uint32_t digit = *p - '0';
    if (value > (UINT32_MAX - digit) / 10) return false;
    value = value * 10 + digit;
  }
  *result = value;
  return true;
}

void executeCommand(char* line, uint32_t now) {
  char* words[7];
  uint8_t count = 0;
  char* state = nullptr;
  for (char* part = strtok_r(line, " \t", &state); part; part = strtok_r(nullptr, " \t", &state)) {
    if (count >= 7) { sendLine("ERR TOO_MANY_ARGUMENTS"); return; }
    words[count++] = part;
  }
  if (!count) return;
  for (char* p = words[0]; *p; ++p) *p = toupper((unsigned char)*p);
  if (!strcmp(words[0], "STOP")) {
    stopNow("USER");
    sendLine("OK STOP");
    return;
  }
  if (!strcmp(words[0], "HELLO") && count == 1) {
    sendLine("DIRTYMINDS_PUMPS 1 pumps=4 max_ms=180000 heartbeat_ms=3000");
    return;
  }
  if (!strcmp(words[0], "PING") && count == 1) {
    engine.ping(now);
    sendLine("PONG");
    return;
  }
  if (!strcmp(words[0], "STATUS") && count == 1) {
    char message[112];
    snprintf(message, sizeof(message), "STATUS armed=%d running=%d preview=%d pump=%d remaining_ms=%lu",
             engine.armed, engine.running, engine.preview, engine.active + 1,
             (unsigned long)engine.remaining(now));
    sendLine(message);
    return;
  }
  if (!strcmp(words[0], "ARM") && count == 1) {
    if (digitalRead(STOP_BUTTON_PIN) == LOW) { sendLine("ERR STOP_BUTTON"); return; }
    sendLine(engine.arm(now) ? "OK ARM" : "ERR BUSY");
    return;
  }
  uint32_t requested[PUMP_COUNT] = {};
  bool lightsOnly = !strcmp(words[0], "PREVIEW");
  bool sequence = !strcmp(words[0], "SEQ");
  if (lightsOnly && count == 1) {
    for (uint8_t i = 0; i < PUMP_COUNT; ++i) requested[i] = 2000;
  } else if ((lightsOnly || sequence) && count == 5) {
    for (uint8_t i = 0; i < PUMP_COUNT; ++i) {
      if (!parseUnsigned(words[i + 1], &requested[i])) { sendLine("ERR BAD_NUMBER"); return; }
    }
  } else if (!strcmp(words[0], "RUN") && count == 3) {
    uint32_t pump, duration;
    if (!parseUnsigned(words[1], &pump) || !parseUnsigned(words[2], &duration) || pump < 1 || pump > 4 || duration == 0) {
      sendLine("ERR BAD_RUN"); return;
    }
    requested[pump - 1] = duration;
  } else {
    sendLine("ERR COMMAND_USE_HELLO_STATUS_PREVIEW_ARM_RUN_SEQ_STOP");
    return;
  }
  if (digitalRead(STOP_BUTTON_PIN) == LOW) { sendLine("ERR STOP_BUTTON"); return; }
  const char* error = engine.start(requested, lightsOnly, now);
  applyOutputs();
  if (error) {
    char message[80];
    snprintf(message, sizeof(message), "ERR %s", error);
    sendLine(message);
  } else {
    sendLine("OK START");
  }
}

void readCommands() {
  // Bound work so serial flooding cannot starve the motor timer or stop button.
  for (uint8_t budget = 0; budget < 64 && Serial.available(); ++budget) {
    int value = Serial.read();
    if (value < 0) break;
    char c = char(value);
    if (c == '!') { // Immediate stop, even in a partial or overlong line.
      inputLength = 0;
      discardingLine = false;
      stopNow("USER");
      sendLine("OK STOP");
    } else if (c == '\n') {
      if (!discardingLine) {
        inputLine[inputLength] = '\0';
        executeCommand(inputLine, millis());
      }
      inputLength = 0;
      discardingLine = false;
      reportChanges(millis());
    } else if (c != '\r' && !discardingLine) {
      if ((c < 32 && c != '\t') || c > 126 || inputLength >= sizeof(inputLine) - 1) {
        discardingLine = true;
        inputLength = 0;
        stopNow("BAD_INPUT");
        sendLine("ERR INPUT_TOO_LONG_OR_INVALID");
      } else {
        inputLine[inputLength++] = c;
      }
    }
  }
}

void setup() {
  // External 10k pull-downs on ENA keep drivers off before this code executes.
  for (uint8_t i = 0; i < PUMP_COUNT; ++i) {
    digitalWrite(PUMP_ENABLE_PINS[i], LOW);
    pinMode(PUMP_ENABLE_PINS[i], OUTPUT);
  }
  pinMode(STOP_BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  sendLine("DIRTYMINDS_PUMPS 1 pumps=4 max_ms=180000 heartbeat_ms=3000");
}

void loop() {
  uint32_t now = millis();
  if (digitalRead(STOP_BUTTON_PIN) == LOW) stopNow("BUTTON");
  engine.tick(now);
  applyOutputs();
  reportChanges(now);
  readCommands();
  // Check again after serial input, before spending time on the LEDs.
  engine.tick(millis());
  applyOutputs();
  reportChanges(millis());
  delay(1);
}
