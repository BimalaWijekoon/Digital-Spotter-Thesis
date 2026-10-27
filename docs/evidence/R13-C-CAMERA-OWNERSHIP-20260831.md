# R13-C camera ownership and capture timestamp spike

**Date:** 2026-08-31

**Package:** R13-C / M3-02

**Status:** PARTIAL (E0/E3 owner selected provisionally; controlled person and
glass-to-glass gates deferred)

**Rollback:** `r13b-measurement-time-pass`; all Pi execution used the isolated
`/home/pibimalawijekoon/digital-spotter-r13c-candidate-20260829` directory and no
service was installed or enabled

## Outcome

Picamera2 dual-stream ownership is the provisional target. It is the only tested
candidate that exposes a defined capture instant in the Pi monotonic clock domain:
`SensorTimestamp - ExposureTime`, representing the first pixel's exposure start.
The MediaMTX-owner/RTSP candidate supplies only decode-arrival time, so its current
form cannot produce a valid `PoseSample.captured_monotonic_ns` for fusion.

The available real-Pi measurements also favored Picamera2 for pose rate, latency,
CPU, RSS, temperature, and source-drop count. Picamera2 successfully published its
1280x720 hardware-H.264 main stream to a MediaMTX relay while independently
delivering a timestamped 640x360 lores stream for pose. The relay's WebRTC page
returned HTTP 200 and a separate RTSP subscriber decoded a real 1280x720 frame.

This does not complete R13-C. The owner requested that the controlled full-body
comparison be skipped because the current area could not provide suitable camera
framing. An attempted Picamera2 run found a possible pose in 1.37% of frames and a
valid required-joint pose in 0%; it is retained as failed evidence. Candidate B was
not run against the same controlled person, and browser glass-to-glass latency was
not observed. No raw still or video was saved or transferred.

## Compared configuration

Both candidates used:

- Raspberry Pi 4B 8 GB and the real IMX219 camera;
- Debian 13/aarch64 with kernel `6.18.34+rpt-rpi-v8`;
- Picamera2 `0.3.37-1` and libcamera Python bindings
  `0.7.2+rpt20260817-1`;
- system Python 3.13.5 for Picamera2 and the retained project Python 3.12.0 for
  OpenCV 4.11.0 and MediaPipe 0.10.18;
- MediaMTX v1.9.1 where a camera owner or relay was required;
- 1280x720 at 30 FPS for the main/browser stream;
- 640x360 MediaPipe input;
- MediaPipe Pose `model_complexity=1`;
- 0.7 detection/tracking confidence and 0.15 required-joint visibility;
- latest-frame semantics and real hardware, with no fake frames or pose results.

Candidate A used one Picamera2 owner with main H.264 and lores YUV streams.
Candidate B used MediaMTX's `rpiCamera` owner, H.264 RTSP decode, and an explicit
downscale to the same 640x360 pose input. CPU percentages below are summed process
CPU and may exceed 100% on the four-core Pi. RSS is the sum across the measured
candidate processes.

## Available E3 comparison

| Measurement | Picamera2 owner | MediaMTX owner + RTSP |
|---|---:|---:|
| Window | 9.820 s | 10.023 s |
| Frames processed | 72 | 68 |
| Effective pose FPS | 7.332 | 6.784 |
| Pose processing p50 / p95 | 122.302 / 124.320 ms | 138.961 / 145.238 ms |
| Capture timestamp coverage | 100% | 0% |
| Capture age p50 / p95 | 71.107 / 72.933 ms | unavailable |
| Source frames dropped | 220 | 256 |
| Full-stack CPU | 121.2% | 199.2% |
| Full-stack RSS peak | 679.6 MB | 709.2 MB |
| Temperature peak | 60.374 C | 62.809 C |
| Throttled | `0x0` | `0x0` |
| Client restart | 3/3 | 3/3 |

Picamera2 camera-owner restart passed 3/3. MediaMTX camera-owner restart was then
tested separately from its RTSP-client restart and passed 3/3, with a decoded real
1280x720 frame after every launch. MediaMTX v1.9.1 leaves its `mtxrpicam` helper
running after the parent receives a normal termination signal, so the test had to
stop the exact helper PID as part of cleanup. No camera process remained afterward.

## Picamera2 publication evidence

The publication run included the pose process, system-Python Picamera2 helper, and
MediaMTX relay. It processed 126 pose frames in 19.853 seconds at 6.347 FPS while
maintaining 100% monotonic exposure timestamps. Full-stack CPU was 126.6%, RSS
peaked at 753.6 MB, temperature peaked at 60.374 C, and throttling remained `0x0`.
An extra RTSP subscriber decoded a real `(720, 1280, 3)` frame and the WebRTC HTTP
endpoint returned 200. Actual browser rendering and glass-to-glass latency remain
unmeasured.

The uncontrolled run reported some visible landmarks, but those values are not
used as person-accuracy evidence because the requested controlled framing was not
available.

## Deterministic evidence

Focused command:

```bash
.venv/bin/python -m pytest tests/test_02_pose/test_camera_spike.py -q
```

Result before documentation consolidation: `17 passed in 0.49s`.

The tests cover exposure-start timestamp conversion and validation, capacity-one
latest-frame semantics, explicit missing-camera/person states, RTSP shutdown order,
RTSP pose-input resizing, helper framing, and restart lifecycle. Compile checks and
`git diff --check` passed.

The complete repository suite passed: `240 passed, 7 warnings in 84.73s`. The
warnings are existing protobuf, multipart, FastAPI lifespan, and MediaPipe
diagnostics. `scripts/validate_model.py` confirmed that the model and scaler still
exist, then failed at the unchanged R13-A blocker because this environment has no
TensorFlow, `ai_edge_litert`, or standalone TFLite runtime capable of loading the
Flex model. No model artifact or contract changed in R13-C.

## Evidence retained

Machine-readable JSON and text logs are under
`docs/evidence/r13-c-20260831/`. `SHA256SUMS` authenticates the selected artifacts.
No camera still, raw video, ESP firmware, BLE state, IMU data, database, API, UI,
cloud configuration, or installed Pi service changed.

## Remaining acceptance work

Before R13-C/M3-02 can be marked PASS and ADR-014 accepted, run one short controlled
full-body scenario for both candidates using the same position, lighting, and slow
squat movements. Record pose visibility/accuracy and effective FPS, then observe
the selected publication path in a browser and measure glass-to-glass latency.
Until then Picamera2 is a provisional implementation direction, not a completed
product gate.

The current proof uses a small system-Python Picamera2 helper process because the
Debian camera bindings target Python 3.13 while the pinned MediaPipe environment is
Python 3.12. M3-03 must either retain and supervise this narrow boundary or align
the runtime versions without changing the measured camera contract.
