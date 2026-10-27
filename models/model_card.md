# Digital Spotter v4 compatibility model card

**Status:** Compatibility/parity artifact only; not approved for product scoring
**Manifest version:** 1
**Artifact introduction:** Git commit `9646772`, 2026-06-22
**Reviewed:** 2026-08-26

## Intended use

This binary classifier is retained to reproduce and measure the current prototype
while the feature, sensor, data, and runtime contracts are corrected. It accepts a
float32 `(1, 4, 40)` tensor and emits one float32 sigmoid value interpreted by the
prototype as probability of bad form. The artifact threshold is
`0.35947465896606445`.

It is not approved for medical, injury-prevention, autonomous equipment control,
or user-facing product claims. A successful load or prediction is not accuracy
evidence.

## Input construction

The first three rows represent the prototype's eccentric/descent,
isometric/bottom, and concentric/lockout phase snapshots. The fourth row is phase 3
minus phase 1. The prototype may overwrite the delta row's
`Velocity_Decel_Ratio` with a cross-phase value. The exact ordered features and
units/unknowns are frozen in `manifest.json`.

Preprocessing order is:

1. winsorize the seven saved IMU features;
2. impute NaN values from saved feature medians;
3. apply the saved 40-column `StandardScaler`;
4. add the batch dimension and invoke the TFLite model.

The current prototype does not reliably represent missing modalities as NaN: parts
of its feature builder use zero defaults. Product inference must reject missing or
stale required data instead of depending on that behavior.

## Known provenance

- The repository describes the files as a training-notebook export.
- The scaler records 40 input features and `n_samples_seen_=5652`.
- No training notebook, immutable dataset manifest, group-safe split definition,
  subject/exercise distribution, consent record, sealed-test results, confusion
  matrix, subgroup analysis, or threshold rationale is present in this repository.
- Accuracy, precision, recall, false-alert rate, and calibration are therefore
  unknown and must not be inferred from the artifact name or threshold.

## Critical limitations

- The accepted physical sensor is an MPU6500 (`WHO_AM_I=0x70`) in a lower-back
  wearable. Features
  named bar velocity and bar power are not directly observed at that location and
  have no validated derivation in the repository.
- The saved accelerometer medians/bounds are centered around gravity near `9.8`,
  which is consistent with metres per second squared. The current ESP32 firmware
  divides raw MPU6500 acceleration by `16384` under the provisional +/-2 g profile,
  producing values in `g`, while the Pi
  bridge does not convert them. This is a confirmed implementation/contract
  mismatch; live product scoring is prohibited until the training unit is proven
  and the sensor path is converted/versioned accordingly. No traceable evidence in
  this repository establishes that the saved model was trained for MPU6500.
- Gyroscope features appear compatible with degrees per second, but training
  provenance is absent, so this remains unverified.
- Camera coordinate orientation, mirroring, subject population, supported exercise
  set, load range, mounting orientation, and calibration are not evidenced.
- Missing artifacts currently trigger random/mock behavior in the prototype. Mock
  predictions are forbidden for persisted or user-facing product analysis.
- The so-called quantized model still has float32 input/output and Flex
  `TensorList` operators. On the audited Pi it required TensorFlow 2.16.2 preloaded
  with AI Edge LiteRT 2.1.5, adding substantial memory and deployment cost.
- A no-person Pi benchmark cannot measure accuracy. It observed only 4 percent
  pose-found frames and 3.04 effective pose FPS; those are pipeline constraints,
  not model quality results.

## Promotion requirements

Do not promote this package to product scoring. M5 requires traceable data/splits,
mount-appropriate features, representative evaluation, threshold calibration,
sealed-test and subgroup evidence, built-in LiteRT operators, real-Pi latency/RSS,
person-in-frame pose parity, real lower-back IMU validation, and a signed immutable
package. Until then, production readiness must fail closed.
