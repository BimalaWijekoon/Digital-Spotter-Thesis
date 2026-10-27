# Final Stage 8 TFLite status

Only the two **locally executable** frozen-weight built-ins artifacts are copied here. Batch size **one** is part of their input contract: temporal float32 `(1,3,29)`, context float32 `(1,2)`, output float32 `(1,1)`. The converter froze variables from the saved final Keras model to constants; it did not retrain or alter weights. The initial SELECT_TF_OPS files required Flex and were not locally executable, so they are intentionally excluded. No INT8 artifact exists because the final representative-dataset conversion crashed. Source: [Stage 8 report](../../documentation/V5_STAGE8_FINAL_DEPLOYMENT_MODEL_REPORT.md#o-tflite-conversion-status) and `outputs/v5/deployment/stage8_gate5/frozen_weights_final_report.md`.

| File | Type | Size | Operators/runtime requirement | Local Keras parity on 64 processed training reps | Raspberry Pi execution |
|---|---|---:|---|---|---|
| `final_v5_fp32_builtins_frozen_batch1.tflite` | FP32 | 502,744 bytes | TFLite built-ins only; SELECT_TF_OPS **no**; Flex **no** | Executable locally; mean/max raw probability difference 1.15e-8 / 5.96e-8; 64/64 label agreement | **Not tested** |
| `final_v5_dynamic_builtins_frozen_batch1.tflite` | Dynamic-range quantized | 212,816 bytes | TFLite built-ins only; SELECT_TF_OPS **no**; Flex **no** | Executable locally; mean/max raw probability difference 0.000348 / 0.001910; 64/64 label agreement | **Not tested** |

Parity details remain in `outputs/v5/deployment/tflite_parity.csv` and per-sample CSVs in the working evidence. Local execution used TensorFlow's full TFLite interpreter; **plain `tflite-runtime` import/load and actual Raspberry Pi execution remain untested**. The TFLite files are candidates, not proof of deployment. Final preprocessing and Platt/threshold application must also be implemented and checked on-device.
