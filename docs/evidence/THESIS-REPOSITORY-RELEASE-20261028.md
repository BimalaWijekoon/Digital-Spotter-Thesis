# Thesis repository release audit — 2026-10-28

## Purpose

This record describes the repository snapshot prepared for citation from the
Digital Spotter thesis. It is a research prototype snapshot, not a claim of
production readiness or clinical validation.

## Included

- Canonical Python product packages, tests, configuration, and deployment files.
- ESP32-C3 research firmware and the verified PCB1 checkpoint.
- The browser dashboard, locally vendored dependencies, and licensed exercise
  animation assets with their source and licence records.
- Research evidence and the anonymised field-testing workbook.
- The original read-only V5 integration package.
- The frozen `digital_spotter_v5_imu_synthetic_r1` candidate package needed to
  reproduce reference inference. Its manifest intentionally retains
  `deployment_ready=false`, `live_scoring_enabled=false`, and
  `real_world_validated=false`.
- The isolated V5 IMU retraining source, documentation, and verification tools.

## Excluded

- Virtual environments, dependency caches, Python bytecode, pytest caches, and
  Arduino temporary build output.
- The 26 generated model-fit directories, regenerated datasets, and other
  retraining output retained locally under the ignored training output tree.
- Local SQLite databases, session runtime state, credentials, and machine-local
  configuration.
- Six duplicate questionnaire backup workbooks; the final anonymised workbook is
  retained at
  `docs/evidence/Gym_Spotter_Final_Real_World_Testing_Questionnaire.xlsx`.

## Privacy, licence, and size audit

- A targeted scan found no private keys, GitHub tokens, AWS credentials, Google
  service-account keys, Firebase secrets, or real Wi-Fi credentials in the
  candidate working tree.
- The field workbook uses participant identifiers P01-P05 and contains no names.
- Third-party browser assets have adjacent licence/source records.
- No candidate file exceeds GitHub's 100 MB per-file limit. The largest included
  files are licensed exercise animation assets of approximately 6.2 MB each.
- Historical documentation records an old MQTT credential exposure in Git
  history. This snapshot does not rewrite history; owner-side credential
  revocation/rotation remains required if it was not already completed.

## Verification

| Check | Result |
|---|---|
| Python suite outside the restricted socket sandbox | 366 passed, 1 failed |
| Remaining Python failure | Spawned crash-isolation worker exceeded the test's fixed 10 s exit timeout; repeated once with the same result |
| Dashboard Node tests | 21/21 passed |
| V5 candidate reference validator | PASS_REFERENCE_INFERENCE |
| Candidate tensor contract | temporal `(1, 3, 29)`, context `(1, 2)` |
| Candidate TFLite/Keras parity | raw absolute error `5.96e-08`; calibrated absolute error `1.86e-08` |
| Research-appliance assembly | passed |
| Research-appliance SHA256 manifest | passed |
| Legacy `scripts/validate_model.py` | failed: historical Flex-op model cannot load in the LiteRT-only environment |
| `git diff --check` | recorded at commit time |

The Python timeout is not represented as a passing test. The legacy validator
failure is also retained explicitly; the committed candidate package uses the
separate built-in-ops validation path.

## Evidence limitations

- No Raspberry Pi, camera, BLE wearable, or PCB was exercised during this
  repository-cleanup operation.
- No new performance, thermal, timing, synchronization, or battery measurement
  was made during cleanup.
- Gym results in the final workbook are owner-reported summaries; the repository
  does not contain the raw per-frame probability or synchronization logs needed
  for independent replay.
- Synthetic/replay success must not be described as calibrated live scoring.

## Rollback

The release is a normal Git commit on `main`. The previous state remains
recoverable through its parent commit; ignored local training outputs and local
runtime data are not modified by the commit.
