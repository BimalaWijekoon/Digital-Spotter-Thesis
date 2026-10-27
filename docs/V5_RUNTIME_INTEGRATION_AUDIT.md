# V5 runtime integration audit — 2026-09-28

**Scope:** M5-00, read-only source intake and Pi-workspace audit. No V5 files
were copied, no runtime code was changed, and no Pi/ESP or person test was run.
This is a dated M5-00 snapshot; the subsequent M5-01 offline implementation is
recorded in `docs/V5_RASPBERRY_PI_INTEGRATION_REPORT.md`.
`READY` below means a subsystem foundation exists, **not** that V5 live scoring
is ready. The source model package is owned by the training workspace and must
remain read-only.

## Source acceptance and frozen target

- Located source: `/mnt/g/FYP/Datasets v2 Model v5/`. The six required intake
  documents are present: root `README.md`, `documentation/FEATURE_CONTRACT.md`,
  `MODEL_CARD.md`, `V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md`,
  `PACKAGE_SHA256.csv`, and `PACKAGE_CONTENTS.md`.
- `PACKAGE_SHA256.csv` covers 67 files (the manifest excludes itself); all 67
  matched their SHA-256 entries with `sha256sum --check --status` on 2026-09-28.
  The source package was not changed. This proves file integrity against the
  package manifest, not training provenance or Pi compatibility.
- Target: `digital_spotter_v5_scope_faithful`, three real phase aggregates in
  order 1, 2, 3; temporal float32 `(1,3,29)` and context float32 `(1,2)` with
  `[Exercise_ID, Load_kg]`. The exact temporal order is the source
  `documentation/FEATURE_CONTRACT.md` and machine-readable registry. The
  historical phase-3 `Class_Binary=1` is *bad form*, not an error subtype.
- Frozen Stage 8 decision: Platt calibration then threshold
  `0.20549274582373653`; do not reuse V4's threshold. The all-data Keras model
  has 105,681 parameters, but no independent held-out estimate. The Stage 7D
  participant-held-out estimate and Stage 8 fit-data figures must not be
  conflated (`documentation/MODEL_CARD.md`).
- Preferred reference backend: built-ins-only batch-one FP32 TFLite,
  `saved_models/tflite/final_v5_fp32_builtins_frozen_batch1.tflite`, 502,744 B,
  SHA-256 `8a1d308c2596e571b2840673c1b437bbd2ccdbef5c590ebdb6dbbd40a7a4f9ab`.
  Dynamic-range built-ins is a later comparison. Both passed local parity on
  **64 processed training repetitions**; neither has run under plain
  `tflite-runtime` on the Pi. No INT8 file exists
  (`saved_models/tflite/TFLITE_STATUS.md`).

## Current Pi-workspace subsystem map

| Subsystem | State | Evidence and V5 gap |
|---|---|---|
| Camera ingestion / WebRTC | READY foundation | Canonical Picamera2/MediaPipe worker exists in `src/digital_spotter/vision/runtime.py:115-150`; browser H.264 playback passed a bounded real-Pi check (`docs/evidence/M3-04-CUSTOM-VIEWER-20260915.md`). No person-in-frame V5 feature evidence. |
| Pose extraction | NEEDS_UPDATE | Canonical `PoseSample` construction is in `src/digital_spotter/vision/pose_events.py:51-98`; no three-phase V5 landmark/angle aggregation or source-coordinate parity. |
| IMU/BLE receiver | READY transport; BLOCKED model eligibility | R9 parser/agent/runtime are in `src/digital_spotter/imu/r9_protocol.py`, `r9_agent.py:241-289`, `r9_runtime.py`. A 501-sample ~50 Hz real check is recorded in `docs/evidence/R9-RECHECK-20260915.md`. Samples are explicitly `IMU_DEGRADED` pending calibration; V5 source gyro units/provenance remain unverified. Do not repeat BLE bring-up for this audit. |
| Camera–IMU synchronization | NEEDS_UPDATE | Sensor-to-Pi clock mapping exists in `src/digital_spotter/imu/clock.py`; no canonical pose/IMU association or three-phase sync window exists in `src/digital_spotter/sync/` (only `__init__.py`). No measured alignment quality. |
| Rep and phase construction | NEEDS_UPDATE | Legacy `vision/rep_segmenter.py:76-81,289-304` emits three phase IDs, while the target `RepEvent` allows eccentric/bottom/concentric/lockout (`docs/INTERFACES.md:467-475`). Neither establishes the training dataset's exact phase-boundary and aggregation rules for squat/deadlift. |
| Feature engineering / preprocessing | NEEDS_UPDATE | Legacy `inference/feature_engineer.py` constructs 40 V4 fields and zero defaults; `inference/sequence_buffer.py:103-129` appends a synthetic delta. `src/digital_spotter/inference/` has no V5 implementation. All 29 ordered values and both context inputs must be built once and fail closed on unavailable data. |
| Model loader / calibration | NEEDS_UPDATE | `models/manifest.json` is `digital-spotter-v4-compat`; `inference/lstm_runner.py:89-180` loads V4 paths or mock inference. No V5 TFLite/Platt/threshold runtime exists. |
| Feedback and wearable cues | NEEDS_UPDATE | Legacy `/predict` in `scripts/dashboard/main.py:692-835` triggers cues from its own V4 path. Model-derived cues remain disabled in the canonical path. V5 is binary, so it cannot justify named error-category feedback. |
| API/dashboard | NEEDS_UPDATE | Active `scripts/run_server.py` launches the legacy dashboard; `scripts/dashboard/main.py:692-835` independently engineers V4 input. Browser research viewer is isolated and does not expose a V5 result. |
| Persistence/logging | READY foundation; NEEDS_UPDATE wiring | Atomic completed-rep/analysis/outbox transaction exists in `src/digital_spotter/persistence/repository.py:465-615`; `src/digital_spotter/core/sessions.py` owns an IMU-only local session. No live completed V5 rep invokes the transaction; structured V5 timing/sync/calibration diagnostics are absent. |
| Services/configuration | NEEDS_UPDATE | `scripts/digital-spotter.service` launches legacy dashboard; `scripts/ds-imu.service` targets R9 agent. Neither installs/selects a verified V5 package. `deploy/digital-spotter.example.toml` currently covers video publication only. |

## Critical contract and portability findings

1. The source `saved_models/preprocessing/final_preprocessing.json` contains the
   feature/phase order, seven IMU winsor bounds, phase/context medians, and fit
   shapes, **but no `StandardScaler` mean/scale arrays**. The frozen scaler state
   is in `final_preprocessor.joblib`. Likewise the calibration policy JSON names
   Platt but contains no coefficient/intercept; those are in
   `final_calibrator.joblib`. The handoff prompt's statement that JSON alone
   contains *all* fitted states is inaccurate. M5-01 must export portable numeric
   state from the trusted, hash-verified joblib files in a controlled offline
   environment, then prove parity. Do not unpickle untrusted runtime input
   (`docs/SECURITY.md:268-269`).
2. The 29 input features are phase **aggregates**, not per-frame windows. Live
   acquisition alone is insufficient. Phase detection, aggregation statistic,
   landmark coordinate convention, engineered asymmetry/coupling formulas, and
   missing/occluded values need source-equivalent fixtures before scoring.
3. The package warns that source V2 IMU acceleration provenance and gyro units
   are unverified (`documentation/FEATURE_CONTRACT.md:31-37`). R9 publishes
   `acceleration_m_s2` and `angular_velocity_rad_s` in
   `src/digital_spotter/contracts/events.py:127-128`; matching field names is
   not evidence that the training values used those units or mounting axes.
4. `Exercise_ID` codes 0=Squat, 1=Deadlift and `Load_kg` are required, real
   repetition-level inputs. No default, guessed load, or zero-filled IMU may
   silently pass the live V5 quality gate.
5. Stage 8 used all 2,018 repetitions to fit the final model; 374 have
   inconsistent phase-level labels. The final model's calibration transfer and
   field false-alert rate remain unvalidated. No injury-prevention or
   error-type claim follows from its binary output.

## M5-01 entry gate and stop rule

Next, copy only final deployment artifacts into a versioned directory beside
the existing `models/` compatibility package, with a per-file copy manifest.
Create one canonical adapter under `src/digital_spotter/inference/`, not a
parallel implementation in the dashboard. Export missing numeric scaler/Platt
state without modifying source; use provenance-recorded, consent-safe fixtures
for exact order, preprocessing, raw probability, calibration and threshold
parity. Training-sample parity is a numerical check, **not** held-out accuracy.
Keep V5 inactive if any hash, feature, state export or parity gate fails.

No artifacts were copied; no offline model execution, real Pi TFLite load,
camera-person feature check, live fusion, or human/mounted test occurred in M5-00.
