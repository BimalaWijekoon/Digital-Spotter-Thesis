# Digital Spotter test and evidence strategy

**Status:** Required product validation framework
**Last reviewed:** 2026-09-15

Tests prove a scoped claim in a named environment. They do not turn a simulated
adapter into real hardware evidence or a lab demo into gym validation.

## 1. Evidence environments

| Code | Environment | Purpose |
|---|---|---|
| E0 | Pure unit process | deterministic algorithms, validation, state machines |
| E1 | Local component sandbox | SQLite/temp files/UDS with fakes, no real hardware |
| E2 | Deterministic replay | synchronized recorded pose/video/IMU fixtures |
| E3 | Pi hardware bench | real Pi/camera/ESP/IMU, controlled scene/network |
| E4 | Gym-like RF/thermal setup | people, metal, Wi-Fi/BLE traffic, enclosure/mount |
| E5 | Approved staging cloud | Cloud Run/Firebase staging, synthetic accounts/data |
| E6 | Controlled pilot | consented users, release candidate, support monitoring |
| E7 | Production smoke | owner-approved, non-destructive post-release checks |

Every result states its environment. E0-E2 cannot satisfy an E3/E4 hardware gate;
E5 cannot prove production configuration; E7 requires explicit release authority.

### 1.1 Proportional validation duration

Validation duration follows the failure mechanism and scoped claim. A longer run is
not automatically better evidence for a small change.

| Level | Use when | Default evidence |
|---|---|---|
| V0 deterministic | Documentation, UI-only, pure schema/parser/algorithm, test-only changes | T01 plus directly relevant E0-E2 tests; no hardware soak |
| V1 short hardware | Localized firmware/adapter change with no sustained-resource mechanism | Relevant tests plus one 10-second E3 confirmation; a 2-second smoke proves detection only |
| V2 extended diagnostic | Sampling/BLE scheduling, clock, queue, actuator concurrency, reconnect, or suspected intermittent behavior | V1 first, then one 2-to-5-minute E3 run with focused counters |
| V3 soak/gate | Closing G2/G4/release, or changing sustained memory, timing, loss, thermal/power, radio, or recovery behavior | One configured 30/60-minute E3/E4 gate run after shorter checks pass |

Do not run a 30-minute soak for documentation, UI, test-only, isolated validation,
or small parser/schema changes. Do not use a long run merely to reconfirm an already
proven unchanged path. Existing soak evidence may be reused only when the firmware,
agent, configuration, hardware, and affected critical path are unchanged.

M6-D01's Demo UI slice uses six focused motion/playback/tab/camera-contract
checks and one 1366x768 browser render/interaction check. Browser software WebGL
is not Pi GPU, pose-detection or hardware-inference proof. Verify controls are
inside their panel as well as no page scrolling. No sensor/model/actuator gate
is closed by the illustrative animation.

M6-D02 checks the four source-labelled replay cases through the actual frozen
LiteRT runtime, exact-context/decision/provenance contracts, isolation from live
sessions, dedicated Origin/header guard and rejection of a forced prediction.
Browser-module checks cover requests and stale-result invalidation. One laptop
browser run proves the real API-to-result wiring. This is not classifier accuracy,
sensor/pose synchronization, real-world reliability or hardware feedback evidence.

M6-D03 uses seven focused JS checks for actual bundled skeleton lengths/planted
feet, prediction-disagreement wording and existing demo request/playback behavior.
One local visual run covers the human and reported bad-squat case; a static setup
frame may be inspected after a visual reach adjustment without more inference.
Do not turn this renderer-only change into model training or a hardware matrix.

M6-D04 needs only the requested bad-squat example through actual V5, captured
loop/rig checks and one local browser run. Confirm actual probability/class,
frozen threshold and explicit curation; retain the previous false negative.
Rendering checks cannot establish classifier accuracy or acceptable motion to
the owner. Keep final visual acceptance distinct from automated test results.

M6-D05 checks exact equality between displayed phase vectors and the raw model
fixture; phase order/units, playback pause/reset and existing client behavior.
One laptop browser flow checks the plots and actual V5 response, source
switching and reset. A pause-time phase/chart discrepancy must be corrected by
painting the same final playback tick. No new accuracy or hardware matrix is
needed for this display-only extension.

M6-D06 checks the four supplied GLB hashes, self-contained resources, distinct
scenario/clip selection, shared animated/skinned hand/barbell nodes and clip-time
mapping. Browser review must use the final four-scenario package, not inherit the
earlier correct-only Review 01 screenshots. No retraining, hardware matrix or
biomechanical-accuracy claim is justified by these rendering checks. Supplied
contact/scenario reports are author evidence, not independent validation.

If a sustained-critical path changes, its earlier soak is historical evidence, not
proof for the new candidate. Iterate with V0-V2 and run one V3 confirmation only
when the candidate is ready to close its gate. If a short test already exposes a
failure, diagnose it before spending time on a longer run.

### Active core-first research cadence (2026-09-28)

For the current `PLAN.md` section 14 sequence, steps 1–5 are implementation
checkpoints, not attempts to close G2/G3/G4. Use focused automated checks for the
boundary changed. Use only one short real Pi confirmation when joining both
existing producers, and one fixed-fixture Pi inference check when selecting the
V5 runtime. Do not rerun previously accepted BLE reconnect, camera-owner,
browser-timing, fallback, or long-soak experiments for unchanged components.
Human-camera and lower-back mounted validation is the last integrated step.

### M5-R03 local synthetic-model revision

For the separately authorized training workspace, use focused feature,
preprocessing, grouped-fold, internal-monitor and calibration/threshold checks;
then the actual final-architecture CV run. Numerical export evidence is Keras
save/reload parity, serialized preprocessing roundtrip and one built-in FP32
TFLite comparison. Do not rerun RF, ablations, quantization sweeps, BLE/camera
reconnects or hardware soaks. Synthetic grouped scores do not satisfy live
accuracy, physical mounting or Pi-runtime gates. See
`training/v5_imu_retraining/docs/TRAINING_PROCEDURE.md`.

M5-R04 checks only candidate artifact integrity, frozen preprocessing/one real
LiteRT inference, explicit version selection and session-version propagation,
plus the affected legacy model/session checks. Tests use synthetic package
fixtures and temporary SQLite, not camera/BLE hardware. Candidate predictions
remain reference-only; no full application matrix or retraining is required.

M5-R05 adds only transfer-hash verification and one provided synthetic-fixture
inference on the real Pi CPU using that same runtime. Compare against the
exported numerical reference; do not substitute this for mounted feature or
model-accuracy evidence. A single timed call is not a latency benchmark.

This defers full acceptance testing; it does not convert untested hardware,
missing V5 features, or mock output into a pass. A failed focused check stops the
next build step until its specific cause is understood. Longer RF, latency,
thermal or recovery tests require a named final gate or a demonstrated sustained
risk, not a generic desire for more evidence.

## 2. Test layers

### T01 Static and repository checks

- formatting/lint/type checks;
- `git diff --check`;
- broken documentation links;
- forbidden files/secrets/large artifacts;
- dependency lock consistency and license/SBOM generation;
- architecture/rule checks where machine-enforceable.

### T02 Unit tests

- packet parsing/ranges/wrap arithmetic;
- time mapping and drift estimator;
- fusion interpolation and quality policy;
- rep/session state machines;
- feature calculations/preprocessing;
- outbox retry/idempotency policy;
- authorization and redaction helpers.

Use injected time/random/hardware/network dependencies. No sleeps or WAN.

### T03 Contract tests

- BLE binary golden vectors and malformed corpus;
- MessagePack event round trips and version rejection;
- API OpenAPI request/response/error schemas;
- model manifest, hashes, shape, feature order, units, threshold;
- SQLite migration and cloud payload compatibility.

Firmware and Pi host share generated/golden protocol fixtures.

### T04 Replay/regression tests

- synchronized normal reps for each supported exercise;
- low visibility, occlusion, dropped frames;
- IMU gaps, jitter, saturation, clock drift/wrap/reset;
- interrupted/incomplete reps and client disconnect;
- golden feature matrices and expected result/model version;
- historical bug regressions, including automatic live-path dispatch, camera
  restart, and manual/live feature parity.

Fixtures must be consent-safe, versioned, immutable, and split from model training
according to the evaluation policy.

### T05 Component/integration tests

- UDS producer reconnect/backpressure/permissions;
- core + SQLite transaction failure/recovery;
- API + core authorization/idempotency;
- sync + fake gateway retries and durable reboot behavior;
- worker crash/restart and graceful shutdown;
- model load/unavailable/incompatible states.

### T06 Pi hardware tests

- camera start/stop/restart and loss;
- real person pose visibility/accuracy/FPS;
- real BLE pair/connect/stream/reconnect;
- sample scaling/calibration/timestamps;
- GPIO/buzzer/RGB policy;
- boot and systemd restart/recovery;
- power loss and storage recovery using disposable test data.

R11 reference evidence is
`docs/evidence/BLE-R11-CANONICAL-PI-ADAPTER-20260828.md`: a 120-second E3 run
delivered 6,003 packets at 50.064697 Hz with zero steady-state gaps, invalid
packets, queue drops, disconnects, or I2C errors. Its controlled disconnect gate
records outage/recovery drops separately, waits for a stable recovered link, and
then applies the normal rate/age/gap/drop checks. It does not substitute for the
M2-06 gym RF/mounting soak.

R12's E0/E1 gate covers idempotent lifecycle, one-active-session enforcement,
bounded ring eviction, controlled core restart, wrong/simulated event rejection,
off-loop database queue pressure, transaction failure rollback, and a real Unix
socket publisher/receiver round trip. The unchanged R11 hardware path needs only a
short E3 confirmation into a disposable SQLite database; another long BLE soak is
not required for this persistence-only slice.

The final R12 E3 confirmation accepted 507 real R11 events in 10.093 seconds at
50.134 Hz with zero gaps, duplicates, or rejected frames. The disposable schema-3
database completed the session, passed SQLite quick-check, and contained only the
aggregate `session_imu_summaries` row. Evidence is
`docs/evidence/R12-LOCAL-SESSIONS-20260828.md`.

R13-A is a V0 characterization gate, not a live-pipeline or performance claim. Its
E0/E2 validator hash-checks the current producer/consumer source snapshot, verifies
the compatibility model package and exact feature contract without loading a model
runtime, and runs the deterministic replay while enforcing `is_real=false` and
`persistence_allowed=false`. No camera, person, Pi, or wearable soak is required.
Evidence is `docs/evidence/R13-A-VISION-MODEL-BASELINE-20260828.md`. R13-B and later
must replace the documented blockers with their own focused tests; the baseline
hash validator is checkpoint evidence and is not a reason to preserve legacy code.

R13-B combines E0 clock/protocol/runtime tests with one exact-source 10-second E3
measurement after acquisition. The gate requires synchronized state, estimated
alignment-error p95 below 20 ms, zero backward-time corrections, and the unchanged
R11 rate/gap/drop/error criteria. Acquisition samples are counted as clock-gate
drops and withheld from the publisher; exchange staleness degrades and closes the
gate after five seconds. The final measured window passed at 50.075418 Hz with
13.017092 ms estimated-error p95 and zero measured gate drops. No long soak is
required until a sustained R13/G2/G4 path changes. Evidence is
`docs/evidence/R13-B-MEASUREMENT-TIME-ALIGNMENT-20260829.md`.

R13-C currently has partial E0/E3 evidence. Picamera2 and MediaMTX camera ownership
were measured on the real Pi/camera at matching main and pose resolutions. Both
owner restart paths passed 3/3, Picamera2 H.264 publication reached the MediaMTX
relay, and only Picamera2 supplied exposure-based monotonic capture timestamps.
The controlled full-body comparison and observed browser glass-to-glass latency
were explicitly deferred because the available environment could not provide valid
framing. Those remain mandatory; uncontrolled or missing-person measurements must
not close the gate. Evidence is
`docs/evidence/R13-C-CAMERA-OWNERSHIP-20260831.md`.

M3-04 Step 1 is a V0/E0 relay-contract slice. Automated tests require the canonical
MediaMTX configuration to expose only a loopback RTSP publisher path, require the
typed vision publication URL to be loopback RTSP, and prove that the feature-gated
vision runtime forwards the configured URL. This does not prove that MediaMTX can
start, that the Pi hardware encoder publishes, that a browser renders WHEP, or that
latency/overlay/multi-client targets pass; those remain E3 gates.

M3-04 Steps 2-4 add E0 contract and browser-module tests. Python tests validate the
strict JSON-safe pose and clock payload conversion. Node's test runner exercises a
fake MediaMTX reader, fake decoded-frame callbacks, deterministic clock exchanges,
bounded pose lookup, letterbox/DPR geometry, stale/degraded clearing, and lifecycle
cleanup. These tests prove deterministic browser logic only; they do not count as
cross-browser playback, real `captureTime` availability, visual alignment,
glass-to-glass latency, WAN-disconnected behavior, or multi-client E3 evidence.
The later loopback-only M3-04 research bridge adds focused HTTP/UDS projection
and same-origin clock checks plus browser telemetry composition/clock expiry.
Real Pi event receipt does not substitute for observed browser `captureTime`,
overlay alignment, or person-in-frame evidence; see
`docs/evidence/M3-04-POSE-TELEMETRY-20260928.md`.

The temporary person-pose UI has two focused E0 checks: countdown-to-capture
state and aggregate JSON persistence with a fake runner, plus loopback HTTP
origin/parallel-start rejection. The user-operated E3 check must then show a
real person in frame during the 30-second window and record actual good versus
degraded pose counts. Neither the E0 checks nor mere camera frames close the
controlled-person vision gate; no raw frames are retained by this diagnostic.

M6-R02's local diagnostics use three focused core/API checks (33-landmark
projection, detected versus quality-approved counts, stale/missing suppression
and request-time age refresh), the existing mutation-origin check, and thirteen
browser-module checks including existing camera/renderer regressions. New cases
cover cover-crop/mirroring, drawing-only degraded visibility, stale/network-
delayed clearing and honest result counts. Inputs are deterministic stand-ins,
not a passed person test. No extra BLE/model/endurance matrix is required for
this presentation-only addition. Real browser/person confirmation follows Pi
activation after the owner's current capture, not during it.

### T07 Performance, resource, and thermal tests

- identical subject/camera/exercise scenario before and after change;
- latency distributions, not only averages;
- process and system CPU, RSS, threads/tasks/file descriptors;
- queue depths/drop counters and database latency;
- CPU temperature, frequency, undervoltage/throttle flags;
- video glass-to-glass measurement;
- 60-minute active-session soak and longer idle test.

### T08 Wireless/RF tests

- final sensor mounting/enclosure/orientation;
- athlete between sensor and Pi;
- metal bar/rack and movement;
- 5 GHz and 2.4 GHz Wi-Fi traffic;
- nearby BLE devices and multiple Digital Spotter units;
- supported distance, low battery, reconnect, ESP reset;
- packet loss, burst loss, RTT/clock error, recovery time.

### T09 Security tests

- repository/history/runtime secret scans;
- unknown/bonded/revoked BLE identities;
- command capture/replay/tamper/malformed payload;
- local API auth, roles, token expiry/replay, origin/CSRF/rate/body limits;
- service/files/socket permissions and denied resource access;
- signed/unsigned/corrupt/downgrade update behavior;
- support-bundle and log redaction;
- cloud cross-tenant/device, direct-access, idempotency, size, and abuse paths.

### T10 Cloud/staging tests

- synthetic account/device provisioning;
- WAN loss, DNS/TLS timeout, 429/5xx, retry and circuit breaker;
- duplicate batches and partial acknowledgments;
- long offline backlog/reboot/disk pressure;
- Firestore/Storage/IAM/rules and audit logs;
- retention expiration, export, deletion, and ownership transfer.

### T11 Usability, accessibility, and safety review

- pairing/calibration/framing/session/recovery journey;
- touch, keyboard, screen reader/contrast where applicable;
- degraded states understood without technical knowledge;
- feedback volume/rate and gym distraction;
- no exaggerated safety/medical language;
- support/factory reset does not expose another user's data.

### T12 Release and rollback drill

- reproducible build and artifact signature verification;
- clean-image install/boot;
- upgrade from supported previous version;
- interrupted/corrupt/failed-health update rollback;
- database backup/migration/restore;
- ESP firmware update/recovery;
- SBOM/license/vulnerability review and known-risk approval.

## 3. Current compatibility baseline

Until M1 reorganizes tests, run:

```bash
python -m pytest tests -q
python scripts/validate_model.py
python scripts/benchmark_pipeline.py --help
git diff --check
```

Record missing dependencies/hardware as blockers, not passes. Existing API tests do
not fully cover the active FastAPI dashboard; M0-03/M3-01 must add that evidence.

## 4. Mandatory acceptance scenarios

### S01 Normal offline session

WAN disabled; real camera/ESP/IMU/model; start, several supported reps, stop, review
history, reboot, review again. Expected: no cloud call in the critical loop and one
durable result per valid completed rep.

### S02 BLE interruption

Interrupt BLE during a rep, restore it, and continue. Expected: explicit degraded
state, no zero-fill/confident multimodal result during loss, packet gap recorded,
automatic recovery within the supported target.

### S03 Camera/pose interruption

Occlude/disconnect/restart camera. Expected: vision degraded, no stale result,
session/control remains recoverable, worker restarts without leaked resources.

### S04 Client and WAN interruption

Disconnect browser and WAN while active, reconnect in either order. Expected:
session state remains authoritative on Pi; no duplicate start/stop/rep; outbox later
syncs idempotently.

### S05 Storage pressure/failure

Approach configured quota and inject write failure. Expected: optional raw capture
stops first, user sees storage degraded, completed reps are not falsely reported as
saved, database remains recoverable.

### S06 Process/power interruption

Restart each service and perform controlled power-loss testing with disposable
data. Expected: consistent DB, bounded recovery, no duplicate events, signed
release remains bootable.

### S07 Unauthorized/replayed traffic

Unknown BLE sensor, replayed control, unauthenticated local mutation/video/WS,
revoked cloud device, duplicate upload. Expected: deny, redacted audit, no state
change or duplicate cloud record.

## 5. Performance evidence format

Every benchmark records:

```text
date/time and code revision
Pi model/RAM/OS/kernel/Python
power supply and cooling/enclosure
camera/sensor/firmware/model versions
exercise, subject-in-frame status, mounting, duration
input resolution/rate and configuration
median, p95, p99 latency/FPS/loss as applicable
CPU/RSS/temp/frequency/throttle flags
queue/drop/reconnect/error counters
mock/replay/real component list
raw evidence path and interpretation
```

Do not compare results from different scenes/configurations as if only the code
change differed.

## 6. Initial product budgets

| Budget | Gate |
|---|---|
| 8-12 pose FPS with person and accuracy met | G4 |
| IMU 50 Hz minimum, 100 Hz goal | G2/G4 |
| BLE loss below 0.5 percent over 30 minutes | G2 |
| Time alignment p95 below 20 ms | G2/G4 |
| Classifier p95 below 25 ms | G4 |
| Rep completion-to-result p95 below 150 ms | G4 |
| Local video p95 below 250 ms | G4 |
| 60-minute soak, no crash/leak/throttling | G4 |

An accuracy or reliability regression cannot be accepted merely to meet a speed
budget.

## 7. Hardware evidence manifest

Each E3/E4 run includes a machine-readable manifest containing:

- Pi serial alias (not public serial), board revision, OS image hash;
- camera module/revision;
- ESP device alias, hardware revision, firmware hash;
- exact IMU module, range/rate, calibration version;
- mount/enclosure/orientation/distance;
- power/cooling and ambient temperature;
- application/model/config hashes;
- scenario and duration;
- whether data may be retained/shared.

## 8. Evidence storage

Use a structure such as:

```text
evidence/<work-package>/<yyyy-mm-dd>-<scenario>/
  manifest.json
  commands.txt
  summary.md
  metrics.json
  logs-redacted/
```

Raw video/IMU is not committed by default. Store it only in an approved private,
retention-controlled location and reference a safe manifest/hash.

## 9. Gate-to-test minimum

| Gate | Minimum layers |
|---|---|
| G0 | T01 plus current baseline |
| G1 | T01-T05 in E0-E2 |
| G2 | T02-T03, T06, T08-T09 in E3-E4 |
| G3 | T02-T07 in E2-E4, S01-S06 |
| G4 | T04, T06-T08 with performance format |
| G5 | T03, T05-T06, T09, T11 |
| G6 | T03, T05, T09-T10 in E5 |
| G7 | T06-T12 in E3-E6 |
| G8 | T01-T12 evidence review plus T12 release drill |

## 10. Completion reporting

For every work package report exact commands/results, environment, hardware,
fixtures, mocks, measurements, failures, skipped tests and reason, artifacts, data
impact, rollback, and Git/deployment state. Honest partial evidence is acceptable;
an unsupported completion claim is not.
