#pragma once
#include <stdint.h>

// Uno pins drive four L298N ENA inputs. See hardware notes before wiring.
constexpr uint8_t PUMP_COUNT = 4;
constexpr uint8_t PUMP_ENABLE_PINS[PUMP_COUNT] = {3, 5, 6, 9};
constexpr uint8_t STOP_BUTTON_PIN = 2;

constexpr uint32_t MIN_PUMP_MS = 100;
constexpr uint32_t MAX_PUMP_MS = 180000;
constexpr uint32_t MAX_SEQUENCE_MS = 600000;
constexpr uint32_t BETWEEN_PUMPS_MS = 300;
constexpr uint32_t HEARTBEAT_TIMEOUT_MS = 3000;
constexpr uint32_t ARM_TIMEOUT_MS = 30000;
