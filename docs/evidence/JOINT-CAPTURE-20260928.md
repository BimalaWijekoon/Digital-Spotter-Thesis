# Joint IMU + vision capture, 2026-09-28

**Scope:** Core-first research sequence, step 1 only. One temporary Pi 4 run;
no firmware change, pairing, camera-person test, fusion, inference, browser,
cloud, or installed service.

The staged code lived under `/tmp/ds-joint-ohFBH4tA/` on the Pi. A single
`LocalSessionService` opened two separate local sockets, started the existing
R9 BLE IMU agent and the canonical real Picamera2/MediaPipe vision agent,
collected both for a bounded interval, and closed all three processes. The
wearable was USB-powered from the PC; its data reached the Pi over BLE.

| Observation | Result |
|---|---:|
| Real IMU events accepted | 410 |
| Real vision pose events accepted | 58 |
| Vision health events received, not stored as poses | 10 |
| IMU sequence gaps | 0 |
| Degraded IMU events | 410 (existing uncalibrated research sensor quality) |
| Invalid/rejected IMU and vision events | 0 / 0 |
| Degraded pose events | 58 (empty scene, no person) |
| Pose ring evictions | 54 (capacity 4; expected bounded behavior) |
| Persisted analysis events | 0 |
| Fusion/model scoring | Not performed |

The IMU capture timestamp range was `3470715576938` to `3480940364786`
Pi-monotonic ns. The vision capture timestamp range was `3472893773000` to
`3480892226000` Pi-monotonic ns. Their ranges overlap; events retained their
original measurement timestamps and quality flags. The IMU range spans about
10.22 seconds, or about 40 accepted samples/s over this one concurrent run.
This is **not** the prior standalone 50-Hz gate and is not a calibrated
performance claim. The vision worker reported 61 received frames, 61 published
events, 61 poses not found, and 195 source-frame drops. Those drops need later
resource/timing assessment, not another immediate test or a claim of real pose
tracking quality.

The IMU log reported `R9 BLE connection and GATT contract verified`. The
vision log reported `adapter_mode=picamera2`, `pose_evaluator_mode=mediapipe`,
`is_simulated=false`, `processing_failures=0`, and `state=stopped`. After the run,
both event sockets were absent and no test client process remained. The Pi
staging directory contains the bounded core/IMU/vision logs and disposable
SQLite database; it is not an installed application.

Focused local checks: `pytest tests/core/test_joint_capture.py
tests/core/test_local_sessions.py -q` passed 8/8. These checks used synthetic
contract events and a temporary SQLite database; they are not hardware evidence.
The Pi run is the hardware evidence for the join only. Next: measurement-time
fusion with explicit missing/stale quality, then phase construction. Human-camera
and mounted-wearable validation remain last.
