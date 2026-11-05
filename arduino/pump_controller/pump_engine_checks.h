#pragma once
#include "pump_engine.h"

// These execute the actual timer engine during C++ compilation. A failing
// invariant fails the firmware build. They neither enable pins nor add runtime code.
namespace PumpChecks {
constexpr bool bootAndArm() {
  PumpEngine e;
  uint32_t job[4] = {1000, 0, 0, 0};
  if (e.motorOutput() != -1 || e.armed || e.running) return false;
  if (e.start(job, false, 0) == nullptr || e.motorOutput() != -1) return false;
  if (!e.arm(0) || e.start(job, false, 1) != nullptr) return false;
  return e.motorOutput() == 0 && !e.armed && !e.arm(2);
}
constexpr bool sequenceAndGap() {
  PumpEngine e;
  uint32_t job[4] = {1000, 0, 500, 0};
  e.arm(0);
  if (e.start(job, false, 0)) return false;
  e.tick(999);
  if (e.motorOutput() != 0) return false;
  e.tick(1000);
  if (e.motorOutput() != -1 || !e.running || e.completed != 1) return false;
  e.tick(1000 + BETWEEN_PUMPS_MS - 1);
  if (e.motorOutput() != -1) return false;
  e.tick(1000 + BETWEEN_PUMPS_MS);
  if (e.motorOutput() != 2) return false;
  e.tick(1500 + BETWEEN_PUMPS_MS);
  return !e.running && !e.armed && e.motorOutput() == -1 && e.completed == 5;
}
constexpr bool previewNeverDrives() {
  PumpEngine e;
  uint32_t job[4] = {500, 500, 500, 500};
  if (e.start(job, true, 0)) return false;
  for (uint32_t t = 0; t <= 4000; t += 100) {
    e.tick(t);
    if (e.motorOutput() != -1) return false;
  }
  return !e.running && e.completed == 15 && !e.armed;
}
constexpr bool stopAndLostLink() {
  PumpEngine e;
  uint32_t job[4] = {10000, 10000, 0, 0};
  e.arm(0);
  e.start(job, false, 0);
  e.tick(HEARTBEAT_TIMEOUT_MS);
  if (e.running || e.armed || e.motorOutput() != -1 || !e.stopped) return false;
  e.ping(4000);
  e.tick(15000);
  if (e.running || e.motorOutput() != -1) return false;
  e.arm(20000);
  e.start(job, false, 20000);
  e.stop("USER");
  e.ping(22000);
  e.tick(60000);
  return !e.running && !e.armed && e.motorOutput() == -1;
}
constexpr bool heartbeatAndRollover() {
  PumpEngine e;
  uint32_t job[4] = {10000, 0, 0, 0};
  const uint32_t start = UINT32_MAX - 500;
  e.arm(start);
  e.start(job, false, start);
  for (uint32_t elapsed = 1000; elapsed < 10000; elapsed += 1000) {
    uint32_t now = start + elapsed;
    e.ping(now);
    e.tick(now);
    if (e.motorOutput() != 0 || e.remaining(now) != 10000 - elapsed) return false;
  }
  e.tick(start + 10000);
  return !e.running && e.motorOutput() == -1 && e.completed == 1;
}
constexpr bool boundsAndExpiry() {
  PumpEngine e;
  uint32_t empty[4] = {};
  uint32_t tooShort[4] = {MIN_PUMP_MS - 1, 0, 0, 0};
  uint32_t tooLong[4] = {MAX_PUMP_MS + 1, 0, 0, 0};
  uint32_t tooMuch[4] = {MAX_PUMP_MS, MAX_PUMP_MS, MAX_PUMP_MS, MAX_PUMP_MS};
  e.arm(0);
  if (!e.start(empty, false, 1) || !e.start(tooShort, false, 1)
      || !e.start(tooLong, false, 1) || !e.start(tooMuch, false, 1)) return false;
  if (e.motorOutput() != -1 || e.running) return false;
  e.tick(ARM_TIMEOUT_MS);
  return !e.armed && !e.running;
}
static_assert(bootAndArm(), "Boot/arming invariant failed");
static_assert(sequenceAndGap(), "Sequential timing, zero skips, or gap failed");
static_assert(previewNeverDrives(), "Preview must never drive a motor");
static_assert(stopAndLostLink(), "Stop or watchdog failed to clear the queue");
static_assert(heartbeatAndRollover(), "Heartbeat or millis rollover handling failed");
static_assert(boundsAndExpiry(), "Duration bounds or idle arm expiry failed");
}  // namespace PumpChecks
