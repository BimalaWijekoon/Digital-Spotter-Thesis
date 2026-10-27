# Digital Spotter current state

**Snapshot date:** 2026-09-28
**Scope:** Repository state after the owner-approved M3-00 cleanup, frozen R9
wearable hardware gate, passing R11 canonical Pi adapter, R12 local-session gate,
R13-A/B/C vision work, M3-03 recovery evidence, and M3-04 Steps 1-4 local
relay/browser-contract implementation, plus a bounded research IMU+vision join

This document records verified current facts. Target behavior remains in
`ARCHITECTURE.md`; implementation order remains in `PLAN.md`.

## Rep tracking separation — 2026-10-27

Release `r14` separates the tolerant knee-motion signal used for research rep
counting from the strict bilateral pose features required by V5. Either complete
hip-knee-ankle side with visibility at least 0.50 may drive segmentation. If
bilateral quality-approved phase features are missing, the completed rep remains
`unavailable` and cannot produce a score or result feedback. Five focused
rep-phase checks pass and all 251 release manifest entries were verified. Core,
IMU and media services are active on the Pi. The owner-operated 38.45-second
check produced 218 frames, 133 detected poses, zero quality-approved poses and
one unavailable-quality rep. This proves the narrow separation without a false
score, but does not pass three-rep reliability, pose quality, calibrated IMU or
live-model eligibility.

M6-D14 locally lowers only MediaPipe acquisition/tracking defaults to 0.50 and
computes tracking confidence from the better visible body side rather than the
face or occluded far side. V5 feature extraction now has its own explicit 0.70
bilateral landmark gate, including feet. Thirteen focused MediaPipe/worker/rep
checks pass. Release `r15` is active on the Pi with all three appliance services
running. The owner-operated person check remains pending; the implementation does
not infer missing body parts.

## Model-data clarification and local retraining preparation — 2026-10-20

The owner disclosed synthetic training-data provenance, informed by recorded
video observations and IMU research. Prior participant/collection/calibration
claims are historical and must not be treated as independently measured evidence.
M5-R01 prepares `training/v5_imu_retraining/` with copied baseline data (6,054
rows / 2,018 complete repetitions), passive V5 training references, contracts,
environment metadata and a SHA256 manifest. FYP, active model artifacts and
runtime code were unchanged by M5-R01–03. M5-R02 subsequently generated an
IMU-only synthetic R1 candidate with all 56 protected columns unchanged; five
focused generator checks passed. The simulated motion, noise and mount remain
unmeasured assumptions, not real-world calibration. Original grouped CV of only
the final V5 LSTM was owner-selected for M5-R03. All 26 fits and one FP32 built-in
TFLite export completed. Synthetic-profile outer OOF accuracy is 85.4807%, F1
0.815839; Keras reload is exact and numerical TFLite parity passed with no class
mismatches. This is an inactive research candidate, not a runtime replacement.
No training job is running. The original source package and existing runtime
artifacts still match recorded hashes. Details:
`training/v5_imu_retraining/docs/TRAINING_REPORT.md`.
Real mounted evaluation has not occurred. See ADR-020 and that folder's
`STATE.md`; none of this closes a live model-accuracy gate.

M5-R04 subsequently added opt-in local runtime support for this new package,
without changing either artifact package or deploying to the offline Pi.
The launcher selects an explicit model version; shared preprocessing/LiteRT
inference uses the new fitted state and session metadata records the selected
version. Nine model/package checks and four local session checks passed. Real
candidate inference used LiteRT without TensorFlow. Live candidate scoring
remains denied. See
`docs/evidence/M5-R04-LOCAL-CANDIDATE-RUNTIME-20261020.md`.

M5-R05 staged the candidate and canonical runtime in the separate Pi directory
`~/digital-spotter-v5-imu-r1-20261020.E7L664/`. All 107 transferred hashes matched.
One reference-only fixture inference matched the PC probabilities/class exactly
under the existing LiteRT 2.1.5/Python 3.12.0 environment; no TensorFlow import or
dependency change. The old Pi trees/configuration were not overwritten. No
core/UI/relay listener was running after the reboot, and this check did not
start one. Service integration and mounted live-feature checks remain pending.
See `docs/evidence/M5-R05-PI-CANDIDATE-STAGING-20261020.md`.

M6-R01 then started the staged canonical UI/core, one real R9 BLE receiver and
the isolated on-demand camera/pose worker in a new private run directory. UI
HTTP and real H.264 playback passed; 96 real pose events reached this core.
All were person-not-found in the unattended check, not a human-test failure.
A real 100-sample IMU window spanned 1980.24 ms without sequence gaps. R9 samples
retain their existing IMU_DEGRADED/calibration-version-0 status; this is not a
claim of calibrated mounting. Camera capture stops when no viewer is present,
so camera status becomes stale until the viewer reconnects. The new model is
loaded reference-only; live scoring remains unavailable. The owner-operated
20-second countdown / 30-second pose test is the next step and is not started.
See `docs/evidence/M6-R01-FIRST-PERSON-TEST-READY-20261020.md` for paths,
interpreters, initial startup issues and rollback. Firmware and prior data were
not changed. No new boot service has been installed.

The owner's subsequent 30-second check received 175 frames: 90 poses detected
but low visibility, 85 not found, zero quality-approved. The UI's "Pose detected"
label incorrectly counts only quality-approved frames; detector/quality-display
correction remains pending. Separately, the almost-opaque full-camera countdown
overlay was replaced with a small bottom-left timer so video remains visible
during countdown and capture. CSS and HTML cache-version changes are deployed
on the Pi, with old files backed up. Three focused UI checks pass; no detector,
firmware or scoring behavior changed. See
`docs/evidence/M6-R01-VISIBLE-POSE-TEST-20261020.md`.

M6-R02 locally implements corrected detected/quality-approved counts and a
bounded 33-landmark latest-pose guide over mirrored/cover-cropped video. Low-
visibility landmarks may be drawn individually for diagnosis without changing
their degraded quality. It is explicitly labelled unsynchronized, rejects old
poses, and cannot enable scoring. Four Python and thirteen browser-module checks
pass. These changes are NOT deployed while the owner checks the active UI;
that Pi still runs the earlier detector and counter. FYP's Heavy Tasks API and
0.50 thresholds differ from the Pi's Full Solutions API and 0.70 thresholds;
no same-image detector comparison or switch has occurred. See
`docs/evidence/M6-R02-LOCAL-POSE-DIAGNOSTICS-20261020.md`.

## 1. Repository shape

M6-D01 (2026-10-22) adds a local Demo tab inside the approved dashboard shell,
not a replacement dashboard. Browser-only offline Three.js r180 renders an
illustrative mannequin performing selectable squat/deadlift and correct/incorrect
form scenarios. Playback pauses on tab exit, ends after three repetitions and
has reset controls. It shares actual core-status/IMU-window events from the
existing UI clients; a disconnected preview remains unavailable. Model results
stay Not run; no fake pose, IMU scenario stream, inference, cue or saved workout
is produced. Six focused checks and one laptop browser check passed. It is
served locally on 4173, not activated on the Pi. See
`docs/evidence/M6-D01-DEMO-PAGE-20261022.md`.

M6-D02 (2026-10-23) completes the next **local-only** slice: Demo now requests
actual frozen V5 synthetic-R1 inference after each animated rep. Four
source-labelled, complete fixture cases retain their original 3-phase/29-feature
inputs and recorded loads; form selection cannot set a prediction. Seven focused
Python checks and eight browser-module checks passed. One local 1366x768 browser
rep returned Good form, calibrated bad-form probability 12.9%, with no scrolling.
The model-backed local UI is on 4176; the old static-only 4173 preview cannot run
inference. No Pi deployment, firmware change, MediaPipe-on-animation claim,
replayed 50-Hz IMU stream, hardware feedback or live-scoring gate change.
See `docs/evidence/M6-D02-DEMO-INFERENCE-20261023.md`.

M6-D03 (2026-10-23) replaces Demo's separate-cylinder mannequin with an offline
741320-byte Quaternius CC0 skinned human. Human appearance and illustrative
animation do not alter the frozen model or replay inputs. The reported incorrect
squat is a confirmed synthetic-replay false negative: 39.1543% bad-form
probability < 39.7601% threshold, actual class 0 versus source label 1. The panel
now explains the disagreement instead of implying scenario selection forces a
class. Seven focused JS checks pass; local browser rendering/model response
checked, no Pi/ESP/real-world accuracy claim. See
`docs/evidence/M6-D03-NATURAL-HUMAN-20261023.md`.

The owner rejected M6-D03's motion quality. M6-D04 now uses a captured CMU squat
cycle instead of the cosine crouch, retaining the existing skinned character.
Motion is adapted/retimed for rendering; bad-form forward lean is an authored
overlay, not measured error data. Deadlift remains illustrative. At the owner's
explicit request, the bad-squat replay is now curated fixture 6, source-labelled
incorrect and classified Check form with 85.0613% probability. Its original
35 kg context, preprocessing, weights, calibrator and threshold are unchanged.
The earlier fixture 1 miss remains a known limitation; this is no accuracy claim.
Local checks passed; no Pi or wearable work by this slice.

The owner still rejects M6-D04's human/bar contact and is sourcing a replacement
complete exercise scene. That visual issue is not resolved by local checks.
M6-D05 adds a separate replay-input chart view: exactly three synthetic IMU phase
medians from the same raw fixture used by V5, with explicit m/s² and rad/s units.
P1/P2/P3 appear in playback order; their equal display slots are not measured
capture times. The selectable live wearable view retains its actual telemetry
and unavailable state. No high-rate replay stream, pose detection, physical cue,
Pi deployment or model change is introduced.

M6-D06 now selects from the owner's four complete demonstration GLBs: intended
correct squat/deadlift and predefined forward-lean squat/spinal-rounding deadlift.
The later four-scenario ZIP supersedes the correct-only Review 01 package.
All supplied hashes match. Whole human/equipment scenes share their baked
timeline; there is no separate bar posing or procedural error overlay. These
are authored review prototypes, not mocap or validated technique. Named errors
describe selected examples, not extra output classes from the binary classifier.
The existing model/replay inputs and scoring gates are unchanged. Earlier
renderer/assets are preserved; no Pi/ESP work. The final four-scenario package
played in Chromium at 1366x768 with matching selections, no page scroll and zero
browser exceptions. Owner visual acceptance remains pending; this is not
biomechanical validation or a real-system test.

The later `(2).zip` character revision now supersedes the procedural-body
package in the active registry. Four approximately 6.2 MB GLBs contain the
textured Quaternius character (65 human bones plus barbell) and seven embedded
PNG images. Earlier assets remain intact. Hashes and embedded-resource checks
pass; all four scenario names/timelines and the model inputs are unchanged.
Texture/ImageBitmap resources are disposed with the renderer. The revision's
four clips passed a fresh local 1366x768 Chromium playback check with no browser
exceptions or page scroll. Owner visual acceptance is still separate from this
basic functional check.

M6-D07 activates that current runtime as an isolated, non-service Pi copy. The
staged archive and each contained source file passed SHA256 verification before
launch. The Pi loaded the immutable `digital_spotter_v5_imu_synthetic_r1`
package and served the dashboard only on loopback behind a private SSH forward.
One BLE adapter delivered a bounded 100-sample real MPU6500 window at 49.99 Hz
with zero sequence gaps; its truthful status remains `degraded` because the
wearable is uncalibrated. Separately, one curated incorrect-squat replay ran
through the Pi's canonical LiteRT/preprocessing/calibration/threshold path and
returned class 1 at 85.06%. This does not establish live V5 feature eligibility,
real-world form accuracy, camera/pose behavior or physical feedback. No firmware,
model, BLE pairing or Pi network configuration changed. See
`docs/evidence/M6-D07-PI-DEMO-AND-LIVE-IMU-20261023.md`.

M6-D08 then added bounded physical demonstration feedback without changing the
model decision: Pi and wearable receive start/good/bad/complete cues selected from
the actual replay result. The owner observed both LED/buzzer paths working and
confirmed the idle-dark wearable correction. Current wearable source reports
`0.9.2-demo-feedback`; the canonical Pi parser allow-lists it while retaining the
same UUIDs, 20-byte packet and 50 Hz acquisition profile.

M6-D09 release `r6` is active on the Pi through systemd user services and the
enabled `digital-spotter-research.target`; user lingering provides boot startup
without storing a sudo password. `workout_v1` now includes a privacy-bounded local
Wi-Fi state; the UI presents it in one compact header chip and Devices row. The Pi
RGB is dim blue when `wlan0` has a local IPv4 address and slowly pulses amber
otherwise, with no buzzer. Demo cues override it; no network state is sent to the
BLE-only wearable. The 23 MB archive contains 247 hash-verified files. A focused
live smoke returned HTTP 200, connected Wi-Fi state, three active services with
zero restarts, and a current 100-sample real MPU6500 window. After a Pi reboot,
all three services entered `active` one second after boot. One bounded RTSP decode
request started the on-demand camera and delivered 75 real frames; the camera
state truthfully remained degraded because no person was visible. Owner visual
confirmation of the Pi RGB network colour remains separate from software proof.

M6-D10 adds a presentation-only pose guide to the four authored Demo animations.
It projects named GLB skeleton bones into the browser canvas and draws the same
33-point cyan connection style as the live-camera overlay. The UI explicitly says
`Simulated pose guide`: these are not MediaPipe detections, do not satisfy the
pending real-person pose gate, and are never supplied to fusion or inference.
Focused local tests pass. Release `r7` is active on the Pi; both the UI document
and pose-guide module returned HTTP 200 while target/core/IMU/media remained
active. Owner visual confirmation remains pending.

The owner then rebooted the Pi and powered the wearable from its battery path.
The target, core, IMU and media services all entered `active` one second after
boot with zero restarts, `r7` remained selected, and the loopback API returned a
current 100-sample gap-free IMU window at approximately 20 ms intervals. Wi-Fi
reported connected and the model loaded. The status contract still reports the
wearable as `degraded` despite incoming samples, so this is not recorded as a
fully healthy wearable state. Camera `unavailable` before an on-demand request is
expected.

M6-D11 release `r9` replaces the repeated SSH-forward requirement for this
owner-approved research appliance with Tailscale Serve. Core/UI and MediaMTX WHEP
continue listening only on Pi loopback; Tailscale exposes HTTPS 443 and HTTPS
8443 exclusively inside the tailnet. Release `r12` binds MediaMTX ICE-TCP 8189
directly and only to the Pi's configured Tailscale IPv4 because the former
loopback proxy caused SDP to advertise unreachable `127.0.0.1`. The exact MagicDNS
HTTPS origin is allow-listed and the browser derives its WHEP hostname from its
own private origin. Funnel remains disabled. Pi-side HTTPS, origin-guard and
100-sample IMU checks pass; owner browser and live-camera confirmation remain
pending. This explicitly accepted research exception is not authenticated
production access.

Release `r10` fixes a camera-only r9 integration defect. The endpoint resolver
produced the correct tailnet WHEP URL, but the shared preview wrapper still
accepted only `127.0.0.1`, while generated MediaMTX configuration still allowed
only the historical loopback browser Origin. The wrapper now accepts a
caller-supplied private endpoint policy and the UI supplies the existing
loopback-or-HTTPS-`.ts.net` policy. The media launcher validates and writes the
same exact `DS_ALLOWED_ORIGIN` used by core. Core, IMU and media are active; the
owner-browser camera check remains pending.

Release `r11` removes the idle UI's redundant request to
`/api/research/person-pose-test/latest`. The primary pose-test snapshot already
reports `complete` and includes the saved result when one exists; fetching the
separate latest route while the state is `idle` could only produce a harmless
404 before the first test. The route and post-test saved-result link remain
available. Core, media and IMU services are active on r11.

Release `r12` fixes the observed black, repeatedly refreshing camera without
changing camera capture, UI, BLE, firmware or model behavior. WHEP signaling
continued to succeed, but the r11 SDP exposed only `127.0.0.1:8189`; the remote
browser could not establish ICE. The r12 SDP exposes `100.104.28.69:8189`, the
ICE state reached `connected`, and a bounded real-hardware browser probe decoded
1280x720 H.264 with 98 advancing frames in three seconds. Core, media and IMU
remain active. This is transport evidence, not real-person pose validation.

M6-D12 adds a visible set-completion path after the owner found that the primary
`Start set` action became disabled and the only Stop button was easy to miss
under the camera. During an active/paused set the primary action is now
`Finish + JSON`; stopping returns and downloads a bounded completed-set summary,
with a repeat `Download JSON` action afterward. The summary preserves truthful
unavailable live-analysis state and excludes raw video, landmarks and raw IMU.
Release `r13` is active on the Pi; its 251-file manifest verified, all three
services remain active, the new control is present in the served HTML, and one
empty bounded live API start/stop returned the expected `completed_set` object.

The repository is intentionally mid-migration:

| Area | Current role |
|---|---|
| `src/digital_spotter/` | Canonical package for new contracts, configuration, persistence, and adapters |
| `scripts/run_server.py` | Supported migration launcher for the current FastAPI dashboard |
| `scripts/dashboard/` | Active FastAPI/UI prototype |
| `vision/`, `inference/`, `integration/`, `database/`, `hardware/`, `imu/` | Legacy modules with active callers/tests; preserve until migrated |
| `api/`, `frontend/`, `TEST DASBOARD/` | Historical application generations retained until their tested behavior is mapped |
| `firmware/esp32_c3_research/` | Only supported wearable firmware path |
| `models/` | Protected current model and preprocessing artifacts |

Generated firmware builds, superseded wearable implementations, old stage
checkpoints/scripts, stale setup files, and obsolete root plans were removed on
2026-08-28. The exact boundary is recorded in `docs/WORKSPACE.md`.

## 2. Active application path

`scripts/run_server.py` starts `scripts.dashboard.main:app` through Uvicorn using
the validated `Config.API` host and port. Port `8000` is the current default.

This remains a migration path. The FastAPI module still owns too many concerns:
UI/API, camera lifecycle, model calls, hardware feedback, health, and WebSocket
broadcasting. It also still imports the legacy MQTT Pi bridge. The R9 wearable is
therefore not yet integrated into the live application.

The older Flask/API and browser implementation is not a supported launcher, but
its tests and behavior have not been fully replaced. It remains until M8-04.

The Pi-hosted research UI has a separate, temporary person-pose diagnostic
button, deployed to the isolated Pi research UI on 2026-10-14. It stops the camera preview, counts down 20 seconds, samples
real Picamera2/MediaPipe pose quality for 30 seconds, and save aggregate-only
JSON. The Pi page and idle status endpoint respond, and local fake-runner/HTTP checks pass; a user-operated full-body run has not
yet validated detection. The prior manually timed 30-frame Pi check found no
pose, so person framing and detection remain open.

On 2026-10-14, a short Pi bench check identified the legacy RGB module's actual
red channel on BCM27 and green channel on BCM17 (owner visual observation).
The legacy config defaults and `.env.example` now match that wiring; blue remains
BCM22 and the buzzer BCM18. This is a pin-map correction, not validation of the
product feedback path. The isolated research Pi copy has no legacy `config/`
package, so that running UI path does not use this mapping.

## 3. Canonical package work completed

The additive `src/digital_spotter/` package currently contains:

- typed product configuration and startup validation;
- versioned event, time, and model contracts;
- deterministic replay fixtures;
- model manifest validation;
- SQLite schema/migrations, transactional repositories, outbox, backup, and
  restore foundations, plus the R12 authoritative local-session runtime;
- the active R9 Pi BLE adapter plus earlier deferred security/clock foundations.

`src/digital_spotter/imu/r9_protocol.py`, `r9_agent.py`, `r9_transport.py`, and
`r9_runtime.py` are now the active R9 Pi path. `ds-imu-agent` resolves to that
runtime. Older authenticated/security modules remain inactive migration source and
must not be confused with the ADR-019 research profile.

## 4. Verified wearable ground truth

The retained real-wearable BLE baseline is
`firmware/esp32_c3_research/esp32_c3_research.ino`, version `0.9.0-r9`.
On 2026-10-17, the ESP32-C3 on the new PCB temporarily ran the USB-serial
MPU6500 motion diagnostic in `firmware/imu_pcb_bringup/`. The new PCB's
GPIO18/GPIO19 bus read `0x70` at `0x68`, and the first stationary motion capture
produced 222 samples across
11.05 seconds (20.0 Hz). An owner-timed tilt/rotation capture then showed
changing accelerometer axes and gyroscope values (141 samples at 20.0 Hz), but
COM7 closed after 7.0 seconds, so post-rotation settling remains unverified.
The 2026-10-17 diagnostic image also accepts serial commands for isolated
ten-second external RGB GPIO tests. GPIO0 reported on/off correctly, but the
owner observed green rather than the handoff-labelled red. GPIO1 likewise
reported on/off, and the owner observed red. The diagnostic source now maps
green=GPIO0 and red=GPIO1; GPIO3/blue was initially handoff-reported. A corrected sequence
diagnostic was flashed and serial-confirmed GPIO1, GPIO0, and GPIO3 in
red/green/blue order, then all off. Physical observation of the full sequence
was not reported.
On the same USB-powered PCB, a brief GPIO10 buzzer diagnostic was compiled and
flashed after the owner confirmed J6 polarity. Serial logs showed two 700 ms
HIGH pulses separated by a 400 ms LOW gap and a final automatic LOW state.
The owner reported no sound on the first USB-powered run; a second run was
serial-confirmed without an audible result report. The ESP then ran a separate
automatic RGB/buzzer test image that loops every 7 s without serial commands.
Its USB serial phase transitions were observed. After the USB-to-external-
power handoff, the owner reported the automatic RGB loop and buzzer working.
This is visual/acoustic owner evidence, not measured voltage/current or an
endurance result. This image does not read the IMU or advertise BLE.
This does not supersede the R9 BLE evidence below.

On 2026-10-19, M2-07 adapted the main application source to `0.9.1-pcb1` with
the assembled-PCB pins, external RGB PWM, and timed active-buzzer control. The
Pi parser now explicitly accepts that revision alongside frozen R9 and reports
the actual version; 17 focused host checks pass and the matched parser is
deployed with a backup. The PCB1 application has now been app-only flashed and
boot-checked over USB: correct pins/PWM, MPU6500 identity and all 50 Hz profile
register readbacks, 250 acquired samples in five seconds with zero acquisition
errors, and expected BLE advertising. After external-power handoff, a 30-second
real Pi stream passed: 1,499 packets, 49.965309 Hz, no sequence gaps, I2C errors
or disconnects. The normal BLE agent reconnected and the existing dashboard's
100-sample graph window updates. Raw, uncalibrated data retains the truthful
`degraded` quality state. Camera-only H.264/WebRTC playback was restored using
the last working launcher; the pose-enabled branch initially timed out while
importing MediaPipe's optional TensorFlow dependency. On 2026-10-20, a separate
pinned pose environment and explicit pose interpreter resolved that timeout:
real pose initialization took 4.999 s, and a combined run delivered 94 real
pose events with zero processing failures alongside a gap-free 100-sample IMU
window. All 94 frames reported no person, so person/pose quality, owner cue
replay, mounted exercise and calibrated V5 scoring remain pending. This is not a
full-system pass. A separate PCB1 stream-pass checkpoint preserves the matched
source/binary/configuration without overwriting R9. See
`docs/evidence/M2-07-PCB-INTEGRATION-20261019.md`.
Pose-startup evidence and current runtime details:
`docs/evidence/m2-07-pcb1-20261019/pose-startup-fix.md`.

Verified hardware and identity:

- ESP32-C3 revision v0.4 with 4 MB flash;
- BLE name `ESP32-C3-Test`;
- observed public address `50:78:7D:92:61:1A`;
- MPU6500 at `0x68`, exact `WHO_AM_I=0x70`;
- SDA GPIO 5, SCL GPIO 6;
- NeoPixel GPIO 8;
- buzzer GPIO 10.

Verified R9 behavior:

- separate device-info, status, bounded control, and notify-only stream
  characteristics;
- explicit stream start/stop;
- real, uncalibrated 20-byte little-endian MPU6500 packets at approximately 50 Hz;
- sequence and sensor-capture timestamp fields;
- bounded advertising recovery after disconnect;
- white boot, blue advertising, green idle, cyan streaming, orange disconnect,
  and red error cues;
- one short manual/test buzzer cue.

The final 30-second real-hardware gate received 1,499 packets in 30.001075 seconds
at 49.964876 Hz, with 14,998-24,994 microsecond sensor intervals, zero sequence
gaps, zero I2C errors, and zero unexpected disconnects. The owner physically
confirmed all LED cues and heard the buzzer. No mocks or replay data were used.

The retained R9 recovery point includes source, validator, application binary,
configuration, partition description, logs, and hashes under
`firmware/esp32_c3_research/checkpoints/r9/pass/`.

R11 verified the same unchanged firmware through the canonical Pi boundary. The
two-minute E3 run delivered 6,003 packets at 50.064697 Hz with zero gaps,
duplicates, invalid packets, queue drops, connection failures, reconnects,
publisher failures, or I2C errors. A controlled link drop recovered automatically;
the stable post-recovery window delivered 502 packets at 50.075473 Hz with zero
steady-state errors. See
`docs/evidence/BLE-R11-CANONICAL-PI-ADAPTER-20260828.md`.

R12 now consumes that unchanged event contract through the canonical core boundary.
Its final short E3 gate accepted 507 real events in 10.093 seconds at 50.134 Hz with
zero gaps, duplicates, or rejected frames. The session completed in SQLite schema
3, `PRAGMA quick_check` returned `ok`, and only aggregate IMU counts/times were
stored; raw accelerometer/gyroscope samples were not persisted. See
`docs/evidence/R12-LOCAL-SESSIONS-20260828.md`.

R13-B now timestamps each existing on-demand R9 status read on the Pi, uses the
ESP `uptime_ms` value as a one-millisecond-resolution clock exchange, and maps the
packet's wrapping `sensor_time_us` into Pi monotonic capture time. Samples are
counted but withheld from the publisher until the clock is synchronized. The final
short E3 measurement then published 501 events at 50.075418 Hz with 13.017092 ms
estimated alignment-error p95 and zero measured gaps, queue drops, clock-gate
drops, invalid packets, future caps, or monotonic corrections. The 256 acquisition
samples were explicit clock-gate drops. The R9 firmware and installed Pi services
were unchanged.

## 5. Current BLE/security profile

ADR-019 deliberately keeps the active research firmware simple:

- local BLE only;
- no Wi-Fi, HiveMQ, or cloud dependency on the wearable;
- no pairing or bonding;
- no application HMAC/HKDF authentication;
- no controller provisioning/binding;
- bounded harmless research commands only.

This is reliable research evidence, not production security. R10 standard bonding
is optional. Production security guidance remains documented but is not active
firmware behavior.

## 6. Model and sensor semantics

Tracked TFLite and preprocessing artifacts exist and validate structurally. Their
provenance and performance limitations remain documented in `models/README.md`.
These tracked `models/` assets are the V4 compatibility package, not V5. On
2026-09-28 the separate finalized V5 Stage 8 source archive was located and all
67 manifest-listed files hash-matched. M5-01 copied 24 final deployment files
into `models/digital_spotter_v5/`, exported portable fitted preprocessing and
Platt parameters, and passed offline FP32 TFLite/Keras-reference parity on 64
training-derived repetitions. A later 2026-09-30 Pi check loaded that FP32 model
with LiteRT 2.2.0 and matched one fitted-median reference-only decision; see
`docs/evidence/M5-02-V5-PI-FIXED-FIXTURE-20260930.md`. This is **not** live
feature validation or production scoring. The V5 path remains inactive. See
`docs/V5_RASPBERRY_PI_INTEGRATION_REPORT.md` for evidence and remaining gates.

R9 emits raw MPU6500 counts. Calibration, body-frame orientation, mounted movement
validation, and alignment with the current model feature contract are open. A
lower-back IMU must not be described as directly measuring barbell velocity or
power.

Missing or stale IMU data must remain explicit. It must not be replaced with zeros
in production scoring.

## 7. Vision and live-pipeline gaps

On 2026-09-15 the connected-device preflight verified Pi SSH access, Bluetooth
power/service, IMX219 enumeration, `throttled=0x0` and an idle temperature of
56.0 C. Windows detected the CP210x USB serial adapter on COM7. The subsequent
R9 BLE check accepted the exact firmware device-info contract and received 501
samples in 10.000704 seconds with no measurement-window packet/I2C errors.
The controlled reconnect bench recovered, but two reconnects and 107 recovery
queue drops remain an unexplained diagnostic note. Owner direction is to retain
the earlier M2 acceptance and proceed with video, without more BLE retesting.
Firmware was not changed. See `docs/evidence/R9-RECHECK-20260915.md`.
The owner directed
that human-camera/mounted acceptance be the last validation stage; section 14 of
`PLAN.md` now tracks this order. See `docs/evidence/DEVICE-PREFLIGHT-20260915.md`.

M3-04 now has a bounded real-browser transport check: the unchanged canonical
Picamera2 adapter published hardware H.264 to the installed MediaMTX v1.9.1,
whose built-in viewer decoded 1280x720 video in headless Chromium (89 frames in
three seconds, one reported dropped frame). This used private SSH-forwarded
loopback HTTP/ICE-TCP, not the target direct-LAN latency path. Both processes
stopped cleanly. See `docs/evidence/M3-04-BROWSER-PLAYBACK-20260915.md`.

The subsequent custom research page now uses our existing `whep-player.mjs`
with a locally vendored, hash-pinned official v1.12.3 reader. It passed real
playback against the unchanged v1.9.1 server: 1280x720, 89 new frames over
approximately three seconds, four total reported dropped frames, state `playing`,
and clean manual Stop. No iframe or built-in viewer substituted for the custom
page in that check. It is a loopback-only, two-minute diagnostic, not the product
UI. That dated check had no telemetry or overlay. A subsequent temporary
loopback-only bridge now wires canonical pose projection and clock exchange to the
research page; a real Pi run delivered 537 pose events with empty-scene degraded
quality, but browser `captureTime`/overlay alignment remains unverified. See
`docs/evidence/M3-04-CUSTOM-VIEWER-20260915.md` and
`docs/evidence/M3-04-POSE-TELEMETRY-20260928.md`.

The current camera path still uses OpenCV/MediaPipe and a migration MJPEG flow.
R13-C real-Pi measurements provisionally select Picamera2 as the sole camera owner.
Its timestamped lores stream and hardware-H.264 main stream operated together, and
the main stream was republished through a MediaMTX WebRTC relay. A real 1280x720
subscriber frame and HTTP-200 browser endpoint were verified. Controlled
person-in-frame accuracy and observed glass-to-glass latency remain open because
the current environment could not provide valid full-body framing. Mounted fusion
quality and enclosure thermal behavior also remain open.

M3-04 Step 1 now promotes the relay boundary from an R13-C experiment to canonical
repository configuration. `deploy/mediamtx.yml` accepts RTSP publication only on
loopback at path `picamera2`; the typed product setting `video.publish_url` (or
`DS_VIDEO_PUBLISH_URL`) supplies that URL to the feature-gated vision runtime.
The setting remains absent by default, so neither the canonical worker nor the
legacy dashboard is activated or redirected implicitly. Subsequent E0-only M3-04
work adds reusable browser modules for MediaMTX reader lifecycle, a versioned
browser-safe pose/clock payload, bounded minimum-RTT clock estimation and pose
matching, letterbox-correct canvas projection, and decoded-frame orchestration.
Deterministic Node tests originally covered those behaviors without hardware.
The later temporary Pi diagnostic received canonical pose events through a
loopback bridge; its browser timing check did not complete. The WHEP listener
remains a development bring-up surface:
local-client authentication, firewall/TLS, live WebSocket delivery, browser
compatibility, measured overlay alignment, and hardware latency remain
unimplemented or unverified.

M3-03 now has shared timestamp/latest-frame primitives, canonical pose-event
construction, an adapter-injected deterministic replay worker, and canonical real
Picamera2/MediaPipe adapters. Replay output is always marked `simulated`; a forced
child-worker failure left a disposable active SQLite session unchanged and
`PRAGMA quick_check` healthy. On the Pi, the additive Step 4 candidate opened the
real IMX219 camera 3/3 times and emitted 30/30 canonical events with strictly
monotonic exposure-start timestamps. The scene contained no person, so all 30
events correctly reported `vision_degraded`/pose missing rather than fabricated
landmarks. M3-03 Step 5 adds an isolated bounded drop-oldest UDS publisher with
frame-size, socket-mode, optional peer-UID, failure, and reconnect accounting. The
worker can now emit canonical `starting`, `ready`, `degraded`, and `stopping`
health transitions plus periodic monotonic heartbeats; a consumer-side watchdog
detects missing or backward heartbeats. Step 6 adds an explicitly gated standalone
canonical vision-agent entry point. `vision_pipeline=legacy` is the default and
leaves the supported dashboard path unchanged; `vision_pipeline=canonical` plus a
real adapter selection assembles Picamera2, MediaPipe, and the bounded publisher.
The canonical agent is not installed as a Pi service. The product core now has an
additive vision event receiver for a research session, but the supported UI
runtime remains the legacy migration path described above.

The 2026-09-28 step-1 temporary Pi run joined the unchanged real R9 BLE agent
and real Picamera2/MediaPipe agent into one `LocalSessionService`: 410 IMU events
and 58 pose events were accepted, with overlapping Pi-monotonic measurement
ranges and zero rejected frames. All poses were degraded because no person was
in the scene. The pose ring stayed bounded at four, the SQLite session stored
only aggregate IMU data, and no analysis result was created. This is a capture
join, **not** measurement-time fusion or live V5 inference. The concurrent run
showed about 40 accepted IMU events/s over its capture range and 195 camera
source-frame drops; these remain later performance questions. See
`docs/evidence/JOINT-CAPTURE-20260928.md`.

Step 2 now adds deterministic, on-demand measurement-time interpolation from
the session's bounded IMU/pose rings. Missing or far IMU, sequence gaps, clock
reset/uncertainty, stale pose, and absent calibration remain explicit degraded
or unavailable outcomes; arrival time and zero filling are not used. Focused
local tests pass, but this fusion code has not been run on the Pi or connected
to V5 inference or persistence. A bounded research `RepPhaseBuilder` is now
connected to `LocalSessionService` for one-shot completed-rep polling. It uses
the owner-confirmed FYP recorded-video knee-peak and phase-split rule, with no
fabricated no-peak rep, plus fail-closed synchronized IMU median summaries.
Only synthetic focused phase checks have passed; no live person/Pi or model
result has used this path. The step-1 Pi run above
must not be retrospectively described as a live fusion test.

On 2026-09-30 a local-only V5 candidate feature bridge was added in
`src/digital_spotter/inference/v5_features.py`. It selects the exact Stage 8
phase fields and derives asymmetry, knee-hip coupling and IMU acceleration
magnitude from the completed research phase summaries; missing/degraded data
fails closed. Three focused E0 checks pass, including frozen preprocessor
shape acceptance. It does not resolve training IMU units/axes or live pose
equivalence and is not wired to scoring or the UI. The later fixed-median Pi
compatibility check is separate from this live-feature gate.

A 2026-09-30 read-only source/Pi audit found a concrete live V5 eligibility
blocker: exact V2 IMU provenance and gyro units are unknown. The historical
sketch outputs intended deg/s, but the current Pi decoder and candidate bridge
pass rad/s. Training vision extraction and the live pose adapter also use
different MediaPipe APIs/models. No V5 scoring caller or installed `ds-*`
service was active on the Pi during the audit. See
`docs/evidence/M5-02-LIVE-V5-FEATURE-SOURCE-AUDIT-20260930.md`.

M3-03 Step 7 passed the bounded E3 process-level camera-loss/recovery gate on the
real Pi 4 and IMX219. After one real frame event, the harness sent `SIGTERM` only
to the canonical agent's Picamera2 helper. The agent emitted degraded and stopping
health with `camera_unavailable`, exited with its expected failure code, and
reaped the helper. A fresh agent then opened the camera, emitted two real frame
events, and stopped cleanly with no orphan process. The Pi remained
`throttled=0x0`; temperature moved from 61.3 C to 63.3 C during this short test.
No frame was retained. The recovery agent recorded both of its frame events as
pose missing, and no person was staged, so the controlled-person landmark/quality
gate remains open.

Known integration blockers include:

- the active dashboard does not yet use one canonical live feature/inference path;
- the camera processing loop does not dispatch its result to the legacy session
  manager, so the active live camera path does not automatically reach inference;
- the manual `/predict` path and legacy session manager build the 40 features
  independently and contain incompatible formulas;
- legacy pose, IMU, preprocessing, and model components can substitute zeros or
  random/default mock outputs rather than publishing explicit unavailable state;
- legacy IMU selection uses the latest network-arrival sample rather than aligning
  pose and IMU by monotonic measurement time;
- camera stop/restart ownership remains prototype-grade;
- the R12 core receiver and session service consume the real R11 event contract,
  but the product systemd/API launcher remains pending for the later integration;
- model-derived wearable cues remain disabled;
- cloud sync/gateway and final authenticated local API are not implemented.

## 8. Local state and environment

- `.venv/` is intentionally retained and ignored.
- `data/` and `logs/` are protected local runtime state and were not deleted.
- model assets were not changed by cleanup.
- no Firebase service-account key belongs on the Pi.
- a previously exposed MQTT credential remains an owner-side rotation/revocation
  blocker even though the legacy firmware and local credential file were removed.

## 9. Next implementation slice

R13-A has frozen and machine-validated the current vision/model source, artifact,
and replay baseline without changing runtime behavior. Its trace and blocker list
are in `docs/evidence/R13-A-VISION-MODEL-BASELINE-20260828.md`.

R13-B has passed for the active research path. R13-C is partially complete and
provisionally selects Picamera2, but its controlled-person and browser-latency
acceptance gates are deferred. M3-03 implementation Steps 1-6 establish its traced
boundary, shared contracts, deterministic replay lifecycle, additive real
adapters, bounded UDS publication, structured health/watchdog behavior, and the
feature-gated standalone component runtime. Camera loss/recovery and the
controlled-person run remain deferred E3 acceptance gates. R13-C and ADR-014 must
not be marked accepted until the physical gates pass. Fusion/rep logic and
shadow-only compatibility inference remain separate R13 slices. The accepted
first UI client is a responsive phone/tablet browser/PWA; its redesign remains
R14.
The separate `ui-preview/` redesign now has an opt-in camera-only research
connection to the existing loopback WHEP viewer. Local browser controls and
unsafe-endpoint rejection have been checked. A narrow 2026-10-03 check confirmed
real Pi H.264 playback and clean Stop inside this redesigned page over a private
SSH tunnel; visual quality and timing remain unverified. It does not change the
supported dashboard.
An additive 2026-09-30 research-status slice now projects the canonical local
session's detected rep count and recent camera/IMU states into a loopback-only,
read-only `/api/research/session-status` route for `ui-preview/`. V5 analysis is
always unavailable in this route: no probability, scored feedback, or analysis
event is generated. The opt-in runner requires an existing migrated SQLite
database and real UDS producers; it has not been deployed or exercised with a
person or wearable on the Pi. The normal dashboard remains unchanged.
An additional opt-in shadow flag now loads the frozen V5 runtime and invokes
reference-only inference for complete candidate reps, reporting only execution
state in the terminal. This has passed focused local deterministic checks,
including one actual frozen-model invocation, but has not run on live Pi sensor
data. It does not change the HTTP response, durable analysis, or wearable cues.

On 2026-10-03, an isolated copy of the redesigned static research page and V5
runtime was placed on the Pi. The copied V5 model loaded and all 24 artifact
hashes matched. A temporary static server listens on Pi loopback only; its page
was reached through a private SSH tunnel. The static server has no session-status
API, camera ownership, fixture prediction, or live analysis, and is not an
installed product UI. See
`docs/evidence/M6-03-PI-RESEARCH-UI-STEP1-20261003.md`.
Step 2 added a temporary, separately started camera/MediaMTX process pair so
the same page could display real H.264 video. These expire automatically and
do not make the static UI a camera owner or enable pose/model/session behavior.
See `docs/evidence/M6-03-PI-RESEARCH-UI-STEP2-20261003.md`.
After the owner found that the expired processes caused SSH tunnel connection
refusals, a research-only on-demand relay was installed on Pi loopback. The
camera button now lives in the Workout panel and reads an internal static
configuration; no WHEP URL is entered by the user. MediaMTX starts the existing
Picamera2 camera owner only while a WebRTC viewer is present, then stops it five
seconds after the viewer closes. One short real Pi/Chromium check passed with
1280x720 video and clean camera release; this is still not product readiness or
live V5 scoring. See `docs/evidence/M6-03-PI-RESEARCH-UI-STEP2B-20261003.md`.
The next UI slice removed page-wide preview/research wording. The Pi computed
one reference-only V5 result from frozen fitted medians after checking all
copied artifact hashes, and the isolated result appears only in Devices →
Analysis as **Test input**. Workout Feedback remains unavailable; no live
camera/IMU rep was scored or saved. See
`docs/evidence/M6-03-PI-UI-TEST-INPUT-20261003.md`.
The next isolated Pi slice replaced its static-only server with the canonical
unscored session-status server on the same loopback port. One short camera run
delivered real Picamera2/MediaPipe pose events and on-demand H.264; the empty
scene was degraded and no rep/model result was generated. The R9 agent did not
discover the wearable during this check, so IMU status remained unavailable.
This is not a person/mounted validation or product dashboard. See
`docs/evidence/M6-03-PI-UNSCORED-STATUS-20261003.md`.
The same isolated Pi server now exposes a bounded recent IMU window, and the
page draws its real acceleration/gyroscope axes. A short loopback read returned
current MPU6500 vectors in degraded (uncalibrated) state. This only confirms
display transport, not model feature equivalence or scored analysis.
