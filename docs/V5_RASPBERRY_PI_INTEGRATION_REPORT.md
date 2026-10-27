# V5 Raspberry Pi integration report — M5-01 offline checkpoint

**Recommendation for physical deployment: FAIL / NOT YET READY.** The artifact
copy, portable transform, calibration and frozen decision pass offline checks.
A subsequent one-input reference-only Pi LiteRT check passed on 2026-09-30
([evidence](evidence/M5-02-V5-PI-FIXED-FIXTURE-20260930.md)). No V5 live
session, phase/sync equivalence, or mounted vision/IMU feature validity is
established.

## Source and copy integrity

- Immutable source: `/mnt/g/FYP/Datasets v2 Model v5/` (read only). All 67 files
  listed in its `documentation/PACKAGE_SHA256.csv` matched their SHA-256 entries.
- Isolated destination: [`models/digital_spotter_v5/`](../models/digital_spotter_v5/).
  The [`COPY_MANIFEST.csv`](../models/digital_spotter_v5/COPY_MANIFEST.csv)
  records 24 copied final model/policy/registry/documentation files; all 24
  copied hashes and sizes match. No dataset, checkpoint, audit folder, or cache
  was copied.
- The trusted, hash-verified Stage 8 joblib scaler and Platt parameters were
  exported once to [`portable_state.json`](../models/digital_spotter_v5/portable_state.json).
  Runtime never deserializes pickle. The local
  [`RUNTIME_MANIFEST.json`](../models/digital_spotter_v5/RUNTIME_MANIFEST.json)
  pins the copy inventory, portable state, model hash, version, signature and
  threshold. Original V4 artifacts remain untouched and are not a fallback.

## Contract and offline evidence

| Check | Result |
|---|---|
| Ordered temporal/context/phase contract | PASS: exactly three real phases, 29 exact Stage 8 temporal fields, `[Exercise_ID, Load_kg]`; outputs float32 `(1,3,29)` and `(1,2)`. No synthetic delta, proxy fields or missingness indicators. |
| Fitted preprocessing parity | PASS: portable imputation, seven IMU winsor bounds and scaling match hash-verified fitted Stage 8 scalers in a deterministic missing/outlier test. No refit. |
| Model loading | PASS offline on x86_64; subsequent narrow Pi fixed-input check passed with LiteRT 2.2.0/aarch64. Not a live-input gate. |
| Inference, calibration and threshold | PASS: raw probability → frozen Platt parameters → `0.20549274582373653` → binary class, with model version. |
| Stage 8 archived Keras parity | PASS on 64 processed **training-derived** repetitions: max raw difference `5.960464477539063e-08`, max calibrated difference `2.77820758620706e-08`, 64/64 label agreement. **Not generalisation accuracy.** |
| Missing IMU in live-call API | PASS fail-closed; separate `predict_reference_only` is explicitly tagged and must not feed workout results, persisted analysis, or feedback. A later isolated owner-viewed Test input card uses it only for fixed-input inspection. |
| V4/V5 isolation | PASS for this isolated adapter; legacy V4 entry points have **not** been migrated or activated. |

Parity input provenance: the source package's `master_dataset.csv` SHA-256
`68b16c054e2435c2b3b07f5b289fa02d18404f309403929ba610d8bab1f6b466`
and archived `outputs/v5/deployment/stage8_gate5/parity_reference_64.csv`
SHA-256 `52d33d42c94cb0ecd96d79e2656e58d04fa035e36c1d82cd9f673d1382fb3eec`.
These files were read in memory for the parity check; neither was copied here.
The 64 results are no substitute for a participant-held-out or live evaluation.

Focused verification: `pytest tests/test_v5_model_contract.py
tests/contract/test_model_manifest.py -q` passed **15/15** (6 new V5 checks,
9 existing V4 manifest checks); `git diff --check` passed. A broader suite was
started but stopped at the owner's request to keep research-stage verification
proportional; it is **not** reported as a pass.

## Remaining blockers

- **Vision/asymmetry/knee–hip coupling:** a local candidate feature bridge now
  calculates the frozen formulas from bounded research phase summaries. Live
  pose coordinate/source equivalence remains unverified; no live score is enabled.
- **IMU:** R9 BLE transport has prior real-hardware evidence and the local
  candidate bridge maps synchronized phase medians, but Stage 8 units/provenance
  and lower-back mounting equivalence remain unresolved. The live V5 path is
  not activated.
- **Phase and synchronization:** bounded local code exists for three-phase
  construction and capture-time fusion, but training-source equivalence and
  mounted live behavior remain unproven.
- **Pi backend:** one fixed-median reference input loaded and ran on the real
  Pi, with matching calibrated class, 24 artifact hashes verified and a short
  20-call latency/RSS snapshot. Full M5-02 sustained performance, concurrent
  workload and thermal acceptance are not measured.
- **Feedback/API/persistence:** no active live route calls this adapter. A
  separate one-shot Pi command now exports one fitted-median reference result
  to a static Devices → Analysis **Test input** card, not to Workout Feedback,
  SQLite or the wearable. Binary V5 output must not generate named error-category
  or safety claims. Structured live inference logging and durable result wiring
  remain pending.
- **Physical deployment commands:** deliberately deferred until M5-02 and the
  live-feature gates pass. Do not upload or enable this package as live scoring.

Offline reproduction in this workspace (no Pi/ESP required):

```bash
./.venv/bin/python -m pytest tests/test_v5_model_contract.py -q
./.venv/bin/python scripts/validate_v5_source_parity.py \
  --package models/digital_spotter_v5 \
  --master-csv '/mnt/g/FYP/Datasets v2 Model v5/master_dataset.csv' \
  --reference-csv /mnt/g/FYP/outputs/v5/deployment/stage8_gate5/parity_reference_64.csv
```

The parity command requires the read-only training workspace and is an offline
development check, **not** a Pi install instruction. Backend rationale:
[`V5_RUNTIME_BACKEND_DECISION.md`](V5_RUNTIME_BACKEND_DECISION.md).
