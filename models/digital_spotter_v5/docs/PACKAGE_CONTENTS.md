# Final package contents

Total size: **9,116,655 bytes** (9.117 decimal MB).
Files: **68**, including this report and the hash manifest.

## Directory tree and purpose

```text
Datasets v2 Model v5/
├── saved_models/
│   └── calibration/final_calibration_policy.json
│   └── calibration/final_calibrator.joblib
│   └── config_hash.json
│   └── final_epoch_policy.json
│   └── final_v5_scope_faithful_bilstm_mha.keras
│   └── loss_policy.json
│   └── preprocessing/context_feature_registry.csv
│   └── preprocessing/final_preprocessing.json
│   └── preprocessing/final_preprocessor.joblib
│   └── preprocessing/temporal_feature_registry.csv
│   └── software_versions.json
│   └── source_hashes.json
│   └── target_definition.json
│   └── tflite/TFLITE_STATUS.md
│   └── tflite/final_v5_dynamic_builtins_frozen_batch1.tflite
│   └── tflite/final_v5_fp32_builtins_frozen_batch1.tflite
│   └── threshold/final_threshold.json
├── results/
│   └── asymmetry_attribution_summary.csv
│   └── asymmetry_feature_attribution.csv
│   └── attention_cells.csv
│   └── attention_summary.csv
│   └── class_balance.csv
│   └── dataset_summary.csv
│   └── final_calibration.json
│   └── final_confusion_matrix.csv
│   └── final_loss_policy.csv
│   └── final_oof_metrics.csv
│   └── final_threshold.json
│   └── final_training_history.csv
│   └── modality_ablation.csv
│   └── outer_fold_summary.csv
│   └── participant_metrics.csv
│   └── per_exercise_metrics.csv
│   └── practical_equivalence.csv
│   └── scope_confirmation.csv
│   └── scope_confirmation_per_seed.csv
│   └── v4_vs_v5_comparison.csv
├── visualizations/
│   └── 00_dataset_summary.png
│   └── 01_class_balance.png
│   └── 02_participant_heldout_folds.png
│   └── 03_final_training_curves.png
│   └── 04_final_bilstm_evaluation.png
│   └── 05_final_confusion_matrix.png
│   └── 06_per_exercise_evaluation.png
│   └── 07_modality_ablation.png
│   └── 08_attention_analysis.png
│   └── 09_asymmetry_analysis.png
│   └── 11_participant_performance.png
│   └── 12_v4_vs_v5_comparison.png
│   └── 13_model_architecture.png
├── documentation/
│   └── ARCHITECTURE_CONTRACT.json
│   └── FEATURE_CONTRACT.md
│   └── FIGURE_SOURCES.md
│   └── MODEL_CARD.md
│   └── PACKAGE_CONTENTS.md
│   └── PACKAGE_SHA256.csv
│   └── README.md
│   └── V5_STAGE7D_SCOPE_PRESERVING_CONFIRMATION_REPORT.md
│   └── V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md
│   └── build_package_inventory.py
│   └── render_figures.py
└── README.md
└── gym_fusion_model_training_v5.ipynb
└── imu_data.csv
└── master_dataset.csv
└── preprocessed_dataset.csv
└── subject_meta.csv
└── vision_data.csv
```

`saved_models/`: one final Keras model and frozen policies; `preprocessing/` has bounds, medians, scalers and exact feature order; `calibration/` has Platt; `threshold/` has the global decision rule; `tflite/` has only the two locally executable files and status.

`results/`: curated OOF, exercise, subject, modality, attention/asymmetry, loss, calibration, threshold, training-history, and size tables. Each filename in the tree is explained by its column names and the `source_path` in `PACKAGE_SHA256.csv`; the three small source-backed class/structure/fold tables and seed-42 confusion matrix are derived copies, not new experiments.

`visualizations/`: 13 numbered source-backed figures; exact inputs and caveats for **every PNG** are in `documentation/FIGURE_SOURCES.md`. Number 10 was intentionally omitted rather than present a fit-data calibration curve as independent validation.

`documentation/`: navigation README, exact feature contract, model card, original Stage 7D and Stage 8 reports, frozen architecture JSON, figure provenance, reproducibility utilities, this contents report, and the SHA256 manifest. The manifest excludes only itself to avoid a self-hash paradox and covers every other file.

Root files: immutable copied `master_dataset.csv`, `vision_data.csv`, `imu_data.csv`, `subject_meta.csv`, the historically V4-derived `preprocessed_dataset.csv` needed only by the notebook's V4 replay, the unexecuted final V5 notebook, and the package README.

## Final checks

- Immutable copied datasets: SHA256 matches the original five source CSVs.
- Final model: present; 105,681 parameters (checked against frozen Stage 8 contract and model load).
- Preprocessing, calibrator, global threshold, feature registries: present and hash-matched to final Stage 8 sources.
- TFLite: final FP32 and dynamic candidates present; INT8 absent; Pi runtime still untested.
- Visualizations: 13 present, each source-linked in `FIGURE_SOURCES.md`.
- Original V2/V4 files: not modified; protected source manifest checks 33/33 unchanged.
- No individual inner/outer models, smoke files, virtual environments, cache, or audit folder included.

This archive is a copy/curation release, **not** a standalone executable training or Raspberry Pi application. See the root README for notebook external-module/V4 replay dependencies and deployment caveats.
