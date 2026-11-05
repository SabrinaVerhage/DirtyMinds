#pragma once
#include <stdint.h>

// Original Adafruit HUZZAH32 ESP32 Feather, not the ESP8266 / S2 / S3 / V2.
// Four L298N channel-A ENA pins; direction is fixed by the wiring in README.md.
constexpr uint8_t PUMP_COUNT = 4;
constexpr uint8_t PUMP_ENABLE_PINS[PUMP_COUNT] = {27, 33, 25, 26};
// Default NeoPixel FeatherWing data-jumper position maps to GPIO 32 on HUZZAH32.
// This is NOT ESP32 GPIO 6 (which is used by flash).
constexpr uint8_t PIXEL_PIN = 32;
constexpr uint16_t PIXEL_COUNT = 32;
constexpr uint8_t PIXEL_BRIGHTNESS = 24;  // 0..255; keep USB current modest.
constexpr uint8_t STOP_BUTTON_PIN = 14;  // Optional normally-open button to GND.

constexpr uint32_t MIN_PUMP_MS = 100;
constexpr uint32_t MAX_PUMP_MS = 180000;
constexpr uint32_t MAX_SEQUENCE_MS = 600000;
constexpr uint32_t BETWEEN_PUMPS_MS = 300;
constexpr uint32_t HEARTBEAT_TIMEOUT_MS = 3000;
constexpr uint32_t ARM_TIMEOUT_MS = 30000;

// No motor runs at boot. PREVIEW always keeps all ENA outputs LOW.
static_assert(PIXEL_COUNT == PUMP_COUNT * 8, "Expected four banks of eight pixels");
constexpr bool pinsAreDistinct() {
  if (PIXEL_PIN == STOP_BUTTON_PIN) return false;
  for (uint8_t i = 0; i < PUMP_COUNT; ++i) {
    if (PUMP_ENABLE_PINS[i] == PIXEL_PIN || PUMP_ENABLE_PINS[i] == STOP_BUTTON_PIN) return false;
    for (uint8_t j = i + 1; j < PUMP_COUNT; ++j)
      if (PUMP_ENABLE_PINS[i] == PUMP_ENABLE_PINS[j]) return false;
  }
  return true;
}
static_assert(pinsAreDistinct(), "Pump, NeoPixel and Stop pins must be distinct");
