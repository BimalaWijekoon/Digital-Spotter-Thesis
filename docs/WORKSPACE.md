# Digital Spotter workspace map

**Status:** M3-00 cleanup snapshot; full milestone acceptance remains pending
**Last reviewed:** 2026-09-15

This is the authoritative map of the retained workspace. The 2026-08-28 cleanup
removed generated firmware builds and superseded wearable implementations after
explicit owner approval. It did not delete product data, model assets, the working
Python environment, current tests, camera code, or prototype application behavior
that has not yet been migrated.

## Supported commands

Create or refresh the Linux development environment:

```bash
bash scripts/setup_dev.sh
```

Run the current migration launcher:

```bash
.venv/bin/python scripts/run_server.py
```

Run repository validation:

```bash
.venv/bin/python -m pytest tests -q
node --test tests/web/*.mjs
.venv/bin/python scripts/validate_model.py
git diff --check
```

Run the canonical R9 Pi adapter hardware gate from an installed/editable package:

```bash
ds-imu-r9-bench --duration 120
```

The active service entry point is `ds-imu-agent`. It uses the R9 plain-BLE
contract; the older security bench entry points are retained migration tooling,
not the active wearable path.

The launcher starts `scripts.dashboard.main:app` on the configured port, currently
`8000`. It remains a migration entry point, not the final component layout.

## Retained paths

| Path | Classification | Purpose and preservation boundary |
|---|---|---|
| `src/digital_spotter/` | Canonical product package | Active R11 Pi IMU adapter, contracts, configuration, persistence, and future product components belong here. |
| `deploy/` | Canonical deployment examples | Non-secret, reviewable service configuration; M3-04 currently contributes the loopback MediaMTX relay and matching product-config example, without installing either as a service. |
| `src/digital_spotter/web/static/` | Canonical browser primitives | Isolated, testable WHEP lifecycle, pose-clock matching, and overlay modules; not wired to the migration dashboard or an unauthenticated API. |
| `scripts/run_server.py` | Active migration entry point | Starts the current FastAPI prototype until the canonical API/core replaces it. |
| `digital_spotter.vision.runtime` / `ds-vision-agent` | Feature-gated canonical component entry point | Starts only when the typed pipeline switch is `canonical`; not installed as a Pi service yet. |
| `scripts/vision_step7_recovery.py` | Bounded E3 vision recovery harness | Terminates only the temporary agent-owned Picamera2 helper, verifies failure health and fresh-owner recovery, and retains no frames. |
| `scripts/dashboard/` | Active prototype | Preserves current camera, session, health, diagnostic, and feedback behavior until canonical replacements pass. |
| `firmware/esp32_c3_research/` | Active wearable firmware | R9 Arduino ESP32-C3/MPU6500 source, matching Pi validator, and compact golden PASS checkpoint. |
| `vision/` | Legacy migration source | Camera, pose, angles, and rep segmentation used by the active prototype. M3 replaces these behind the canonical vision boundary. |
| `inference/` | Legacy migration source | Existing feature, preprocessing, sequence, and model runtime behavior. M4/M5 must prove parity before retirement. |
| `integration/` | Legacy migration source | Existing session orchestration and lifecycle behavior. M4 replaces it with explicit core state machines. |
| `database/` | Legacy migration source | Existing SQLite schema and queries. Preserve compatibility while consumers migrate to `src/digital_spotter/persistence/`. |
| `hardware/` | Legacy migration source | Pi RGB LED and buzzer behavior that must remain represented in the final feedback path. |
| `imu/` | Legacy migration source | Cloud-MQTT Pi bridge still imported by the dashboard; it is not the target sensor transport and retires after R11/caller migration. |
| `models/` | Protected product artifacts | Current model/preprocessing assets and documentation. Do not rename or delete without model-contract evidence. |
| `training/v5_imu_retraining/` | Owner-approved isolated local research training | M5-R01 copies FYP references without changing them; data/reference/run folders are Git-ignored. Not a Pi runtime component or an activated replacement model. |
| `models/digital_spotter_v5_imu_synthetic_r1/` | Frozen final research package for the retrained V5 candidate | Compact Keras/TFLite model, preprocessing, calibration, threshold, fixture, manifest and hashes. Synthetic training provenance; reference/demo use only until live scoring is independently verified. |
| `tests/` | Mixed validation suite | Canonical tests coexist with prototype compatibility tests until migration is complete. |
| `api/` and `frontend/` | Historical prototype still under test | Older Flask/Socket.IO application and browser UI; preserve until test/behavior parity is mapped. |
| `TEST DASBOARD/` | Historical experiment | Retained because its exact retirement gate has not passed; it is not a supported entry point. |
| `data/` and `logs/` | Local runtime state | Ignored mutable data. Never remove without a separate backup/data decision. |
| `.venv/` | Local development environment | Ignored and reproducible from `uv.lock`; retained at the owner's request. |

## Removed on 2026-08-28

The owner explicitly approved permanent removal of:

- about 464 MB of generated Arduino build directories;
- R1-R8 firmware checkpoint binaries and stage-specific validators;
- the failed R9 candidate and reproducible R9 ELF/map/merged/build artifacts;
- abandoned ESP-IDF secure-recovery firmware;
- legacy ESP32-C3 Wi-Fi/HiveMQ firmware and its ignored local credential file;
- the original one-off BLE diagnostic sketch;
- stale SSH-key setup text, obsolete JSON plans, and the obsolete placeholder
  tracker;
- the superseded secure-BLE implementation evidence document.

R9 retains its directly flashable application binary, exact source, validator,
configuration, partition description, serial/Pi logs, physical observation, and
hash manifest. Previously tracked deleted files remain recoverable from Git commit
`326651e`; untracked experimental firmware was intentionally not archived.

## Generated paths

The repository ignores Python caches, coverage output, package/build directories,
and nested firmware build products. In particular, future Arduino build folders,
ELF/map files, merged images, bootloader copies, and partition binaries must not be
committed. A deliberately retained golden application `.bin` remains allowed.

## Retirement rule

The current cleanup does not authorize deleting the remaining camera, model,
database, dashboard, API, or UI migration sources. Those paths still have active
callers or tests. Retire them only through M8-04 after their behavior is mapped,
the canonical replacement passes, rollback exists, and the owner approves the
exact deletion set.
