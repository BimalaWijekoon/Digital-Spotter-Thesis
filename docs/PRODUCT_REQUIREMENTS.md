# Digital Spotter product requirements

**Status:** Research baseline; future commercial requirements are explicitly marked
**Last reviewed:** 2026-08-27

The active deliverable is a controlled research system. ADR-019 and
`docs/BLE_RESEARCH_BRINGUP_PLAN.md` define the current reliability-first BLE scope.
Commercial provisioning, custom application cryptography, signed updates, and
hostile-device security validation are future hardening and are not gates for the
current research result. Basic secret hygiene, local-only operation, honest
security-state reporting, and safe bounded inputs remain mandatory.

## 1. Product statement

Digital Spotter is a local-first exercise analysis assistant for supported barbell
lifts. A Raspberry Pi observes the athlete through a camera, receives motion data
from a wireless ESP32-C3 IMU, detects repetitions, estimates form quality, provides
non-blocking feedback, saves the workout locally, and synchronizes selected
analysis data when internet access is available.

It supports training awareness. It is not a medical device, injury-prevention
guarantee, or replacement for a qualified coach.

## 2. Primary users

- **Athlete:** starts a session, sees camera alignment and sensor health, receives
  rep feedback, and reviews history.
- **Coach/operator:** provisions devices, calibrates a sensor, reviews sessions,
  diagnoses failures, and manages supported exercises/models.
- **Support engineer:** receives redacted health evidence, restores a device, and
  safely rolls forward/back.

The first release may combine athlete and owner roles, but authorization boundaries
must not assume every LAN user is trusted.

## 3. Fixed constraints

- Raspberry Pi 4B 8 GB is the edge device.
- A separate lower-back wearable contains the ESP32-C3 and MPU6500
  (`WHO_AM_I=0x70`).
- The moving sensor is not tethered to the Pi.
- Analysis must continue without WAN access.
- Vision, IMU fusion, model inference, and feedback run locally.
- Cloud storage is asynchronous and cannot be the local system of record.

## 4. Supported first-release journey

1. Device boots into a visible ready or degraded state.
2. Owner pairs/provisions the local Pi and ESP32-C3.
3. Athlete selects a supported exercise and enters required subject/load context.
4. UI verifies camera framing, pose quality, BLE link, battery, calibration, model,
   storage, and temperature.
5. Athlete starts the session while WAN may be unavailable.
6. System captures synchronized pose and IMU data and detects reps.
7. Every completed, sufficiently high-quality rep receives at most one analysis.
8. Feedback is delivered without blocking or controlling equipment.
9. Session can be stopped cleanly after client disconnect/reconnect.
10. Session and rep analysis is saved locally before it is shown as durable.
11. Cloud synchronization resumes later and is idempotent.
12. Athlete can review and, where policy applies, export/delete their data.

## 5. Functional requirements

### FR-01 Device readiness

The product shall expose individual readiness for camera, pose worker, BLE sensor,
calibration, time synchronization, model/artifacts, database, storage capacity,
temperature/throttling, video, local API, and cloud sync.

Readiness must distinguish real hardware from simulated/replay adapters.

### FR-02 Sensor provisioning and connection

The product shall provision exactly identified ESP32-C3 sensors, reject unknown
devices, reconnect after transient loss, report battery/link/data quality, and
support a physical factory-reset/re-pair workflow.

### FR-03 Calibration

The product shall guide a mounting-specific calibration, store its version and
timestamp, detect invalid/stale calibration, and prevent multimodal scoring when
the required calibration is unavailable.

### FR-04 Camera setup

The product shall show a low-latency local stream, framing guidance, pose
visibility/quality, and explicit camera loss/recovery state.

### FR-05 Session lifecycle

Start/stop must be idempotent. A session has one authoritative owner/state and can
recover after UI disconnect or a controlled process restart without duplicate
records.

### FR-06 Rep detection and analysis

For supported exercises, the system shall segment reps, construct the versioned
multimodal input contract, run the approved model, quality-gate the result, and
persist the model/version/confidence/quality/limitations with the rep.

### FR-07 Feedback

The product shall provide visual and optional audible feedback. Feedback must be
rate-limited and suppressed for mock, stale, unsynchronized, low-quality, or
unavailable results.

The assembled lower-back wearable uses the external RGB module (red GPIO1,
green GPIO0, blue GPIO3) for visible device state and its GPIO10 active-buzzer
driver for optional session/error/form cues. Actuator execution must be
non-blocking. Model-derived wearable cues require an authenticated Pi command and
the same quality suppression policy as every other user-facing feedback channel.

For the research appliance, the separate Pi RGB may show local `wlan0` readiness:
dim blue when the interface has a local IPv4 address and a slow amber pulse when
it does not. This check must not contact an internet host, expose the address, or
change Wi-Fi/Tailscale configuration. Exercise/demo result cues override this
idle indication; network state never activates the buzzer or wearable LED.

### FR-08 Local history

Users shall review sessions and per-rep summaries when offline. Data shall remain
consistent across reboot and interrupted cloud upload.

### FR-09 Cloud synchronization

Selected versioned events shall upload through an authenticated gateway with stable
idempotency keys. Duplicate requests, timeout, reboot, and long offline periods
must not create duplicate cloud sessions/reps.

### FR-10 Updates and recovery

The Pi application, model package, and ESP firmware shall accept only approved
signed updates, validate health after activation, and provide rollback/recovery.

## 6. Non-functional requirements

### NFR-01 Latency and throughput

- Pose target: 8-12 FPS on a real person while meeting accuracy criteria.
- IMU: 50 Hz minimum; 100 Hz goal.
- Camera/IMU alignment: p95 under 20 ms.
- Classifier: p95 under 25 ms.
- Result after rep completion: p95 under 150 ms.
- Local video: p95 glass-to-glass under 250 ms.

These are acceptance targets to validate on the final Pi/enclosure/mount.

### NFR-02 Reliability

- No unbounded runtime queue.
- 60-minute supported-session soak without crash, memory growth, or throttling.
- BLE loss under 0.5 percent over 30 minutes in the target gym scenario.
- Local session survives WAN loss and client reconnect.
- Completed reps are transactionally persisted.

### NFR-03 Security (future commercial profile)

- Unique device identities; no shared production default secret.
- Encrypted/authenticated BLE and local/cloud command channels.
- Explicit production CORS/origin and authorization policy.
- No Firebase Admin key on the Pi.
- Verified TLS, least-privilege services, signed updates, redacted logs.
- Revocation, reset, and recovery paths are tested.

### NFR-04 Privacy

- Collect the minimum data needed for the approved feature.
- Continuous raw video is neither retained nor uploaded by default.
- Raw IMU retention/upload requires a named purpose, limit, consent, and deletion
  policy.
- Export/deletion and retention behavior must be testable before cloud release.

### NFR-05 Maintainability

- One canonical implementation per responsibility.
- Versioned, executable BLE/event/API/model/database contracts.
- Reproducible locked dependencies and signed artifacts.
- Automated unit/contract/replay/integration tests plus real-hardware evidence.
- Operational health, structured logs, backup, rollback, and support runbooks.

## 7. Safety and quality states

Analysis is allowed only when all model-required modalities are sufficiently fresh,
synchronized, calibrated, visible, and contract-compatible. Otherwise the system
shall return an explicit reason such as:

- `pose_low_visibility`
- `imu_stale`
- `imu_packet_loss_high`
- `clock_unsynchronized`
- `calibration_required`
- `model_unavailable`
- `model_contract_mismatch`
- `storage_unavailable`

It must not silently use zeros, random output, or the last valid sample.

## 8. First-release exercises

The prototype lists barbell back squat and conventional deadlift. Their inclusion
in the product release depends on model/data evidence for the selected IMU mounting
and sensor. An exercise is supported only when its calibration, segmentation,
evaluation, UI guidance, and limitations pass the release gate.

## Controlled viva demonstration (owner request, 2026-10-22)

The existing dashboard has a separate Demo tab sharing its layout and actual
device status. The first slice provides illustrative squat/deadlift animation,
correct/incorrect form-scenario selection and start/pause/reset; scenario choice
is not a forced classifier result. Browser rendering must work offline. Live
workout controls, inference eligibility and sensor data remain independent.
Later replay/model and demonstration-only hardware feedback require explicit
source labels and isolated records, never real gym-validation/readiness claims.
The initial UI does not implement or advertise those later capabilities.
M6-D02 adds local, explicitly synthetic reference-only inference from frozen
three-phase fixtures. The animation schedules calculation but does not provide
measured pose/IMU features. Actual hardware feedback and Pi activation remain
separate; selected form cannot force the classifier decision.

## 9. Explicit non-goals for the first release

- Counting every exercise type.
- Coaching claims beyond the trained/evaluated labels.
- Multi-camera fusion.
- Remote real-time video coaching.
- Fully autonomous hardware actuation.
- Raw-data surveillance or indefinite retention.
- Hiding failures behind fallback/random predictions.

## 10. Open product decisions

1. MPU6500 range, digital filtering, sample rate, orientation, and calibration
   profile for the lower-back enclosure.
2. First supported client and pairing UX.
3. Supported exercise/label set after evaluation, including replacement or
   validation of the prototype's direct-bar feature semantics.
4. Whether any evidence clip/raw sensor upload is allowed.
5. Retention, account ownership, export/deletion, and privacy terms.
6. Ambient temperature, distance, session duration, and number of nearby units to
   support.
7. Feedback hardware and gym noise/accessibility requirements.

Record accepted answers in `docs/DECISIONS.md` and update the relevant contracts.

## 11. Release acceptance

The product is release-ready only when all gates in `PLAN.md` through G8 have
evidence. A successful demo, mock-mode test, architecture implementation, or cloud
connection alone is not release acceptance.
