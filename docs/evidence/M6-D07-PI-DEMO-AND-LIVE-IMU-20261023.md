# M6-D07 Pi Demo and Live IMU Evidence — 2026-10-23

## Scope

Focused activation of the current dashboard/runtime on the Raspberry Pi, with
one bounded real-wearable IMU observation and one frozen V5 replay prediction.
No camera/person test, reconnect matrix, firmware flash, retraining, pairing,
network reconfiguration, persistence or actuator command was in scope.

## Staging integrity

- Pi directory: `/home/pibimalawijekoon/digital-spotter-demo-20261023.Yj6ZyB`
- Runtime archive SHA256:
  `ee352bace8787212d88788ea138b1d51804cdaed6253b343ebb4ed310e4d1439`
- The staged `STAGE_SHA256SUMS.txt` verification returned success for every
  copied source/UI file and `scripts/run_workout.py`.
- Existing model package reused read-only:
  `/home/pibimalawijekoon/digital-spotter-v5-imu-r1-20261020.E7L664/package`

## Pi preflight

- Raspberry Pi reported `throttled=0x0`, temperature 43.3 C and 13 GB free.
- Bluetooth was powered, not scanning, and no stray BLE client was running.
- Core loaded `digital_spotter_v5_imu_synthetic_r1` through LiteRT and served
  only `127.0.0.1:8766`; PC access used a private SSH forward to 4174.
- Dashboard GET through the forward returned HTTP 200.

## Real wearable observation

The existing single BLE adapter verified the ESP32 GATT contract and forwarded
real MPU6500 events to the new run's Unix socket.

| Measurement | Result |
|---|---:|
| Samples | 100 |
| Sequence range | 843–942 |
| Sequence gaps | 0 |
| Capture span | 1980.20 ms |
| Measured rate | 49.99 Hz |
| Mean acceleration magnitude | 9.819 m/s2 |
| Reported quality | degraded |

`degraded` is the correct current state because physical calibration has not
been certified. It is not interpreted as a BLE transport failure.

## Pi-side model replay

One whitelisted `squat/incorrect`, rep 1 request used fixture 6 (35 kg,
source label 1, forward-lean example) and the canonical frozen model path.

| Output | Result |
|---|---:|
| Raw bad-form probability | 0.7873480319976807 |
| Calibrated probability | 0.8506133561202271 |
| Frozen threshold | 0.3976007923801824 |
| Predicted class | 1 (`Check form`) |
| Matches source label | true |
| Pi compute time | 2.724 ms |

The response explicitly remained `reference_only=true`, `live=false`,
`animation_drives_features=false` and `actuators_enabled=false`.

## Result and remaining boundary

M6-D07 PASS for the narrowly scoped Pi demo activation and live IMU display.
This evidence does not prove live V5 feature eligibility, real-world form
accuracy, pose/camera quality, synchronization, wearable calibration, session
persistence, boot-time service behavior, or LED/buzzer result feedback.
