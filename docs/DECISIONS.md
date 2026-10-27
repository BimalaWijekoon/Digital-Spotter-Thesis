# Digital Spotter decision log

Use this file for decisions that constrain several components. Do not silently
change an accepted decision in code. Create a new decision that supersedes it and
records migration/rollback.

Status values: `ACCEPTED`, `PROPOSED`, `DECISION NEEDED`, `SUPERSEDED`.

## Accepted decisions

### ADR-001 — Fixed first-product edge hardware

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Target Raspberry Pi 4 Model B with 8 GB RAM and ESP32-C3. Do not
  require a Pi 5 or AI accelerator for the first product architecture.
- **Reason:** This is the hardware the owner has fixed for the product work.
- **Consequences:** Optimize CPU, memory, camera, model operators, and thermals for
  the Pi 4. Acceleration may be a future optional SKU, not a hidden dependency.

### ADR-002 — No moving tether

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** No normal-operation wire between the lower-back wearable and the
  Pi.
- **Reason:** A cable is unreliable and unsafe/awkward in real gym movement.
- **Consequences:** Sensor power is local; transport, enclosure, battery, pairing,
  recovery, and RF testing are product requirements.

### ADR-003 — BLE is the primary sensor transport

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Use secure local BLE GATT between ESP32-C3 and Pi. Use NimBLE on the
  ESP32-C3 and BlueZ through a Pi adapter.
- **Reason:** IMU bandwidth is small, ESP32-C3 supports BLE, the Pi is a direct
  central, and the real-time path should not require Wi-Fi/cloud infrastructure.
- **Consequences:** Implement a binary protocol, device provisioning, bonding,
  authenticated commands, clock synchronization, reconnect, and gym RF tests.
  Preserve MQTT firmware only as a migration rollback until G2.

### ADR-004 — Edge-first critical loop

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Capture, fusion, rep segmentation, inference, feedback, and local
  persistence run on the Pi with no WAN dependency.
- **Reason:** Gyms have variable connectivity; latency and availability must be
  deterministic.
- **Consequences:** Cloud sync operates only from a durable outbox. Cloud failure is
  a sync health issue, not a session failure.

### ADR-005 — SQLite local truth and outbox

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** SQLite is the local system of record and durable cloud outbox.
- **Reason:** It is lightweight, transactional, offline-capable, and appropriate for
  one edge device.
- **Consequences:** Use WAL, migrations, foreign keys, atomic rep+outbox commits,
  backups, retention, and disk-pressure policy.

### ADR-006 — Firebase behind a cloud gateway

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Use Firestore/Storage for approved cloud data through a Cloud Run
  ingestion gateway. Do not place Firebase Admin credentials on the Pi.
- **Reason:** The gateway centralizes validation, authorization, idempotency,
  auditing, rate limits, and tenant/device ownership.
- **Consequences:** Pi uses unique device authentication. Firebase rules/IAM and
  human Firebase Auth remain cloud/client concerns.

### ADR-007 — Latest-frame isolated vision worker

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Run camera/pose in an isolated worker with a one-frame latest buffer.
- **Reason:** MediaPipe is the measured CPU bottleneck; stale queued frames create
  latency without increasing useful information.
- **Consequences:** Dropped-frame metrics are normal. The core consumes timestamped
  poses and remains alive if the worker restarts.

### ADR-008 — Hardware video and direct WebRTC

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Target hardware H.264 to MediaMTX/WHEP and draw pose overlays in the
  browser. Python MJPEG remains migration-only.
- **Reason:** Avoid redundant decode/draw/JPEG work on the Pi and lower dashboard
  latency/CPU.
- **Consequences:** Camera ownership/publication method must pass M3-02 before it is
  frozen.

### ADR-009 — One canonical model path, no silent mocks

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Live, replay, and diagnostic API use one feature/inference contract.
  Missing artifacts or modalities produce explicit unavailability in production.
- **Reason:** Current duplicated feature math and mock fallback can create results
  that do not represent the trained model.
- **Consequences:** Manifest/artifact checks and replay/golden-vector tests precede
  migration. Mocks remain test-only and are visibly labeled.

### ADR-010 — Native systemd edge deployment

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Run bounded native services under systemd on the Pi; use containers
  for cloud deployment where appropriate.
- **Reason:** Native services give direct camera/BlueZ/GPIO integration with lower
  edge operational overhead.
- **Consequences:** Build signed immutable releases, least-privilege units,
  watchdogs, health-gated activation, and rollback.

### ADR-011 — IMU mounting position

- **Status:** ACCEPTED
- **Date:** 2026-08-25
- **Decision:** Mount a separate ESP32-C3 + IMU wearable on the athlete's lower
  back. It has no tether to the Pi. ADR-017 controls the exact sensor identity.
- **Consequences:** Define a repeatable body-frame orientation and validate
  attachment slippage, comfort, enclosure, antenna/RF behavior, and agreement with
  training data. The signal is body/trunk motion and cannot be labeled as direct
  barbell velocity or power without independent reference validation.

### ADR-012 — Exact IMU sensor and range

- **Status:** SUPERSEDED by ADR-017
- **Date:** 2026-08-25
- **Decision:** Use the MPU6050 connected to the ESP32-C3 over internal I2C. Current
  firmware identifies WHO_AM_I `0x68`, samples at 50 Hz, and converts using the
  default +/-2 g and +/-250 degrees/s scales.
- **Consequences:** Lower-back field tests must still select and version the final
  range, digital filtering, rate, orientation transform, calibration, module
  replacement policy, and saturation/noise limits before the model contract is
  frozen.

### ADR-017 — Correct physical IMU identity to MPU6500

- **Status:** ACCEPTED; operating profile and model compatibility remain open
- **Date:** 2026-08-26
- **Decision:** Use the MPU6500 connected to the ESP32-C3 over internal I2C and
  require the exact identity `WHO_AM_I=0x70`. Do not silently accept MPU9250
  identity `0x71` or the former MPU6050 identity `0x68` under this contract.
- **Context/evidence:** The owner corrected the module identification after the
  real USB bench repeatedly read `0x70` at I2C address `0x68`; the legacy driver
  mapping also labels `0x70` as MPU6500. The owner explicitly approved changing
  the product sensor contract to MPU6500 on 2026-08-26.
- **Consequences/risks:** The development profile remains 50 Hz, +/-2 g and
  +/-250 degrees/s, but its range, DLPF, unit conversion, orientation, calibration,
  noise, saturation, and attachment behavior require real lower-back evidence.
  Existing model artifacts have no traceable MPU6500 provenance; production/live
  scoring remains prohibited until the model and unit contracts pass M4/M5.
- **Migration:** Update firmware identity checks, typed device-info contracts,
  fixtures, current product documents, and real-hardware evidence. Preserve the
  sensor-error state when the exact device is absent or unstable.
- **Rollback:** Replace the module with a separately approved and verified sensor
  contract or revert the product decision and firmware together; never relabel an
  unmatched identity byte.
- **Owner approval:** "I approve changing the product sensor contract to MPU6500
  and pairing this Pi with this wearable."

### ADR-016 — BLE application-session authentication

- **Status:** SUPERSEDED for the active research build by ADR-019
- **Date:** 2026-08-26
- **Decision:** Keep NimBLE Secure Connections bonding/encryption and additionally
  authenticate canonical control commands with a unique 32-byte per-wearable key.
  Prove the device on each connection, derive a per-boot/session HKDF-SHA-256 key,
  require sensor-time freshness windows, and retain a bounded command-ID replay
  cache. Return authenticated logical results as control-characteristic
  indications.
- **Reason:** Headless `Just Works` pairing does not prove the intended product
  identity, while a shared fleet secret or unauthenticated command path would make
  nearby spoofing/replay a product risk.
- **Consequences:** Missing credentials fail closed. The Pi key file is exact,
  owner-only, and non-symlink; the ESP key lives in protected NVS and is never
  compiled into firmware. Only one command is outstanding per connection. Physical
  provisioning/reset, bond allow-listing, and production flash protection remain
  required before M2-03 can finish.
- **Rollback:** Disable the new agent/firmware feature flag and return to the
  non-product prototype; never fall back to a default key or unauthenticated BLE
  mutation.

The implementation and evidence remain historical. ADR-019 defers this control;
it is not part of the current research bring-up ladder.

### ADR-018 — Preserve wearable NeoPixel and buzzer with split policy/execution

- **Status:** ACCEPTED
- **Date:** 2026-08-26
- **Decision:** Retain the lower-back wearable's GPIO 8 NeoPixel and GPIO 10 buzzer.
  ESP32 firmware executes bounded non-blocking cues and local device-state signals;
  `ds-core` decides whether analysis feedback is eligible, and `ds-imu` transports
  only versioned authenticated/replay-resistant commands.
- **Reason:** Visible state, identification, session cues, and optional audible form
  feedback are product behavior worth preserving. The legacy Arduino implementation
  uses blocking `delay()` patterns and unauthenticated MQTT delivery, so it cannot be
  copied into the real-time BLE path unchanged.
- **Consequences/risks:** M2-05 adds an actuator scheduler, strict command contract,
  priority/cancellation/rate limits, health counters, and real GPIO tests. Mock,
  stale, unsynchronized, low-quality, or unavailable analysis cannot trigger form
  feedback. Actuator concurrency must not degrade 50 Hz IMU or BLE behavior.
- **Migration:** Port behavior pattern-by-pattern from the legacy firmware after
  defining golden command vectors. Keep model-derived cues disabled until M4-04
  supplies the canonical feedback policy.
- **Rollback:** Compile-time disable actuators while preserving IMU streaming and
  health; never fall back to blocking or unauthenticated cue execution.
- **Owner direction:** Preserve these wearable functions in the M2 plan and use
  proportional validation rather than repeating long soaks for small changes.
- **Assembled PCB amendment (2026-10-19, M2-07):** Owner-approved PCB integration
  replaces the GPIO8 NeoPixel with external PWM RGB red1/green0/blue3 and retains
  GPIO10 as a timed active-buzzer driver. SDA/SCL become GPIO18/19. The earlier
  R9 checkpoint remains immutable; policy/execution boundaries and ADR-019's
  research profile are unchanged. Electrical diagnostics passed; the combined
  BLE/50 Hz application requires its own scoped evidence.

### ADR-019 — Reliability-first Arduino BLE research baseline

- **Status:** ACCEPTED
- **Date:** 2026-08-27
- **Decision:** Treat the real passing Arduino ESP32-C3 plus Pi Bleak test as the
  active BLE ground truth. Derive the research firmware from that baseline and add
  one capability at a time. Use plain BLE through the functional/IMU stages.
  Standard BLE pairing/bonding is an optional later research stage. Custom
  HMAC/HKDF, device claims, controller binding, secure boot, flash encryption,
  eFuses, signed OTA, and commercial hostile-device controls are deferred.
- **Reason:** The project is a controlled research system, and the owner prioritizes
  a reliable, understandable experimental path after complex recovery/security
  state made the BLE system difficult to diagnose. The minimal Arduino test proved
  the physical BLE link and GATT path on the actual Pi and ESP hardware.
- **Consequences:** The research build must not be called production-secure. Before
  bonding, only sensor data and harmless test controls may be exposed. The Pi
  checks the expected name/address, secrets remain outside Git/logs, and the
  real-time path stays local BLE with no MQTT dependency. Commercial security work
  may be reconsidered only after the complete functional research path is stable.
- **Migration:** Follow `docs/BLE_RESEARCH_BRINGUP_PLAN.md`. The R9 source,
  validator, compact PASS checkpoint, and application binary are the retained
  recovery point. The earlier diagnostic, MQTT, and ESP-IDF firmware trees were
  removed with explicit owner approval on 2026-08-28.
- **Rollback:** Reflash the frozen R9 application binary and run its matching Pi
  validator.
  Do not recover by erasing flash/NVS or changing BlueZ globally.
- **Supersedes:** ADR-016 for the active research build and the mandatory
  ESP-IDF/custom-authentication portions of ADR-003. BLE remains the transport.
- **Owner direction:** The project is research, not a commercial product; avoid
  hard security that risks destabilizing the system and progress slowly from the
  working BLE test.

## Client and remaining decisions

### ADR-013 — First product client

- **Status:** ACCEPTED 2026-08-28
- **Decision:** The first client is a responsive phone/tablet browser experience,
  with installable PWA behavior where useful. The Pi hosts the local edge
  application; a dedicated Pi-connected display is not required initially.
- **Reason:** A wireless browser fits gym use, reuses users' existing devices,
  avoids another display/cable/enclosure dependency, and keeps one responsive UI
  implementation for phones and tablets.
- **Consequences:** M7 must support phone and tablet viewport/touch testing,
  offline local assets, clear reconnect/degraded states, and a reviewed local
  access/authentication policy. This decision does not authorize cloud dependency,
  wildcard CORS, or exposing the Pi API without authentication.

### ADR-014 — Camera owner/publication implementation

- **Status:** PROVISIONALLY SELECTED 2026-08-31; final acceptance pending the
  controlled-person and browser-latency gates
- **Candidates:** Picamera2 dual-stream owner with H.264 publication, or MediaMTX
  camera owner plus local RTSP decode.
- **Provisional decision:** use Picamera2 as the sole camera owner, obtain
  exposure-start timestamps from request metadata, feed the lores stream directly
  to pose, and publish the hardware-H.264 main stream to MediaMTX as a relay only.
- **Evidence:** the real-Pi spike measured 100% monotonic capture timestamps only
  for Picamera2. It also used less CPU/RSS and achieved higher pose FPS than
  MediaMTX-owner plus RTSP decode. Both owners restarted 3/3. Picamera2 publication
  produced a real 1280x720 H.264 RTSP frame and an HTTP-200 WebRTC endpoint.
- **Remaining gate:** the current environment could not frame a full person, so a
  comparable controlled person-in-frame accuracy/FPS run and observed browser
  glass-to-glass latency remain mandatory before this ADR becomes accepted. See
  `docs/evidence/R13-C-CAMERA-OWNERSHIP-20260831.md`.

### ADR-015 — Raw media and sensor retention

- **Status:** DECISION NEEDED before cloud analytics
- **Default until approved:** Do not retain or upload continuous raw video. Do not
  upload raw IMU. Keep only the minimum local derived data needed for session use
  and debugging under a bounded retention policy.
- **Required input:** product purpose, consent, retention time, deletion/export,
  regions/accounts, cost and privacy review.

### ADR-020 — Separate local IMU-dataset retraining revision

- **Status:** ACCEPTED 2026-10-20; isolated generation and LSTM-only training
  authorized. This does not authorize runtime promotion or Pi deployment.
- **Owner approval:** "copy the required files from the fyp workspace to here in
  a seperate folder and here lets train the new model".
- **Decision:** allow an isolated local PC/WSL research workspace at
  `training/v5_imu_retraining/`, without modifying FYP or the active V5 model.
- **Context:** owner disclosed that the dataset was synthetically constructed
  using recorded-video observations and IMU research. Historical participant,
  calibration and accuracy claims are not independent real-measurement evidence.
- **Boundaries:** preserve vision, labels, identity/context and phase order;
  define a new explicit simulated IMU contract before generation. Fit new
  preprocessing, model, calibration and threshold; no reuse of cached fitted
  state or automatic deployment. The pasted v5.1 generator is not approved as a
  physically corrected generator.
- **Consequences:** copied data/references and generated runs are Git-ignored;
  source/copy hashes are recorded. No Pi TensorFlow installation, runtime
  dependency change, firmware flash or hardware test is authorized by setup.
  Real mounted validation remains pending; no recording is available now.
- **Rollback:** continue using existing runtime packages; never activate the
  isolated training candidate without an explicit integration step.
- **2026-10-20 follow-up:** owner explicitly chose original grouped
  cross-validation of the final V5 LSTM only. Preserve preprocessing,
  BatchNorm/dropout, early stopping, calibration, thresholding and export; omit
  RF, architecture ablations and parameter searches. M5-R02's motion/noise/frame
  specification is an offline synthetic assumption set, not verified mounting
  or real-world calibration. No runtime or physical contract is changed by it.
- **Local integration follow-up:** owner requested the next step and explicitly
  asked to continue with the Pi offline. M5-R04 may read the candidate artifacts
  through a version-specific, reference-only local adapter and expose the correct
  model version to the existing launcher/session metadata. This is not model
  promotion: default artifact selection, live scoring, deployed Pi files and
  physical-validation requirements are unchanged.
- **Pi staging follow-up:** after the owner brought the Pi online, M5-R05 may
  copy this candidate/runtime into a separate directory and run one numerical
  compatibility check using existing dependencies. This is side-by-side staging,
  not permission to overwrite old models, activate services or bypass live
  mounting/scoring gates. No system/pose environment upgrade is required.

### ADR-021 — Demo page is isolated from live analysis

- **Status:** ACCEPTED for the UI/animation slice, 2026-10-22 owner request.
- **Decision:** Demo is an additional tab in the existing dashboard. Share real
  device-status presentation and chart primitives, not duplicated sensor owners.
  Browser-only illustrative animation cannot create predictions, feedback commands
  or real workout records. Vendor/pin the renderer for offline use.
- **Boundary:** later synthetic/replay inputs, actual reference-only inference
  and explicit demonstration hardware cues require separate implementation and
  truthful provenance. Form-scenario selection is never a forced model class.
- **Rollback:** leave Demo unselected or remove this additive UI slice. Existing
  live source selection, firmware, data, model packages and scoring gates remain.

### ADR-022 — Real model inference over explicitly synthetic demo fixtures

- **Status:** ACCEPTED for the next local demo slice, 2026-10-22 owner go-ahead.
- **Decision:** share the frozen synthetic-R1 V5 runtime and fitted preprocessing,
  calibration and threshold. Choose the first complete, consistently labelled
  source case per scenario in fixture order, not by model output. Freeze the
  original load. Model disagreement must remain visible.
- **Boundary:** animation does not become measured pose or generate features.
  Local replay never enables live scoring, persists a workout, or sends cues.
  Live telemetry is displayed separately. The actual Pi/ESP demonstration lane
  and physical feedback are not implemented by this decision.
- **Rollback:** omit `--enable-demo`; all demo routes then remain unavailable.
  Immutable models, training data, live code paths and firmware are preserved.

- **Owner amendment, 2026-10-23 (M6-D04):** owner explicitly requests a correctly
  recognised bad-squat demonstration example. Replace fixture 1 with complete,
  consistently labelled forward-lean fixture 6, without modifying its inputs or
  policy. Selection is now explicitly curated using model output, not an
  independent evaluation. Keep fixture 1's false negative documented, disclose
  curation in catalog/UI, and do not infer improved model accuracy.

### ADR-023 — Research appliance boot services and Pi network indicator

- **Status:** ACCEPTED for the research demonstration, 2026-10-25 owner request.
- **Decision:** package the current loopback-only core/UI, one BLE owner and
  on-demand camera/pose relay as separate native systemd services. The external Pi
  RGB may show local `wlan0` readiness while idle; demonstration cues always win.
  Use the Pi account's enabled systemd user lingering rather than storing a sudo
  credential or depending on an interactive login.
- **Boundary:** this is not M8 production service hardening or G5 completion. It
  does not change Wi-Fi/Tailscale/SSH, contact an external connectivity endpoint,
  add wearable Wi-Fi, enable live V5 scoring or claim authenticated production BLE.
- **Rollback:** disable the research target and restore the previous immutable
  release link. Existing manually staged runs and current ESP firmware remain
  preserved.

### ADR-024 — Tailnet-only direct access to the research appliance

- **Status:** ACCEPTED as a research-only exception, 2026-10-26.
- **Decision:** retain loopback UI/API, WHEP and RTSP listeners behind Tailscale
  Serve. Bind MediaMTX ICE-TCP directly and only to the configured Tailscale IPv4
  so SDP contains a reachable candidate. Allow only the exact MagicDNS HTTPS
  Origin; never enable Funnel or a LAN/wildcard listener.
- **Context/evidence:** repeated SSH forwards made the bootable appliance awkward
  to use. The owner explicitly accepted that every authorized tailnet device can
  reach the unauthenticated research surfaces and separately confirmed enabling
  HTTPS certificates, whose device names enter public transparency logs.
- **Consequences/risks:** this is transport membership, not application login or
  production authorization. UI/API use tailnet HTTPS 443, WHEP uses HTTPS 8443,
  and ICE uses direct tailnet TCP 8189. Pose/camera privacy and custom Origin/header
  guards remain; public or LAN exposure is still forbidden.
- **Rollback:** reset Tailscale Serve, restore the pre-r9 appliance environment,
  restore release `r7`, and restart core/media. The SSH-forward path remains.
- **Owner approval:** “I approve exposing the unauthenticated Digital Spotter
  research UI, API, camera WHEP and WebRTC transport to devices authorized on my
  private Tailscale network. Do not enable public Funnel access.”

## Decision template

```markdown
### ADR-NNN — Title

- **Status:** PROPOSED
- **Date:** YYYY-MM-DD
- **Decision:**
- **Context/evidence:**
- **Alternatives considered:**
- **Consequences/risks:**
- **Migration:**
- **Rollback:**
- **Owner approval:**
```
