# M5-R04 — local reference-only V5 candidate integration

2026-10-20. **PASS for this local software boundary only.** Pi offline; no
hardware, deployment, user-facing scoring or real-world accuracy pass claimed.

## Implemented

- `src/digital_spotter/inference/v5_candidate.py`: explicitly loads only
  `digital_spotter_v5_imu_synthetic_r1`. Verifies the package SHA256 inventories,
  exact feature/context/shape/units and export contract, then reads the new
  preprocessing, raw-probability Platt calibration and threshold. No old fitted
  state is reused; no training/sklearn/TensorFlow import or refitting occurs.
- `v5_preprocessing.py`: reads the candidate frozen JSON state into the same
  numeric transform used by the legacy package. Public `reference_inputs()`
  exposes fitted medians for explicitly non-live reference calculation.
- `v5_model.py`: shares strict LiteRT tensor setup/inference and emits the
  loaded instance's model version. The legacy loader/default is preserved.
- `scripts/run_workout.py`: explicit `--model-version` selects the matching
  loader. Package path is still supplied by the operator; no automatic fallback
  or active-model path replacement. The legacy version remains the default.
- `core/workout.py`: session creation, saved context, inference diagnostics and
  status use the selected runtime model version rather than the old constant.
  Existing live-score unavailability is unchanged. The candidate's `predict()`
  refuses live scoring; only `predict_reference_only()` may infer.

Both model artifact packages and all training output bytes remain unchanged.
No firmware, camera, BLE, GPIO, Pi, network configuration or dependencies changed.

## Checks actually run

```text
.venv/bin/python -m pytest tests/test_v5_candidate_runtime.py \
  tests/test_v5_model_contract.py -q --disable-warnings --maxfail=1
9 passed in 7.63s

.venv/bin/python -m pytest tests/core/test_workout.py \
  -q --disable-warnings --maxfail=1
4 passed in 5.88s
```

The three new candidate checks cover:

1. Exact serialized preprocessing on one provided synthetic fixture, real
   LiteRT inference matching its exported Keras reference within 1e-4, correct
   new calibration/threshold/version, `reference_only=True`, and no TensorFlow
   import. Live prediction is refused.
2. Modified preprocessing bytes are rejected by the artifact hash inventory.
3. Explicit launcher selection and fitted-median reference output retain the
   candidate version and non-live status; unknown versions are rejected.

The six existing legacy model checks still pass. The four session checks use
temporary SQLite and a fake model/sensor-free session; the new one verifies
the selected candidate version is persisted while scores remain unavailable.
They are not hardware or full UI/browser evidence. No throughput or latency
measurement was taken in this step.

Tests were written before implementation: collection first failed because the
candidate runtime did not exist. During verification, both a baseline and a
modified session check stalled in the restricted sandbox's thread/asyncio path.
A bounded diagnostic showed an idle executor and selector; no database/queue
source was changed. Running the four scoped session checks outside that sandbox
passed. Interrupted sandbox attempts are not reported as passes. No broad app,
hardware, timeout-policy, fallback or endurance test matrix was added.

## Local opt-in launch syntax

This is a command reference, **not a claim that the UI or Pi was launched**.
Use a new, nonexistent run directory; do not overwrite session data.

```bash
.venv/bin/python scripts/run_workout.py \
  --model-version digital_spotter_v5_imu_synthetic_r1 \
  --model-package training/v5_imu_retraining/outputs/main_v5_imu_r1_20261020/package \
  --run-dir /tmp/ds-v5-candidate-local-NEW \
  --edge-device-id research-local \
  --imu-device-id wearable-local
```

This uses the existing loopback-only workout server, with no automatic hardware
producer startup. Without real producers it truthfully reports absent camera/
IMU data. Loading this model does not permit live feedback or validate mounting.

## Next gate and rollback

When the Pi is online, copy the candidate into a separate versioned model area
and verify one target-runtime load/inference before changing launch selection.
Preserve the old model and launcher configuration. Match the mounted sensor's
frame, SI units and synchronized phase reducer before any separate live-scoring
decision. Synthetic training scores cannot replace real independently labelled
evaluation. No automatic activation or readiness bypass was implemented.

Files changed: the five runtime/launcher files above, two focused test files,
`PLAN.md`, architecture/current-state/interface/security/operations/decision/test
documents, and the local training `STATE.md`. No database/schema, credential or
security migration. SHA256 checks detect local drift, not signed authenticity.
All changes are local and uncommitted; no commit or push occurred.
