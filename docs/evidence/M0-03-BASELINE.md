# M0-03 local baseline evidence

**Date:** 2026-08-25 to 2026-08-26

## Scope

Establish a reproducible E1 Linux baseline and an E3 characterization of the
current Pi prototype. This evidence includes a real Pi, IMX219, model-load check,
camera/pose benchmark, and 30-minute bench soak. It does not satisfy person-in-frame
pose accuracy, BLE/IMU, gym RF, final-enclosure thermal, or production gates.

## Source state

- Repository revision before the uncommitted migration work: `326651e`
- Branch: `main`
- Documentation and M0 migration edits: uncommitted
- Historical/user files deleted: none

## E1 host environment

- Host: WSL2, x86_64 Linux
- System Python selected by shell: CPython 3.14.6, missing project packages
- Tracked `venv/`: Windows layout; not executable in this WSL session
- Test environment: isolated `/tmp/digital-spotter-venv`
- Test Python: CPython 3.12.13 downloaded by `uv`
- Pi hardware used in this E1 section: no
- Camera/ESP32-C3/IMU used: no
- WAN required by exercise loop: not evaluated

## Dependency reproduction

The active application imported FastAPI/Uvicorn but the former requirements listed
only the Flask server. The M0 requirements were updated with the active FastAPI
stack, pinned MediaPipe/OpenCV versions, and scikit-learn 1.8.0. The scikit-learn
version was read from the tracked `models/scaler.save` metadata.

MediaPipe 0.10.14 attempted to download its Heavy pose model during test
initialization. The official asset was installed into the temporary environment and
verified as:

```text
pose_landmark_heavy.tflite
sha256 59e42d71bcd44cbdbabc419f0ff76686595fd265419566bd4009ef703ea8e1fe
```

`scripts/setup_dev.sh` now reproduces this temporary E1 setup and verifies that
checksum. M1-01 must replace it with the final locked development and Pi/aarch64
package definitions.

Dependency consistency command:

```text
UV_CACHE_DIR=/tmp/digital-spotter-uv-cache uv pip check \
  --python /tmp/digital-spotter-venv/bin/python
```

Final result on 2026-08-26: all 86 installed packages are compatible.

Known dependency concern: MediaPipe depends on `opencv-contrib-python`, while the
prototype also directly requests `opencv-python-headless`. M1-01 must produce one
tested OpenCV runtime choice for x86 development and Pi/aarch64.

## Test results

Initial run before the MediaPipe asset:

```text
70 passed, 8 failed
```

All eight failures were MediaPipe/SessionManager initialization attempts to fetch
`pose_landmark_heavy.tflite` while network access was unavailable.

After the verified asset and M0 tests:

```text
MPLCONFIGDIR=/tmp/digital-spotter-mpl-cache \
DS_MQTT_ENABLED=false DS_BUZZER_ENABLED=false DS_RGB_ENABLED=false \
/tmp/digital-spotter-venv/bin/python -m pytest tests -q

86 passed, 7 warnings in 34.51s
```

The warnings include MediaPipe/protobuf compatibility warnings, Starlette multipart
pending deprecation, and FastAPI `on_event` lifespan deprecations. These are debt,
not failed tests.

New M0 coverage:

- launcher delegates host/port to `Config.API`;
- active FastAPI `/health` route responds through an in-process ASGI transport;
- process environment takes precedence over project `.env` values;
- the systemd migration template points to the verified Pi account, checkout,
  Python, and port;
- the pose benchmark uses a capacity-one latest-frame reader, bounds a stalled
  stream, reports dropped source frames, and returns a failure status on errors.

Uvicorn also reached `Application startup complete` in E1. On the Pi, a controlled
launcher run bound to `127.0.0.1:8000` returned HTTP 200 from `/health` and `/` with
MQTT/buzzer/RGB disabled. Health identified the real model and preprocessor and the
mock IMU. The temporary process was stopped after the tests and the port was
verified closed. This is a launcher/HTTP pass, not an installed-systemd boot pass.

## Model validation

`scripts/validate_model.py` found the tracked TFLite/scaler files but failed because
the base environment has neither `ai_edge_litert` nor TensorFlow. No real model
prediction was produced.

An isolated install of `tensorflow==2.16.2` and `ai-edge-litert` was attempted. The
TensorFlow wheel was 563.4 MB and extraction failed with `No space left on device`
while flushing `libtensorflow_cc.so.2`. Only the task-owned temporary UV cache was
removed afterward; repository data and the working temporary test environment were
preserved.

This is an environment blocker and architecture debt. M1-03 must manifest the
current runtime exactly; M5 must replace Flex/full TensorFlow with a built-in-op
LiteRT/TFLite model after accuracy parity.

## Raspberry Pi baseline

The corrected documented identity is `pibimalawijekoon@100.104.28.69`, machine
`pidigitalspotter`. The earlier `bimalawijekoon@192.168.1.8` reference was stale.
Tailscale reached the Pi directly over the LAN at 7 ms during the audit.

Verified platform:

- Raspberry Pi 4 Model B Rev 1.4, 8 GB RAM, four Cortex-A72 CPUs;
- Debian 13.5 (trixie), aarch64 kernel `6.18.34+rpt-rpi-v8`;
- system Python 3.13.5; application service Python 3.12.0 through pyenv;
- 29 GB ext4 root filesystem, 18 GB available at the measurement time;
- CPU governor `ondemand`, measured clock about 1.8 GHz;
- temperature 46.2 degrees C at idle and 51.1 degrees C after model validation;
- `vcgencmd get_throttled` returned `0x0` throughout the checks;
- 2 GB swap configured, unused; the `swapon` CLI itself was unavailable.

Service/device state:

- Tailscale, SSH, and Bluetooth services were active and enabled;
- the Bluetooth controller reported `Powered: no`, so BLE was not usable;
- `digitalspotter.service` and `mediamtx.service` were installed but disabled and
  inactive; port 8000 health therefore refused the connection;
- systemd reported no failed units;
- MediaMTX v1.9.1 was present;
- IMX219 was enumerated at 3280x2464 and a three-second, no-preview/no-recording
  `rpicam-hello` open test exited successfully;
- GPIO device access was present; Pi I2C/SPI device nodes were not enabled. The
  MPU6050 uses internal I2C on the separate ESP32-C3 wearable, not Pi I2C.

Deployed source state was deliberately preserved and backed up before the bounded
M0 deployment:

- Pi checkout: `/home/pibimalawijekoon/Digital-Spotter` at `cabc738`;
- current workspace revision: `326651e` plus uncommitted M0 changes;
- Pi tracked modifications: `CHANGELOG.md`, `imu/esp32_bridge.py`,
  `scripts/dashboard/index.html`, `scripts/dashboard/main.py`, and
  `vision/frame_processor.py`;
- Pi untracked runtime/work files: SQLite `-shm`/`-wal` and
  `scripts/benchmark_pipeline.py`;
- comparison showed the Pi source delta is already represented in workspace
  revision `326651e`: the bridge, dashboard HTML, frame processor, and benchmark
  hashes matched byte-for-byte; the Pi dashboard backend matched the clean
  `326651e` version, while this workspace additionally contains the M0 background-
  task lifecycle fix; the Pi changelog additions are also present locally;
- the SQLite database/WAL remains device-owned runtime data;
- a restricted backup was created at
  `/home/pibimalawijekoon/Digital-Spotter-backups/m0-03-20260825`, including an
  online SQLite backup, source status/patch, service metadata, benchmark, and
  SHA-256 manifest. The manifest verified and SQLite `quick_check` returned `ok`;
- exact pre-deploy copies and hashes of `config/config.py`,
  `scripts/run_server.py`, and `scripts/dashboard/main.py` were stored under the
  backup's `predeploy/` directory;
- only those three bounded M0 files and the repaired benchmark script were staged,
  hash/syntax checked, and installed. No fetch, pull, checkout, cleanup, database
  mutation, service installation, enablement, or reboot was performed;
- final Pi status still contained its earlier source modifications and runtime
  SQLite WAL/SHM files. They were not deleted or reset.

The six deployed model/preprocessing artifact hashes exactly matched this
workspace. In the Pi Python 3.12 environment, OpenCV 4.11.0, MediaPipe 0.10.18,
TensorFlow 2.16.2, and AI Edge LiteRT 2.1.5 imported successfully. The existing
validator loaded `model_quantized.tflite` with the TensorFlow Flex and XNNPACK
delegates, confirmed input `[1, 4, 40]` and output `[1, 1]`, produced a sample
output, and passed with a 2.97 ms sample inference. This is a load/smoke result, not
accuracy or representative latency evidence. TensorFlow also reported a tolerated
unknown `TensorListReserve` attribute. `pip check` reported that MediaPipe's `jax`
and `jaxlib` requirements were missing even though the import smoke passed.

## Controlled Pi runtime measurements

The test used MediaMTX v1.9.1 on loopback-only RTSP/TCP with its IMX219 helper at
1280x720 and 15 FPS. WebRTC, UDP listeners, and recording were disabled. The
FastAPI migration backend was also loopback-only; MQTT, buzzer, and RGB were
disabled. The camera and pose engine were real. The model/preprocessor loaded as
real, but the current automatic camera-to-inference path is disconnected, and the
IMU was explicitly mock because the ESP32-C3 was not present.

An idle 12-second backend smoke, before enabling the camera, measured 0.1 percent
system CPU, 0.2 percent backend CPU, 759.9 MB backend RSS, 51.6 degrees C, and
`throttled=0x0`.

The repaired latest-frame benchmark processed 200 frames at 640-pixel analysis
width using MediaPipe Pose complexity 2:

```text
source: 1280x720 at 15 FPS
effective pose throughput: 3.04 FPS
source frames dropped by latest-frame policy: 742
capture/read: median 65.5 ms, p95 72.2 ms
resize/color preparation: median 1.9 ms, p95 3.3 ms
pose inference: median 125.2 ms, p95 697.8 ms
benchmark process CPU: 139.1 percent
pose-found frames: 4.0 percent
read failures: 0
end temperature: 67.7 degrees C
throttled: 0x0
```

The 4.0 percent pose-found result confirms that the scene did not contain a usable
person for this run. It is performance/failure evidence only and cannot support an
accuracy claim. The high p95 and 3.04 FPS are substantially outside the product
target and make worker isolation, newest-frame semantics, a lower-cost pose model,
and person-in-frame parity testing mandatory.

A separate 30-minute active camera/pose soak took one 60-second process/system
sample and one loopback health request per minute:

```text
health: 30/30 HTTP 200
system CPU: 37.9 to 38.8 percent
backend CPU: 141.9 to 145.7 percent
backend RSS: 818.8 MB first, 820.3 MB final (+1.5 MB)
MediaMTX RSS: 33.9 to 34.9 MB
camera-helper RSS: 10.0 MB throughout
temperature: 60.4 to 76.0 degrees C; 61.3 degrees C final loaded
throttle/undervoltage flags: 0x0 in every sample
MediaMTX/decoder/reconnect errors: none observed
```

Afterward, only the two recorded PIDs were signaled. The backend, MediaMTX, and
camera helper were absent; ports 8000/8554 were closed; temperature had fallen to
56.4 degrees C; and `get_throttled` remained `0x0`. This 30-minute no-person bench
run closes the current-system soak deliverable, but not the 60-minute final product
soak or final-enclosure/ambient gate.

## Open M0-03 evidence

- person-in-frame pose accuracy/FPS baseline
- real lower-back ESP32-C3/MPU6050 state and operating profile
- sustained CPU frequency sampling under the same load
- 60-minute person/real-IMU final-product soak (later G4 gate)
- physical lower-back orientation, attachment, enclosure, battery, and RF evidence

M0-03 remains `IN PROGRESS` until these are captured.
