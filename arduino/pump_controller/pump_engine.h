#pragma once
#include "pump_config.h"

// Hardware-independent, nonblocking timer. Durations are milliseconds, not ml.
class PumpEngine {
 public:
  bool armed = false;
  bool running = false;
  bool preview = false;
  int8_t active = -1;
  uint8_t completed = 0;
  uint32_t durations[PUMP_COUNT] = {};
  uint32_t phaseStarted = 0;
  const char* stopped = nullptr;

  constexpr bool arm(uint32_t now) {
    if (running) return false;
    armed = true;
    preview = false;
    armedAt = lastContact = now;
    stopped = nullptr;
    completed = 0;
    for (uint8_t i = 0; i < PUMP_COUNT; ++i) durations[i] = 0;
    return true;
  }

  constexpr void ping(uint32_t now) { lastContact = now; }

  // Returns nullptr on success, or a stable protocol error string.
  constexpr const char* start(const uint32_t* requested, bool lightsOnly, uint32_t now) {
    if (running) return "BUSY";
    if (!lightsOnly && !armed) return "NOT_ARMED";
    uint32_t total = 0;
    for (uint8_t i = 0; i < PUMP_COUNT; ++i) {
      if (requested[i] != 0 && (requested[i] < MIN_PUMP_MS || requested[i] > MAX_PUMP_MS))
        return "DURATION_RANGE";
      total += requested[i];
    }
    if (total == 0) return "EMPTY_SEQUENCE";
    if (total > MAX_SEQUENCE_MS) return "SEQUENCE_TOO_LONG";
    for (uint8_t i = 0; i < PUMP_COUNT; ++i) durations[i] = requested[i];
    preview = lightsOnly;
    // An arm authorizes one job only; preview consumes any previous arm too.
    armed = false;
    running = true;
    completed = 0;
    stopped = nullptr;
    lastContact = now;
    lastIndex = -1;
    activateNext(now);
    return nullptr;
  }

  constexpr void stop(const char* reason) {
    active = -1;
    running = false;
    armed = false;
    stopped = reason;
  }

  constexpr void tick(uint32_t now) {
    if (armed && uint32_t(now - armedAt) >= ARM_TIMEOUT_MS) stop("ARM_TIMEOUT");
    if (!running) return;
    // Preview may finish without a host because no motor outputs are enabled.
    if (!preview && uint32_t(now - lastContact) >= HEARTBEAT_TIMEOUT_MS) {
      stop("LINK_LOST");
      return;
    }
    if (active >= 0) {
      if (uint32_t(now - phaseStarted) < durations[active]) return;
      completed |= (1U << active);
      lastIndex = active;
      active = -1;
      phaseStarted = now;
      if (nextIndex() < 0) running = false;
    } else if (uint32_t(now - phaseStarted) >= BETWEEN_PUMPS_MS) {
      activateNext(now);
    }
  }

  constexpr int8_t motorOutput() const { return running && !preview ? active : -1; }
  constexpr uint32_t remaining(uint32_t now) const {
    if (!running || active < 0) return 0;
    uint32_t elapsed = uint32_t(now - phaseStarted);
    return elapsed >= durations[active] ? 0 : durations[active] - elapsed;
  }

 private:
  uint32_t armedAt = 0;
  uint32_t lastContact = 0;
  int8_t lastIndex = -1;

  constexpr int8_t nextIndex() const {
    for (int8_t i = lastIndex + 1; i < PUMP_COUNT; ++i)
      if (durations[i] > 0) return i;
    return -1;
  }
  constexpr void activateNext(uint32_t now) {
    active = nextIndex();
    phaseStarted = now;
    if (active < 0) running = false;
  }
};
