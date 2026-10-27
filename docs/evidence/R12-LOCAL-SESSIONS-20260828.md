# R12 canonical local sessions evidence

**Date:** 2026-08-28
**Work package:** R12
**Status:** PASS (E0/E1/E3)
**Privacy:** synthetic component data only; no raw real-user IMU retained

## Scope

R12 connects the frozen R11 canonical IMU event boundary to one authoritative
local session service and SQLite. It adds no camera, fusion, model, UI, cloud, BLE
security, firmware, or raw sensor-retention behavior.

The implementation provides:

- idempotent durable start/stop and a database-enforced single active session;
- controlled-restart restoration of the same active session UUID and aggregate
  counters;
- a 250-event in-memory IMU ring (five seconds at 50 Hz), evicting oldest samples;
- validated, bounded length-prefixed Unix-socket ingestion with optional peer UID;
- a 256-item bounded database worker using off-event-loop SQLite calls;
- transactional active checkpoints and completed-session summaries;
- explicit storage-degraded behavior on transaction/queue failure;
- aggregate-only persistence in `session_imu_summaries` and no raw 50 Hz table.

## E0/E1 results

Focused command:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/core/test_local_sessions.py \
  tests/persistence/test_sqlite_foundation.py -q
```

Result:

```text
14 passed in 2.49s
```

Full repository command:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q
```

Result:

```text
215 passed, 7 warnings in 64.74s
```

The warnings are the existing protobuf/Starlette/FastAPI deprecations. TensorFlow
Lite feedback-manager messages were also emitted by existing model tests; neither
is an R12 failure.

The repository baseline model validator was also invoked:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_model.py
```

It remains blocked because this workspace has neither TensorFlow 2.16.2 nor an
`ai_edge_litert` runtime capable of loading the model. Model artifacts were found;
this pre-existing environment dependency is outside R12 and is not represented as
a passing model gate.

Covered claims:

- same start request returns the same active session;
- repeated stop does not change the original completion time;
- a second process restores the active UUID and persisted counts without adding a
  second session row;
- a three-item test ring receives five events, retains the latest three, and
  reports two expected evictions;
- wrong-device and simulated events fail closed;
- injected SQLite failure rolls back completion and leaves the session active in
  explicit `storage_degraded` state;
- database queue saturation rejects new work instead of blocking indefinitely;
- the existing `UnixEventPublisher` sends a canonical `IMUSample` through a real
  temporary Unix socket into the session ring;
- backup/restore manifests now include the session-summary table count.

## Real-hardware gate

Environment:

```text
Pi: Raspberry Pi 4B 8 GB
Pi OS/kernel: Debian aarch64, 6.18.34+rpt-rpi-v8
Wearable: unchanged frozen R9 ESP32-C3 + real MPU6500
Wearable identity: ESP32-C3-Test / 50:78:7D:92:61:1A
Pi Bluetooth controller: E4:5F:01:63:AD:F1
Python/dependencies: retained R11 Python 3.12 environment
Duration: 10-second accepted stream after first event
Raw retention: disabled
```

Preflight after the Pi reboot:

```text
Bluetooth powered: yes
Bluetooth discovering: no
throttled=0x0
temperature=49.1 C
available RAM=7.4 GiB
root filesystem free=14 GiB
stray BLE clients=none
```

The staged R12 files matched their local SHA-256 hashes. The final validator output
was:

```text
result=PASS
sample_count=507
elapsed_s=10.093022683
measured_hz=50.13364339825293
gap_count=0
duplicate_event_count=0
frames_rejected=0
connections_accepted=1
distinct_boot_count=1
clock_reset_count=0
ring_eviction_count=257
session_state=completed
raw_imu_persisted=false
```

The 257 evictions are exactly the expected bounded-ring behavior: 507 events entered
a 250-event ring, so the oldest 257 were discarded from memory rather than queued
or persisted. All 507 events contributed to the durable aggregate summary.

Final database verification:

```text
path=/home/pibimalawijekoon/digital-spotter-r12-candidate/evidence/
     r12-e3-shutdownfix-20260828.sqlite3
sha256=8bf0168757f857e2c5aabb628946b3281b3114719bf262bf0fe20ff86a2128a1
schema_version=3
PRAGMA quick_check=ok
privacy_mode=summary_only
sessions=one completed test session
session_imu_summaries=one aggregate row
raw IMU table/rows=none
```

Post-test state was Bluetooth powered/idle, no validator/R11-agent/bluetoothctl
process remained, `throttled=0x0`, and temperature was 49.6 C. No package was
installed; no systemd, network, Tailscale, BlueZ, ESP firmware, or existing product
database configuration was changed.

## Failure found and corrected during E3

The first diagnostic run proved the data path but exposed a Python 3.12 shutdown
ordering defect: `Server.wait_closed()` waited for the still-connected R11 client,
while the wrapper planned to stop R11 only after the validator exited. The process
was released by cleanly terminating only the temporary R11 agent; it had accepted
4,020 events at 50.023 Hz with zero gaps/rejections, but that run was not used as
the final acceptance result.

R12 now closes client writers, cancels their handler tasks, and only then awaits
the server. A regression test closes the server while its publisher remains
connected, and the fresh E3 rerun above exited normally after 10 seconds. The R11
agent logged one expected `core event socket unavailable: Connection lost` during
the deliberate core-first test teardown, then stopped cleanly.

## Rollback

Code rollback is the previous R11 tag. Database migration 0003 is additive, but an
existing database may be migrated only through the existing backup-gated migration
runner; rollback restores the verified pre-migration backup with the previous
release. No existing repository or Pi database was migrated for E0/E1.
