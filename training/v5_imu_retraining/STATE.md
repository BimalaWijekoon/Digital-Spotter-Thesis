# Progress

Work packages: **M5-R01 reference preparation PASS; M5-R02 generator PASS**.
**M5-R03 PASS for offline LSTM-only CV training and numerical export.**
No training job is running. The model is staged on the Pi, but not activated.

M5-R04 local integration is also complete: the runtime can explicitly load this
package reference-only, with its own preprocessing/calibration/threshold and
correct session version. Nine model/package checks and four session checks
passed; no TensorFlow or training import in the runtime. The Pi stayed offline.
See `../../docs/evidence/M5-R04-LOCAL-CANDIDATE-RUNTIME-20261020.md` from this
folder (repository `docs/evidence/`). Next is deliberate Pi deployment and
mounted-feature verification, not another training run.

M5-R05 side-by-side Pi staging and one inference are complete:
`~/digital-spotter-v5-imu-r1-20261020.E7L664/`, 107 verified transferred files,
Pi/PC reference probabilities identical, no TensorFlow import or package upgrade.
No UI/service or live scoring was enabled. Next: controlled launcher/producer
integration and physical mounted-feature verification. See repository
`docs/evidence/M5-R05-PI-CANDIDATE-STAGING-20261020.md`.

| Step | Status |
| --- | --- |
| Inventory source files and verify listed package hashes | PASS |
| Copy required data/contracts/training references without modifying sources | PASS |
| Verify all copied files and original hashes | PASS: 37/37 copies and originals |
| Review owner-pasted v5.1 generator | COMPLETE; not accepted as corrected generator |
| Define simulation frame, physical model and phase reducer | DONE for explicit synthetic assumptions; actual mounting unverified |
| Implement IMU-only regeneration | PASS: five focused tests |
| Generate replacement IMU dataset with unchanged vision/labels | PASS: 6,054 rows; zero protected-cell changes |
| Choose evaluation procedure | Original grouped CV; final V5 LSTM architecture only |
| Prepare isolated training dependencies and adapted final V5 entry point | PASS; five focused tests, existing PC interpreter, no package changes |
| Fit new preprocessing, model, calibrator and threshold | PASS; all 26 main-architecture fits, final 12 epochs |
| Export and evaluate a new model revision | PASS offline; Keras reload exact, built-in FP32 TFLite parity |
| Validate on actual mounted, synchronized measurements | DEFERRED; recording unavailable |

M5-R01–03 changed no frozen source model, runtime, firmware, Pi, network or
active environment. M5-R04 adds only the opt-in reference runtime described
above. Deployment/mounting validation remains separate, not another training
sweep. See `docs/TRAINING_REPORT.md`.
Do not execute the archived generator/notebook unchanged. Only the main final V5
architecture may be trained. There are 20 inner fits, five outer fits and one
final fit. Internal epoch monitoring is separate from validation prediction.

Run: `outputs/main_v5_imu_r1_20261020/`.
Log: `outputs/main_v5_imu_r1_20261020-training.log`.
The exact dataset/config/source hashes are bound in `RUN_CONTRACT.json`.

Final status: `COMPLETE_OFFLINE_SYNTHETIC_CANDIDATE`. Pooled synthetic-profile
outer OOF accuracy 85.4807%, F1 0.815839, ROC AUC 0.886581. No real-world accuracy
claim. Model: `package/model_fp32_builtins_batch1.tflite`, 497,416 bytes, SHA256
`c3da4c5b03461e2e2ecceadfd4081f921777676b4342e87f0153558af71a941c`.
No Flex, maximum raw export difference 2.0862e-7, zero class mismatches on 64
deterministic parity samples. Final threshold 0.3976007923801824 is new.

All 67 listed original V5 package files and 24 listed existing runtime model
artifacts still match recorded hashes. Changes remain local/uncommitted.

Candidate: `data/generated/imu_r1_20261020/`. See
`docs/IMU_GENERATION_REPORT.md` for hashes, exact checks, 104 missing trunk
summaries handled as priors, inherited label contradictions and limitations.

## Copy-verification result

On 2026-10-20:

```text
python3 training/v5_imu_retraining/scripts/verify_copy.py --check-source
PASS: 37/37 copied files match SHA256 and size
PASS: 37/37 original source hashes unchanged
PASS: baseline has 6,054 rows / 2,018 complete [1, 2, 3] repetitions
```

Listed source-package assets matched the original package hash manifest during
preflight. `git diff --check` passed. Git-ignore checks confirmed that copied
references and future data/output paths are excluded from normal staging.

For the thesis repository snapshot, the final 1.9 MB package only is published
at `models/digital_spotter_v5_imu_synthetic_r1/`. Copied datasets, all 26 fit
directories, caches and the full generated run remain ignored. Publishing the
package does not change its manifest flags: deployment readiness, live scoring
and real-world validation remain false.
No training imports, dependency installation, network calls, real hardware,
performance measurements, security/data migration, commit or push were performed.
Changes remain local and uncommitted.
