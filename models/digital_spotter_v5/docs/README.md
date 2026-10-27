# Digital Spotter V5 Final Model Package

This is a copy-only, human-readable archive of the finalized V5 research and Stage 8 deployment artifacts. The authoritative working evidence remains in the original `Datasets v2/` and `outputs/v5/` locations; this folder does not replace or modify them. File hashes and original paths are listed in [documentation/PACKAGE_SHA256.csv](documentation/PACKAGE_SHA256.csv).

## Final model

**SCOPE_FAITHFUL**: multimodal Vision + lower-back IMU → two-layer BiLSTM → two-head Multi-Head Attention → form classifier. It takes **three real phases**, **29 temporal features per phase**, and **two repetition-level context fields** (`Exercise_ID`, `Load_kg`). The Keras model has **105,681 parameters**. Exact ordered inputs and preprocessing are in [FEATURE_CONTRACT.md](documentation/FEATURE_CONTRACT.md) and [saved_models/preprocessing](saved_models/preprocessing/).

The model retains Vision+IMU fusion, the BiLSTM, attention, and engineered hip/knee/ankle asymmetry. Retention of attention/asymmetry preserves the intended research representation: Stage 7D found the scope-faithful candidate within its predeclared practical-equivalence margins, **not** that those components uniquely improve prediction or provide causal explanations. See [Stage 7D confirmation](documentation/V5_STAGE7D_SCOPE_PRESERVING_CONFIRMATION_REPORT.md).

Removed from the V4 representation: the synthetic fourth delta timestep; unresolved `V_Bar_Velocity_Vertical`, `P_Bar_Power_Watts`, `Smoothness_Jerk`, and `Velocity_Decel_Ratio` proxies; anthropometric inputs; and explicit missingness indicators. There is no delta branch. The physical bar-motion provenance of the removed proxies remains unresolved; their original columns were not renamed or altered.

## Research evaluation

The selected Scope-Faithful model was evaluated with **five participant-held-out outer folds**, repeated with seeds 42, 43, and 44. Each seed yields one out-of-fold prediction per 2,018 repetitions. Its three-seed mean pooled OOF F1 was **0.921673 ± 0.001933**, bad-form recall **0.913522 ± 0.002968**, and PR-AUC **0.918418 ± 0.001698** ([results/scope_confirmation.csv](results/scope_confirmation.csv), [per-seed table](results/final_oof_metrics.csv)). The `final_confusion_matrix.csv` is specifically **seed 42**, not a three-seed aggregate. Stage 8 loss-selection OOF and global calibrator/threshold fit-data scores are deployment decisions and **must not replace** this research estimate. The final all-data Keras model has no independent held-out performance estimate because all available repetitions were used to train it.

The [modality ablation](results/modality_ablation.csv) is Stage 7B evidence from a different feature/architecture contract, not a fresh ablation of the exact final Stage 8 model. Its `FULL_FUSED` condition includes unresolved proxy fields, so use it as historical V5 development evidence rather than a clean proof that the final fusion contract beats both unimodal alternatives. The separate ICAC session-split experiment is not included here.

## Source data and target limitation

The final V5 feature construction reads `master_dataset.csv` and `subject_meta.csv`; `vision_data.csv` and `imu_data.csv` are copied as immutable upstream provenance. **`preprocessed_dataset.csv` is included only because the final notebook's historical V4 artifact-replay cell reads it** (`outputs/v5/v5_stage1_6_pipeline.py:v4_reproduction`). It is a historical V4-derived artifact, **not** the final V5 training input. The notebook also imports V5 pipeline modules from the original `outputs/v5/` tree and its V4 replay needs V4 saved artifacts in `Datasets v2/`; this clean archive alone is not a fully executable training environment. No such experimental checkpoints or V4 models were copied here.

Of 2,018 repetitions, **374** contain inconsistent phase-level `Class_Binary` values. The historical terminal-phase (phase-3) rule is retained as `V5_REPRO_TARGET` for continuity; no label was reconstructed, majority-voted, or repaired. This is a research-label limitation, not corrected ground truth.

## Deployment status

The all-data Keras model was trained and packaged. Built-ins-only FP32 and dynamic-range TFLite files were converted and passed local Keras/TFLite parity on 64 deterministic processed training repetitions. There is **no successful INT8 file**. The package's joblib preprocessor depends on the original V5 Python module and is not a standalone Raspberry Pi runtime. Plain `tflite-runtime` loading on the Pi, camera–IMU integration/synchronization, and hardware latency/CPU/memory/thermal benchmarks are **pending**. Conversion/parity does not prove live deployment. See [TFLITE_STATUS.md](saved_models/tflite/TFLITE_STATUS.md), [model card](documentation/MODEL_CARD.md), and the [Stage 8 final report](documentation/V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md).

## Folder guide

- `saved_models/`: the one final Keras model, exact preprocessing/calibration/threshold policies, and only the two valid local TFLite candidates.
- `results/`: curated, source-traceable final research/deployment tables; no per-fold model checkpoints.
- `visualizations/`: figures backed by tables in `results/` or the frozen architecture contract. Captions and exact sources are in [FIGURE_SOURCES.md](documentation/FIGURE_SOURCES.md).
- `documentation/`: feature contract, model card, final decision reports, figure provenance, hashes, and contents report.

**Stop point:** packaging only. No Raspberry Pi integration or hardware claim was made in this task.
