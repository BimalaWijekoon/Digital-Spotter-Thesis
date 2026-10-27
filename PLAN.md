# Digital Spotter zero-to-product plan

**Plan status:** Active
**Started:** 2026-08-25
**Target hardware:** Raspberry Pi 4B 8 GB + separate lower-back ESP32-C3/MPU6500 wearable
**Execution rule:** Work in dependency order and close one verifiable package at a time.
Use the shortest evidence run that proves the scoped change; reserve long soaks for
sustained-risk changes and milestone/release gates.

This plan turns the current prototype into a field-testable and releasable product.
It is deliberately staged: an architecture document or passing mock test is not a
product milestone.

## Owner-approved model-data revision — 2026-10-20

### M5-R01 — Prepare isolated local retraining references

- **Status:** DONE for reference preparation; subsequent work is in M5-R02/R03.
- **Owner decision:** create `training/v5_imu_retraining/` in this workspace for
  a new research training revision. FYP and the existing deployed V5 package
  remain read-only; this overrides earlier training-workspace-only restrictions
  for this separate revision (ADR-020).
- **Provenance:** owner disclosed synthetic data informed by video observations
  and IMU research. Earlier participant/calibration claims are not verified
  real-world evidence. Pasted v5.1 generator is reference-only, not accepted.
- **Scope:** copy relevant data, generator reference, vision extractor, V5
  pipeline/dependency source, notebook, contracts and environment metadata.
  Preserve 6,054 baseline rows / 2,018 three-phase repetitions.
- **Acceptance:** copied-file and unchanged-source SHA256 checks; complete
  three-phase groups; no training, environment installation or hardware change.
- **Next:** specify and implement an IMU-only motion generator while preserving
  vision and labels; only then fit new preprocessing/model/calibration/threshold.
  Real mounted evaluation is deferred, not waived or marked passed.
- **Evidence:** `training/v5_imu_retraining/COPY_MANIFEST.csv` and `STATE.md`.
  `python3 training/v5_imu_retraining/scripts/verify_copy.py --check-source`
  passed 37/37 copied hashes/sizes, 37/37 unchanged original hashes and all
  2,018 complete phase groups. `git diff --check` passed. No hardware was used.
- **Rollback:** do not activate this training folder; leave runtime models and
  hardware untouched. Historical "do not retrain" instructions below still
  protect the frozen V5 package, not this newly authorized research revision.

### M5-R02 — IMU-only synthetic motion generator

- **Status:** DONE for offline generation; not real-world calibration.
- **Scope:** explicit SI/body-frame assumptions, C2 sensor motion, consistent
  specific force/angular rates, actual-profile quantization, pose-associated
  phase medians, preserved missingness and no target-conditioned IMU means.
- **Evidence:** `training/v5_imu_retraining/docs/IMU_GENERATION_REPORT.md`.
  Five focused synthetic-fixture tests pass. New candidate has 6,054 rows;
  all 56 protected columns are unchanged. 37/37 original reference hashes still
  match. No real hardware, model training or runtime activation occurred.
- **Limitations:** unmeasured mounting/motion/noise priors; 104 missing trunk
  summaries and 374 inherited phase-label inconsistencies remain explicit.

### M5-R03 — Retrain only final V5 using original grouped CV

- **Status:** DONE for offline training/export; not a live-model accuracy gate.
- **Owner decision:** retain original grouped cross-validation (multiple fits
  of the same final V5 LSTM), not one holdout split. Skip Random Forest, other
  model families, architecture ablations and parameter searches.
- **Required:** exact 29/2/3 contract, fresh train-only preprocessing,
  original regularization/early stopping, cross-fitted calibration/threshold,
  final epoch policy and all-data fit, Keras/TFLite export parity and hashes.
  Stage 8-style 5 outer/4 inner folds imply 26 main-architecture fits including
  outer and final fits; no historical checkpoints or fitted policies reused.
- **Execution:** `training/v5_imu_retraining/v5_training.py`; the final Stage 8
  internal 12-fit / 3-monitor / 5-validation profile separation is retained.
  The existing PC training interpreter is reused without installing or changing
  packages. Runs and logs are isolated under the training workspace's `outputs/`.
- **Evidence:** `training/v5_imu_retraining/docs/TRAINING_REPORT.md`. Five focused
  checks pass; all 26 LSTM fits completed, final epoch count 12. Synthetic-profile
  outer OOF accuracy 85.4807%, F1 0.815839, ROC AUC 0.886581. Keras reload exact
  on 2,018 reps; FP32 built-in TFLite parity on 64 reps has max raw error 2.0862e-7
  and zero class mismatches. No RF/ablations or Pi/runtime activation occurred.
- **Boundary:** synthetic-only metrics; no automatic Pi deployment. Actual
  mounted evaluation remains deferred, not passed.

### M5-R04 — Local runtime support for the isolated candidate

- **Status:** DONE for local reference-only runtime integration; Pi not used.
- **Scope:** opt-in version-specific candidate loading, its own frozen JSON
  preprocessing/calibration/threshold, shared LiteRT inference, correct session
  model-version metadata. Keep the legacy default and both packages unchanged.
- **Acceptance:** focused package/fixture/inference and version-propagation
  checks; preserve existing model checks. No training, Pi access or deployment.
- **Evidence:** `docs/evidence/M5-R04-LOCAL-CANDIDATE-RUNTIME-20261020.md`;
  nine model/package checks and four session checks passed. The real LiteRT
  candidate inference matches the frozen numerical reference without TensorFlow.
- **Boundary:** candidate predictions remain reference-only; live feature/mount
  verification and real-world accuracy gates stay open. No automatic activation.

### M5-R05 — Side-by-side Pi candidate staging and one inference

- **Status:** DONE for side-by-side staging/reference inference; not activated.
- **Scope:** inspect host health and reuse its existing runtime interpreter;
  stage a new isolated source/model directory without replacing the old one.
  Verify transferred hashes and one provided synthetic reference inference.
- **Acceptance:** canonical candidate runtime on aarch64 matches exported
  preprocessing/probability/class within the frozen numerical tolerances;
  TensorFlow remains unimported. Record the target path, versions and result.
- **Evidence:** `docs/evidence/M5-R05-PI-CANDIDATE-STAGING-20261020.md`.
  All 107 transfer hashes matched. One Pi fixture inference matched PC
  probabilities/class exactly using existing LiteRT 2.1.5; no package install.
  Staged under `~/digital-spotter-v5-imu-r1-20261020.E7L664/`. Pi power health
  remained normal. No service was started; previous run data stayed intact.
- **Boundary:** no service activation, camera/BLE test, live scoring, package
  installation, old-model overwrite, network/config change or firmware flash.

### M6-R01 — Combined Pi bring-up to the first person test

- **Status:** IN PROGRESS; stop at the owner-operated person-in-frame check.
- **Scope:** start the staged canonical UI/core, one existing R9 BLE receiver,
  and the isolated on-demand camera/pose worker in a new run directory.
  Preserve firmware, old run data, networking and model packages.
- **Acceptance:** UI reachable through private SSH forwarding, real IMU samples
  and real camera/pose events reaching the same core. No mock data, extra BLE
  matrix or automatic human-test countdown. Candidate live scoring stays denied.
- **Next physical step:** owner starts the UI's 20-second countdown / 30-second
  pose check when ready to move into frame. Detection quality remains pending.
- **Bring-up evidence:** UI HTTP 200; one real camera playback check and 96
  MediaPipe events; real IMU window of 100 sequential samples spanning 1980.24 ms
  with zero sequence gaps. Existing BLE environment selected after a missing
  dependency in the core environment. Initial bring-up did not start a human test. See
  `docs/evidence/M6-R01-FIRST-PERSON-TEST-READY-20261020.md`.
- **Owner test follow-up:** 175 frames, 90 detected/low-visibility and 85 not
  found; zero passed the strict quality gate. This is not zero detections.
  The full-size opaque timer obscured video during countdown/capture. Replaced
  it with a small corner badge and deployed only CSS/cache-version changes;
  three focused UI checks pass. Pose detector and scoring policy unchanged.
  `docs/evidence/M6-R01-VISIBLE-POSE-TEST-20261020.md`.

### M6-R02 — Truthful pose diagnostics and visible landmarks

- **Status:** Local implementation PASS; Pi activation/person check pending.
- **Scope:** distinguish detected/quality-approved counts; expose only the
  newest bounded pose through the private research API; draw visible joints
  as a clearly labelled latest-pose guide, not a frame-synchronized analysis.
- **Acceptance:** focused real contract/renderer checks for 33 landmarks,
  mirrored/cropped video geometry, missing/stale pose and preserved quality
  gates. No firmware/model changes or automatic human test.
- **Deployment:** do not restart the owner's running test. Prepare locally;
  activate only after the current capture is finished.
- **Evidence:** 4 focused Python checks and 13 browser-module checks pass;
  `docs/evidence/M6-R02-LOCAL-POSE-DIAGNOSTICS-20261020.md`. No detector threshold
  or model change. Full/Heavy detector comparison is source-based only so far.

### M6-D01 — Demo page inside the existing dashboard

- **Status:** UI/animation slice DONE locally; model/hardware demo integration pending.
- **Scope:** add Demo beside Workout/Devices; reuse the approved layout and
  actual core/wearable status. Offline 3D squat/deadlift, correct/incorrect form
  scenarios, and start/pause/reset. Keep live mode unchanged.
- **Acceptance:** focused deterministic playback/pose checks and one laptop
  browser check. Animation must not fabricate pose detections, model predictions,
  sensor values, hardware feedback or successful connections.
- **Next slices:** synchronized scenario inputs and real reference-only model
  calculation; then separately gated demonstration-only BLE actuator commands.
  No automatic firmware flash, live-scoring override or real workout persistence.
- **Evidence:** `docs/evidence/M6-D01-DEMO-PAGE-20261022.md`; six focused browser
  module checks and one 1366x768 visual/interaction check passed. Local preview
  runs at `http://127.0.0.1:4173/ui-preview/#demo`. No Pi activation or hardware
  test. No selected/forced prediction, generated IMU stream or pose inference.

### M6-D02 — Frozen replay to actual reference-only V5 inference

- **Status:** Local reference-only inference PASS, 2026-10-23; Pi/hardware activation pending.
- **Scope:** opt-in `--enable-demo` on the existing core launcher; four fixed
  synthetic fixture cases selected by original source labels, not model output.
  Browser rep completion invokes the canonical preprocessor/LiteRT/calibrator/
  threshold path. Never override a model decision with the form selector.
- **Boundary:** original replay load is read-only; animation is illustrative,
  not MediaPipe input. Live IMU charts stay separate. No firmware, BLE command,
  physical feedback, live-scoring override or saved workout analysis.
- **Acceptance:** focused replay/API/client checks and one local laptop browser
  run showing an actual model probability. Pi activation is a separate step.
- **Evidence:** seven focused Python checks, eight browser-module checks, and
  one animated rep through the real local model passed. Result: Good form,
  calibrated bad-form probability 0.12908328534088956. No further test matrix.
  `docs/evidence/M6-D02-DEMO-INFERENCE-20261023.md`; local URL
  `http://127.0.0.1:4176/ui-preview/#demo`.

### M6-D03 — Bad-squat diagnosis and natural human renderer

- **Status:** Local implementation checked; owner rejected motion quality.
  Superseded for the demonstration by M6-D04; original model miss retained.
- **Finding:** incorrect squat fixture 1 returns calibrated probability
  0.39154328994402116, below frozen threshold 0.3976007923801824. Correctly routed
  request, source label 1, actual model class 0. No threshold/data/model change.
- **UI:** show source-label disagreement and comparison; replace primitive
  mannequin with a licensed, offline Quaternius skinned human, fixed-length limb
  IK and articulated hands. Animation still does not construct model inputs.
- **Evidence:** seven focused browser-module checks passed; one short local
  browser run reproduced the mismatch and rendered squat/deadlift. A final
  setup-frame inspection followed the reach adjustment; no extra inference.
  `docs/evidence/M6-D03-NATURAL-HUMAN-20261023.md`. No Pi/ESP operations.

### M6-D04 — Curated recognised bad squat and captured squat movement

- **Authorization:** owner explicitly requested a source-labelled example that
  the model recognises, and a correction to the animation (2026-10-23).
- **Status:** Curated model/API/UI check PASS; owner still rejects hand/bar
  contact and animation quality. Better complete exercise asset pending.
- **Replay:** use fixture 6 (35 kg), consistent bad-form labels and forward-lean
  error type 3. Actual calibrated probability 0.8506134321850672, class 1.
  Original fixture 1 remains documented as a miss; model/threshold unchanged.
  This is a curated demonstration, not an accuracy estimate or model repair.
- **Animation:** CMU 13_29 squat capture, adapted into a small in-place loop;
  source heading/height normalized, retimed, and rendered on the existing human.
  Incorrect-form lean is an authored overlay; no model features come from it.
  Closer camera and non-block belt. Deadlift remains illustrative, not captured.
- **Acceptance:** one targeted actual V5 case, focused loop/rig checks, one local
  browser repetition. No retraining, Pi/ESP operations or hardware matrix.
- **Observed:** UI Check form, 85.1%, 35 kg, rep 1/3, no scrolling at 1366x768.
  Automated/local visual evidence is not owner acceptance of motion quality.
  `docs/evidence/M6-D04-CURATED-SQUAT-20261023.md`.

### M6-D05 — Show the replay's actual IMU phase inputs

- **Status:** Local replay/chart/model flow PASS; no Pi or actuator activation.
- **Scope:** while the owner sources a better exercise asset, expose the six
  original IMU fields for each of the selected fixture's three phases. Add a
  replay/live chart selector, phase indicator, units and X/Y/Z legend.
- **Boundary:** three synthetic phase medians, not invented 50 Hz samples or
  measured animation synchronization. Equal playback slots are presentation
  timing only. Live wearable data remains separate and cannot become replay
  model input. No firmware, model, threshold, Pi or actuator changes.
- **Acceptance:** exact chart/model-input equality, phase order and units;
  focused playback/client checks and one laptop browser flow through inference,
  live/replay switching and reset. No extended hardware tests.
- **Evidence:** `docs/evidence/M6-D05-REPLAY-IMU-20261023.md`.

### M6-D06 — Owner-supplied complete four-scenario animations

- **Status:** Four-asset integrity/playback-contract checks and local browser
  playback PASS; owner visual acceptance pending.
- **Source:** owner supplied Review 01, then superseded it in the same work
  session with `Four_Exercise_Demonstration_Scenarios.zip` (2026-10-23).
  All 21 inventoried files verified; preserve both original archives and the
  earlier renderer/assets. Copy runtime assets into a distinct vendor directory.
- **Scope:** correct squat, excessive-forward-lean squat, correct conventional
  deadlift, spinal-rounding deadlift. One complete human/barbell scene and mixer
  per scenario, no retargeting, independent equipment motion or cross-fades.
- **Boundary:** named faults are user-selected examples, not binary-model
  diagnoses. Uniformly map each 5.3-second clip to the existing six-second replay
  cycle; no ML input, threshold, training, firmware or Pi changes.
- **Evidence:** `docs/evidence/M6-D06-FOUR-SCENARIOS-20261023.md`.
- **Character revision:** owner supplied `Four_Exercise_Demonstration_Scenarios
  (2).zip`; activate a distinct `exercise-scenarios-character-r1` vendor copy,
  retaining the previous assets. Same scenario/model contract, now textured
  Quaternius scenes. Verify new hashes/embedded resources and short playback;
  owner visual acceptance remains required.

### M6-D07 — Isolated Pi demo activation with real wearable telemetry

- **Status:** Focused Pi activation PASS, 2026-10-23; physical result cues and
  live form scoring remain separate pending slices.
- **Scope:** copy the current canonical runtime into a new Pi directory, verify
  every copied source file, launch the existing loopback-only core with the
  immutable synthetic-R1 model package, connect one BLE adapter, and retain the
  strict separation between live wearable plots and frozen replay inference.
- **Observed:** 100 consecutive real MPU6500 samples spanned 1980.20 ms at
  49.99 Hz with zero sequence gaps and mean acceleration magnitude 9.819 m/s2.
  Wearable quality correctly remained `degraded` because calibration is not
  certified. One whitelisted incorrect-squat replay produced raw probability
  0.787348, calibrated probability 0.850613, class 1 (`Check form`) at the frozen
  0.397601 threshold, matching its source label. Pi inference took 2.724 ms.
- **Boundary:** the replay remains synthetic/reference-only and does not consume
  live IMU or animation output. Camera/pose, live scoring, persistence and
  actuator feedback were not exercised. No firmware, model, pairing, network or
  service configuration was changed; no reconnect or endurance matrix was run.
- **Evidence:** `docs/evidence/M6-D07-PI-DEMO-AND-LIVE-IMU-20261023.md`.

### M6-D08 — Bounded physical demonstration feedback

- **Status:** PASS on assembled Pi + PCB wearable; 2026-10-23 owner-observed.
- **Scope:** fan the actual frozen replay result into non-blocking Pi and wearable
  start/good/bad/complete cues. Demo selection never chooses the cue; the model's
  returned binary class does. Keep the wearable dark outside a demo and preserve
  the 50 Hz IMU path.
- **Observed:** owner confirmed both Pi and wearable LEDs/buzzers responded during
  the bounded demo flow and later confirmed the idle-dark correction. Focused
  coordinator/GPIO tests passed. Firmware is `0.9.2-demo-feedback`; BLE protocol,
  UUIDs and stream packet remain unchanged.
- **Boundary:** research open BLE remains accepted only under ADR-019. These cues
  do not prove live-form scoring, mounted calibration or production authorization.

### M6-D09 — Bootable research demonstration appliance

- **Status:** Release `r6` deployed; boot, service, private UI, BLE/IMU and
  on-demand camera smoke PASS. Owner-observed Pi RGB network colour remains.
- **Scope:** preserve the approved UI; expose local Pi Wi-Fi state in the header
  and Devices view; show dim-blue/slow-amber Pi RGB network state when no demo is
  active; package loopback-only core/UI, one BLE owner and on-demand camera/pose
  relay as native systemd services. Do not change Wi-Fi, Tailscale, SSH, BlueZ
  pairing, model weights or ESP firmware.
- **Acceptance:** focused network/feedback/UI contracts; hashed secret-free release;
  install side by side; one boot/restart smoke proving UI, BLE/IMU, on-demand
  camera and physical demo cues. No extended matrix or soak in this research slice.
- **Rollback:** disable the user research target and restore the prior
  `~/digital-spotter-research/current` release link; retained older Pi runs remain
  untouched.
- **Observed:** archive and 247-file manifest verified on Pi; target/core/IMU/media
  active with zero restarts; loopback UI HTTP 200; `wlan0` connected; a current
  100-sample MPU6500 window arrived. The UI truthfully keeps live analysis
  unavailable because the live V5 feature contract is not validated. After a Pi
  reboot, all three services entered `active` one second after boot; a bounded
  on-demand decode produced 75 real camera frames without restarting MediaMTX.

### M6-D10 — Demonstration pose guide

- **Status:** Release `r7` deployed on Pi; focused local, Pi HTTP and reboot
  auto-start checks PASS. Battery-powered IMU packets arrived after reboot, while
  the current status contract still reports the wearable as degraded.
- **Scope:** overlay the four authored demonstration GLBs with the same 33-point
  cyan guide and connection styling used by the live-camera view. Points are
  projected from authored model bones and are labelled `Simulated pose guide`;
  they are not MediaPipe detections and do not enter fusion or inference.
- **Acceptance:** required bones exist in all four GLBs; the overlay uses the
  shared live guide styling and connection contract; the page visibly identifies
  the source as simulated. No model, BLE, firmware or live-pose behavior changes.
- **Evidence:** `docs/evidence/M6-D10-DEMO-POSE-GUIDE-20261026.md`.

### M6-D11 — Private direct Tailscale research URL

- **Status:** Release `r12` deployed. `r10` repaired the incomplete r9 camera
  migration by allowing the private `.ts.net` WHEP endpoint in the preview
  wrapper and applying the exact HTTPS browser Origin to MediaMTX. `r11` removes
  an unnecessary initial request for a nonexistent saved pose result. `r12`
  fixes the black/reconnecting camera by binding ICE-TCP to the Pi's Tailscale
  IPv4 instead of advertising `127.0.0.1`. A bounded real-camera browser check
  decoded 1280x720 video and advanced 98 frames in three seconds.
- **Scope:** preserve UI/API, WHEP and RTSP loopback listeners behind Tailscale
  Serve. Bind ICE-TCP 8189 only to the configured Tailscale IPv4 so SDP contains
  a browser-reachable tailnet candidate. Allow the exact HTTPS MagicDNS origin.
  Never enable Funnel or a LAN listener.
- **Security boundary:** the owner explicitly accepted tailnet exposure of the
  unauthenticated research surfaces on 2026-10-26. This is not production auth,
  LAN exposure or public access. The device hostname is present in public
  certificate-transparency logs because HTTPS certificates were enabled.
- **Rollback:** point `current` back to `r11` and restore its tailnet TCP 8189
  Serve proxy, or point back to `r10`/`r9` with their documented regressions. For
  the full direct-access rollback, use
  `tailscale serve reset`, restore the saved appliance environment, point
  `current` back to `r7`, and restart core/media.
- **Evidence:** `docs/evidence/M6-D11-TAILSCALE-PRIVATE-URL-20261026.md`.

### M6-D12 — Visible set finish and bounded JSON export

- **Status:** Release `r13` deployed on Pi; focused local and live API checks PASS.
- **Scope:** while a live set is active or paused, make the primary Set action
  visibly become `Finish + JSON`; retain the compact camera-panel Finish action.
  A successful stop saves the session and downloads one privacy-bounded JSON
  summary. Keep a separate `Download JSON` action for a repeat download until
  the next set begins.
- **Boundary:** the export reports only observed counts/states and the explicit
  unavailable live-analysis reason. It contains no raw video, landmarks, raw IMU
  samples or fabricated form prediction. No model, camera, BLE or firmware change.
- **Acceptance:** focused control/serialization and core export-contract tests;
  activate one immutable release and verify one stop response on Pi. Do not run
  an extended workout or model test matrix.
- **Evidence:** `docs/evidence/M6-D12-SET-JSON-EXPORT-20261027.md`.

### M6-D13 — Separate rep tracking from model-quality eligibility

- **Status:** Focused implementation and narrow real-person behavior PASS in
  release `r14`: one degraded rep was counted with scoring blocked. Full
  three-rep reliability is PARTIAL because only one rep was recorded; pose
  quality remained 0/133 detected frames and wearable quality was degraded.
- **Scope:** derive the rep-segmentation knee signal from either complete
  hip-knee-ankle side whose landmark visibility is at least 0.50. Preserve the
  existing strict bilateral/quality-approved path for V5 phase features.
- **Boundary:** a one-side/degraded pose may count a completed physical rep, but
  its phase features and analysis remain explicitly unavailable. It cannot emit
  a probability, class, green/red feedback result or readiness claim.
- **Acceptance:** the focused rep-phase checks must show that one visible side
  counts one rep as `unavailable`, while good bilateral input still builds three
  good phases and flat motion still produces no rep. Then activate one immutable
  Pi release and run one short owner-operated set; no broad soak or model matrix.
- **Evidence:** `docs/evidence/M6-D13-REP-TRACKING-SEPARATION-20261027.md`.

### M6-D14 — Partial-body pose acquisition without weakening V5 gating

- **Status:** Focused local implementation PASS; release `r15` deployed on Pi;
  owner movement check pending.
- **Scope:** align MediaPipe detection/tracking thresholds with the working FYP
  video extractor at 0.50. Define pose tracking confidence as the stronger of
  the left/right shoulder-hip-knee-ankle chains so a hidden face or far side
  does not block acquisition.
- **Boundary:** this is not arbitrary isolated-body-part reconstruction. At least
  one coherent body side must be returned by MediaPipe. V5 feature extraction
  independently requires all bilateral shoulder/hip/knee/ankle/foot landmarks
  at 0.70 visibility, so tracking readiness cannot enable an unsafe score.
- **Acceptance:** focused MediaPipe, worker and rep-phase tests; one immutable Pi
  release; then one short owner-operated three-rep check. No broad soak or model
  matrix.
- **Evidence:** `docs/evidence/M6-D14-PARTIAL-BODY-POSE-ACQUISITION-20261027.md`.

## Immediate field-test path — owner priority, 2026-10-20

Finish the research software for real-world testing before optional hardening,
redesigns or endurance matrices. Work one integration slice at a time:

1. **Pose startup (STARTUP PASS, M2-07/M3-03):** isolated environment and one
   combined real camera/pose/IMU check passed on 2026-10-20. MediaPipe initialized
   in 4.999 s; 94 real pose events and a gap-free 100-sample IMU window reached
   the session. All frames lacked a detected person; full-body quality is still
   pending. [Evidence](docs/evidence/m2-07-pcb1-20261019/pose-startup-fix.md).
2. **Wearable freeze (PCB1 stream PASS):** retain the current source/binary/pins,
   replay the missed physical RGB/buzzer cues and avoid additional BLE/security
   changes unless a real failure requires them.
3. **Final research UI/session wiring (PENDING):** retain the approved layout;
   connect exercise/load, session controls, camera, IMU graphs, rep state and
   binary V5 feedback to one real session path. Remove placeholder behavior, not
   truthful unavailable/degraded states. No further visual redesign is scheduled.
4. **V5 integration + Pi launch (PENDING):** use the immutable V5 contract and
   one canonical preprocessing/model path; provide a repeatable Pi launcher and
   exact artifact/dependency configuration. Resolve/report live IMU unit/axis,
   pose-source and mounting/calibration eligibility rather than bypassing them.
5. **Systematic real-system checks (PENDING):** full-body pose/framing; real
   camera+IMU synchronization; one supported exercise's rep/three-phase flow;
   V5 input/inference/calibration/threshold/result display; session stop/save;
   observable feedback. Do the mounted-person check last. Start with short
   representative runs; extend only if a specific failure requires it.

The prior standalone transport and fixed-input model passes are reused where
unchanged. They do not imply live V5 accuracy. Production security, cloud,
extra failure-injection matrices and long soaks are not on this critical path.

## 1. Status vocabulary

- `NOT STARTED`: no implementation evidence exists.
- `IN PROGRESS`: scoped work exists but its acceptance checks are incomplete.
- `BLOCKED`: a named external decision or prerequisite prevents useful progress.
- `DONE`: deliverables, tests, evidence, documentation, and rollback are complete.

Only update a package to `DONE` with links or commands in its evidence field.

## 2. Program gates

| Gate | Meaning | Required evidence |
|---|---|---|
| G0 Foundation | Safe, reproducible repository baseline | secrets handled, dependency lock, current tests/benchmarks, canonical entry point |
| G1 Contracts | Data/model/protocol semantics are executable | contract tests, replay fixtures, model manifest, migration skeleton |
| G2 Wireless | ESP32-C3 BLE is reliable in the intended mounting | security, clock sync, loss/reconnect/soak evidence |
| G3 Edge loop | Real camera + real IMU produce durable real rep results offline | end-to-end Pi replay/live tests, failure-mode evidence |
| G4 Performance | Pi 4 meets latency, memory, and thermal budgets | person-in-frame benchmark, 60-minute soak, no throttling |
| G5 Secure local product | Authenticated dashboard and hardened services | threat-control tests, provisioning/recovery tests |
| G6 Cloud | Offline outbox synchronizes safely and idempotently | emulator/staging evidence, WAN-loss/retry tests |
| G7 Pilot | Gym users can complete sessions reliably | field protocol results, privacy/retention approval, support runbook |
| G8 Release | Signed, recoverable, supportable product image | release checklist, update/rollback drill, owner approval |

## 3. Immediate owner decisions

| ID | Decision | Why it matters | Status |
|---|---|---|---|
| D-01 | Mount the separate wearable at the athlete's lower back | Determines coordinate frame, calibration, enclosure, RF behavior, and model validity | ACCEPTED 2026-08-25 |
| D-02 | Use the MPU6500 (`WHO_AM_I=0x70`) with ESP32-C3 | Determines range, noise, rate, calibration, and driver | ACCEPTED 2026-08-26; operating profile pending |
| D-03 | Confirm first client: phone/tablet browser or dedicated Pi display | Determines local TLS/pairing and UI delivery | ACCEPTED 2026-08-28: responsive phone/tablet browser/PWA; no dedicated Pi display initially |
| D-04 | Decide whether raw video/IMU is ever retained or uploaded | Determines consent, storage, privacy, and cloud cost | DECISION NEEDED before G6 |

Work can continue on repository, event, BLE framing, and replay foundations while
the remaining decisions are open. Lower-back calibration and the MPU6500 operating
profile still need field evidence. The prototype's direct bar-velocity/power fields
do not match this sensor location and must be validated against a reference or
replaced through a versioned model retraining decision.

## 4. Milestone M0: establish truth and remove immediate risk

### M0-01 Canonical project documentation

- **Status:** DONE
- **Dependencies:** none
- **Deliverables:** `AGENTS.md`, `ARCHITECTURE.md`, `RULES.md`, `PLAN.md`, refreshed
  `README.md`, and supporting documents under `docs/`.
- **Acceptance:** documents have consistent hardware, transport, security, model,
  testing, and cloud boundaries; all internal links resolve; `git diff --check`
  passes.
- **Rollback:** revert documentation-only change.
- **Evidence:** 2026-08-25 documentation structure/link checks and
  `git diff --check` passed. The existing Python tests/model validator were also
  attempted, but the repository contains a Windows virtual environment that cannot
  execute in this WSL session and system Python lacks `pytest`/`numpy`; this is an
  M0-03 environment blocker, not a test pass.

### M0-02 Revoke exposed MQTT and local Wi-Fi credentials

- **Status:** BLOCKED; repository contained, external credential-owner action required
- **Dependencies:** none
- **Deliverables:** revoke and rotate the previously committed broker password and
  the real-looking Wi-Fi/MQTT values found in the ignored local firmware file;
  inspect broker/router logs; provision a temporary unique broker replacement only
  if the prototype still requires MQTT; decide whether approved Git-history
  rewriting is required for the committed broker secret.
- **Acceptance:** old broker credential rejected, exposed Wi-Fi password changed,
  repository/examples contain no working secret, and secret scan passes.
- **Rollback:** rotation is intentionally not rolled back; restore connectivity with
  a newly scoped credential.
- **Important:** sanitizing `.env.example` does not complete this package.
- **Evidence:** `docs/evidence/M0-02-CREDENTIAL-ROTATION.md` records the historical
  introduction, current containment, safe owner checklist, and completion fields.

### M0-03 Reproduce the current baseline

- **Status:** IN PROGRESS; E1, Pi inventory/model/camera, resource benchmark, and
  30-minute no-person soak evidence complete; person-in-frame/IMU evidence pending
- **Dependencies:** M0-01
- **Deliverables:** clean setup instructions; locked OS/Python/tool versions; current
  test report; model artifact hashes/validation; Pi hardware inventory; person-in-
  frame pose benchmark; CPU/RAM/temperature/throttle data; 30-minute current-system
  soak.
- **Acceptance:** a second clean environment can reproduce tests; Pi report states
  every mock and missing component; baseline data is stored under a documented
  evidence path without user data.
- **Rollback:** none; read-only characterization.
- **Evidence:** `docs/evidence/M0-03-BASELINE.md`. Linux Python 3.12 dependencies are
  consistent and 86 tests pass. Pi inventory, verified backup, IMX219, artifact
  hashes, real Flex/LiteRT load, HTTP launcher smoke, corrected pose/resource
  benchmark, and a clean 30-minute no-person soak were captured. Person-in-frame
  measurements and real ESP32-C3/MPU6500 stream evidence remain open.

### M0-04 Choose one current entry point and retire false documentation

- **Status:** DONE
- **Dependencies:** M0-01, M0-03
- **Deliverables:** temporarily designate FastAPI port 8000 as the migration entry;
  align service/config docs; label Flask/frontend/test dashboards historical; map
  behavior that must be preserved.
- **Acceptance:** one command starts the prototype; service health URL matches the
  process; no documentation calls old Flask/MQTT architecture the product target.
- **Rollback:** keep old launchers available until G3.
- **Evidence to date:** FastAPI default/config/service/installer now agree on port
  8000; launcher uses shared config and has a regression test; ASGI `/health` smoke
  passes. A bounded Pi deployment proved `.env`/process precedence and the real
  launcher returned 200 from `/health` on loopback. The workspace service template
  matches the verified migration account, Python, checkout, and port, and tests
  enforce those values. Installed units remain disabled/inactive; privileged boot
  hardening is deliberately deferred to M8 and is not evidence for this migration
  entry-point package.

### G0 exit

- M0-02 through M0-04 are `DONE`.
- No real secret is tracked.
- Baseline tests and Pi measurements are recorded honestly.
- The current application has one documented launch path.

## 5. Milestone M1: product package and executable contracts

### M1-01 Create the canonical Python package

- **Status:** DONE
- **Dependencies:** G0
- **Deliverables:** `pyproject.toml`, locked aarch64-compatible dependencies,
  `src/digital_spotter/` skeleton from `ARCHITECTURE.md`, typed configuration with
  dev/test/prod profiles, CLI entry points, and test layout.
- **Acceptance:** editable and clean installs work; import tests need no `sys.path`
  mutation; production profile rejects missing mandatory configuration.
- **Rollback:** old prototype entry remains available.
- **Evidence:** `docs/evidence/M1-01-PACKAGE.md`; universal lock, editable install,
  clean wheel install, installed `dsctl`, seven configuration/package tests, and
  binary aarch64 dependency resolution passed on 2026-08-26.

### M1-02 Define event and time contracts

- **Status:** DONE
- **Dependencies:** M1-01
- **Deliverables:** versioned `IMUSample`, `PoseSample`, `FusedSample`, `RepEvent`,
  `AnalysisEvent`, health state, and common event envelope; monotonic clock types;
  serialization size limits.
- **Acceptance:** round-trip and malformed-input contract tests pass; monotonic time
  cannot be confused with UTC in typed APIs.
- **Rollback:** version 1 contracts are additive until consumers migrate.
- **Evidence:** `docs/evidence/M1-02-EVENT-CONTRACTS.md`; all six versioned payloads
  round-trip through bounded MessagePack, malformed/range/time/type cases fail
  closed, and 20 M1 unit/contract tests pass.

### M1-03 Freeze and manifest the current model contract

- **Status:** DONE
- **Dependencies:** M1-01
- **Deliverables:** manifest with hashes, `(4, 40)` input, ordered features, units,
  preprocessing artifacts/order, threshold from the artifact, output meaning,
  runtime operators, training provenance, evaluation metrics, and limitations.
- **Acceptance:** startup validates every artifact against the manifest; mismatch or
  missing artifact fails production readiness; feature-order test compares code and
  artifact exactly.
- **Rollback:** existing model remains untouched; manifest initially wraps it.
- **Evidence:** `docs/evidence/M1-03-MODEL-MANIFEST.md`; all artifact hashes, exact
  feature order/units/shape/threshold/operators/provenance gaps are executable.
  Tamper/missing/order tests fail closed, and the startup gate intentionally rejects
  this compatibility-only package in production.

### M1-04 Build deterministic replay fixtures

- **Status:** DONE
- **Dependencies:** M1-02, M1-03, D-01, D-02
- **Deliverables:** consent-safe synchronized video/landmark/IMU fixtures, expected
  rep phases/results, corrupted/gap/reset cases, deterministic clock and hardware
  fakes.
- **Acceptance:** replay produces identical results across repeated runs and cannot
  accidentally report simulated adapters as real.
- **Rollback:** fixtures are additive and versioned.
- **Evidence:** `docs/evidence/M1-04-REPLAY.md`; a hash-bound three-frame synthetic
  Y4M stream is aligned to synthetic landmark/IMU/rep/analysis events. Exact normal,
  sequence-gap, clock-reset, corrupt-type, tamper, duplicate-ID, and backward-clock
  checks pass, and replay results hard-code non-real/non-persistable identity.

### M1-05 Add SQLite migration and outbox foundation

- **Status:** DONE
- **Dependencies:** M1-01, M1-02
- **Deliverables:** numbered migrations, WAL/foreign-key configuration, target core
  tables, repository layer, atomic rep+outbox transaction, backup/restore command.
- **Acceptance:** migrate fresh and copied prototype databases; transaction/failure/
  idempotency tests pass; restore drill preserves session and rep counts.
- **Rollback:** backup plus documented compatible migration boundary.
- **Evidence:** `docs/evidence/M1-05-SQLITE.md`; two checksum-bound migrations,
  guarded online pre-migration backup, legacy-row identity backfill, strict target
  tables, atomic completed-rep/analysis/composite-outbox persistence, idempotency,
  failure rollback, and manifest-verified restore all pass.

### G1 exit

- M1-01 through M1-05 are `DONE`.
- Protocol, model, time, and database contracts are machine-tested.
- Deterministic replay exists before hardware pipelines are rewritten.

**Implementation status:** criteria complete on 2026-08-26. Progression into live
G2 evidence remains dependent on G0 owner actions and the real wearable operating
profile; completing M1 does not waive those gates.

## 6. Milestone M2: reliable local BLE sensor

**Assembled PCB follow-up (2026-10-19):** M2-07 is the next hardware task before
mounted validation. Earlier R9 results refer to the old SDA5/SCL6 and NeoPixel
hardware. The assembled PCB has passed separate IMU and external RGB/buzzer
diagnostics; the full application/Pi path still needs adaptation. See
[`docs/PCB_INTEGRATION_PLAN.md`](docs/PCB_INTEGRATION_PLAN.md).

**Active implementation order (owner correction, 2026-08-27):** ADR-019
supersedes the earlier security-first recovery sequence for the active research
build. The ground truth is now the retained R9 source, Pi validator, compact PASS
checkpoint, and `docs/evidence/BLE-R9-ACTUATOR-CUES-20260828.md`. The remaining
order is defined by `docs/BLE_RESEARCH_BRINGUP_PLAN.md`: optionally decide standard
bonding, then build the canonical Pi adapter against unchanged R9 behavior. Custom
HMAC/HKDF, controller provisioning, Secure Boot, flash encryption, and eFuses are
deferred.

**Active stage evidence:** R1-R9 pass as recorded in the bring-up plan. R7 passed
10/10 disconnect/reconnect plus ESP power-cycle and Pi Bluetooth-service restart
recovery. R8 added bounded status and explicit start/stop/identify/buzzer-test
controls. Its real concurrent stream delivered 522 20-byte MPU6500 packets at
50.478014 Hz with zero gaps, I2C errors, or disconnects. R9 finalized the
non-blocking GPIO 8/GPIO 10 policy; the corrected 30-second run passed at
49.964876 Hz with zero gaps, I2C errors, or disconnects, and the owner observed
all state colors and heard the short beep. R10 remains an explicit optional
open-versus-bonded research-mode decision and has not started.

R11 now supplies the canonical R9 Pi adapter. Its final E3 run delivered 6,003
packets over 120.000838 seconds at 50.064697 Hz with zero gaps, invalid packets,
steady-state queue drops, connection failures, reconnects, publisher failures, or
I2C errors. A controlled disconnect recovered automatically and then delivered 502
packets over 10.000465 seconds at 50.075473 Hz with no steady-state errors. See
`docs/evidence/BLE-R11-CANONICAL-PI-ADAPTER-20260828.md`.

The abandoned ESP-IDF/security-recovery experiment is not an active implementation
or rollback. Its superseded source and detailed evidence were removed with explicit
owner approval on 2026-08-28. Current claims come only from the retained R9 source,
validator, checkpoint, and R9 evidence.

### M2 validation cadence

- **Short check:** unit/contract tests plus a 10-second E3 connection for small,
  localized firmware/agent changes that do not alter sustained scheduling, queues,
  memory ownership, clock estimation, radio parameters, power, or recovery.
- **Extended check:** a 2-to-5-minute E3 run for changes that interact with sampling,
  BLE scheduling, clock exchange, or actuator concurrency. Run it only after short
  checks pass.
- **Soak/gate check:** a 30-minute E3/E4 run only when closing a reliability gate or
  after a change that can affect sustained timing, loss, memory, thermal/power, or
  reconnect behavior. Do not repeat it for documentation, UI, pure validation,
  test-only, or isolated parser/schema edits.
- A prior soak remains valid only for the exact firmware, Pi agent, configuration,
  and critical path it measured. A later critical-path change must pass one final
  integrated soak before G2, but iterative small edits should use short/extended
  checks rather than repeatedly spending 30 minutes.

### M2-01 Implement ESP32-C3 BLE firmware foundation

- **Status:** PASS through retained R9 research firmware
- **Dependencies:** G1, D-02
- **Deliverables:** Arduino-ESP32 GATT service; 20-byte real MPU6500 samples;
  bounded control/status/device-info characteristics; reconnect behavior; GPIO 8
  NeoPixel and GPIO 10 buzzer cues.
- **Acceptance:** real ESP enumerates; exact sensor identity; approximately 50 Hz;
  strict packet/sequence/timestamp checks; reconnect and actuator gates pass.
- **Rollback:** retained R9 application binary and matching validator.
- **Evidence:** `docs/evidence/BLE-R9-ACTUATOR-CUES-20260828.md` and the compact
  `firmware/esp32_c3_research/checkpoints/r9/pass/` checkpoint.

### M2-02 Implement Pi BLE agent

- **Status:** PASS as R11 on 2026-08-28; system-image installation/boot remains a G2 deployment check
- **Dependencies:** M2-01, M1-02
- **Deliverables:** one BLE owner; expected R9 name/address/UUID checks;
  connect/reconnect; strict 20-byte parser; bounded latest-sample delivery;
  sequence/rate/age/error health; systemd lifecycle; deterministic fake.
- **Acceptance:** malformed packets rejected; disconnect/reboot/reconnect tests pass;
  no unbounded memory growth; UDS contract tests pass.
- **Rollback:** disable the canonical adapter and use the retained standalone R9
  validator without changing the ESP.
- **Evidence:** strict R9 parser/identity/transport/runtime/bench tests pass; the
  full repository suite passes 209 tests. The unchanged R9 validator still passes.
  The canonical E3 adapter delivered 6,003 packets at 50.064697 Hz over two minutes
  with zero steady-state errors, and a deliberate disconnect recovered without
  pairing or manual BlueZ cleanup. Transition loss is reported separately. See
  `docs/evidence/BLE-R11-CANONICAL-PI-ADAPTER-20260828.md`.

### M2-03 Provisioning and BLE security

- **Status:** PAUSED/SUPERSEDED by ADR-019 for the active research build
- **Dependencies:** M2-01, M2-02
- **Deliverables:** unique per-device key; physical pairing mode; QR/one-time
  provisioning flow; bond allow-list; LE encryption; authenticated session challenge
  and commands; nonce/replay policy; factory reset and re-pair recovery.
- **Acceptance:** unknown device rejected; captured command replay rejected; reset
  invalidates old authorization as designed; secrets absent from logs and Git.
- **Rollback:** physical recovery procedure restores provisioning without a shared
  factory credential.
- **Evidence:** deferred for the active research build. Prior experimental source,
  binaries, and detailed recovery evidence were removed in the approved cleanup;
  they are not current product claims.

### M2-04 Clock synchronization and data-quality policy

- **Status:** PASS for the active R9/R11 research path (E0/E3)
- **Dependencies:** M2-02
- **Deliverables:** counter-wrap/reset handling, offset/drift estimator, RTT
  diagnostics, Pi monotonic mapping, stale/gap/unsynchronized state transitions.
- **Acceptance:** synthetic drift/wrap/reset tests; p95 alignment under 20 ms in real
  hardware test; degraded state triggers rather than zero-fill.
- **Validation cadence:** iterate with E0/E2 tests, 10-second checks, and at most a
  2-to-5-minute diagnostic run. Perform one 30-minute confirmation only after the
  clock candidate passes the shorter gates and is ready to close M2-04/G2.
- **Rollback:** disable scoring when sync quality is unknown.
- **Evidence:** R13-B reuses the unchanged R9 on-demand status read as a bounded
  request/response clock exchange. Deterministic wrap/reset/drift/RTT/stale/causal
  tests pass. After clock acquisition, the exact-source E3 run published 501
  samples at 50.075418 Hz with synchronized clock, 13.017092 ms estimated-error
  p95, and zero measured mapping corrections, clock-gate drops, gaps, queue drops,
  or invalid packets. The 256 acquisition samples were explicitly withheld. See
  `docs/evidence/R13-B-MEASUREMENT-TIME-ALIGNMENT-20260829.md`. This does not close
  M2-06/G2 gym RF, mounting, or sustained-duration evidence.

### M2-05 Restore wearable LED and buzzer safely

- **Status:** PASS in R9
- **Dependencies:** M2-01
- **Deliverables:** non-blocking GPIO 8 NeoPixel states and a bounded GPIO 10
  manual/test buzzer cue without disturbing the 50 Hz sensor schedule.
- **Boundary:** the ESP32 executes cues but never decides model quality. `ds-core`
  owns the M4-04 feedback policy and must suppress commands for mock, stale,
  unsynchronized, low-quality, or unavailable analysis.
- **Acceptance:** malformed/unknown/busy control behavior is bounded; no actuator
  work blocks IMU/BLE scheduling; real GPIO cues are verified; a short concurrent
  50 Hz run has no retry/gap/drop regression.
- **Rollback:** compile with `DS_ENABLE_ACTUATOR_CUES=0` and retain sensor
  streaming/status.
- **Evidence:** the corrected R9 run delivered 1,499 packets at 49.964876 Hz with
  zero gaps, I2C errors, or disconnects while exercising the bounded controls. The
  owner observed every state color and heard the short buzzer. Gym audibility
  remains a later physical-product observation.

### M2-07 Integrate the assembled wearable PCB

- **Status:** IN PROGRESS; PCB1 stream PASS, dashboard/camera restored; physical cues/person gates pending
- **Dependencies:** M2-01, M2-02, M2-04, M2-05; assembled-PCB diagnostics
- **Scope:** original application on SDA18/SCL19; external RGB red1/green0/blue3;
  active GPIO10 buzzer drive; matching Pi firmware identity acceptance; restore
  the existing UI/camera/IMU flow.
- **Acceptance:** compile and app-only upload; correct MPU6500 startup/profile;
  one short real 50 Hz BLE/actuator check; one normal restart/reconnect; one
  short camera/UI/IMU integration observation; mounted person/rep/model gates
  reported independently. No new security ladder or endurance matrix.
- **Rollback:** retain the current PCB actuator image; freeze the first passing
  PCB application and matching Pi files. The archived R9 binary requires old
  wiring and must not be treated as a compatible new-PCB rollback.
- **Plan/evidence:** [`docs/PCB_INTEGRATION_PLAN.md`](docs/PCB_INTEGRATION_PLAN.md).
  On 2026-10-19 read-only SSH confirmed Bluetooth powered, no throttling,
  temperature 45.2 C, and the project UI/agents stopped after boot. The subsequent
  implementation adapted PCB1 pins/PWM/active-buzzer drive and strict Pi identity
  acceptance; 17 focused host checks pass. The installed parser is backed up in
  `~/pcb1-before-20261019.vi9L9t/` and the matched parser is deployed. Firmware
  build and app-only upload pass (664,224-byte application). Serial startup
  verifies MPU6500 0x70, the 50 Hz register profile, PWM RGB initialization and
  BLE advertising with zero acquisition errors. External-power stream passed:
  1,499 samples at 49.965309 Hz with zero gaps/I2C errors/disconnects. The normal
  Pi receiver reconnected, graph data updates and existing camera-only WebRTC
  playback works. A separate PCB1 stream-pass checkpoint is frozen. Owner
  missed the cue observation and requested replay later. The pose-startup timeout
  was resolved on 2026-10-20 with an isolated, pinned Python environment and an
  explicit pose interpreter. One combined real run delivered 94 pose events,
  no processing failures and a gap-free 100-sample IMU window. All poses were
  missing, so mounted person/rep/model checks remain pending.

### M2-06 Gym RF and mounting soak

- **Status:** NOT STARTED
- **Dependencies:** M2-02, M2-04, M2-05, D-01, enclosure prototype
- **Deliverables:** tests around people, metal rack/bar, multiple orientations,
  active Wi-Fi, nearby BLE devices, low battery, and realistic distance/movement.
- **Acceptance:** 50 Hz minimum, less than 0.5 percent loss over 30 minutes, recovery
  under two seconds target, and no unsafe/confident scoring during loss.
- **Rollback:** adjust antenna/enclosure/rate/connection policy and repeat; do not
  change transport based on a lab-only observation.

### G2 exit

- Real MPU6500 data streams over BLE at the accepted rate and packet contract.
- Reconnect and restart behavior pass on the real Pi and ESP without destructive
  recovery.
- Wearable state and feedback cues remain non-blocking while the IMU streams.
- The Pi ends with one canonical boot-capable BLE adapter, strict parser, bounded
  queue/reconnect logic, observable health counters, and preserved
  Wi-Fi/SSH/Tailscale management access.
- The selected research security mode is explicitly recorded as open or standard
  bonded BLE; no custom application security is required under ADR-019.
- MQTT is disabled in the real-time product configuration.
- Final BLE parameters and mounting assumptions are recorded.

## 7. Milestone M3: Pi vision and video path

### M3-00 Non-destructive workspace normalization

- **Status:** IN PROGRESS; owner reprioritized repository-only normalization on
  2026-08-27 while G2 hardware recovery remains paused
- **Dependencies:** G2, M0-04, M1-01
- **Deliverables:** authoritative top-level layout and entry-point map; inventory of
  every prototype path and behavior to preserve; explicit legacy/deprecation labels;
  removal of duplicate generated/cache/build artifacts; import/config/documentation
  normalization. Move historical source only after references/tests are updated;
  delete no user data or prototype source in this package.
- **Acceptance:** canonical commands and imports pass from a clean environment;
  documentation links resolve; no active path depends on an unexplained duplicate;
  `git diff --check` and full repository tests pass.
- **Rollback:** file moves remain reviewable in Git and the pre-normalization paths
  remain recoverable; destructive archival is deferred to M8-04.
- **Evidence to date:** `docs/WORKSPACE.md` defines the authoritative commands and
  classifies every major active, canonical, legacy, historical, generated, and
  local-state path. The unusable ignored Windows `venv/` and reproducible project
  caches were removed; the working Linux `.venv/`, local data, secrets, models,
  firmware, `_archive/`, and every prototype source path were preserved. Completion
  remains gated on the full clean-environment tests and the existing G2 dependency.

### M3-01 Repair the current live orchestration regression

- **Status:** NOT STARTED
- **Dependencies:** G1
- **Deliverables:** make processed frame results reach the canonical session path;
  add a regression test that a real/replayed completed rep causes one inference and
  one database transaction; repair camera stop/start lifecycle.
- **Acceptance:** automatic path works without `/predict`; no duplicate reps;
  restart recreates released MediaPipe resources.
- **Rollback:** old manual endpoint remains diagnostic-only.

### M3-02 Camera ownership and dual-stream spike

- **Status:** PARTIAL (E0/E3; controlled-person and visual-latency gates deferred)
- **Dependencies:** M0-03, M1-02
- **Deliverables:** compare (A) Picamera2 dual-stream owner publishing hardware H.264
  to MediaMTX and (B) MediaMTX camera owner plus local RTSP decode, using a person in
  frame.
- **Acceptance:** record CPU, RSS, temperature, throttle, pose FPS/accuracy, video
  latency, restart reliability, and implementation risk; approve one in
  `docs/DECISIONS.md`.
- **Rollback:** keep the measured current RTSP path.
- **Evidence to date:** Picamera2 is provisionally selected because it preserved
  100% monotonic exposure-start timestamps, used less CPU/RSS, ran pose faster, and
  published a real 1280x720 H.264 stream through the WebRTC relay. The
  MediaMTX-owner candidate had no capture-time metadata. Both owner lifecycles
  restarted 3/3. The current environment could not support a comparable full-body
  run, so pose accuracy and browser glass-to-glass latency remain open. See
  `docs/evidence/R13-C-CAMERA-OWNERSHIP-20260831.md`.

### M3-03 Build isolated latest-frame vision worker

- **Status:** IN PROGRESS (implementation Steps 1-7 and the E3 camera-loss/
  recovery gate complete; controlled-person gate deferred)
- **Dependencies:** M3-02, M1-02
- **Deliverables:** selected camera adapter, MediaPipe live/latest-frame processing,
  capture timestamps, pose quality, UDS publisher, health/watchdog, deterministic
  replay adapter.
- **Acceptance:** bounded queue tests; camera loss/recovery; real person pose test;
  worker crash does not corrupt an active database.
- **Rollback:** feature switch to current processor during migration.
- **Evidence to date:** the legacy and canonical paths, process/runtime boundary,
  acceptance layers, and rollback boundary are traced in
  `docs/evidence/M3-03-VISION-WORKER-TRACE-20260831.md`. Step 2 promoted the
  capture-time and capacity-one frame primitives and added deterministic canonical
  pose-event construction with explicit missing/low-visibility states. Step 3
  added an adapter-injected one-shot worker plus bounded deterministic Y4M replay,
  explicit simulated output, lifecycle/failure counters, and an E1 child-process
  crash test that leaves an active disposable SQLite session intact. Step 4 added
  the canonical split-runtime Picamera2 and real MediaPipe adapters, typed
  camera/protocol/pose failures, bounded stall handling, and compatibility wrappers
  so the R13-C benchmark uses the same implementation. E3 evidence passed 3/3
  camera-owner restarts and 30/30 real-camera canonical events with strictly
  monotonic exposure-start timestamps. The available scene contained no person,
  so real-landmark accuracy remains open. Step 5 added the separate bounded
  drop-oldest vision UDS publisher, length/permission/peer validation, reconnect
  counters, canonical worker health transitions and periodic heartbeat, plus a
  monotonic watchdog. Its focused E0/E1 gate passed 40/40 tests and the broader
  affected regression gate passed 100 tests with 2 existing warnings. Step 6
  added a typed `legacy|canonical` migration switch whose default remains legacy,
  a standalone canonical vision-agent entry point, real adapter/publisher assembly,
  signal-driven bounded shutdown, and a local end-to-end runtime test that
  delivered three replay pose plus five simulated health events with zero drops.
  The Step 6 affected gate passed 131 tests with 7 existing warnings, and the
  repository regression gate passed 282 tests with the same 7 warnings. No Pi
  service was installed or enabled. Step 7 then used the hash-matched candidate on
  the real Pi/IMX219: terminating only the agent-owned Picamera2 helper produced
  canonical `camera_unavailable` degraded/stopping health, the expected agent
  failure exit, complete helper cleanup, and a fresh-owner restart that returned
  real camera events and stopped cleanly. The Pi remained unthrottled. The
  controlled-person E3 gate remains required before M3-03 can be marked complete.
  The 2026-10-20 M2-07 follow-up resolved the on-demand startup timeout without
  changing pose settings: isolate MediaPipe from the full TensorFlow environment
  and select that interpreter explicitly. One short real combined run passed
  startup/capture delivery but found no person; it does not close this gate. See
  `docs/evidence/m2-07-pcb1-20261019/pose-startup-fix.md`.

### M3-04 Direct WebRTC and browser overlay

- **Status:** IN PROGRESS (Steps 1-4 software contracts implemented; custom
  research viewer playback passed E3; telemetry integration, authenticated API
  and remaining timing/acceptance gates pending)
- **Dependencies:** M3-02, M3-03
- **Deliverables:** loopback H.264 publication, MediaMTX WHEP, authenticated local
  access policy, browser canvas landmarks, timestamp matching, removal plan for
  MJPEG/server-side drawing.
- **Acceptance:** p95 local glass-to-glass target under 250 ms; overlay remains
  aligned; WAN disconnected test works; multiple clients respect resource limits.
- **Rollback:** migration-only MJPEG endpoint behind a development flag.
- **Evidence to date:** Step 1 adds the canonical MediaMTX relay configuration with
  a loopback-only RTSP publisher at `127.0.0.1:8554/picamera2`, a development WHEP
  listener, and typed `video.publish_url`/`DS_VIDEO_PUBLISH_URL` wiring into the
  feature-gated vision agent. Steps 2-4 add an isolated wrapper around MediaMTX's
  supported browser reader, a strict browser pose/clock contract, bounded
  minimum-RTT clock mapping and pose lookup, letterbox-correct canvas projection,
  explicit stale/degraded clearing, and a decoded-frame controller. The existing
  legacy default and dashboard remain unchanged. E0 tests use deterministic fakes;
  The later private E3 check proved custom-viewer H.264/WHEP playback with a
  pinned v1.12.3 official reader and unchanged v1.9.1 server. Authenticated
  delivery, observed latency/alignment, offline operation and multi-client limits
  remain open. See `docs/evidence/M3-04-DIRECT-WEBRTC-TRACE-20260915.md` and
  `docs/evidence/M3-04-CUSTOM-VIEWER-20260915.md`. A later pose/clock research
  bridge passed focused E0 checks and received real Pi canonical pose events;
  browser `captureTime` and visual alignment remain unverified. See
  `docs/evidence/M3-04-POSE-TELEMETRY-20260928.md`.

### G3-vision exit

- One component owns the camera.
- Vision worker is bounded, restartable, and measured with a person.
- Browser uses direct WebRTC without Python JPEG encoding in product mode.

## 8. Milestone M4: canonical local exercise loop

### M4-01 Implement fusion engine

- **Status:** IN PROGRESS; the research step-2 on-demand measurement-time slice
  passes focused deterministic checks, but mounted coordinate calibration,
  live scheduling, and the full M4-01 acceptance matrix remain open.
- **Dependencies:** G2, M3-03
- **Deliverables:** bounded IMU ring, pose association/interpolation, quality
  assessment, calibration/coordinate transform, fused event contract.
- **Acceptance:** deterministic replay covers jitter, gaps, clock drift, pose loss,
  and reconnect; fusion never uses arrival time as measurement time.
- **Rollback:** feature flag prevents model scoring while allowing capture evidence.

### M4-02 Implement session and rep state machines

- **Status:** NOT STARTED
- **Dependencies:** M4-01, M1-05
- **Deliverables:** explicit device/session/rep states, idempotent start/stop,
  interruption recovery, one canonical completed-rep event.
- **Acceptance:** state transition/property tests; crash/restart recovery; repeated
  commands do not duplicate sessions or reps.
- **Rollback:** export/recover prototype sessions before migration.

### M4-03 Unify feature building and inference

- **Status:** IN PROGRESS; completed-rep to V5 candidate-input bridge passes
  focused E0 checks, but live scoring remains disabled.
- **Dependencies:** M4-02, M1-03
- **Deliverables:** one feature builder and preprocessing pipeline used by live,
  replay, and diagnostic API; remove duplicated manual `/predict` calculations;
  explicit unavailable/degraded result.
- **Acceptance:** golden vectors match training contract; live and replay paths are
  bitwise/equivalently preprocessed; no padding/truncation/zero-fill in production.
- **Rollback:** compare both paths in shadow mode without presenting duplicate
  results.

### M4-04 Feedback policy and durable transaction

- **Status:** NOT STARTED
- **Dependencies:** M4-03, M1-05
- **Deliverables:** confidence/quality gating, rate-limited buzzer/LED feedback,
  model/version metadata, atomic rep+analysis+outbox save.
- **Acceptance:** feedback never fires from mock/unavailable/low-quality results;
  database failure does not create a false saved state; outbox event is idempotent.
- **Rollback:** disable physical feedback while preserving analysis logs.

**Pi legacy RGB wiring note (2026-10-14):** An owner-observed single-channel
check showed BCM27 lights red and BCM17 lights green. The legacy Pi defaults
were swapped to match; this does not advance M4-04 feedback acceptance or
change the ESP32-C3 NeoPixel/buzzer mapping.

### G3 edge-loop exit

- A real ESP32-C3 and real camera complete a WAN-disconnected session.
- Each completed rep produces at most one model result and durable transaction.
- Disconnect/degraded behavior is visible and does not fabricate data.

## 9. Milestone M5: finalized V5 intake, Pi runtime, and validation

The model-training workspace owns the immutable `Datasets v2 Model v5/` Stage 8
package. This repository does not retrain, refit, change the frozen threshold, or
modify that source package. The existing V4 `(1, 4, 40)` assets remain isolated
compatibility evidence, not a live V5 fallback. See
`docs/V5_RUNTIME_INTEGRATION_AUDIT.md` and
`docs/V4_TO_V5_RUNTIME_MIGRATION.md`.

### M5-00 Accept and audit the finalized V5 handoff

- **Status:** PASS for documentation/intake only; no artifacts copied or runtime
  activated (2026-09-28).
- **Dependencies:** none; precedes V5 runtime implementation.
- **Deliverables:** verify the source package hash manifest; map existing Pi
  components and V4 assumptions; record feature, phase, unit, and backend gaps.
- **Acceptance:** all manifest-listed source files hash-match; audit and migration
  inventory identify blockers without claiming hardware or inference success.
- **Rollback:** documentation-only change; source package and V4 runtime unchanged.

### M5-01 Build a portable V5 contract and prove offline parity

- **Status:** PASS for offline artifact/contract parity on 2026-09-28; V5 not
  activated on the Pi or in a live session. See
  `docs/V5_RASPBERRY_PI_INTEGRATION_REPORT.md`.
- **Dependencies:** M5-00.
- **Deliverables:** isolated, hash-verified copy of deployment-only V5 artifacts;
  one canonical three-phase `(1, 3, 29)` plus context `(1, 2)` adapter; trusted
  export of fitted scaler/Platt state to portable runtime data; fail-closed
  loading, calibration, and frozen threshold; deterministic contract tests.
- **Acceptance:** exact Stage 8 feature/context order and preprocessing parity
  against trusted source execution, Keras/FP32 TFLite numerical parity on a
  provenance-recorded fixture, no forbidden V4 fields or synthetic delta, and
  no training-data parity result misreported as held-out accuracy.
- **Rollback:** leave V4 compatibility package untouched; V5 remains inactive.

### M5-02 Verify built-in TFLite on the real Pi

- **Status:** PARTIAL; one E3 fixed-fitted-median input loaded and inferred on the
  real Pi with `ai-edge-litert==2.2.0` on 2026-09-30. The 24 copied artifacts
  hash-matched, the frozen decision matched the local reference, and a short
  20-call adapter run measured 2.445 ms p95. This is not live-feature or full
  thermal/performance acceptance; see
  `docs/evidence/M5-02-V5-PI-FIXED-FIXTURE-20260930.md`.
- **Dependencies:** M5-01.
- **Deliverables:** batch-one FP32 built-ins baseline, optional dynamic-range
  comparison, actual Pi interpreter/operator compatibility, latency/RSS/thermal
  evidence, and versioned backend decision. No full TensorFlow in final Pi mode.
- **Acceptance:** exact V5 inputs load and infer in the selected Pi runtime;
  calibrated decision parity passes; p95 classifier latency target is under 25 ms
  without claiming end-to-end or live-feature readiness.
- **Rollback:** V5 integration stays disabled; retain verified artifacts/evidence.

### M5-03 Validate frozen V5 policy with live, mounted data

- **Status:** NOT STARTED; human-camera and mounted gym validation remains last.
- **Dependencies:** M5-02, M4-03, M4-04, D-01, D-02.
- **Deliverables:** representative squat/deadlift, sensor-unit, phase, sync,
  false-alert, and subgroup evidence; model-card limitations and release decision.
- **Acceptance:** live V5 features and quality gates match the frozen contract;
  owner-approved field criteria pass. The Stage 8 threshold is not retuned here;
  a change requires a separate model-owner decision and versioned package.
- **Rollback:** suppress V5 user-facing scoring; preserve consented evidence.

### G4 exit

- Real Pi meets model, pose, end-to-end latency, memory, and thermal budgets.
- Selected model requires no full TensorFlow runtime.
- Accuracy and limitations are supported by versioned evidence.

## 10. Milestone M6: secure local API and product UI

### M6-01 Versioned local API

- **Status:** NOT STARTED
- **Dependencies:** M4-02
- **Deliverables:** `/api/v1` schemas, stable errors, health/readiness, session
  commands, history, WebSocket event stream, generated API specification.
- **Acceptance:** schema/authorization/idempotency tests; handlers contain no feature
  math or private-attribute access.
- **Rollback:** prototype endpoints remain on a development-only adapter.

### M6-02 Local identity and authorization

- **Status:** NOT STARTED
- **Dependencies:** M2-03, M6-01, D-03
- **Deliverables:** physical pairing mode, pinned device identity/local TLS approach,
  short-lived tokens, owner/guest roles, CSRF/origin protection, explicit CORS.
- **Acceptance:** unauthenticated mutations rejected; stolen/expired/replayed tokens
  rejected; recovery and device reset tested.
- **Rollback:** bind management interface to loopback during recovery; never enable
  wildcard unauthenticated production mode.

### M6-03 Product dashboard

- **Status:** NOT STARTED
- **Dependencies:** M3-04, M6-01, M6-02
- **Deliverables:** setup/pairing, calibration, exercise/session flow, direct WebRTC,
  pose overlay, rep feedback, degraded/offline states, history, accessibility.
- **Acceptance:** supported client/device matrix; no-internet session; keyboard/touch/
  screen-size tests; real/mock state is unmistakable.
- **Rollback:** retain a diagnostic UI accessible only in development mode.

**Interim research Step 1 (2026-10-03):** The existing redesigned page and
hash-verified V5 runtime were copied to a new isolated Pi directory. The model
loads there; a read-only static page is reachable only through Pi loopback and a
private SSH tunnel. No camera, fixture prediction, session control, or scoring
was enabled. This does not satisfy M6-01/M6-02 or change the M6-03 status. See
`docs/evidence/M6-03-PI-RESEARCH-UI-STEP1-20261003.md`.

**Interim research Step 2 (2026-10-03):** The real Pi IMX219/H.264 stream played
inside that redesigned page through a temporary loopback-only MediaMTX relay
and private SSH tunnel. One short headless-browser playback/Stop check passed;
visual quality, timing, pose, mounted IMU, analysis and full M3-04/M6-03 gates
remain open. See `docs/evidence/M6-03-PI-RESEARCH-UI-STEP2-20261003.md`.

**Interim research Step 2B (2026-10-03):** The owner-reported tunnel refusals
were traced to the bounded Step 2 camera and relay processes expiring. A
loopback-only, on-demand MediaMTX relay now starts/stops the real Pi camera
with browser readership; the Workout panel connects from one button without
requiring a typed URL. One short browser playback/Stop and process-cleanup
check passed. This remains a temporary research UI, not M6-03 product
completion or a scored session. See
`docs/evidence/M6-03-PI-RESEARCH-UI-STEP2B-20261003.md`.

**Interim research Step 3 (2026-10-03):** The Pi-hosted page now uses normal
Digital Spotter branding without global preview/research badges. One frozen
fitted-median V5 input was run on the Pi and its reference-only output is shown
solely in Devices → Analysis under a small **Test input** label. Workout Feedback,
live analysis readiness, persistence and wearable cues remain unavailable. See
`docs/evidence/M6-03-PI-UI-TEST-INPUT-20261003.md`.

**Interim research Step 4 (2026-10-03): PARTIAL.** The same Pi page now reads
the existing canonical session's read-only sensor/rep status. A short Pi check
confirmed real Picamera2/MediaPipe pose events and on-demand H.264 from one
camera owner; the empty scene stayed degraded, not scored. The expected ESP
was not discovered, so wearable receipt and combined live status are still
unverified. V5 feedback, mounted-person analysis, and product dashboard gates
remain open. See `docs/evidence/M6-03-PI-UNSCORED-STATUS-20261003.md`.

**Interim research Step 4B (2026-10-03): DISPLAY ONLY.** The Pi page now
draws acceleration and gyroscope from a bounded, read-only window of real
canonical IMU samples. One short live endpoint check returned current MPU6500
vectors. Stale input clears the plots. Calibration, mounted-person validation,
V5 scoring, and M6-03 product acceptance remain open.

**Interim person-pose diagnostic (2026-10-14): DEPLOYED TO PI; PENDING HUMAN RUN.** A loopback-only
Camera-panel action provides a visible 20-second walk-in countdown, then a
30-second canonical real-camera/MediaPipe check and an aggregate-only saved JSON
result. The Pi UI/status smoke check and focused fake-runner/HTTP-origin tests pass. The earlier manually
timed 30-frame real-Pi check processed 30 frames but found no person pose; this
tool must not be marked as controlled-person acceptance until the owner runs it
with verified framing. No V5 scoring, rep, IMU calibration, or product API gate
is claimed.

### G5 exit

- Local product is authenticated, explicitly degraded, and usable without WAN.
- Security controls and recovery paths pass tests.

## 11. Milestone M7: cloud and analytics

### M7-01 Provision staging cloud boundary

- **Status:** NOT STARTED
- **Dependencies:** G5, owner approval for cloud/billing
- **Deliverables:** separate staging Firebase/GCP project, Cloud Run ingestion API,
  least-privilege service account/IAM, secret manager, budgets/alerts, audit logs.
- **Acceptance:** infrastructure/config is reviewable; no Admin key on Pi; denied
  paths and cross-tenant access tests pass.
- **Rollback:** destroy staging resources only with owner approval; local product is
  unaffected.

### M7-02 Implement device upload authentication

- **Status:** NOT STARTED
- **Dependencies:** M7-01, M2-03
- **Deliverables:** unique device identity/token exchange, key rotation/revocation,
  request signing/nonces, ownership binding, rate/size limits.
- **Acceptance:** cloned/revoked/unknown device requests rejected; credentials are
  rotatable without reimaging the Pi.
- **Rollback:** disable upload and retain local outbox.

### M7-03 Implement idempotent outbox synchronization

- **Status:** NOT STARTED
- **Dependencies:** M1-05, M7-02
- **Deliverables:** `ds-sync`, versioned cloud payload, retry/circuit-breaker policy,
  Firestore summary writes, optional Storage upload policy, acknowledgments.
- **Acceptance:** WAN loss, timeout, 429, 5xx, duplicate request, reboot, and long
  backlog tests; no duplicate cloud rep; local session remains responsive.
- **Rollback:** stop sync service; queue remains durable.

### M7-04 Privacy-safe analytics

- **Status:** NOT STARTED
- **Dependencies:** M7-03, D-04, privacy approval
- **Deliverables:** data inventory, retention/deletion/export policy, aggregation,
  consent controls, operator dashboard metrics, redaction.
- **Acceptance:** user deletion/export and retention expiry tested; raw media cannot
  upload without explicit policy and consent.
- **Rollback:** disable analytics export; retain only required local records.

### G6 exit

- Staging sync is secure, idempotent, offline-tolerant, and observable.
- Data minimization, retention, deletion, and consent behavior are approved.

## 12. Milestone M8: product deployment and operations

### M8-01 Harden Pi services

- **Status:** NOT STARTED
- **Dependencies:** G5
- **Deliverables:** dedicated user/group, systemd services and targets, filesystem
  permissions, capability/device allow-list, watchdogs, restart limits, firewall,
  log rotation, health aggregation.
- **Acceptance:** least-privilege review; process crash/restart tests; secrets mode
  checks; boot reaches correct ready/degraded state.
- **Rollback:** boot into previous release/service target.

### M8-02 Atomic signed updates and rollback

- **Status:** NOT STARTED
- **Dependencies:** M8-01, M7-02
- **Deliverables:** signed application/model/firmware manifests, immutable versioned
  release directories, atomic activation, pre/post-health checks, automatic
  rollback, ESP OTA recovery.
- **Acceptance:** corrupt/unsigned/interrupted/bad-health updates rejected or rolled
  back; power-loss drill preserves bootability and data.
- **Rollback:** previous signed release remains installed and selectable.

### M8-03 Backup, restore, factory reset, and support bundle

- **Status:** NOT STARTED
- **Dependencies:** M1-05, M8-01
- **Deliverables:** encrypted backup/export, restore validation, safe factory reset,
  redacted diagnostic bundle, operator runbooks and alert thresholds.
- **Acceptance:** restore drill on a replacement SD image; reset removes user keys/
  data as specified; support bundle secret/PII scan passes.
- **Rollback:** documented recovery image and local backup.

### M8-04 Retire replaced prototypes and finish workspace cleanup

- **Status:** NOT STARTED
- **Dependencies:** G5, M3-00, M8-03, explicit owner approval for deletion/archive
- **Deliverables:** archive or remove only behaviorally replaced Flask,
  test-dashboard, MQTT, duplicate launcher/config, and obsolete dependency paths;
  preserve tagged rollback history; remove stale documentation and secret-bearing
  local artifacts; leave one supported application, firmware, test, and operations
  path.
- **Acceptance:** parity map has no unresolved behavior/data dependency; clean build,
  full tests, Pi boot/session smoke, secret scan, backup/restore, and rollback-tag
  verification pass; workspace inventory contains no unexplained active duplicate.
- **Rollback:** restore the tagged pre-cleanup revision and validated data backup.

### G7 operations exit

- Device survives reboot, crash, disk pressure, WAN outage, and failed update.
- Operators can diagnose and recover it without source-code edits.
- Replaced prototype paths are retired only with owner approval and verified
  rollback; the supported workspace has one clear product path.

## 13. Milestone M9: gym pilot and release

### M9-01 Final enclosure/mounting and environmental validation

- **Status:** NOT STARTED
- **Dependencies:** G4, D-01, D-02
- **Deliverables:** antenna-safe enclosure, secure attachment, battery/runtime plan,
  sweat/impact/cleaning considerations, cooling/airflow, labeled reset/pairing.
- **Acceptance:** repeated real-gym RF, movement, temperature, battery, and attachment
  tests; no exposed moving cable; no thermal throttling.

### M9-02 Controlled pilot

- **Status:** NOT STARTED
- **Dependencies:** G6, G7 operations exit, privacy approval
- **Deliverables:** consented pilot protocol, supported exercises, onboarding,
  incident reporting, product telemetry, feedback review, exit criteria.
- **Acceptance:** agreed session success rate, false-alert rate, reconnect behavior,
  usability, and support metrics; every incident triaged.

### M9-03 Release candidate and owner approval

- **Status:** NOT STARTED
- **Dependencies:** M9-01, M9-02
- **Deliverables:** signed reproducible image, SBOM/license review, model card, privacy/
  retention terms, release notes, known limitations, rollback image, support plan.
- **Acceptance:** G0-G7 evidence reviewed; release checklist passes; explicit owner
  approval is recorded.

### G8 exit

The product is release-ready only after M9-03. Earlier demos, passing unit tests,
architecture completion, or cloud deployment do not satisfy this gate.

## 14. Recommended next execution sequence

### Core-first research sequence — owner direction, 2026-09-28

The immediate objective is **one real, local camera + wireless IMU exercise loop**,
not another browser, BLE recovery, or endurance campaign. Reuse the accepted R9/R11
BLE stream, R12 local session, R13-B clock mapping, M3-03 camera worker, and M5-01
offline V5 adapter. These are foundations, not proof of live V5 scoring. The
wearable may be USB-powered from the PC for development; its normal data path to
the Pi remains wireless BLE. Do not reflash or re-pair it for unchanged behavior.

| Next | Build only this core capability | Small proof before moving on |
|---|---|---|
| 1. Join the real producers (M3-01, M4-01) | Let one canonical core session consume the existing `ds-imu` and `ds-vision` event streams together. Preserve each event's measurement timestamp, source/quality and bounded buffering; do not use the legacy dashboard's independent capture path. | One short simultaneous Pi run shows real IMU and real camera events arriving at the same session. An empty scene may correctly report `vision_degraded`; it is not a scored rep. |
| 2. Fuse by measurement time (M4-01) | Associate pose with nearby clock-mapped IMU samples; surface gaps, stale data, clock resets and unavailable calibration explicitly. Do not substitute arrival time or zeros. | Focused deterministic cases for near/far timestamps and missing data; inspect one short joined event trace only if the integration changed. |
| 3. Build three real rep phases (M4-02) | Establish squat/deadlift phase boundaries and aggregation from the V5 training contract, then produce one completed-rep event. Keep the session state authoritative and avoid duplicate reps. | Focused recorded/replay example produces exactly three ordered phase records. If source phase semantics are missing, stop scoring and obtain them from the model owner; do not guess. |
| 4. Build and run exact V5 input (M4-03, M5-02) | Produce the ordered 29 phase features and `[Exercise_ID, Load_kg]` through the existing canonical V5 adapter; verify live sensor units, axes, asymmetry and knee–hip formulas before enabling results. Load the frozen built-ins FP32 TFLite on the actual Pi. | Exact-contract checks and one fixed-fixture Pi inference. A missing or non-equivalent live feature yields `unavailable`, never a fabricated probability or V4 fallback. Do not retrain or retune. |
| 5. Finish one local result path (M4-04, M6 research subset) | Quality-gate one binary V5 result per rep, save it transactionally in SQLite, and show session/sensor/result state in a simple local UI. Reuse existing LED/buzzer device-state cues. Keep model-derived wearable cues disabled until an allowed research command policy is recorded; do not invent error categories. | One focused local session/result transaction check. No cloud, UI redesign, or production authentication is required to prove the local research loop; do not expose unauthenticated mutation endpoints beyond a controlled bench. |
| 6. Validate the finished integrated flow LAST (deferred M3-04, M5-03, M2-06) | With approved person framing and lower-back mounting, check real three-phase features, one saved result, visible feedback, camera/IMU alignment and browser overlay/timing if needed. Then decide whether longer RF/thermal/endurance evidence is justified for a named gate. | One planned end-to-end session with recorded limitations. This is the first human-camera/mounted acceptance run, not a repeated test after every coding step. |

**Step 1 joined-capture status (2026-09-28): PASS for the narrow research gate.**
One temporary Pi run received 410 real R9 IMU events and 58 real Picamera2/
MediaPipe pose events in the same core session, with overlapping Pi-monotonic
measurement ranges and bounded pose buffering. The empty scene correctly
produced degraded poses; no result was scored or saved. See
`docs/evidence/JOINT-CAPTURE-20260928.md`. This does not complete measurement-
time fusion, 50-Hz under concurrent load, controlled-person vision, or M3-01/
M4-01 as whole work packages. Continue with step 2; no extra hardware test is
needed for unchanged BLE/camera producers.

**Step 2 measurement-time fusion status (2026-09-28): PASS for the narrow
deterministic research slice.** `FusionEngine` interpolates from capture-time
brackets in the Pi monotonic domain, and `LocalSessionService` exposes the
latest-pose outcome from its bounded rings. Missing/far data, gaps, clock
reset/uncertainty, stale pose, and uncalibrated IMU fail closed or stay
degraded; no arrival-time substitution, zero filling, analysis persistence, or
model scoring was added. Only focused local checks ran; there was no Pi or
human-camera test. Continue with step 3 after checking exact V5 phase semantics.

**Step 3 narrow code status (2026-09-29): locally implemented, not live-validated.**
The owner confirmed `FYP/Vision/vision.py` as the recorded-video extraction
script. `RepPhaseBuilder` now adapts its knee-peak/35%-45% split/vision-median
rule for completed live events, without its no-peak fake-rep fallback. The
session owns bounded rep history separately from its latest-pose ring and
exposes one-shot polling; synchronized IMU medians are explicitly a research
adaptation, not proven V2 source parity. Focused synthetic tests passed; no
real person, Pi/ESP, model scoring, or persistence test ran. See
`docs/V5_PHASE_CONTRACT.md`. Continue with Step 4 only as fail-closed feature
construction and actual Pi model loading; do not infer live model readiness.

**Step 4 local feature-construction status (2026-09-30): PARTIAL, E0 only.**
`inference/v5_features.py` maps a good completed rep's three phase summaries
to exactly the Stage 8 ordered 29 fields and `[Exercise_ID, Load_kg]`, including
the frozen asymmetry, coupling and acceleration-magnitude formulas. Missing or
degraded inputs fail closed. A focused three-case check passes and the frozen
preprocessor accepts the candidate shapes. The bridge is not connected to
scoring, persistence or the UI; training IMU units/axes, live pose equivalence,
mounted behavior and actual Pi TFLite loading were unverified at this local
checkpoint. The subsequent fixed-fixture Pi check above passed narrowly; M4-03
and the full M5-02 gate are not complete. Do not start a person-camera test here.

**Step 4 source-equivalence audit (2026-09-30): BLOCKED for live scoring.**
The V2 training IMU capture/phase generator and gyro unit are not traceable from
the available source. The historical sketch intends deg/s, whereas the current
Pi path emits rad/s into the V5 candidate fields; the training vision extractor
also uses a different MediaPipe implementation from the live adapter. These
are not automatic reasons to discard the model, but they prohibit asserting
feature parity or enabling user-facing V5 results. No extra hardware test was
run. A read-only recheck of the FYP workspace found the historical seven-column
MPU6050 serial sketch/logger but no saved `real_imu_data.csv` or exact V2 IMU
capture/phase generator; the V5 IMU CSV is byte-identical to V2's phase-level
CSV. The live-scoring gate remains blocked; do not infer units from V1 code.
See `docs/evidence/M5-02-LIVE-V5-FEATURE-SOURCE-AUDIT-20260930.md`.

**Step 5 unscored status slice (2026-09-30): LOCALLY IMPLEMENTED, NOT E3.**
A loopback-only research runner can use the canonical `LocalSessionService` and
existing IMU/vision UDS receivers to project detected rep count and sensor
freshness to `ui-preview/`. The route is read-only and always reports V5
analysis unavailable; it neither loads the model nor saves an analysis result.
Focused E0/E1 contract and browser-client checks pass. No Pi deployment, live
person test, mounted IMU comparison, scored result transaction, or product API
acceptance is claimed. The full M4-04/M6 result path remains open.

**Step 5 unscored persistence boundary (2026-09-30): REVIEWED, NOT IMPLEMENTED.**
The existing `reps` table has nullable inference/analysis columns, but the
supported `SQLiteRepository.save_completed_rep()` path commits a completed rep,
analysis and outbox event together. Persisting a detected-only rep would need a
separate explicit contract and a safe later promotion path for the same rep UUID;
using the scored transaction or inserting a bare row would misstate durability
or collide with later scoring. Keep the research UI's unscored rep count
process-local for now. No schema migration or database write was added. Decide
whether detected-only reps need durable retention when the V5 live-feature gate
is resolved and the M4-04 result path is specified.

**Step 5 reference-only shadow slice (2026-09-30): LOCALLY IMPLEMENTED, NOT E3.**
An explicit runner option can build exact V5 candidate inputs from a completed
rep and invoke the frozen model off the capture callback. The terminal reports
only whether reference-only inference executed; the read-only UI remains
`analysis: unavailable`, and no probability, class, feedback or analysis/outbox
write is emitted. Focused local checks include one frozen-model invocation.
No live Pi/person/mounted test, source-unit calibration, or validated V5 result
is claimed. Resolve those at the planned final integrated gate, not by silently
promoting this shadow result to a scored one.

During steps 1–5 run only the focused code checks needed for the changed boundary
and the two named short hardware confirmations in steps 1 and 4. Do not repeat old
BLE pairing/reconnect, camera ownership, WebRTC fallback, browser `captureTime`,
factory-reset, or 30/60-minute soak experiments merely to advance the core. If a
focused check fails, preserve its evidence, identify the failing layer, and fix
that layer before continuing; do not launch a sequence of speculative retries.
The incomplete M3-04 browser timing check is **deferred**, not passed or waived.
Existing commercial security, cloud, deployment, privacy and final product gates
remain open; this sequence does not redefine them as complete.

### Historical bring-up sequence

1. R1 and R2 are complete: the exact Arduino toolchain/binary is frozen, the
   stronger real-hardware assertions pass, and plain BLE passed 10/10 cycles.
2. R3A through R9 are complete. Preserve the frozen R9 checkpoint.
3. R11 passed against the unchanged open R9 research contract. R10 standard BLE
   bonding remains optional and has not started; it does not invalidate that
   recorded R11 evidence.
4. Execute R12-R14: SQLite/local sessions, camera/fusion/model, then the research UI
   and optional asynchronous cloud sync.
5. Run R15 once as the final research checkpoint. Do not repeat 30-minute soaks for
   small changes and do not resume custom HMAC/HKDF/provisioning work unless the
   owner opens a new security objective.

### R12 — Canonical local sessions and SQLite ingestion

- **Status:** PASS (E0/E1/E3)
- **Dependencies:** R11 and M1-05
- **Scope:** one authoritative local session lifecycle, validated R11 IMU UDS
  ingestion, a five-second/250-sample bounded in-memory ring, and aggregate-only
  session IMU persistence through a bounded 256-item off-loop database worker.
  Camera, fusion, inference, HTTP/UI, cloud sync, and raw IMU retention are outside
  R12.
- **Acceptance:** start/stop are idempotent; only one active session can exist;
  start is durable before success; a controlled core restart restores the same
  active UUID and counters; storage failure leaves the session active/degraded and
  never falsely reports completion; wrong/simulated IMU fails closed; UDS frames
  are bounded and peer UID can be restricted; SQLite stores the aggregate summary
  but no raw 50 Hz samples. A short E3 run must prove that unchanged R11 hardware
  events reach this path and the completed summary is durable.
- **Rollback:** restore the pre-migration database backup and previous release.
  Migration 0003 is additive, but applying it to any existing database still
  requires the migration runner's backup gate.
- **Evidence:** 14 focused E0/E1 tests and the full 215-test suite pass. The final
  short E3 run accepted 507 real R11 MPU6500 events in 10.093 seconds at 50.134 Hz
  with zero gaps, duplicates, or rejected frames; SQLite quick-check passed and the
  completed summary retained no raw IMU samples. See
  `docs/evidence/R12-LOCAL-SESSIONS-20260828.md`.

### R13-A — Vision/model contract and migration baseline

- **Status:** PASS (V0, E0/E2)
- **Dependencies:** R12, M1-02, M1-03, M1-04
- **Scope:** trace and hash-freeze the active camera, pose, rep, IMU-consumer,
  feature, preprocessing, model, and persistence paths; record all confirmed
  divergences from canonical contracts; validate the compatibility model manifest
  and deterministic replay boundary; define the ordered R13-B through R13-G gates.
  Runtime migration, camera-owner selection, model execution, feature-semantic
  changes, firmware, Pi configuration, and UI redesign are outside R13-A.
- **Acceptance:** every current producer/consumer path is mapped; relevant source,
  model-manifest, and replay hashes are machine-verifiable; duplicate feature
  construction, mock/zero fallback, arrival-time fusion, camera lifecycle, live
  dispatch, dependency, and model-readiness blockers are explicit; canonical event,
  model, and replay tests pass; the full suite and `git diff --check` pass.
- **Rollback:** documentation and checkpoint validator can be reverted; runtime is
  unchanged. The live rollback point remains `ble-r12-local-sessions-pass`.
- **Evidence:** `docs/evidence/R13-A-VISION-MODEL-BASELINE-20260828.md` and
  `docs/evidence/r13a-baseline-manifest.json`. The V0 validator checks 20 source
  identities, all model artifacts/order/shape/threshold/readiness, and deterministic
  non-real replay. No hardware or person data is required for this characterization
  package.

### R13-B — Measurement-time alignment

- **Status:** PASS (E0/E3)
- **Dependencies:** R13-A
- **Scope:** make the R11 live event timestamp a measured R9 sensor-to-Pi monotonic
  mapping with explicit synchronization, drift, reset, gap, and stale states before
  camera fusion begins.
- **Acceptance:** deterministic wrap/reset/drift tests pass; live frames no longer
  equate arrival time with sensor capture time; quality fails closed when the clock
  is not usable; a focused E3 timing run records error percentiles and counters.
- **Rollback:** revert the isolated R13-B host changes to the tagged R13-A
  checkpoint. Arrival-only R11 diagnostics must remain outside fused scoring.
- **Evidence:** the host timestamps existing R9 status GATT reads, includes the
  ESP millisecond resolution in the error budget, and maps each wrapping packet
  timestamp into Pi monotonic time. Focused deterministic tests pass; the exact
  final candidate passed a short E3 run at 50.075418 Hz with 13.017092 ms estimated
  alignment-error p95 and zero measured correction/gate-drop/gap/queue-drop/error
  counters. Pre-sync samples were counted and withheld rather than published. No
  firmware or installed Pi service changed. See
  `docs/evidence/R13-B-MEASUREMENT-TIME-ALIGNMENT-20260829.md`.

### R13-C — Camera ownership and capture-timestamp spike

- **Status:** PARTIAL (E0/E3; provisional owner selected, person gate deferred)
- **Dependencies:** R13-B, ADR-014
- **Scope:** measure the accepted Picamera2 dual-stream and MediaMTX-owner candidates
  with a real person, then choose one camera owner and prove monotonic capture-time,
  restart, pose accuracy/FPS, CPU/RSS, temperature, and browser-video feasibility.
- **Acceptance:** one owner is selected from comparable E3 evidence; no second
  process contends for the camera; timestamps are captured near exposure rather
  than after pose processing; start/stop/restart is repeatable; missing person or
  camera is explicit; no final UI redesign is included.
- **Rollback:** retain the current migration camera path while it remains outside
  fused scoring; revert the isolated spike without touching R9/R11/R12.
- **Evidence:** Picamera2 passed 3/3 camera-owner restarts, provided 100% monotonic
  exposure-start timestamps, and published real 1280x720 H.264 through a MediaMTX
  WebRTC relay while retaining the 640x360 pose stream. MediaMTX camera ownership
  passed 3/3 restarts but RTSP provided only arrival time and consumed more measured
  CPU. The owner explicitly deferred the controlled full-body comparison because
  the available area could not provide valid framing; glass-to-glass observation is
  also pending. See `docs/evidence/R13-C-CAMERA-OWNERSHIP-20260831.md`.

## 15. Work-package handoff template

Use this in a PR, issue, or agent handoff:

```text
Package:
Scope completed:
Files changed:
Acceptance criteria:
Commands/tests and results:
Hardware used:
Mocks/replays used:
Performance/security evidence:
Data/schema impact:
Rollback:
Known limitations:
Plan/docs updated:
Git status (uncommitted/committed/pushed):
```
