# Models Directory

This directory contains ML model artifacts used by the inference pipeline.

## Expected Files

| File | Description | Source |
|------|------------|--------|
| `model_quantized.tflite` | INT8 quantized LSTM model | Training notebook export |
| `model_fullprec.tflite` | Full precision LSTM model | Training notebook export |
| `scaler.save` | StandardScaler from training | joblib.dump() from training |
| `winsor_bounds.save` | Preprocessing bounds | joblib.dump() from training |
| `feature_medians.save` | Preprocessing imputation values | joblib.dump() from training |
| `deployment_config.save` | Exported feature order, threshold, and window | Training export |
| `manifest.json` | Hash-bound executable compatibility contract | M1-03 audit |
| `model_card.md` | Evidence, limitations, and promotion blockers | M1-03 audit |

## Notes

- The current compatibility artifacts are tracked and hash-bound by `manifest.json`.
- Validate them with `.venv/bin/dsctl model check --manifest models/manifest.json`.
- `--production` intentionally fails: this package is unsigned, requires Flex,
  lacks traceable training/evaluation evidence, and has unresolved sensor semantics.
- The historical inference path can fall back to mock predictions if files are
  missing. That is preserved for prototype tests only and is forbidden for
  persisted/user-facing product analysis.
- Do not replace a file independently. A future package is immutable, versioned,
  signed, evaluated, and promoted with a new manifest/model card.
