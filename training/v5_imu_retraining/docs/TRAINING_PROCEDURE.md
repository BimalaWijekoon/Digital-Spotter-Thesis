# M5-R03 — final V5 LSTM-only training procedure

Owner-selected scope: original subject-grouped cross-validation, only the final
V5 architecture. No RF, ablations, alternative losses, parameter search or
automatic deployment. Reference scripts are read, never imported or executed.

## Retained methods and reference evidence

| Method | New implementation | Historical reference |
| --- | --- | --- |
| Exact 29 temporal features / 2 context / 3 phases | `v5_training.py:phase_features`, immutable copied registry | `reference/v5_package/documentation/FEATURE_CONTRACT.md` |
| Five outer / four inner stratified profile-grouped folds | `grouped_folds` | `reference/pipeline/v5_stage1_6_pipeline.py` |
| Separate 12-fit / 3-monitor / 5-validation profiles in each inner job | `monitor_split`, `_fit` | `reference/pipeline/v5_stage8_gate3.py:monitor_split`, `fit_one` |
| Train-only phase medians, seven IMU 3-IQR bounds, separate StandardScalers | `Preprocessor` | `reference/pipeline/v5_stage1_6_pipeline.py:FoldPreprocessor` |
| BiLSTM 64, BN, dropout .25, BiLSTM 32, dropout .20, MHA 2×16, residual/LN, GAP, context Dense16, Dense64/32, sigmoid | `build_model` | `reference/pipeline/v5_stage7c_pipeline.py:build_model`; final Stage 8 specification |
| Adam .0003, BCE, batch32, no shuffle, max60, monitor-loss patience8 / min_delta .0001, absolute-best checkpoint | `_fit`, `config/training_plan.json` | `reference/pipeline/v5_stage7a_pipeline.py`; `v5_stage8_gate3.py:fit_one` |
| Cross-fitted raw-probability Platt / identity decision by .001 Brier improvement | `cross_calibrate` | `reference/pipeline/v5_stage8_gate3.py:crossfit_calibration` |
| Max-F1 threshold; ties closest to .5, then lower | `choose_threshold` | `reference/pipeline/v5_stage1_6_pipeline.py` |
| Round-half-up median inner best epochs for fixed outer/final fits | `run_cv` | `reference/pipeline/v5_stage8_gate3.py:epoch_policy` |
| Final all-data fit and OOF-fitted Platt/threshold | `run_cv` | `reference/pipeline/v5_stage8_gate4.py` |
| Fixed batch1, frozen weights, built-in FP32 TFLite | `export_v5.py` | `reference/pipeline/v5_stage8_gate5_frozen_weights.py`; fixed signature reference |

Training-only imputation retains the historical raw-training-median then IMU
clipping order. Runtime adapters must consume the new serialized state, not
refit it. No unused delta scaler or model branch is introduced. The archival
loss/feature/architecture searches are not rerun; final plain BCE is fixed.

## Leakage boundaries

Each complete repetition is a single sample; three rows never become three
independent examples. Target remains phase-3 `Class_Binary` without relabeling.
All sessions of one synthetic profile stay together. Each inner model fits
preprocessing and weights on 12 profiles; three disjoint profiles control
stopping; five other profiles supply validation predictions only. Outer test
profiles influence neither preprocessing, stopping, calibration nor threshold.

Inner cross-fitted Platt probabilities are used for development policy choice.
Outer metrics use only held-out outer predictions and development-derived
policies. Pooled outer OOF metrics are the reported evaluation. The final
global Platt/threshold uses the outer OOF labels; statistics from that refit
are not reported as a second independent test. Transfer of calibration from
OOF fits to the all-data model remains unverified, as with the original method.

## Evidence and interruption handling

`RUN_CONTRACT.json` binds dataset manifest/hash, exact source and feature
registry hashes, recipe, target and provenance. `fold_manifest.csv` records
every fit/monitor/validation/test assignment. Each fit saves its history,
fresh preprocessing, best model, predictions and `COMPLETE.json` hashes.
Only exact matching complete fits can be resumed. A run lock prevents concurrent
writers. Partial fits are preserved rather than silently treated as complete.

`TRAINING_RESULT.json` holds outer metrics. `package/` contains the final Keras,
portable preprocessing, calibration, threshold, fixed fixture, model manifest,
FP32 TFLite, numerical export report and SHA256 list. Successful export does not
set deployment readiness or update the Pi/runtime's model paths.

## Focused acceptance

Five small tests cover exact features/formulas, frozen preprocessing roundtrip,
grouped fold coverage, stopping-monitor separation and calibration/threshold.
The real training run checks 105,681 parameters and both signatures on every
fit. Export compares reloaded Keras on all 2,018 repetitions, preprocessing
fixture roundtrip, and TFLite on 64 deterministic, evenly spaced repetitions.
Required export tolerance: max raw/calibrated probability error ≤1e-4 and zero
class mismatches. No hardware, RF, endurance or broad application test matrix.

## Scope limits

All 25 profile IDs are synthetic. The 6,054 rows / 2,018 repetitions retain 374
phase-inconsistent historical targets, preserved vision/context and 104 trunk
summaries reconstructed only inside the generator. The new IMU motion, frame
and noise are explicit but unmeasured priors. These metrics cannot establish
generalization to real people, biomechanical truth, safety or clinical utility.
No live camera/IMU validation, Pi benchmark, firmware change, credential change
or runtime activation is included. Keep existing model artifacts as rollback.
