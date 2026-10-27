# V5 IMU synthetic R1 — offline research candidate

Version: `digital_spotter_v5_imu_synthetic_r1`. Not activated in the Pi or local runtime.

BiLSTM 64/32 + 2-head attention, 105,681 parameters; temporal `(1,3,29)`,
context `(1,2)` ordered Exercise_ID, Load_kg. Exact features are in
MODEL_MANIFEST.json and preprocessing.json. No delta, bar proxies or RF.

Training: 20 inner fits, five outer evaluation fits, one all-data fit. Inner
profiles are disjoint 12 fitting / 3 early-stopping monitor / 5 validation.
Preprocessing is fitted on fitting profiles only. Final weights, preprocessing,
Platt calibration and threshold are new, not reused from the historical model.

## Synthetic evaluation only

Held-out-profile outer OOF: accuracy 0.854807, F1 0.815839,
ROC AUC 0.886581, bad-form recall 0.765330.
The 25 profile IDs are synthetic, not measured people. Target is the historical
phase-3 Class_Binary; 374 phase-inconsistent repetitions are retained. These
numbers are not estimates of accuracy on real exercises or clinical validity.
Global calibration/threshold fit on outer OOF is a finalization policy, not a
second independent evaluation. Its transfer to the all-data model is unverified.

## Numerical export

FP32 built-in TFLite, no Flex; 497416 bytes.
Keras reload compared on 2,018 repetitions. TFLite compared on 64 fixed,
evenly spaced repetitions: maximum raw probability difference
2.08616257e-07, zero class mismatches. Preprocessing fixture
round-trip is exact. This is a host check, not a Pi benchmark.

## Simulation contract and deployment gate

Acceleration: m/s² specific force, gravity retained. Gyroscope: rad/s.
Assumed X-forward/Y-left/Z-up virtual sensor frame, 50 Hz acquisition, phase
medians of pose-associated samples. Physical PCB-to-body mounting and motion/
noise parameters are unmeasured assumptions. Original vision, labels, context
and metadata were preserved; only the IMU generation changed.

Before activation, verify the actual mounted frame/units, synchronized live
phase features, model adapter compatibility and Pi numerical/runtime behavior.
Then evaluate real independently labelled repetitions. Do not interpret a
successful training/export as validated real-world form accuracy.

Use the JSON preprocessing/calibration/threshold alongside the TFLite model.
Do not use historical scalers/thresholds or silently fall back to them.
