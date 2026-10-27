# Digital Spotter

Digital Spotter is an edge-first exercise analysis product for Raspberry Pi 4B.
It combines camera pose estimation with a wireless ESP32-C3 IMU, performs rep
analysis locally, and asynchronously synchronizes selected results to the cloud.

> The repository currently contains a working prototype and several historical
> implementations. The production architecture is defined, but its migration is
> not yet complete. Do not describe this repository as production-ready.

## Thesis research snapshot — 2026-10-28

The current research appliance integrates the Pi camera, an assembled wireless
ESP32-C3/MPU6500 lower-back wearable, local BLE, a browser dashboard, repetition
tracking, an explicitly synthetic-training V5 model package, and Pi/wearable
LED-buzzer feedback. The latest recorded Pi release is
`digital-spotter-research-appliance-20261027-r15`.

Owner-reported gym testing covered five anonymous participants, ten sets and 42
attempted squat/deadlift repetitions:

- 36/42 repetitions detected (85.7%);
- 31/36 detected repetitions classified correctly (86.1%);
- bad-form precision 50.0%, recall 40.0%, F1 44.4%;
- continuous camera and 50 Hz IMU reported for all ten sets, with no BLE
  disconnect reported.

These small-sample field results are owner observations without retained raw
probabilities or synchronized machine logs. The model was trained on generated
multimodal data and is not clinically or statistically validated. See
[the thesis evidence summary](docs/evidence/Digital_Spotter_Thesis_Latest_Modifications_20261027.md),
[the completed questionnaire](docs/evidence/Gym_Spotter_Final_Real_World_Testing_Questionnaire.xlsx),
and [the retraining report](training/v5_imu_retraining/docs/TRAINING_REPORT.md).

The frozen final candidate package is committed under
`models/digital_spotter_v5_imu_synthetic_r1/`. It includes the built-in-ops
TFLite model, Keras model, preprocessing, calibration, threshold, fixture,
manifest and hashes. Copied datasets, fold checkpoints and training caches are
intentionally excluded.

Validate the compact package with:

```bash
.venv/bin/python scripts/validate_v5_candidate.py \
  --package models/digital_spotter_v5_imu_synthetic_r1
```

## Fixed product hardware

- Raspberry Pi 4 Model B with 8 GB RAM
- Raspberry Pi Camera Module v2 / IMX219, unless a later hardware decision changes it
- Separate lower-back wearable containing an ESP32-C3 and MPU6500
- Wireless wearable-to-Pi communication; no cable between the athlete and Pi
- Active cooling and a product-quality power supply for the Pi

The lower-back mounting position and MPU6500 are accepted product inputs. Physical
testing must still freeze orientation, attachment repeatability, sensor range and
filtering, calibration, enclosure, battery, and antenna behavior. Lower-back motion
must not be represented as direct barbell velocity or power without an independently
validated derivation.

## Target system

```text
ESP32-C3 IMU ---- local BLE ----> Pi IMU agent ---+
                                                |
Pi camera --> vision worker --> pose samples -->+--> fusion/rep/model core
                                                |           |
                                                |           +--> SQLite outbox
                                                |                        |
Browser <-- WebRTC + WebSocket/API -------------+                        +--> cloud sync
```

The real-time exercise loop is local. Wi-Fi and Firebase are not dependencies for
rep detection, scoring, feedback, or session completion.

The active reliability-first research firmware uses plain local BLE with strict
device-name/address checks; it is not the target production-secure BLE design.

## Start here

| Document | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Mandatory operating instructions for contributors and agents |
| [PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) | Product scope and acceptance criteria |
| [CURRENT_STATE.md](docs/CURRENT_STATE.md) | Evidence-backed description of the prototype today |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Target edge, wireless, cloud, and deployment architecture |
| [INTERFACES.md](docs/INTERFACES.md) | BLE, event, API, persistence, and cloud contracts |
| [SECURITY.md](docs/SECURITY.md) | Threat model, required controls, and credential handling |
| [RULES.md](RULES.md) | Non-negotiable engineering rules |
| [PLAN.md](PLAN.md) | Ordered zero-to-product implementation plan and gates |
| [BLE_RESEARCH_BRINGUP_PLAN.md](docs/BLE_RESEARCH_BRINGUP_PLAN.md) | Active step-by-step Arduino-to-research BLE/IMU ladder |
| [TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Test layers, hardware tests, and release evidence |
| [OPERATIONS.md](docs/OPERATIONS.md) | Deployment, observability, updates, and recovery |
| [DECISIONS.md](docs/DECISIONS.md) | Architecture decisions and unresolved decisions |
| [WORKSPACE.md](docs/WORKSPACE.md) | Canonical commands and status of every major repository path |

## Current prototype entry point

Create the isolated Linux development environment and install the pinned prototype
dependencies:

```bash
bash scripts/setup_dev.sh
```

The setup also installs the checksum-verified MediaPipe Heavy asset that the
upstream package otherwise downloads during startup. Then launch the newer
dashboard with:

```bash
.venv/bin/python scripts/run_server.py
```

It starts `scripts.dashboard.main:app` with Uvicorn on port `8000`. This is a
prototype monolith, not the final service layout.

Run the existing local test suite with:

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/validate_model.py
```

The ignored legacy `venv/` directory, if recreated, is a Windows environment and
must not be used from WSL/Linux. The model validator additionally needs the current TensorFlow/Flex
runtime, which remains outside the small canonical core lock; M1-03 manifests that
compatibility runtime and M5 replaces it after parity evidence.

Hardware-dependent checks must run on the Pi and must state whether the real
camera, real ESP32-C3, real IMU, and real model were used. Mock mode is never
release evidence.

## Canonical product package foundation

M1 migration code now lives under `src/digital_spotter/`; the old paths remain for
behavioral parity and rollback. Create the small locked package environment with:

```bash
UV_CACHE_DIR=/tmp/digital-spotter-uv-cache uv sync --frozen
.venv/bin/dsctl version
.venv/bin/dsctl config check --config config.example.toml
.venv/bin/python -m pytest tests/unit tests/contract tests/replay tests/persistence -q
```

`config.example.toml` is non-secret and development-only. A production profile
fails closed until real adapters and provisioned identity, signed-model manifest,
TLS files, explicit HTTPS origins, and absolute state paths are supplied. Do not
place key contents or service-account JSON in TOML or Git.

The M1 SQLite foundation is operator-accessible without touching the legacy runtime:

```bash
.venv/bin/dsctl database status --database /path/to/digital-spotter.sqlite3
.venv/bin/dsctl database migrate --database /path/to/digital-spotter.sqlite3 \
  --backup-dir /path/to/protected/backups
.venv/bin/dsctl database backup --database /path/to/digital-spotter.sqlite3 \
  --output /path/to/protected/backups/digital-spotter.sqlite3
.venv/bin/dsctl database restore --backup /path/to/protected/backups/digital-spotter.sqlite3 \
  --database /new/path/digital-spotter.sqlite3
```

Existing databases cannot receive pending migrations without an online backup.
Restore verifies its manifest and refuses to overwrite a target. Do not migrate the
live Pi database until its writer services are stopped and the deployment gate is
explicitly approved.

## Current repository areas

The complete authoritative path classification is maintained in
[WORKSPACE.md](docs/WORKSPACE.md). In summary:

- `scripts/dashboard/`: active FastAPI dashboard prototype
- `vision/`: OpenCV/MediaPipe pose and rep segmentation prototype
- `imu/`: legacy cloud-MQTT Pi bridge retained only until the canonical BLE adapter replaces its remaining callers
- `inference/`: feature preprocessing and TFLite inference
- `integration/`: session orchestration prototype
- `database/`: local SQLite schema and queries
- `firmware/esp32_c3_research/`: active Arduino ESP32-C3/MPU6500 BLE research firmware and R9 validator
- `api/` and `frontend/`: older Flask/dashboard implementation
- `TEST DASBOARD/`: earlier experimental dashboard

The approved 2026-08-28 cleanup removed superseded firmware and generated build
artifacts. Remaining prototype application paths stay until their behavior has
been migrated and the relevant gate in [PLAN.md](PLAN.md) has passed.

## Security warning

An MQTT credential was previously present in `.env.example`. The tracked example
has been sanitized, but the real broker credential must be revoked and rotated;
editing Git does not invalidate an exposed secret. See [SECURITY.md](docs/SECURITY.md).
