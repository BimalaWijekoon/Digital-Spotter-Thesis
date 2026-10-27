# M5-R02 — synthetic IMU generation result

Date: 2026-10-20. **PASS for the scoped generator/preservation checks only.**
No real-world calibration, classifier training, hardware test or deployment pass
is claimed. The owner cannot record mounted measurements at present.

## Candidate

- Version: `v5-imu-synthetic-r1`.
- Directory: `data/generated/imu_r1_20261020/` (local, Git-ignored).
- Master SHA256:
  `934925aa40ad7e24e6f34ff12075d76d70d0a97ba1f200374508505323d620ff`.
- Rows: **6,054**; complete repetitions: **2,018**.
- Full simulated samples used for reduction: **414,964**, at configured 50 Hz.
- Source: hash-verified local copy of the frozen synthetic master dataset.
- Old FYP and runtime model packages remain unchanged.

Each candidate directory contains `master_dataset.csv`, an explicitly keyed
phase-level `imu_data.csv`, unchanged `vision_data.csv` and `subject_meta.csv`,
`phase_manifest.csv`, one `example_trace_50hz.csv`, exact simulation configuration,
a frozen specification and `DATASET_MANIFEST.json` with provenance and hashes.
No raw video or permanent device credentials are involved.

## Actual checks

```text
.venv/bin/python -m unittest discover \
  -s training/v5_imu_retraining/tests -p test_imu_generator.py -q
Ran 5 tests in 0.113s: OK
```

The tests cover stationary/tilted specific force, a consistent gyro mounting
rotation, signed bend/return rates with smooth derivatives, actual-profile
quantization, deterministic generation independent of class/error labels,
protected-cell/missingness preservation and refusal to overwrite a bundle.
They use deterministic synthetic fixtures, not real hardware measurements.

One direct post-write CSV/manifest comparison checked all 6,054 written rows:

| Check | Result |
| --- | --- |
| Source/output headers, row count and row order | unchanged |
| Protected non-IMU columns | all 56 unchanged; zero changed cells |
| Original vision/meta CSV bytes | identical SHA256 |
| Original missing IMU cells | 1,278 preserved (213 complete missing-IMU rows) |
| Available generated IMU values | finite and inside actual representable ranges |
| Saturated accelerometer axis samples | 0 |
| Saturated gyro axis samples | 0 |
| Generated artifact hashes | 8/8 checked against bundle manifest |
| Copied-reference/original hashes | 37/37 and 37/37 unchanged |

`python3 training/v5_imu_retraining/scripts/verify_copy.py --check-source`
also reconfirmed all 2,018 complete source phase groups.

## Limits retained explicitly

- 104 missing trunk summaries needed within-rep interpolation or a documented
  fallback prior. No protected vision cell was changed; no bend-angle clipping
  occurred. This is not reconstruction of lost measurements.
- Motion/noise/cadence/mounting parameters are assumed, not calibrated against
  actual lower-back recordings. The physical PCB-to-body rotation is unverified.
- 374 repetitions retain inconsistent historical phase labels. Labels were not
  repaired or newly flipped. The planned target remains the original phase-3
  `Class_Binary`; synthetic scores cannot establish expert-labelled accuracy.
- Preserved vision summaries need not be a full physically consistent 3D body
  trajectory. The generator is a reduced-order approximation, not a recovered
  real camera/IMU pair or proof of source-equivalent synchronization.
- No model was fitted or scored during generation. No accuracy forecast, injury
  threshold or readiness flag was manufactured.

## Owner-selected training procedure

The owner explicitly chose original grouped cross-validation, not one holdout
split. Retain the final V5 BiLSTM 64/32 + two-head attention, train-only fitted
winsorization/imputation/scaling, BatchNorm/dropout, early stopping, fresh
cross-fitted calibration and threshold selection, then one final all-data fit
and TFLite export/parity. See `config/training_plan.json`.

The planned final-model-only Stage 8-style run is 5 outer x 4 inner folds plus
5 outer fits and one final fit (26 LSTM fits), not 26 different architectures.
No Random Forest, other model family, ablation, larger network or hyperparameter
search is planned. Old loss searches are not repeated; retain final V5 plain BCE.
New split/source metadata and fitted states are mandatory. No historical fit,
epoch count, calibrator or numeric threshold may be reused on the revised data.

The existing separate FYP training interpreter was inventoried read-only:
Python 3.12.13 and discoverable TensorFlow/Keras/NumPy/pandas/scikit-learn. It was
not imported for fitting, copied, modified or installed into the runtime `.venv`.
At the generation checkpoint, preparing the adapted training entry point was
still pending. Subsequent M5-R03 execution is tracked in `../STATE.md` and
`TRAINING_PROCEDURE.md`; this generation report is not a current job status.

All changes are local/uncommitted. Rollback: leave this candidate inactive and
continue using the unchanged original artifacts. Do not delete the evidence or
activate the synthetic candidate as validated live scoring.
