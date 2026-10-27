# V5 IMU retraining workspace

Prepared 2026-10-20 under owner authorization. This is a **local PC/WSL research
workspace**, not a Pi runtime component. Candidates are not activated automatically.

## Current state

- 37 relevant source/reference files copied from `/mnt/g/FYP/` (4,919,221 bytes).
- Dataset baseline: **6,054 rows, 2,018 complete three-phase repetitions**.
- FYP and `models/digital_spotter_v5/` remain untouched.
- IMU-only synthetic R1 generated under `data/generated/imu_r1_20261020/`:
  all 56 protected columns unchanged, five focused generator tests passed.
- M5-R03 uses only the final V5 LSTM architecture with original nested grouped
  CV. See `STATE.md` and the run's `RUN_STATUS.json` for actual progress.
- No dependencies installed or physical device accessed. Generation and fitting
  are offline synthetic research experiments, not real-world calibration.

`COPY_MANIFEST.csv` records each exact source, destination, size and SHA256.
Package files are checked against the original package manifest where listed;
the package manifest itself is copied and checked by its captured source hash.

## Layout

```text
reference/                 Local, immutable historical copies (Git-ignored)
  dataset/                 master, vision, IMU and synthetic subject metadata
  pipeline/                V5 training, preprocessing and export source closure
  notebooks/               Original V5 notebook, reference only
  generators/              Historical V1 generator, not the exact V2 generator
  vision/                  Existing recorded-video feature extractor
  v5_package/              Contract, final policy metadata and version evidence
docs/USER_V5_1_REVIEW.md    Review of the generator pasted by the owner
docs/IMU_GENERATION_SPEC.md Explicit physics/units/phase assumptions
docs/IMU_GENERATION_REPORT.md Scoped generation result and remaining limitations
config/                   Simulation priors and owner-selected CV training plan
imu_generator.py          IMU-only generator (not the historical generator)
v5_training.py            Final V5 architecture only; isolated, resumable CV
export_v5.py              One FP32 built-in TFLite export and numerical parity
requirements-training.txt Exact observed PC training dependency versions
data/generated/           New candidate bundles; never active runtime assets
outputs/                  New fitted states, models, logs and synthetic metrics
scripts/verify_copy.py     Read-only copy/source-integrity check
COPY_MANIFEST.csv          Provenance of all 37 copied files
STATE.md                   Resumable work status
```

New code, generated data and training outputs will be added separately. No
virtual environment, raw videos, old checkpoints, old fitted scalers or model
weights were copied. The empty FYP `requirements.txt` was not treated as an
installable dependency definition. Historical versions are recorded under
`reference/environment.json` and `reference/v5_package/saved_models/`.

## Verify the setup

From the main repository:

```bash
python3 training/v5_imu_retraining/scripts/verify_copy.py --check-source
```

Omit `--check-source` if FYP is unavailable; that verifies local copies against
the recorded hashes only. This command does not import the training code,
generate data, load a model or access hardware.

## Generate another new candidate (no overwrite)

```bash
.venv/bin/python -m training.v5_imu_retraining.imu_generator \
  --output training/v5_imu_retraining/data/generated/NEW_RUN_NAME
```

The existing R1 output is preserved; a new name is required. Configuration
contains unmeasured priors. Do not describe another run as real-world calibrated.

## Training procedure

See `docs/TRAINING_PROCEDURE.md`. The original PC training interpreter can run
the new local code without modifying its environment or executing FYP scripts:

```bash
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=-1 OPENBLAS_NUM_THREADS=2 \
  /mnt/g/FYP/outputs/v5/.venv-py312/bin/python -u -B \
  -m training.v5_imu_retraining.v5_training \
  --output training/v5_imu_retraining/outputs/NEW_RUN_NAME
```

An existing output is refused. `--resume` is allowed only for the identical
source/data/configuration hash contract; completed fit hashes are checked.
An interrupted fit directory is retained with an interruption suffix. Do not
edit the training source halfway through a resumable run.

After all 26 fits finish:

```bash
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=-1 OPENBLAS_NUM_THREADS=2 \
  /mnt/g/FYP/outputs/v5/.venv-py312/bin/python -u -B \
  -m training.v5_imu_retraining.export_v5 \
  --run training/v5_imu_retraining/outputs/NEW_RUN_NAME
```

Export checks the serialized preprocessing, reloaded Keras predictions and
one FP32 built-in TFLite file. The original interpreter is not a runtime/Pi
dependency. All output stays here, Git-ignored. Evaluate real mounted data
before claiming real-world accuracy or replacing the active runtime model.

## Provenance correction

The owner disclosed that the training dataset is synthetic, informed by recorded
video observations and IMU research. Treat all copied metadata, subject IDs and
reviewer fields in that light. Copied historical documents retain their original
claims for traceability; those claims are not adopted as verified facts here.
The V1 generator is only a historical reference. The pasted v5.1 generator has
not been demonstrated to reproduce the final baseline dataset.

Synthetic data can support research and engineering experiments. Changing the
generator does not by itself establish real-world predictive accuracy. No new
model version is deployable merely because training or conversion succeeds.
