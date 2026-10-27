# R13-B measurement-time alignment

**Date:** 2026-08-29

**Package:** R13-B / active-R9 M2-04

**Status:** PASS (E0/E3 research gate)

**Validation:** deterministic clock/protocol/runtime tests plus staged short
real-Pi diagnostics and one final exact-source gate; no long soak required

**Rollback:** `r13a-vision-model-baseline-pass`; the Pi candidate is isolated and
no installed service or firmware was changed

## Outcome

The canonical R9 agent no longer treats BLE notification arrival as IMU capture
time after its clock model is acquired. The unchanged wearable's wrapping
`sensor_time_us` is mapped into the Pi monotonic clock domain, while arrival time,
mapping error, drift, clock state, wrap/reset events, and transport delay remain
separate and measurable.

Valid packets received before synchronization are counted as clock-gate drops but
withheld from the core publisher. A pre-final diagnostic exposed one timestamp
correction at the acquisition-to-mapped transition; the final publish gate removed
that ambiguity without discarding or hiding the acquisition evidence.

No ESP32 firmware, BLE UUID, packet, command, pairing state, R12 database schema,
camera, model, API, UI, or systemd installation changed.

## Existing R9 exchange reused

No new firmware command was needed. The existing R9 status characteristic is
generated inside its GATT read callback and includes ESP `uptime_ms`. For every
status read the runtime now records:

```text
t1_pi_ns
    -> BlueZ GATT status read
    -> ESP callback captures uptime_ms
t4_pi_ns
```

`uptime_ms * 1000 mod 2^32` shares the same ESP boot-monotonic domain as the
packet's `micros()` timestamp. The host accounts for the status value's one
millisecond resolution as explicit sensor-timestamp uncertainty.

The mapper:

- rejects negative or greater-than-50 ms exchanges;
- keeps at most 20 points and requires at least five;
- fits lower-RTT observations so BLE scheduling outliers do not pull the model;
- uses the nominal microsecond rate during a short acquisition burst and estimates
  drift only after a five-second sensor span;
- unwraps the u32 microsecond counter without confusing wrap with reboot;
- resets on the R9 boot epoch change already inferred from status regression;
- marks the clock degraded when no accepted exchange is seen for five seconds;
- caps any future projection at arrival and preserves the projection in the error;
- prevents a refit from publishing capture time backward and counts any correction.
- withholds events from the core publisher unless clock state is synchronized.

R9 samples remain `IMU_DEGRADED` because calibration/body-frame validation is still
open. `clock_state=SYNCHRONIZED` only means their timestamp mapping met the clock
budget; it does not approve the sample for model scoring.

## Deterministic evidence

The R13-B tests cover:

- offset/drift convergence and error budget;
- u32 sensor-counter wrap;
- boot reset followed by reacquisition;
- high-RTT rejection;
- low-delay filtering and excessive drift;
- one-millisecond status timestamp uncertainty;
- five-second exchange staleness;
- causal future cap and nondecreasing published capture time;
- R9 status-to-clock integration and fail-closed pre-sync behavior;
- runtime status-read acquisition;
- R12 ingestion compatibility;
- the real-hardware bench's clock acceptance failures.

Focused command:

```bash
.venv/bin/python -m pytest \
  tests/imu/test_clock_mapping.py \
  tests/imu/test_r9_protocol.py \
  tests/imu/test_r9_agent.py \
  tests/imu/test_r9_runtime.py \
  tests/imu/test_r9_bench.py \
  tests/core/test_local_sessions.py -q
```

Result: `43 passed in 3.92s`.

Complete suite: `223 passed, 7 warnings in 52.26s`. The warnings are the existing
dependency/FastAPI deprecations and MediaPipe feedback-manager diagnostics.

`scripts/validate_model.py` was also run as required by the prototype baseline. It
confirmed the model/scaler files exist but could not load the Flex model because
this environment intentionally has no TensorFlow, `ai_edge_litert`, or standalone
TFLite runtime; this is the unchanged R13-A model-runtime blocker, not an R13-B
failure. The frozen `validate_r13a_baseline.py` checkpoint correctly reported only
the two intentional R13-B source hash changes (`clock.py` and `r9_agent.py`), while
its model-package validation and deterministic replay remained valid. The R13-A
manifest was not rewritten. `git diff --check` passed with no output.

## Real Pi evidence

The exact final source was copied to an isolated directory:

```text
/home/pibimalawijekoon/digital-spotter-r13b-candidate-20260829
```

The retained R11 Python 3.12 virtual environment ran the candidate through
`PYTHONPATH`; no service was installed or enabled. The ESP continued running the
frozen R9 firmware.

Final 10-second E3 result:

| Measurement | Result |
|---|---:|
| Published samples | 501 |
| Duration | 10.000863 s |
| Published rate | 50.075418 Hz |
| Post-first-publish sync check | 0.000325 s |
| Clock state | synchronized |
| Estimated alignment-error p95 | 13.017092 ms |
| Current model error | 12.522348 ms |
| Accepted/rejected exchanges | 14 / 1 |
| Exchange RTT p95 | 23.364515 ms |
| Estimated drift | -62.887564 ppm |
| Capture-to-arrival p50/p95 | 31.616416 / 51.855530 ms |
| Acquisition clock-gate drops | 256 |
| Measured clock-gate drops | 0 |
| Sequence gaps/duplicates/invalid | 0 / 0 / 0 |
| Queue drops/publisher failures | 0 / 0 |
| Causal caps/monotonic corrections | 0 / 0 |
| I2C errors/unexpected disconnects | 0 / 0 |
| Result | PASS |

The capture-to-arrival values are measured BLE delivery latency, not clock mapping
error. They show why fusion must use capture timestamps and a bounded time ring
rather than pairing a pose with whichever IMU notification arrived most recently.

Raw evidence remains on the Pi:

```text
evidence/r13b-e3-clock-final5-20260829.json
SHA256 5aa6a1c1139acd43a974e625becd907ad3ef9e6ecdb4ba132927448ead5fff29

evidence/r13b-e3-clock-final5-20260829.log
SHA256 3b3de15e6a3c546672998ad7e52fd8aa7d55b1d0d662c48d38c422f59f7ec5b9
```

Post-run Pi state was clean: Bluetooth powered, discovery off, no stray BLE test
client, `throttled=0x0`, and temperature 47.2 C. There was no reported connection,
power, or crash failure and the benchmark disconnected cleanly.

## Exact deployed-source identity

Local and Pi candidate hashes matched:

```text
clock.py       2f979d6a85392ee0faac1e1c8b74ecb85ee90586fbb296ee1b40a9ff9a0d3091
r9_agent.py    02b85dbcd87a12731b2a78feaee210553ee2999a7ea9b215f787360abd6c6fdd
r9_runtime.py  505128cdaf1f6b8c88af195db5254d46226e01c1479d016f1652ff4ca20822ba
r9_bench.py    8080bf93d35526764cc386f6dd90144efb467d60ce5824b8a53213f97cc4dcec
r9_protocol.py b8dfff42043fa378e60e88668d2a25c68e675f99bdd12b81414adf70d64eae72
```

## Limits and next gate

- The error is an NTP-style bound derived from measured RTT, fit residual, and
  sensor timestamp resolution; it is not an independent oscilloscope reference.
- The unchanged R9 sensor remains uncalibrated and unapproved for model input.
- No camera/person alignment was attempted. R13-C must measure the camera's real
  capture timestamp behavior before R13-E fusion.
- A 30-minute clock/BLE soak is deliberately deferred to the final sustained gate;
  staged short diagnostics plus the final exact-source pass were sufficient for
  this bounded host-only change.
- M2-06 gym RF/mount/enclosure evidence and G2 exit remain open.
