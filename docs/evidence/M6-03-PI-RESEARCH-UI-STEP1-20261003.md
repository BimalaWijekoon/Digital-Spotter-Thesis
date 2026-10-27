# Pi-hosted research UI and V5 runtime — Step 1 (2026-10-03)

**Scope:** Install an isolated copy of the existing redesigned research page and
frozen V5 runtime on the Raspberry Pi. This is not M6-03 product acceptance,
camera playback, a live session, or scored analysis.

- Pi: `pidigitalspotter`, aarch64, Python 3.13.5. New owner-only directory:
  `~/digital-spotter-research-step1-20261003/`.
- Copied only `src/digital_spotter/web/static/`, the minimal V5 Python runtime
  modules, and `models/digital_spotter_v5/`. Existing Pi project directories,
  services, BLE state, camera setup, and firmware were not changed.
- Isolated virtual environment uses system `numpy 2.2.4` and installed
  `ai-edge-litert 2.2.0`; no full TensorFlow was installed.
- All 24 copied V5 artifact hashes passed `COPY_MANIFEST.csv` verification.
  `V5ModelRuntime` loaded the frozen built-in-ops FP32 interpreter. Its manifest
  reports version `digital_spotter_v5_scope_faithful`, shapes `(1,3,29)` and
  `(1,2)`, and `live_scoring_enabled=false`. No prediction was requested.
- The copied UI `index.html`, `v5_model.py`, and selected FP32 TFLite file have
  the same SHA-256 locally and on the Pi. Selected model SHA-256:
  `8a1d308c2596e571b2840673c1b437bbd2ccdbef5c590ebdb6dbbd40a7a4f9ab`.
- A temporary Python static server listens on `127.0.0.1:8766` only. A fresh
  SSH session observed the listener and HTTP 200 for `/ui-preview/` and its JS;
  `/api/research/session-status` returned 404. A separate-machine private SSH
  tunnel returned HTTP 200 for the page. No API mutation endpoint is active.
- The first transient user-systemd launch did not persist after SSH logout
  because `Linger=no`; it was replaced by a detached static process. No boot
  service was installed. Current-process status must be rechecked before use.

The UI still says research preview/analysis unavailable. Camera, wearable,
fixture predictions, set controls, and feedback were intentionally not activated.
There was no person, camera, mounted IMU, performance, or end-to-end test.
Rollback is to stop the exact static-server process after verifying its command
and port; the new deployment directory can be retained as a reversible snapshot.
