# Local model-retraining workspace

Root repository instructions still apply. Owner authorization on 2026-10-20
allows a new, isolated training revision here; it does not permit changes to FYP,
the frozen V5 package, the deployed model, or hardware configuration.

- `reference/` contains byte-for-byte historical copies. Do not edit, execute or
  import the archived generator, notebook or pipeline directly. Some scripts
  execute generation on import; others depend on historical paths, cached folds,
  source hashes and metrics. Use them as source references for new code.
- The owner disclosed synthetic dataset provenance. Historical participant,
  reviewer, calibration and accuracy claims in copied documents are not verified
  real-world evidence. See `docs/USER_V5_1_REVIEW.md`.
- Preserve existing vision, labels, IDs, context and phase order. Replace only
  the six IMU channels and recompute their derived magnitude in a new dataset.
  Do not silently repair labels or regenerate the existing vision columns.
- Write new generator/training code outside `reference/`. Generated datasets go
  in `data/generated/`; new runs and fitted artifacts go in `outputs/`.
- Fix and document the simulated units, sensor frame and phase reducer before
  generation. Unknown mounting parameters are assumptions, not measurements.
- Fit new preprocessing, weights, calibration and threshold. Never reuse old
  fitted state or count synthetic subjects as independently measured people.
- Keep all variants of the same source repetition/session together in splits.
  Fit any generator/calibration parameters using development data only.
- Use a separate training environment; do not modify the runtime `.venv` or
  install TensorFlow on the Pi. No training or hardware tests are part of setup.
- Do not promote a candidate into `models/`, change runtime scoring gates or
  deploy to the Pi without a separate integration decision and relevant evidence.
- Use only focused checks: copy integrity now; generation invariants and model
  contract checks when those components exist. No unrelated hardware matrix.
