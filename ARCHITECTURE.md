# Digital Spotter target architecture

**Status:** Target architecture for the product migration
**Hardware:** Raspberry Pi 4B 8 GB, IMX219 camera, separate lower-back ESP32-C3 + MPU6500 wearable
**Last reviewed:** 2026-08-25

This document describes the system we are building. It is not a description of
the current prototype. Current facts and gaps are recorded in
`docs/CURRENT_STATE.md`; implementation order is controlled by `PLAN.md`.

## 1. Architecture goals

1. Keep the exercise loop operational without internet access.
2. Minimize latency by dropping stale work rather than building queues.
3. Isolate CPU-heavy vision and failure-prone hardware/network adapters.
4. Align camera and IMU data by measurement time.
5. Make degraded sensor, camera, model, and cloud states explicit.
6. Store sessions durably on the Pi before cloud synchronization.
7. Use per-device identity and least privilege from sensor to cloud.
8. Make every model result traceable to an input and model contract.
9. Be observable, recoverable, updateable, and testable on real hardware.

## 2. Product boundaries

### In scope

- Live camera pose estimation for supported barbell exercises.
- Wireless lower-back ESP32-C3 + MPU6500 acquisition over BLE.
- Timestamp alignment and multimodal feature construction.
- Rep segmentation, form classification, and non-blocking feedback.
- Local dashboard, session history, and device health.
- Durable offline storage and eventual cloud synchronization.
- Secure provisioning, authentication, signed updates, and audit events.

### Out of scope until separately approved

- Medical diagnosis or injury-prevention guarantees.
- Control of gym equipment.
- Continuous cloud dependence for live analysis.
- Continuous raw video upload by default.
- Supporting arbitrary camera/MCU/sensor hardware in the first product release.
- Adding an AI accelerator as a hidden requirement.

## 3. System context

```text
                 local BLE                         HTTPS
  Lower-back ESP32-C3/MPU6500 -> Raspberry Pi --------------> Cloud gateway
       ^                            |   ^                           |
       | feedback/control           |   | local HTTPS/WSS           +--> Firestore
       |                            |   |                           +--> Storage
       +----------------------------+   +---- phone/tablet/browser  +--> monitoring

  Camera --------------------------> Pi vision worker

  Internet outage boundary: everything left of the cloud gateway keeps working.
```

The moving sensor does not need a Wi-Fi connection. The Pi can use 5 GHz Wi-Fi for
the local dashboard and cloud where available, reducing competition with BLE in
the 2.4 GHz band.

## 4. Pi runtime topology

The product uses native systemd services on the Pi. Containers are useful in the
cloud but add little value to the fixed single-device edge deployment.

```text
                              +----------------------+
 camera --> ds-vision -------->                      |
               | H.264         |       ds-core       |<----> SQLite WAL
               +--> MediaMTX   | session/fusion/model|         |
                      |        | FastAPI + WebSocket  |         +--> outbox
                      +--> UI  +----------^-----------+                  |
                                         | UDS events                   v
 ESP32-C3 -- BLE --> ds-imu --------------+                         ds-sync
                                                                        |
                                                                        v
                                                                 Cloud gateway
```

### 4.1 `ds-core`

Owns:

- authoritative session state machine;
- timestamp mapping and multimodal fusion buffers;
- rep segmentation orchestration;
- canonical feature builder and inference runtime;
- local feedback policy;
- SQLite write transactions;
- versioned local HTTP/WebSocket API;
- readiness/degraded state aggregation.

It runs one Uvicorn worker because session state is device-local. CPU-heavy work is
not performed on the asyncio event loop. The core never owns the camera or BlueZ
connection.

R12 implements the first canonical core slice: one durable active session,
idempotent start/stop, controlled-restart restoration, a 250-sample IMU ring, and
aggregate-only IMU session summaries. SQLite calls run through a single bounded
256-item off-loop worker. R12 deliberately does not persist raw 50 Hz IMU samples
or introduce camera, fusion, model, API, UI, or cloud behavior.

### 4.2 `ds-vision`

Owns:

- Picamera2/libcamera configuration;
- camera capture timestamps;
- MediaPipe pose estimator lifecycle;
- landmark visibility and pose-quality calculation;
- hardware H.264 encoder output for MediaMTX;
- a latest-frame buffer with capacity one.

The intended camera configuration has two streams from one capture owner:

- a main 1280x720 stream encoded in hardware for WebRTC;
- a lower-resolution analysis stream for pose inference.

Encoded H.264 is published to MediaMTX on a loopback-only input. If the Pi camera
stack cannot sustain this ownership model, the measured fallback is MediaMTX as
camera owner plus local RTSP decode; that fallback must be decided by the camera
spike in `PLAN.md`, not by assumption.

R13-C provisionally selected the Picamera2 ownership model: it was the only tested
candidate with exposure-based monotonic timestamps and it used less measured CPU
than local RTSP decode. MediaMTX remains a relay and browser-facing WebRTC server,
not a second camera owner. Final acceptance still requires the deferred controlled
person and browser-latency gates recorded in ADR-014.

The worker publishes `PoseSample` events and health metrics. It does not draw the
skeleton for the live video and does not write the database.

### 4.3 `ds-imu`

Owns:

- BlueZ/DBus BLE discovery, pairing, connection, and reconnection;
- GATT protocol negotiation and session authentication;
- binary packet parsing and validation;
- sequence-gap accounting;
- ESP-to-Pi monotonic clock mapping;
- bounded sample buffering and sensor health.

The first implementation may use Bleak. A native Rust/C++ helper is justified only
if real measurements show unacceptable DBus/Python jitter or loss.

R11 is the first active implementation: one Bleak process verifies the frozen R9
identity/GATT contract, controls streaming, parses 20-byte samples, bounds ingress
at 16 packets, exposes a one-value latest slot, and publishes canonical events over
UDS. R13-B adds ESP-to-Pi monotonic mapping without changing R9 firmware by
timestamping the existing on-demand status read around its ESP `uptime_ms` value.
It counts but withholds samples from the core publisher until the clock is
synchronized. Pairing/session authentication remains deferred under ADR-019.

### 4.3.1 Wearable actuator boundary

The assembled wearable uses external RGB red1/green0/blue3 with hardware PWM
and the GPIO10 active-buzzer transistor driver. The archived R9 board used a
GPIO8 NeoPixel. ESP32 firmware owns
only non-blocking cue execution, local device-state indication, actuator health,
and bounded priority/cancellation. It does not classify form or decide whether a
model result is safe to communicate.

`ds-core` owns feedback eligibility, quality suppression, and rate limiting. It
delegates an allowed cue through `ds-imu`, which sends a versioned authenticated and
replay-resistant BLE command. Local boot, provisioning, ready, streaming, degraded,
error, and low-battery indications may be derived from authoritative firmware state;
model-result cues always require the Pi policy decision. Actuator work must never
block the IMU sampler, NimBLE host, or control-response path.

### 4.4 MediaMTX

Owns WebRTC/WHEP delivery to the browser. It receives an already hardware-encoded
H.264 stream over loopback. The browser draws pose landmarks on a canvas using
timestamped telemetry from `ds-core`.

### 4.5 `ds-sync`

Reads the durable SQLite outbox and uploads records asynchronously. It uses finite
timeouts, idempotency keys, capped exponential backoff with jitter, and a circuit
breaker. It never subscribes to raw capture callbacks and can be stopped without
affecting an active session.

### 4.6 Browser/client

The client:

- authenticates and pairs with the local device;
- receives WebRTC video directly from MediaMTX;
- receives low-rate status, landmarks, rep events, and analysis over WSS;
- renders overlays client-side;
- clearly displays real, degraded, offline, and simulated states;
- does not contain model/business logic or Firebase Admin access.

M3-04 implements the reusable browser video primitives under
`src/digital_spotter/web/static/` without promoting the historical frontend or
changing the migration dashboard. WHEP negotiation is delegated to MediaMTX's
supported browser reader. A bounded client-side timeline maps WebRTC frame
`captureTime` into the Pi monotonic clock using a four-timestamp exchange, then
draws only a nearby `good` pose sample inside the video's contained display
rectangle. Missing timing, stale/degraded pose, and simulated pose clear the
overlay. The authenticated WSS/stream-config transport remains owned by M6.
For M3-04 research only, a temporary `127.0.0.1` HTTP bridge consumes the
existing vision UDS stream, projects bounded pose events, and answers clock
exchanges for the isolated preview. It is not an installed product service or
the M6 authenticated API.

M6-D01 adds a browser-only Demo tab to the same dashboard shell. It lazily loads
a pinned offline 3D renderer, draws illustrative exercise motion, and consumes
existing UI status/window events. It is not a camera/BLE owner or model runtime;
normal Workout remains independent. Subsequent scenario replay, inference and
physical demo feedback require separate canonical integration slices, not
hard-coded predictions or a production readiness override (ADR-021).

M6-D02 adds an opt-in `DemoReplay` adapter beside, not inside, live session
ingestion. It loads four integrity-checked raw phase fixtures and calls the
existing `predict_reference_only` on the core event loop. The interpreter is
shared with normal model diagnostics; HTTP threads never own it. Demo requests
do not enter sensor queues, session persistence or actuator dispatch. Animation
only schedules a request after each rep; it does not supply pose/features.

M6-D03 replaces the primitive body renderer with one local, licensed GLB skin and
fixed-length skeletal posing. The glTF loader is pinned to the already vendored
Three.js release. No external model requests, camera/pose worker or new inference
path are introduced; rendering remains browser-side and illustrative only.

## 5. Internal communication

Pi processes exchange versioned MessagePack event envelopes over Unix domain
`SOCK_SEQPACKET` sockets under `/run/digital-spotter/`.

The active R11/R12 research bridge currently uses a bounded length-prefixed Unix
stream because the frozen R11 publisher was accepted on that interface. R12
enforces the same 64 KiB event limit, schema validation, restrictive socket mode,
single-client default, and optional Linux peer-UID check. Moving the unchanged
event contract to `SOCK_SEQPACKET` remains a later transport-hardening change and
must not be mixed into the R12 persistence gate.

- Local sockets are owned by the dedicated service user/group and are not exposed
  on the LAN.
- Producers reconnect with bounded backoff.
- Event payloads are size-limited and validated.
- The core authenticates the peer process through socket permissions and Linux
  peer credentials.
- High-rate producers send non-blockingly; when the kernel buffer is full, a
  measured sample/frame is dropped and a counter is incremented.
- Lifecycle commands use a separate request/response control socket so data bursts
  cannot delay stop or health commands.

The initial limits are:

| Path | Limit | Overflow behavior |
|---|---:|---|
| Camera frame awaiting pose | 1 frame | Replace with newest frame |
| Pose events in core | 4 events | Drop oldest pose event |
| IMU fusion ring | 5 seconds | Evict oldest sample |
| WebSocket telemetry per client | 2 messages | Coalesce to newest state |
| Database work queue | 256 events | Enter degraded state; do not lose completed reps |
| Cloud sync | Durable SQLite outbox | Backpressure by disk quota/retention policy |

These are configuration defaults and must be confirmed by Pi tests.

## 6. Time and fusion model

All internal measurement time is integer nanoseconds in the Pi monotonic clock
domain.

1. ESP32 samples contain a wrapping monotonic sensor counter and sequence number.
2. Active R9 timestamps its on-demand status read around ESP `uptime_ms`; the later
   secure protocol may replace this with a higher-resolution authenticated
   request/response exchange without changing the event contract.
3. It estimates offset and drift using multiple low-round-trip samples and maps
   sensor timestamps to `captured_monotonic_ns`.
4. `ds-vision` stamps the frame as close to sensor exposure/capture as the camera
   API permits.
5. The fusion engine finds/interpolates IMU samples around each pose timestamp.
6. Wall-clock UTC is attached only for display/cloud correlation; wall-clock jumps
   never change rep logic.

Quality state is part of every fused sample:

- `good`: pose and IMU are fresh and synchronized;
- `vision_degraded`: pose visibility/confidence below policy;
- `imu_degraded`: IMU stale, gaps excessive, or calibration invalid;
- `unsynchronized`: estimated clock error exceeds budget;
- `unavailable`: required input/model absent.

The current multimodal model may score only `good` samples. No zeros are injected
for missing IMU. A future vision-only fallback requires a separately trained and
versioned model.

## 7. Exercise processing pipeline

```text
capture -> pose/IMU samples -> quality gate -> time fusion -> rep state machine
        -> phase snapshots -> canonical 40-feature contract -> preprocessing
        -> model -> feedback policy -> one rep transaction -> outbox event
```

During migration, the current `(4, 40)` model contract remains immutable only for
reproducibility and parity testing. Its four timesteps are three rep phases plus the
computed delta row. The contract contains `V_Bar_Velocity_Vertical`,
`P_Bar_Power_Watts`, and velocity-derived fields, but the accepted lower-back sensor
does not directly observe bar movement. Those fields cannot support product claims
unless a derivation is independently validated against a bar-motion reference;
otherwise they must be renamed/removed and the model retrained. The final runtime
must use one feature builder for live, replay, and diagnostic API calls.

The current model imports full TensorFlow for Flex operators. The product target is
an int8 model using only built-in LiteRT/TFLite operations, with accuracy parity
evaluated before replacement.

### 7.1 Isolated research retraining boundary (ADR-020)

The owner authorized local PC/WSL retraining preparation on 2026-10-20 under
`training/v5_imu_retraining/`. This is not imported by the Pi runtime. FYP and
`models/digital_spotter_v5/` remain unchanged reference/deployment artifacts.
Only a separately fitted and evaluated candidate package may later cross the
training-to-runtime boundary. Copied historical pipelines are passive references,
not active launchers. The disclosed synthetic provenance limits evaluation claims;
copy integrity or successful training cannot establish real-world form accuracy.

M5-R04 adds a reference-only reader for the new candidate in
`src/digital_spotter/inference/v5_candidate.py`. It reads immutable exported
JSON/TFLite artifacts and imports no training code, sklearn or TensorFlow.
It reuses the canonical V5 numeric transform, feature registry and LiteRT
inference implementation. Selection is explicit by package path and version;
the legacy default is unchanged. Live candidate scoring remains denied until a
separate physical-feature and activation decision. Session metadata follows the
loaded model's version rather than a global historical constant.

## 8. Wireless sensor architecture

ESP32-C3 acts as a BLE peripheral and the Pi is the central. The active research
bring-up uses the proven Arduino-ESP32 BLE API and advances through
`docs/BLE_RESEARCH_BRINGUP_PLAN.md`. The interface contract, not a framework name,
is the immediate gate. A later measured decision may keep Arduino-ESP32 or migrate
the same passing behavior to native ESP-IDF/NimBLE; the working baseline remains
the rollback oracle.

The ESP32-C3 and MPU6500 form one self-contained lower-back wearable. The MPU6500
uses short internal I2C wiring inside that device; there is no tether from the
wearable to the Pi. Calibration must define a repeatable body coordinate frame and
detect incorrect orientation or attachment slippage. The signal can support
validated trunk movement, rotation, tempo, rep phase, and smoothness features, but
is not a direct barbell-motion measurement.

The service has four logical characteristics:

| Characteristic | Direction | BLE mode | Purpose |
|---|---|---|---|
| control | Pi to ESP | write with response | pair/provision, start, stop, calibrate, time-sync |
| IMU stream | ESP to Pi | notification | high-rate binary samples |
| status | ESP to Pi | indication/notification | battery, calibration, errors, firmware, counters |
| device info | ESP to Pi | read | protocol, device, hardware, firmware versions |

The baseline IMU sample is exactly 20 bytes so it fits the default ATT payload:

```text
u8 version | u8 flags | u16 sequence | u32 sensor_time_us |
i16 ax | i16 ay | i16 az | i16 gx | i16 gy | i16 gz
```

Units/scales and byte order are frozen by protocol version and specified in
`docs/INTERFACES.md`. Battery and extended diagnostics are carried in status
packets. A larger negotiated MTU may batch samples later, but correctness cannot
depend on that optimization.

Active mode starts at 50 Hz with 100 Hz as the target. Notifications carry data;
indications/write responses are reserved for critical state changes. Under the
active research profile, device name/address checks and bounded harmless commands
are sufficient during bring-up. Standard BLE bonding/encryption is an optional
later stage. Custom session challenges, device allow-lists, and replay protection
are deferred commercial hardening under ADR-019.

## 9. Local persistence

SQLite runs in WAL mode with foreign keys enabled. The core is the primary writer.
The target logical tables are:

- `schema_migrations`
- `devices`
- `sessions`
- `reps`
- `analysis_events`
- `sensor_chunks` (optional and retention-bound)
- `model_registry`
- `outbox`
- `audit_events`

A completed rep and its outbox event commit atomically. Every cloud-bound event has
a stable UUID, schema version, device ID, session ID, creation time, payload hash,
attempt count, next-attempt time, and acknowledgment state.

## 10. Cloud architecture

```text
Pi ds-sync -- HTTPS + device identity --> Cloud Run ingestion API
                                               |
                        +----------------------+------------------+
                        |                      |                  |
                   Firestore              Cloud Storage      monitoring
                 summaries/events       approved evidence    audit/alerts
```

- Firebase Authentication identifies human users.
- The ingestion gateway validates device identity, authorization, schema, size,
  nonce/idempotency key, and ownership.
- Firestore stores normalized session/rep/analysis summaries.
- Cloud Storage stores only explicitly approved media or compressed diagnostic
  artifacts.
- Firebase Admin SDK credentials exist only in the cloud runtime and are governed
  by IAM.
- App Check may protect supported user clients/gateway endpoints but does not
  replace user/device authentication.

Cloud collection names and retention periods remain provisional until privacy and
account requirements are approved.

## 11. Security boundaries

Trust boundaries exist at:

1. physical sensor to Pi BLE;
2. browser/client to local Pi API;
3. Pi to cloud gateway;
4. gateway to Firebase services;
5. update service to Pi/ESP firmware;
6. local processes to privileged hardware and secrets.

Each physical device receives a unique identity. The Pi stores secrets outside the
repository with owner-only permissions. Production services run unprivileged with
systemd hardening. Updates are signed and rollback-capable. Full requirements and
current blockers are in `docs/SECURITY.md`.

## 12. Deployment layout

Target filesystem layout:

```text
/opt/digital-spotter/releases/<version>/  immutable application release
/opt/digital-spotter/current              atomic symlink to active release
/etc/digital-spotter/config.toml          non-secret product configuration
/etc/digital-spotter/secrets.env          root-owned secrets, mode 0600
/var/lib/digital-spotter/                  SQLite, model packages, device identity
/var/log/ or journald                      structured operational logs
/run/digital-spotter/                      runtime sockets and PID/state files
```

Application code is read-only at runtime. Mutable data lives on a separate path and
is backed up before migrations. Systemd applies restart limits, watchdogs, resource
limits, capability restrictions, and dependency ordering.

## 13. Degraded and recovery behavior

| Failure | Local behavior |
|---|---|
| WAN/Firebase unavailable | Continue session; enqueue uploads |
| ESP32 disconnects | Mark IMU degraded; reconnect; stop multimodal scoring |
| Camera/pose unavailable | Mark vision degraded; preserve session controls/data |
| Model missing/incompatible | Fail inference readiness; never use random output |
| MediaMTX unavailable | Analysis continues; UI video unavailable |
| API client disconnects | Session continues according to explicit session policy |
| Disk approaching quota | Stop optional raw capture first; preserve reps/outbox |
| Process crash | systemd restarts; recover last consistent session state |
| Bad software update | Health gate fails and release symlink rolls back |

## 14. Initial performance budgets

These are product acceptance targets, not current claims:

| Metric | Target |
|---|---:|
| Pose throughput on a person | 8-12 FPS with accuracy gate met |
| IMU active sample rate | 50 Hz minimum; 100 Hz goal |
| BLE loss over 30 minutes | less than 0.5 percent |
| Camera/IMU alignment error | p95 less than 20 ms |
| Classifier latency | p95 less than 25 ms |
| Rep result after completion | p95 less than 150 ms |
| Local video glass-to-glass latency | p95 less than 250 ms |
| Active-session cloud calls | zero in critical path |
| Soak duration | 60 minutes without crash, leak, or throttling |

Accuracy, safety, and reliability gates take priority over a higher frame rate.

## 15. Target source layout

```text
src/digital_spotter/
  api/             local HTTP/WebSocket schemas and handlers
  web/             reusable browser video/overlay modules (not an API owner)
  core/            sessions, fusion, rep state, feedback policy
  contracts/       versioned event/model/wire schemas
  vision/          camera and pose worker
  imu/             BLE adapter, parser, clock synchronization
  inference/       feature builder, preprocessing, model runtime
  persistence/     SQLite repositories, migrations, outbox
  sync/            cloud gateway client and retry policy
  security/        provisioning, identity, authorization helpers
  observability/   health, metrics, structured logging
firmware/esp32_c3_research/
tests/
  unit/
  contract/
  replay/
  integration/
  hardware/
```

Migration to this layout is incremental. Historical paths are removed only after
their behavior is covered by the new packages and release gates.

## 16. Official technical references

Reviewed 2026-08-25:

- [ESP32-C3 Bluetooth LE overview](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c3/api-guides/ble/overview.html)
- [Raspberry Pi camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [MediaPipe Pose Landmarker API](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarker)
- [MediaMTX WebRTC/WHEP documentation](https://github.com/bluenviron/mediamtx/blob/main/docs/4-read/03-webrtc.md)
- [Firebase security checklist](https://firebase.google.com/support/guides/security-checklist)
