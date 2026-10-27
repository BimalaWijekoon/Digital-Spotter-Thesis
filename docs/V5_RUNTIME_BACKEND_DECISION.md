# V5 runtime backend decision — M5-01 and narrow M5-02 check

**Decision:** Retain the Stage 8 batch-one FP32, built-in-ops TFLite artifact
for the isolated adapter. Live scoring remains disabled. A short real-Pi
fixed-input compatibility check passed on 2026-09-30, but full Pi performance
and live-feature gates remain open.

| Candidate | Size | Operator/dependency status | Evidence |
|---|---:|---|---|
| `final_v5_fp32_builtins_frozen_batch1.tflite` | 502,744 B | TFLite built-ins; no Flex/SELECT_TF_OPS | Selected. Local `ai-edge-litert==2.2.0` inference matched 64 archived Stage 8 Keras probabilities with maximum raw difference `5.960464477539063e-08`; 64/64 frozen-label agreement. |
| `final_v5_dynamic_builtins_frozen_batch1.tflite` | 212,816 B | TFLite built-ins; no Flex/SELECT_TF_OPS | Kept for later Pi comparison. Source package reports max raw difference `0.001910` on the same 64 processed training reps. |
| SELECT_TF_OPS/Flex | Not copied | Would require Flex runtime | Source package reports these candidates were not locally executable. |
| INT8 | Not available | No validated artifact | Final conversion crashed; do not invent an INT8 option. |
| Keras | 1,393,077 B | Full TensorFlow | Provenance/reference artifact only; not the Pi production loader. |

The runtime imports LiteRT/TFLite lazily, verifies the copied file and fixed
two-input signature, and does not import TensorFlow. The Pi aarch64/Python 3.13
check used `ai-edge-litert==2.2.0` in an isolated temporary virtual environment:
all 24 copied artifacts matched their hashes, one reference-only input produced
the same binary decision as local x86, and a 20-call adapter run measured
2.445 ms p95. This is a narrow benchmark, not a sustained latency/thermal or
live sensor claim. See
[`M5-02 fixed-fixture evidence`](evidence/M5-02-V5-PI-FIXED-FIXTURE-20260930.md).
No size-only selection.

Source: hash-verified copied
[`TFLITE_STATUS.md`](../models/digital_spotter_v5/saved_models/tflite/TFLITE_STATUS.md)
and [`Stage 8 report`](../models/digital_spotter_v5/docs/V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md).
Numerical agreement on training-derived reference inputs is **not** independent
accuracy, live-feature validity, or Pi performance evidence.
