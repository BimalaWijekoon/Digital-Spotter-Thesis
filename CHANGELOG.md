# Changelog

All notable changes to the Digital Spotter project will be documented in this file.

## [Unreleased]

### 2026-08-28 — R11 canonical Pi BLE adapter

- Activated one canonical Bleak owner for the unchanged R9 research firmware with
  exact identity/GATT validation, strict 20-byte parsing, bounded ingress/latest
  delivery, UDS event publication, observable health, graceful control, and capped
  reconnect backoff.
- Added deterministic regressions for transient Bleak callbacks, initial
  connection failures, per-stream R9 sequence epochs, queue bounds, and automatic
  reconnect.
- Passed a 6,003-sample two-minute E3 run at 50.064697 Hz with zero steady-state
  gaps, invalid packets, queue drops, reconnects, publisher failures, or I2C
  errors. A deliberate disconnect also recovered automatically and passed a clean
  post-recovery 10-second window.
- Accepted a responsive phone/tablet browser/PWA as the first client; UI work
  remains sequenced after the sensor/core/persistence path.

### 2026-08-28 — R9 firmware freeze and workspace normalization

- Froze the real-hardware R9 Arduino ESP32-C3/MPU6500 firmware, matching Pi
  validator, directly flashable application binary, exact configuration, hashes,
  and acceptance logs as the only supported wearable path.
- Recorded the passing 30-second R9 stream and owner-observed GPIO 8 NeoPixel/GPIO
  10 buzzer cues; R10 bonding remains optional and R11 Pi integration is next.
- With explicit owner approval, removed generated Arduino builds, R1-R8
  checkpoints/scripts, the failed R9 candidate, abandoned ESP-IDF and MQTT
  firmware, the original BLE diagnostic sketch, stale SSH setup text, obsolete
  JSON plans/placeholder tracker, and superseded secure-BLE evidence.
- Preserved the canonical product package, active/prototype camera and model code,
  tests, model assets, `.venv`, and local `data/`/`logs/` state. Added ignore rules
  preventing nested firmware build products from returning.

### 2026-08-26 — Physical IMU contract correction

- Corrected the accepted wearable sensor from MPU6050 to exact MPU6500 after the
  real ESP32-C3 bench repeatedly reported `WHO_AM_I=0x70` and the owner explicitly
  approved the product change. MPU9250 identity `0x71` remains outside the contract;
  operating-profile, lower-back, and model-compatibility evidence remain open.

### 2026-08-25 — M0 foundation and canonical migration entry point

- Added the product architecture, rules, phased implementation plan, current-state
  audit, BLE/API/model contracts, security baseline, test strategy, operations
  guide, decision log, and root agent instructions.
- Sanitized the credential-bearing `.env.example`; the former broker credential
  still requires owner-side revocation/rotation.
- Designated the current FastAPI application as the temporary migration entry point
  and aligned config, launcher, systemd unit, installer output, and tests on
  configurable port 8000.
- Added a temporary Linux Python 3.12 bootstrap with a checksum-verified MediaPipe
  Heavy asset, filled the missing FastAPI/scikit-learn dependency declarations, and
  added launcher plus FastAPI health smoke tests.
- Recorded the separate lower-back ESP32-C3 + MPU6050 wearable decision and flagged
  the prototype's direct bar-velocity/power fields as an unvalidated model-contract
  mismatch for that sensor location.
- Local E1 result: 86 tests passed and all 86 installed packages are compatible.
  Pi 4 inventory, verified runtime/database backup, direct Tailscale path, IMX219
  open test, matching artifact hashes, real Flex/LiteRT model validation, loopback
  HTTP smoke, bounded latest-frame benchmark, and a clean 30-minute no-person soak
  were captured. Person-in-frame, ESP32/MPU6050, and privileged systemd boot
  evidence remain pending; see `docs/evidence/M0-03-BASELINE.md`.
- Fixed project `.env` loading so explicit shell/systemd configuration wins and the
  launcher cannot silently bind to stale hard-coded settings.
- Reworked the camera benchmark around a bounded latest-frame reader with stall
  limits, drop/error counters, and failure exit codes; this prevented slow pose
  inference from accumulating stale RTSP frames.
- Added a safe M0-02 credential-rotation evidence checklist. Repository containment
  is complete, but broker/Wi-Fi rotation and audit remain owner actions. A later
  firmware read found an ignored/untracked plaintext local secret file; Git history
  did not contain it, and it was replaced by a fail-closed placeholder template
  plus an ignored `secrets.local.h` override path.

### 2026-08-26 — M1-01 canonical package foundation

- Added a Python 3.12 `pyproject.toml`, universal hash-bearing `uv.lock`, buildable
  `src/digital_spotter` package, target component skeleton, and installed `dsctl`
  command.
- Added versioned TOML/environment configuration with explicit development/test/
  production profiles. Production rejects simulated adapters, wildcard origins,
  unsigned-model policy, relative state paths, and missing provisioned model,
  identity, or TLS files.
- Verified editable installation, a clean wheel install, core binary dependency
  resolution for Raspberry Pi aarch64, and seven new package/configuration tests.

### 2026-08-26 — M1-02 executable event/time contracts

- Added frozen v1 models for the common envelope, IMU, pose, fusion, rep, analysis,
  and component health data with stable quality/reason/state enums.
- Added distinct monotonic/UTC clock-domain types, deterministic UUIDv7 generation,
  and a strict 64 KiB MessagePack codec with field/container bounds.
- Added round-trip and rejection tests for all payloads, schema/type/time/quality
  mismatches, malformed/oversized data, non-finite values, and clock ordering.

### 2026-08-26 — M1-03 compatibility model manifest

- Hash-bound every current model/preprocessing artifact and froze the exact tensor,
  feature, phase/delta, preprocessing, threshold, runtime operator, and limitation
  contract in `models/manifest.json` and `models/model_card.md`.
- Added strict manifest/hash/order validation, `dsctl model check`, and a shared
  startup gate. Tampered/missing/reordered packages fail; the current unsigned,
  Flex-dependent, unevaluated package is allowed only for compatibility parity and
  is rejected in production.
- Confirmed a critical unit mismatch: saved acceleration artifacts imply values
  near `9.8 m/s2`, while current ESP firmware emits `g` and the Pi bridge performs
  no conversion. Product scoring remains blocked pending traceable unit validation.

### 2026-08-26 — M1-04 deterministic replay fixtures

- Added a strict, bounded replay-fixture contract, no-sleep monotonic replay clock,
  and an adapter that is permanently marked simulated and cannot authorize durable
  product persistence.
- Added a tiny hash-bound synthetic Y4M stream synchronized with synthetic pose,
  IMU, rep-phase, and analysis events, without human images or personal data.
- Added exact deterministic digests and negative fixtures/tests for IMU loss,
  sensor reboot/clock reset, event-type corruption, duplicate IDs, backward time,
  expectation tampering, and unsafe or mismatched video artifacts.

### 2026-08-26 — M1-05 SQLite migration and durable outbox

- Added two ordered, source-checksummed migrations that upgrade both fresh and
  copied prototype databases, backfill stable UUIDs for legacy rows, and create the
  target device/session/rep/model/analysis/outbox/audit tables and indexes.
- Added one-writer SQLite configuration with WAL, full synchronization, foreign
  keys, busy timeout, integrity checks, guarded pre-migration online backup, and a
  manifest-verified restore command that refuses overwrite.
- Added an idempotent repository transaction that commits completed rep, analysis,
  and an immutable composite cloud event together, rolls all three back on failure,
  and rejects simulated replay data from durable product storage.
- Added `dsctl database status|migrate|backup|restore` and fresh/legacy migration,
  tamper, rollback, idempotency, backup, and restore tests.

### 2026-07-19 — Pi 4B performance pass (benchmarked, see docs/PERFORMANCE.md)

Benchmarked with `scripts/benchmark_pipeline.py`. Findings: MediaPipe is the hard
bottleneck (~122 ms/frame → ~7.5 FPS ceiling, ~1.2 cores); resolution barely affects
pose cost (kept 1280×720 for clear camera). Two safe, measured optimizations kept:

- **mediamtx `rpiCameraFPS` 30 → 15** — the pipeline only consumes ~7.5 FPS, so 30 FPS
  capture/decode was ~3/4 wasted; video is pose-rate limited so this is invisible to the
  viewer. (Pi config; 30 FPS backup at `~/mediamtx.yml.bak30fps`.)
- **MJPEG encode caching** (`scripts/dashboard/main.py` `generate_mjpeg_frames`) —
  re-encode only when the frame actually changes (`FrameResult.timestamp_ms`), instead of
  every poll (~4× redundant JPEG encodes eliminated).

Result: system CPU 47.9% → **39.4%**, dashboard process 174% → **149%**, camera helper
CPU halved, temp −2 °C, **camera quality unchanged (720p)**; ESP32/MQTT/inference all
verified working. Added `scripts/benchmark_pipeline.py` and `docs/PERFORMANCE.md`.
Deliberately NOT changed: resolution (kept 720p) and `model_complexity` (kept 2 — lowering
needs a subject-in-frame accuracy check; see recommendations).

### 2026-07-19 — Demo fixes: camera corruption, IMU/camera decoupling, no auto-stop

- **Camera corruption fixed** (`vision/frame_processor.py`): removed the
  `analyzeduration;0|probesize;32` FFMPEG flags that starved the H.264 decoder of
  init data and produced corrupted macroblocks (lines/smears). Now uses
  `rtsp_transport;tcp|fflags;nobuffer|flags;low_delay` — clean video, still
  low-latency (verified: `/video_feed` frame is sharp). The camera/mediamtx H.264
  was never at fault (proved with a direct RTSP snapshot).
- **IMU no longer gated on the camera** (`scripts/dashboard/main.py`
  `_broadcast_live_data`): telemetry was only broadcast when the frame processor
  had a result, so IMU appeared on the graph only with the camera on. IMU now
  streams whenever the session is active and the sensor is on, independent of the
  camera. Camera-derived fields (fps/angles/rep_state) are still gated on the camera.
- **Toggling IMU off no longer stops the session** (`_monitor_connection` +
  frontend `startDisconnectWatch`): the monitor keyed "disconnect" off IMU data
  flow, so pausing the sensor looked like a disconnect and force-stopped the
  session (returning to the init screen). Now disconnect is based on the ESP32
  heartbeat (`esp32_online`), it never force-stops the session, and the dashboard
  just shows an "IMU OFF (paused)" / "IMU DISCONNECTED" notice on the chart label.
- **Chart status label** now reflects real state (LIVE / IMU OFF / DISCONNECTED)
  instead of being stuck on "connecting…".

### 2026-07-19 — Demo controls (sensor/camera toggles) + firmware v3.1

**Firmware (ESP32-C3, v3.1 — requires re-flash):**
- Removed the 30 s "Pi silent" battery-saving auto-stop. Once a session starts,
  both devices stay active and the MPU streams for the whole session
  (`checkPiTimeout()` is now a no-op in `DigitalSpotterComms.h`).
- Added `imu_on` / `imu_off` MQTT commands (with `_imuPaused` gate in
  `publishIMU`) so the dashboard can pause/resume IMU publishing without ending
  the session. Default = streaming ON. Acks: `ack_imu_on` / `ack_imu_off`.
- **MQTT connect diagnostics:** `_connectMqtt()` now logs a layered result —
  STEP 1 DNS resolve → STEP 2 TLS socket (cert check disabled) → STEP 3 MQTT
  CONNECT — so a failure names the exact layer (no-internet/DNS vs TLS/cert vs
  bad credentials) instead of only `rc=-2`. On TLS failure it prints the
  mbedTLS error via `WiFiClientSecure::lastError()`. `connectMQTT()` retries 5×
  before giving up. Added `_mqttStateStr()` for human-readable PubSubClient codes.
  STEP 1 now treats a `0.0.0.0` result as a DNS failure.
- **DNS override fix:** after WiFi connects, `_forcePublicDNS()` sets the lwIP
  resolvers to 8.8.8.8 / 1.1.1.1, bypassing broken hotspot DNS (Windows ICS
  proxies often resolve every name to 0.0.0.0, which was the real cause of the
  ESP32's `rc=-2`). Diagnosed via the new STEP logging (STEP 1 showed
  `DNS OK → 0.0.0.0`).

**Backend (`scripts/dashboard/main.py`, `imu/esp32_bridge.py`):**
- `ESP32Bridge.set_imu_streaming(enabled)` publishes the `imu_on`/`imu_off` cmd.
- New `POST /toggle-sensor` — toggles ESP32 IMU publishing (default ON).
- New `POST /toggle-camera` — toggles the live camera pipeline (default OFF);
  starts/stops the frame processor on demand.
- Camera now starts **OFF** by default; `/video_feed` streams a "Camera Off"
  placeholder until enabled (demo runs on pre-loaded data).
- `sensor_on` / `camera_on` exposed in `/status` and `/health`.
- Fixed `/health` 500 (`_feature_engineer._preprocessor` → `_lstm_runner._preprocessor`).

**Frontend (`scripts/dashboard/index.html`):**
- Added IMU sensor toggle (default ON) and camera toggle (default OFF) buttons
  by the live graph / camera panel; button state syncs from `/status`.

### Added
- PHASE_0: Project bootstrap — directory structure, dependencies, git setup

### Changed
- Upgraded inference pipeline to support v4 BiLSTM+MHA model
- Expanded feature vector from 38 to 40 features
- Added 4th synthetic timestep (delta sequence) for temporal context
- Replaced scaler_wrapper with preprocessor for full joblib artifact chain (winsorize, impute, scale)
- Updated session metadata and database schema to track subject height, weight, and FTR
