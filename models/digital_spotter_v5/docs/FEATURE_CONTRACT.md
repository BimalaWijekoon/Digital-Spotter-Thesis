# Final V5 feature and tensor contract

The ordered registry copied from the frozen Stage 8 package is machine-readable at [`saved_models/preprocessing/temporal_feature_registry.csv`](../saved_models/preprocessing/temporal_feature_registry.csv) and [`context_feature_registry.csv`](../saved_models/preprocessing/context_feature_registry.csv). The final model accepts **temporal float32 `(1,3,29)`** (phases 1, 2, 3 in that order) and **context float32 `(1,2)`**, with batch size one for the packaged TFLite files. Positions below are **zero-based**. The source values are phase aggregates, not dense video/IMU windows. Stage 8 deliberately moved the asymmetry fields to positions 17–19 relative to the Stage 7D feature order; use this exact Stage 8 order with the final model.

`T` preprocessing means: apply saved IQR winsor bounds **only for the seven IMU fields**, phase-specific median imputation for missing temporal values, then the fitted temporal `StandardScaler`. `C` means: saved context median imputation and context `StandardScaler`. Both fitted states, all bounds and medians are in [`final_preprocessing.json`](../saved_models/preprocessing/final_preprocessing.json) and [`final_preprocessor.joblib`](../saved_models/preprocessing/final_preprocessor.joblib). Do not refit them at inference. The generic preprocessor also serializes a delta scaler, but the final model **does not consume it**.

| Position `temporal[0, phase, i]` | Exact feature | Source modality | Expected source unit / caveat | Phase-dependent? | Preprocessing |
|---:|---|---|---|---|---|
| 0 | `Vis_L_Shoulder_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 1 | `Vis_L_Shoulder_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 2 | `Vis_R_Shoulder_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 3 | `Vis_R_Shoulder_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 4 | `Vis_L_Hip_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 5 | `Vis_L_Hip_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 6 | `Vis_R_Hip_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 7 | `Vis_R_Hip_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 8 | `Vis_L_Knee_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 9 | `Vis_L_Knee_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 10 | `Vis_R_Knee_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 11 | `Vis_R_Knee_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 12 | `Vis_L_Ankle_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 13 | `Vis_L_Ankle_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 14 | `Vis_R_Ankle_X` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 15 | `Vis_R_Ankle_Y` | Vision landmark | normalized image coordinate; capture units not independently verified | Yes | T |
| 16 | `Angle_Trunk_Inclination` | Vision-derived angle | nominal degrees | Yes | T |
| 17 | `Hip_Flexion_Asymmetry` | Engineered vision | absolute L–R hip flexion angle difference; nominal degrees | Yes | T |
| 18 | `Knee_Flexion_Asymmetry` | Engineered vision | absolute L–R knee flexion angle difference; nominal degrees | Yes | T |
| 19 | `Ankle_Dorsiflexion_Asymmetry` | Engineered vision | absolute L–R ankle dorsiflexion angle difference; nominal degrees | Yes | T |
| 20 | `Knee_Hip_Coupling_L` | Engineered vision | left knee flexion / (left hip flexion + 1e-6); dimensionless | Yes | T |
| 21 | `Knee_Hip_Coupling_R` | Engineered vision | right knee flexion / (right hip flexion + 1e-6); dimensionless | Yes | T |
| 22 | `IMU_Acc_X` | Lower-back IMU | nominal m/s²; V2 capture provenance unverified | Yes | T + winsor |
| 23 | `IMU_Acc_Y` | Lower-back IMU | nominal m/s²; V2 capture provenance unverified | Yes | T + winsor |
| 24 | `IMU_Acc_Z` | Lower-back IMU | nominal m/s²; V2 capture provenance unverified | Yes | T + winsor |
| 25 | `IMU_Gyro_X` | Lower-back IMU | V2 unit unverified; firmware/documentation disagree on deg/s vs rad/s | Yes | T + winsor |
| 26 | `IMU_Gyro_Y` | Lower-back IMU | V2 unit unverified; firmware/documentation disagree on deg/s vs rad/s | Yes | T + winsor |
| 27 | `IMU_Gyro_Z` | Lower-back IMU | V2 unit unverified; firmware/documentation disagree on deg/s vs rad/s | Yes | T + winsor |
| 28 | `IMU_Acc_Magnitude` | Engineered lower-back IMU | Euclidean norm of X/Y/Z; same unverified acceleration unit | Yes | T + winsor |

| Position `context[0, i]` | Exact feature | Source modality | Expected source unit | Context/static? | Preprocessing |
|---:|---|---|---|---|---|
| 0 | `Exercise_ID` | Exercise context | categorical code: 0 Squat, 1 Deadlift | One value per repetition | C |
| 1 | `Load_kg` | Exercise context | kilograms | One value per repetition | C |

The six engineered fields are constructed **in memory** from `master_dataset.csv` in `outputs/v5/v5_stage1_6_pipeline.py:engineer_phase_frame` and are not written back to any source CSV. Source-unit caveats follow `audit_v5/V5_FEATURE_INVENTORY.csv`; the final packaged registry itself says its units are not independently verified. The final package includes no bar-motion proxy, anthropometric, explicit missingness-indicator, or delta input. Target is the historical phase-3 `Class_Binary`, not a reconstructed error-type label.
