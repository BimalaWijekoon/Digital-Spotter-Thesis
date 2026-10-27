# V5 Stage 8 — Final scope-faithful deployment-model handoff

**Stage 8 artifact gate: PASS. Immediate Raspberry Pi integration gate: FAIL pending the runtime checks in S–T.** This report consolidates the frozen Gate 1–5 evidence; Gate 6 performs no fitting, conversion, or hardware integration. The final all-data model is a deployment artifact, **not a new unbiased generalisation estimate**. Participant-held-out research results remain in the [Stage 7D report](V5_STAGE7D_SCOPE_PRESERVING_CONFIRMATION_REPORT.md) and earlier Stage 7 reports. Each result below cites its saved source.

## A. Source integrity

The [frozen source manifest](manifests/source_hashes_before.json) covers 33 protected research files. Gate 1 through Gate 5 reported matching before/after hashes, and Gate 6 rechecked all 33 against that manifest before and after editing this report/notebook: **33/33 matched; zero mismatches** (see [Gate 1](V5_STAGE8_GATE1_REPORT.md), [Gate 4](V5_STAGE8_GATE4_FINAL_MODEL_REPORT.md), and [Gate 5 final conversion](deployment/stage8_gate5/frozen_weights_final_report.md)). The V5 notebook is an authorized Stage 8 handoff edit and is **not** in that protected-source manifest; its SHA256 changed from `f4e1729627f1a3f2a14884cd02b1b7d011f1a3969379b13324ae2c83317e6eea` to `fe1af33b1d6a17d207f23ae05b4124c754a5c74811608d64dc64b53d2c3abc2e`. Its 45 cells passed `nbformat` validation. The 16 package files also matched their [package manifest](deployment/final_package/package_manifest.json). No original V2/V4 evidence was changed. The historical terminal-phase `Class_Binary` target remains unchanged for all 2,018 repetitions; 374 have inconsistent phase labels and were not relabelled ([Gate 1 preflight](deployment/stage8_gate1/preflight.json), [repetition manifest](manifests/repetition_manifest.csv)).

## B. Frozen scope-faithful architecture

Three real phase rows feed a two-layer BiLSTM (64 then 32 units, both returning sequences), BatchNorm, dropout 0.25/0.20, two-head self-attention (`key_dim=16`), residual Add, LayerNorm, and global average pooling. A repetition-level context Dense 16 branch joins a Dense 64/dropout 0.25/Dense 32/dropout 0.15/sigmoid head. Inputs are temporal `(batch,3,29)` and context `(batch,2)`; output is one bad-form probability ([frozen contract](deployment/stage8_gate1/stage8_frozen_contract.json), [Gate 1 report](V5_STAGE8_GATE1_REPORT.md)). Attention and asymmetry are retained for scope continuity because the candidate stayed within Stage 7D's predeclared practical margins; neither is established as uniquely predictive or causal ([Stage 7D report](V5_STAGE7D_SCOPE_PRESERVING_CONFIRMATION_REPORT.md)).

## C. Exact feature contract

Temporal order, repeated for each of phases 1–3: `Vis_L_Shoulder_X`, `Vis_L_Shoulder_Y`, `Vis_R_Shoulder_X`, `Vis_R_Shoulder_Y`, `Vis_L_Hip_X`, `Vis_L_Hip_Y`, `Vis_R_Hip_X`, `Vis_R_Hip_Y`, `Vis_L_Knee_X`, `Vis_L_Knee_Y`, `Vis_R_Knee_X`, `Vis_R_Knee_Y`, `Vis_L_Ankle_X`, `Vis_L_Ankle_Y`, `Vis_R_Ankle_X`, `Vis_R_Ankle_Y`, `Angle_Trunk_Inclination`, `Hip_Flexion_Asymmetry`, `Knee_Flexion_Asymmetry`, `Ankle_Dorsiflexion_Asymmetry`, `Knee_Hip_Coupling_L`, `Knee_Hip_Coupling_R`, `IMU_Acc_X`, `IMU_Acc_Y`, `IMU_Acc_Z`, `IMU_Gyro_X`, `IMU_Gyro_Y`, `IMU_Gyro_Z`, `IMU_Acc_Magnitude`. Context order: `Exercise_ID`, `Load_kg`. Source: [temporal registry](deployment/final_package/temporal_feature_registry.csv), [context registry](deployment/final_package/context_feature_registry.csv), [frozen contract](deployment/stage8_gate1/stage8_frozen_contract.json). Stage 8 uses the same feature *set* as Stage 7D but places asymmetry at positions 17–19 rather than 26–28; the changed order is frozen for every Stage 8 fit, not silently treated as byte-equivalent to Stage 7D ([Gate 1 report](V5_STAGE8_GATE1_REPORT.md)).

Excluded: `V_Bar_Velocity_Vertical`, `P_Bar_Power_Watts`, `Smoothness_Jerk`, `Velocity_Decel_Ratio`, `Subject_Height_cm`, `Subject_Weight_kg`, `Femur_Tibia_Ratio`, `BMI`, explicit missingness indicators, synthetic fourth timestep, and delta branch ([frozen contract](deployment/stage8_gate1/stage8_frozen_contract.json)). The four proxy fields were excluded for unresolved physical provenance, not because this handoff proved they have no predictive value.

## D. Parameter count

The built final architecture has **105,681** total parameters: 105,425 trainable and 256 non-trainable ([Gate 1 architecture inspection](deployment/stage8_gate1/preflight.json)). Gate 4 asserted the saved final model retains the count ([Gate 4 completion](deployment/stage8_gate4/completion.json)).

## E. Loss-policy comparison

The same five participant-held-out outer folds, seed 42, batch 32, Adam 3e-4, development-only preprocessing, and raw-probability 0.5 decision rule were used for each policy. Plain BCE: 2,018 OOF predictions, PR-AUC **0.916312**, F1 **0.921781**, bad-form recall **0.903302**, Brier **0.060582**. Training-only balanced class weights: PR-AUC **0.915045**, F1 **0.921227**, recall **0.903302**, Brier **0.060677**. Full fold and pooled values: [comparison CSV](deployment/final_loss_policy_comparison.csv), [Gate 2 report](V5_STAGE8_GATE2_LOSS_POLICY_REPORT.md). **Selection used outer OOF labels** and is a deployment-policy decision, not an independent new generalisation comparison.

## F. Selected global loss

`LOSS_A_BCE` (plain binary cross-entropy) won the frozen practical-tie rule; the final all-data fit used no class weights or focal loss ([selected loss](deployment/stage8_gate2/selected_global_loss.json), [Gate 4 training record](deployment/stage8_gate4/final_training.json)).

## G. Cross-fitted calibration procedure

For each of five outer development splits, all four saved participant-disjoint inner folds generated one raw out-of-fit prediction for every development repetition. Each inner fit used 12 fit subjects, 3 separate epoch-monitor subjects, and 5 inner-validation subjects; preprocessing was fitted on the fit subjects only. The 20 inner-fit rows and five prediction tables are saved under [Gate 3](deployment/stage8_gate3/) and summarized in the [Gate 3 report](V5_STAGE8_GATE3_CROSSFIT_REPORT.md). Platt versus uncalibrated was evaluated by development-only participant-disjoint cross-calibration; Platt required at least 0.001 Brier improvement and was selected in all five outer folds. No outer-test label chose these fold decisions. A documented limitation: per-fold Platt refitting on all development predictions shifts the scale relative to cross-calibrated threshold-selection probabilities ([Gate 4 scale check](deployment/stage8_gate4/gate3_platt_scale_check.csv)). Gate 2's earlier loss choice had already used outer OOF labels; Gate 3 does not undo that selection dependence.

## H. Final calibration policy

One global **Platt** calibrator was fitted to 2,018 selected-loss outer-OOF raw probabilities and their historical labels, then persisted as [final_calibrator.joblib](deployment/final_calibrator.joblib). Raw Brier on that fit set was 0.060582; calibrated Brier on the **same fit set** was 0.059175. These values do not demonstrate independent calibration generalisation. Transfer of this OOF-derived calibrator to the one all-data model's probability scale is unvalidated ([calibration policy](deployment/final_calibration_policy.json), [Gate 4 report](V5_STAGE8_GATE4_FINAL_MODEL_REPORT.md)).

## I. Cross-fitted threshold procedure

Each outer-fold threshold maximized bad-form F1 on the selected calibrated **cross-fitted development** probability stream; the outer test remained sealed for that fold's threshold decision. Per-fold thresholds were 0.252702, 0.310581, 0.297337, 0.282984, and 0.578628, with precision/recall/F1/F2/PR-AUC and source sweeps saved under [Gate 3 decisions](deployment/stage8_gate3/decisions/) and [threshold sweeps](deployment/stage8_gate3/threshold/) ([Gate 3 report](V5_STAGE8_GATE3_CROSSFIT_REPORT.md)). They are not the final single deployment threshold.

## J. Final global threshold

The deployment threshold is **`0.20549274582373653`**, maximizing bad-form F1 on globally Platt-calibrated selected-loss OOF probabilities; ties use distance to 0.5 then the lower threshold. Source: [threshold policy](deployment/final_threshold.json), [global OOF probabilities](deployment/stage8_gate4/global_calibrated_oof.csv), [sweep](deployment/stage8_gate4/global_threshold_f1_sweep.csv). The global calibrator and threshold both used OOF labels, so the recorded fit-set F1 0.925284 is **not an independent generalisation estimate**. The historical V4 0.359474659 threshold was not reused.

## K. Final epoch policy

The round-half-up median of the 20 inner best `val_loss` epochs is **9**. Final training used this fixed count, without final-data early stopping or any outer-test epoch decision ([epoch policy](deployment/final_epoch_policy.json), [inner-fit summary](deployment/stage8_gate3/inner_fit_summary.csv)).

## L. Preprocessing inventory

The final preprocessor was fitted on all 2,018 historical-target repetitions. It saves justified IQR winsor bounds for selected IMU features, phase-specific temporal medians, context medians, temporal and context `StandardScaler` states, feature and phase order, and input-shape metadata: [preprocessing JSON](deployment/preprocessing/final_preprocessing.json), [joblib](deployment/preprocessing/final_preprocessor.joblib). The generic engine persists an **unused** delta scaler; the final network consumes no delta branch. Inference order is specified in the [package README](deployment/final_package/README.md): build three real phases, ordered features/context, winsorize, impute, scale, infer, calibrate, threshold. The joblib object depends on the repository's `v5_stage1_6_pipeline.FoldPreprocessor` class and Python dependencies; it is not yet a portable Pi implementation.

## M. Final all-data training completion

Exactly one final seed-42 model was trained on all 2,018 repetitions for nine epochs, batch 32, Adam 3e-4, plain BCE, `shuffle=False`, using the frozen architecture and all-data preprocessor. The [saved Keras model](deployment/model/final_v5_scope_faithful_bilstm_mha.keras) is 1,393,077 bytes, SHA256 `f9e2c6b942a57050a4b6f9d010a3c7c48ac2fdb966bb84e194ecac2a137ca424`; a deterministic 32-input save/reload check had maximum prediction difference zero. Fit wall time was 12.8 seconds ([training record](deployment/stage8_gate4/final_training.json), [history](deployment/stage8_gate4/final_training_history.csv), [Gate 4 report](V5_STAGE8_GATE4_FINAL_MODEL_REPORT.md)). Training history is engineering evidence only, not held-out performance.

## N. Final package inventory

The [final package](deployment/final_package/) contains 16 hash-listed files: Keras model; exact temporal/context registries; preprocessor state and JSON; Platt calibrator/policy; threshold; loss/epoch policies; target definition; protected source hashes; config hash; software versions; model card; and inference README. [Package manifest](deployment/final_package/package_manifest.json) provides each SHA256. The two executable TFLite candidates are separately saved under [deployment/tflite](deployment/tflite/) and **not** counted among these 16 package files. The package is a research-to-runtime handoff, not a working Pi application.

## O. TFLite conversion status

The original generic built-ins converter failed on TensorList operations; SELECT_TF_OPS variants converted but needed Flex and were not executable in the local interpreter. Fixed-batch-one conversion with unresolved resource variables also produced unusable artifacts. The final converter-only route froze the **saved** Keras variables to constants, preserving weights and architecture, and produced two locally executable built-ins-only batch-one files: [FP32](deployment/tflite/final_v5_fp32_builtins_frozen_batch1.tflite), **502,744 B**, SHA256 `8a1d308c2596e571b2840673c1b437bbd2ccdbef5c590ebdb6dbbd40a7a4f9ab`; [dynamic-range](deployment/tflite/final_v5_dynamic_builtins_frozen_batch1.tflite), **212,816 B**, SHA256 `7877ebafd7c90c0c8a278ee791b1eca1fb7127efe8840ebb3dd66566d25bd408`. Neither requires Flex or SELECT_TF_OPS in the saved operator inventory. An INT8 attempt with a valid 128-example representative set crashed the converter (exit 139); **no INT8 artifact** is available. Details: [final conversion report](deployment/stage8_gate5/frozen_weights_final_report.md), [attempt log](deployment/stage8_gate5/frozen_weights_conversion_attempts.csv), [INT8 crash marker](deployment/stage8_gate5/int8_converter_crash.json). Local full-TensorFlow interpreter execution does not prove plain `tflite-runtime` or Pi compatibility. Both input dtypes are float32, with shapes `(1,3,29)` and `(1,2)`; output is `(1,1)` ([FP32 interpreter metadata](deployment/tflite/fp32_builtins_frozen_batch1_interpreter.json), [dynamic metadata](deployment/tflite/dynamic_builtins_frozen_batch1_interpreter.json)).

## P. Keras/TFLite parity

On the same 64 deterministic **training** repetitions, FP32 mean/max raw probability absolute differences were **1.15e-8 / 5.96e-8**; dynamic-range mean/max were **0.000348 / 0.001910**. Pearson correlations were approximately 1.000000 and 0.9999994; each variant agreed on all 64 thresholded labels after the frozen Platt/threshold pipeline. Calibrated differences, identifiers, and every comparison row are in [parity summary](deployment/tflite_parity.csv) and the per-variant `*_parity_samples.csv` files under [deployment/tflite](deployment/tflite/). This is local numerical parity, **not** a held-out estimate or hardware benchmark ([Gate 5 final report](deployment/stage8_gate5/frozen_weights_final_report.md)).

## Q. V4 versus V5 size and parameters

Measured file comparison: V4 **430,081** versus V5 **105,681** parameters (75.43% fewer); Keras **5,275,297** versus **1,393,077 B** (73.59% smaller); executable FP32 TFLite **1,768,756** versus **502,744 B** (71.58% smaller); executable dynamic TFLite **536,488** versus **212,816 B** (60.33% smaller). The comparison uses the final *executable* V5 files, not earlier converted-but-unusable files ([size CSV](deployment/v4_v5_deployment_size_comparison.csv), [Gate 5 final report](deployment/stage8_gate5/frozen_weights_final_report.md)). There is no comparable V5 INT8 file.

## R. Remaining deployment blockers

1. The joblib preprocessor requires repository code/dependencies and has no portable, parity-tested Pi implementation ([package README](deployment/final_package/README.md)).
2. These built-ins files have not been loaded by plain `tflite-runtime` or executed on the actual Raspberry Pi; operator compatibility and batch-one invocation need verification ([interpreter metadata](deployment/tflite/fp32_builtins_frozen_batch1_interpreter.json)).
3. The global OOF-derived Platt calibrator and threshold have not been independently checked against the all-data model's probability scale ([calibration policy](deployment/final_calibration_policy.json), [threshold policy](deployment/final_threshold.json)).
4. Live phase segmentation/feature derivation, camera–IMU timestamp alignment, missing-input behavior, per-repetition latency, CPU/memory/thermal use, and BLE reliability are **not measured by Stage 8** ([model card](deployment/final_package/MODEL_CARD.md), [Gate 5 report](deployment/stage8_gate5/frozen_weights_final_report.md)).
5. The research target is historical phase-3 `Class_Binary`; the 374 phase-inconsistent repetitions remain an annotation limitation, not a repaired truth set ([repetition manifest](manifests/repetition_manifest.csv), [Gate 1 report](V5_STAGE8_GATE1_REPORT.md)).

## S. Exact next steps for Raspberry Pi integration

After separate approval, first freeze the package hashes and choose the FP32 batch-one file as the conservative parity reference. Implement a portable, **read-only** three-phase feature/preprocessing adapter matching the saved registry, winsor bounds, medians, scaler states, context order, calibration, and threshold; establish repetition-ID-level parity with the saved Python path, including missing/occluded values. Then verify the chosen TFLite file loads and runs in the actual Pi `tflite-runtime` version, matching Keras on a fixed parity set. Only then connect live camera, pose, BLE, phase segmentation, timestamp mapping, and classifier; measure synchronization, end-to-end latency, packet loss, CPU, memory, temperature, and failure/reconnect behavior. Preserve original datasets, V4 outputs, and Stage 8 artifacts throughout. These are **future tasks**, not completed Stage 8 results ([package README](deployment/final_package/README.md), [model card](deployment/final_package/MODEL_CARD.md)).

## T. PASS/FAIL recommendation for hardware integration

**PASS for the Stage 8 research artifact and local numerical-parity handoff. FAIL for immediate hardware integration or a claim of deployment readiness.** The executable, parity-checked FP32/dynamic files are candidates for a separately approved Pi validation phase, not evidence that the present package can run live. Resolve R.1–R.4 and measure hardware performance before calling the model deployed. This is the Stage 8 stop point; no Pi runtime or firmware changes were made ([Gate 5 final report](deployment/stage8_gate5/frozen_weights_final_report.md), [package README](deployment/final_package/README.md)).
