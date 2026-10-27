# M1-03 current-model manifest evidence

**Date:** 2026-08-26
**Environment:** E0/E1 plus read-only E3 tensor/operator inspection
**Status:** DONE for compatibility freeze; package is intentionally not production-ready

## Delivered

- `models/manifest.json` with exact hashes/sizes for the primary TFLite model,
  scaler, winsor bounds, medians, exported deployment config, full-precision
  reference, and model card;
- exact float32 input `(1, 4, 40)`/signature `(-1, 4, 40)`, scalar sigmoid output,
  tensor names, output meaning, and artifact threshold
  `0.35947465896606445`;
- exact 40-feature order, per-feature source and unit status, three phase rows plus
  phase-3-minus-phase-1 construction, and preprocessing order;
- Pi-observed runtime/delegate/operator contract, including TensorFlow Flex
  `TensorList` requirements and XNNPACK;
- explicit unknown provenance, metrics, threshold rationale, and approved exercise
  scope instead of invented values;
- model card documenting sensor semantics, missing-data/mock behavior, deployment
  cost, and promotion requirements;
- strict manifest schema, safe relative paths, bounded JSON, every-file size/hash
  validation, canonical feature-order comparison, and profile-aware startup gate;
- `dsctl model check`, with `--production` fail-closed behavior.

The validator hashes artifacts as opaque bytes and never deserializes joblib files.
The audit loaded the already-tracked joblib files once in the existing trusted E1
environment to read export metadata; untrusted/cloud/user pickle/joblib remains
forbidden.

## Pi runtime inspection

The existing Pi Python 3.12 environment loaded the exact hashed primary artifact
with AI Edge LiteRT 2.1.5 after TensorFlow 2.16.2 preload. It reported:

```text
input:  serving_default_sequence_input:0, float32, [1,4,40], signature [-1,4,40]
output: StatefulPartitionedCall_1:0, float32, [1,1], signature [-1,1]
I/O quantization tuple: scale 0.0, zero point 0
Flex delegate: 6 of 71 nodes in 3 partitions
delegates observed: TensorFlow Flex and XNNPACK
```

The unique operator set is frozen in the manifest. This is load/contract evidence,
not accuracy evidence.

## Newly explicit critical mismatch

The saved acceleration medians/winsor bounds are centered near gravity at `9.8`,
consistent with metres per second squared. The current MPU6050 firmware divides by
`16384`, producing acceleration in `g`, and the MQTT Pi bridge forwards that number
without conversion. Therefore the current real sensor path is incompatible with
the model's apparent training distribution. Because the training notebook/dataset
is absent, the unit remains marked `inferred`, and real scoring is blocked until it
is proven and versioned. Lower-back bar velocity/power semantics remain separately
unvalidated.

## Acceptance evidence

```text
.venv/bin/python -m pytest tests/unit tests/contract -q
29 passed in 5.42s
```

Tests prove current hashes/order/threshold, compatibility round-trip, tamper and
missing-artifact rejection, feature-order rejection, CLI results, development
startup acceptance for parity, and production startup rejection.

Expected compatibility result:

```text
compatibility_ready=true
production_ready=false
```

Production is blocked by unsigned status, compatibility-only release status,
incomplete provenance, unavailable evaluation, unknown units, and Flex operators.

## Rollback

The manifest/card/validator are additive. The model bytes and legacy inference path
were not modified. Removing the M1 files restores the prior prototype behavior but
also removes the fail-closed readiness evidence.
