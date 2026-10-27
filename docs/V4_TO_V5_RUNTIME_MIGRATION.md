# V4-to-V5 runtime migration inventory — 2026-09-28

**Purpose:** M5-00 inventory, not an activation or deletion. A source search
covered application code, configs, tests, manifests and current documentation
for `(4,40)`, `(3,38)`, `114`, `160`, V4 proxy names, delta construction,
V4 artifact names, V4 threshold, and RF paths. Historical evidence and
`models/` V4 files remain intact for reproducibility. Never select V4 as an
implicit fallback when V5 readiness fails.

M5-01 update: the isolated V5 artifact copy, portable three-phase transform and
offline FP32 runtime now pass their scoped checks. The legacy V4 application
entry points below are **not** migrated; see
`docs/V5_RASPBERRY_PI_INTEGRATION_REPORT.md`.

## Frozen differences that drive the migration

| Boundary | Existing compatibility behavior | Final Stage 8 V5 behavior |
|---|---|---|
| Inputs | One `(1,4,40)` tensor: three phases plus synthetic delta | Temporal float32 `(1,3,29)` **and** context float32 `(1,2)`; no delta |
| Features | Bar-velocity/power/jerk/deceleration proxies, anthropometrics and missingness indicators | Exact 29-feature registry; context `[Exercise_ID, Load_kg]`; no listed proxies, anthropometrics or explicit indicators |
| Preprocessing | V4 `.save` artifacts and independent feature calculations | Seven IMU winsor bounds, phase medians, separate temporal/context scaler, then model |
| Calibration/decision | Legacy threshold about 0.359 | Frozen Platt calibration, then `0.20549274582373653` threshold |
| Backend | V4 model file and legacy mock fallback | Built-ins-only batch-one V5 FP32 TFLite candidate; fail closed if unavailable |
| Output | Legacy cues/fields can imply specific errors | Binary historical bad-form probability only; no error-type diagnosis |

Source of truth: `/mnt/g/FYP/Datasets v2 Model v5/documentation/FEATURE_CONTRACT.md`,
`MODEL_CARD.md`, `V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md`, and the package
registries and policies. The source folder is read-only.

## Exact incompatible files and planned disposition

| Files | Current incompatibility | Planned action / gate |
|---|---|---|
| `models/manifest.json`, `models/model_quantized.tflite`, `models/model_fullprec.tflite`, `models/scaler.save`, `models/winsor_bounds.save`, `models/feature_medians.save`, `models/deployment_config.save`, `models/model_card.md`, `models/README.md` | Versioned V4 compatibility package (`digital-spotter-v4-compat`). | Retain unchanged as historical compatibility evidence; create sibling `models/digital_spotter_v5/` with independent copy manifest and explicit selection. |
| `src/digital_spotter/contracts/model.py` | `COMPATIBILITY_FEATURE_ORDER` contains proxy fields and V4 manifest rules. | Keep compatibility validator; add separate strict V5 manifest/shape/order validator, never reinterpret V4 as V5. |
| `config/config.py`, `config/constants.py` | Default paths are V4 `.tflite`/`.save`; `SEQUENCE_LENGTH_MODEL=4`, 40 fields, ~0.359 threshold. | Route canonical V5 path through typed, explicit versioned settings; leave legacy constants only for legacy mode. |
| `inference/feature_engineer.py` | Produces 40 fields, proxy values, zero defaults and old engineered formulas. | Do not reuse for V5; create one source-equivalent V5 builder and compare exact formulas/units to training code. |
| `inference/sequence_buffer.py` | Appends phase-3-minus-phase-1 fourth row and pads missing phase data. | V5 path accepts exactly three ordered real phase aggregates; reject incomplete reps. |
| `inference/preprocessor.py` | Loads V4 scaler/bounds/medians; can pass through mock/unscaled values. | V5 adapter must use frozen fitted Stage 8 state and fail closed; verify parity before activation. |
| `inference/lstm_runner.py` | One-input V4 model, V4 threshold, random mock fallback. | New two-input V5 built-ins TFLite loader with explicit raw/calibrated/threshold result and no mock result persistence. |
| `integration/session_manager.py`, `vision/rep_segmenter.py` | Legacy three-phase events feed V4 features/delta; no proven match to V5 training phase aggregation. | Define source-equivalent squat/deadlift phase contract, then route completed reps through canonical V5 builder. Keep manual/human gate pending. |
| `scripts/dashboard/main.py` | `/predict` assembles 40 features independently, adds delta, calls V4 runner and can fire feedback. | Remove direct feature/model math from active endpoint; delegate to canonical V5 service after readiness/quality/authorization gates. |
| `imu/esp32_bridge.py` | Legacy MQTT/mock IMU consumer used by legacy session path. | Do not connect V5 to this path; use the accepted R9 BLE event adapter and explicit quality state. |
| `api/routes.py`, `TEST DASBOARD/main.py` | Older development endpoints use dummy `(4,40)` or historical `(3,38)`/RF `(1,114)` contracts. | Keep quarantined as historical code; do not deploy or claim V5 coverage. Retire only through separately approved cleanup. |
| `scripts/validate_model.py` | Resolves V4 default model paths/messages. | Keep V4 compatibility check selectable; add a distinct V5 artifact/inference validator and copy-hash check. |
| `tests/contract/test_model_manifest.py`; `tests/test_03_inference/test_sequence_buffer.py`, `test_preprocessor.py`, `test_model_load.py`, `test_full_inference.py` | Assert V4 shapes, files, feature order and delta. | Preserve V4 regression coverage while adding strict `tests/test_v5_model_contract.py`; change active-path tests only with the runtime migration. |
| `ARCHITECTURE.md`, `docs/INTERFACES.md`, `docs/CURRENT_STATE.md` | Describe V4 `(4,40)` as current compatibility and forecast retraining; `RepEvent` has four named movement states. | During M5-01/M4-03, add versioned V5 wire/model contract and exact three-phase mapping; continue to label V4 as compatibility, not active V5. |
| `PLAN.md` | Earlier M5-02 directed new training/int8 export and item 7 postponed model readiness. | M5 now accepts immutable Stage 8 V5, proves offline parity first, then Pi backend and last-stage field validation. |
| `CHANGELOG.md` and old evidence documents | Historical V4 statements and measurements. | Do not rewrite history; retain as dated evidence with explicit V5 supersession in current docs. |

## Issues that cannot be solved by renaming fields

- V5 temporal inputs are phase **aggregates**. Existing per-frame pose and 50 Hz
  IMU events need source-equivalent phase boundaries, aggregation, camera–IMU
  alignment and quality handling. The current `RepEvent` enum's four names are
  not an automatic mapping to training phase IDs 1–3.
- The training package documents unverified V2 IMU units/provenance, especially
  gyro deg/s versus rad/s, while the accepted R9 adapter publishes rad/s.
  Establish the unit/mounting transform before real scoring; do not fabricate
  V5 values from the lower-back wearable.
- The package JSON does **not** contain temporal/context scaler mean/scale or
  Platt coefficients. Those fitted values live in trusted hash-verified joblib
  objects. M5-01 needs a controlled derived portable export and parity test;
  no joblib deserialization from arbitrary runtime/cloud input.
- The package has built-ins FP32/dynamic TFLite files with local parity only.
  Neither plain `tflite-runtime` on Pi nor end-to-end latency/thermal behavior
  has passed. INT8 and Flex are not needed/available as deployment choices now.
- A binary classifier supports a bad-form decision, not specific error names or
  medical/injury-prevention claims. The historical phase-3 target and 374
  inconsistent phase-label repetitions remain documented limitations.

## Activation rule

Keep the V4 compatibility package untouched and the V5 runtime inactive until
M5-01 hash/copy/preprocessing/model/calibration parity passes. Keep live V5
scoring disabled until M4 source-feature, phase, sync and real-sensor quality
gates pass. Preserve the owner-directed human-camera/mounted test as the last
validation stage. A failure must show a contract/unavailable state, never
silently fall back to V4, zeros, random predictions or mock analysis.
