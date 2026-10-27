# M5-R03 — final V5 LSTM-only retraining result

**Completed 2026-10-20. PASS for offline training and numerical export only.**
No real-world accuracy, physical mounting, Pi benchmark or deployment pass is
claimed. All changes are local/uncommitted; nothing was pushed or activated.

## Scope and artifacts

- Model version: `digital_spotter_v5_imu_synthetic_r1`.
- Run: `../outputs/main_v5_imu_r1_20261020/` relative to this report's directory;
  actual repository path is
  `training/v5_imu_retraining/outputs/main_v5_imu_r1_20261020/`.
- Dataset: `data/generated/imu_r1_20261020/`, **6,054 rows / 2,018 complete
  repetitions / 25 synthetic profiles**. All 56 non-IMU columns were preserved.
- Dataset SHA256:
  `934925aa40ad7e24e6f34ff12075d76d70d0a97ba1f200374508505323d620ff`.
- Training: **26 fits of one architecture**: 20 inner, five outer, one final.
  No RF, ablations, loss/hyperparameter searches or historical fitted states.
- Architecture: BiLSTM 64/32, BN/dropout, 2-head attention with key_dim16,
  residual/LayerNorm, GAP, context Dense16, Dense64/32, sigmoid. **105,681
  parameters**; inputs `(1,3,29)` and `(1,2)`, no delta/bar-proxy inputs.
- Final fit: **12 epochs**, round-half-up median of 20 inner best epochs.
  Summed measured fit wall time: **891.619 seconds**; excludes startup and
  between-fit work, so is not total end-to-end runtime.

`package/` contains Keras, one built-in FP32 TFLite, portable preprocessing,
calibration, threshold, fixtures/parity, training/config/source metadata,
simulation contract, model manifest and SHA256 list. `source_snapshot/`
preserves the exact local generator/training/export source and dependency pins.

| Artifact | Size | SHA256 |
| --- | ---: | --- |
| `package/model.keras` | 1,393,067 bytes | `ff7088943ea9797e84e321523b6a09665de2bb5bbab07f87f74fa5b6bfb78465` |
| `package/model_fp32_builtins_batch1.tflite` | 497,416 bytes | `c3da4c5b03461e2e2ecceadfd4081f921777676b4342e87f0153558af71a941c` |

## Retained training procedure

Five outer and four inner stratified profile-grouped folds; each inner job has
12 fitting, three independent early-stopping monitor and five validation
profiles. The focused test-first check caught the missing internal-monitor
separation in the prepared adapter; it was corrected **before any fit**.
Preprocessing uses only fitting profiles: phase medians, seven IMU 3-IQR bounds,
separate temporal/context StandardScalers. Adam .0003, plain BCE, batch32,
shuffle disabled, max60, patience8, min_delta .0001, absolute-best checkpoint.
Fresh grouped cross-calibration and development-only threshold choice precede
fixed-epoch outer evaluation. See `TRAINING_PROCEDURE.md` for source references.

## Actual held-out synthetic-profile evaluation

These are pooled outer OOF results with development-derived calibration and
thresholds, not in-sample final-model accuracy or results on measured people.

| Outer fold | Repetitions | Accuracy | Bad-form F1 |
| --- | ---: | ---: | ---: |
| 1 | 400 | 85.25% | 0.8078 |
| 2 | 407 | 85.50% | 0.8139 |
| 3 | 409 | 88.02% | 0.8555 |
| 4 | 413 | 83.78% | 0.7976 |
| 5 | 389 | 84.83% | 0.8013 |

Pooled: accuracy **85.4807%**, balanced accuracy **84.2494%**, F1 **0.815839**,
ROC AUC **0.886581**, PR AUC **0.860392**, bad-form recall **76.5330%**,
precision **87.3486%**, Brier **0.118318**. Confusion matrix, rows true / columns
predicted `[0,1]`: `[[1076,94],[199,649]]`. Positive class is historical bad-form
`Class_Binary=1` at phase 3.

Final Platt calibration acts on raw sigmoid probability: coefficient
`5.021459685155982`, intercept `-2.214216586475489`. Final threshold is
**0.3976007923801824**, with class 1 for calibrated probability >= threshold.
The global calibrator/threshold was fitted on outer OOF labels for finalization;
those refit statistics are **not** another independent evaluation. Transfer of
this calibration to the all-data model remains unverified.

## Focused checks actually run

- Five training unit checks: **PASS**, 0.161 seconds, using the existing PC
  training interpreter. Exact features/formulas, frozen preprocessing, grouped
  coverage, independent monitor, calibration/threshold. No full app/hardware suite.
- Every actual fit passed the 105,681-parameter and two-input shape assertions.
- Rebuilt serialized preprocessing fixture: **exact match**.
- Keras save/reload: **2,018/2,018**, maximum probability difference **0**.
- One FP32 TFLite export: built-in ops only; **no Flex/custom operators**.
- TFLite parity: **64 evenly spaced repetitions**, max raw probability error
  `2.086162567138672e-07`, calibrated error `2.4867203052281184e-07`, **zero
  class mismatches**; both below the fixed 1e-4 acceptance limit.
- Host TFLite invocation median **0.68695 ms**, maximum **8.71820 ms** over
  those 64 calls, including first invocation. This is **not a Pi benchmark**.
- Integrity: **37/37 reference copies**, **37/37 corresponding originals**,
  **67/67 original V5 package listed files**, **24/24 existing runtime model
  copied artifacts** match their recorded hashes. No original model changed.
- Final package SHA256 manifest and final source-contract checks: PASS.
- `git diff --check` for the touched tracked documents: PASS.

Training environment reused read-only: Python **3.12.13**, TensorFlow **2.21.0**,
Keras **3.13.2**, NumPy **2.4.4**, scikit-learn **1.8.0**, WSL2 x86-64 CPU.
No packages installed, runtime venv modified, hardware accessed, Pi rebooted,
firmware flashed, credentials rotated or security/data migration performed.

## Remaining limits and next integration gate

- The data remains synthetic. Motion/noise/mounting assumptions were not
  calibrated from measured lower-back recordings; synthetic CV is not evidence
  of real-world form accuracy, safety or clinical validity.
- **374 phase-label-inconsistent repetitions** retain the historical phase-3
  target. Labels were not silently repaired. All vision values remain unchanged;
  the existing synthetic vision is not independently validated by this work.
- Units are explicit m/s² specific force / rad/s; virtual X-forward/Y-left/Z-up
  and phase medians must be matched by the actual mounted live pipeline.
  Physical rotation, phase semantics and synchronized feature equivalence remain
  unverified; 104 missing trunk summaries used generator-only documented priors.
- Runtime activation requires a separate version-aware adapter/integration step;
  the existing V5 adapter must not silently consume this new preprocessing state.
  No live scoring flags or current `models/` paths were changed.
- Next: integrate this isolated candidate deliberately, verify Pi execution and
  actual mounted/synchronized features, then evaluate independently labelled real
  repetitions when available. Do not retrain again merely to improve this score.

Rollback is unchanged: keep using the existing runtime package; this candidate
is inactive. Hardware, UI, networking and existing source/evidence were preserved.

## Files changed in this training step

Added `v5_training.py`, `export_v5.py`, `requirements-training.txt`,
`tests/test_v5_training.py`, `docs/TRAINING_PROCEDURE.md` and this report.
Updated the local recipe, README/STATE and generation-report follow-up, plus
root `PLAN.md`, `docs/CURRENT_STATE.md`, `docs/DECISIONS.md` and
`docs/TEST_STRATEGY.md`. Unrelated pre-existing worktree changes were preserved.
Generated models, datasets, caches and per-fit checkpoints remain Git-ignored.

For the thesis repository snapshot, only the frozen final package is published
at `models/digital_spotter_v5_imu_synthetic_r1/`. Its files are byte-identical
to the package described above. Copied datasets, fold models, weights,
predictions, caches and the remainder of the 67 MB training run remain excluded.
