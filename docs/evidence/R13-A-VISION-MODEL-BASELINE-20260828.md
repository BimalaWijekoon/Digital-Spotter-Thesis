# R13-A vision/model contract and migration baseline

**Date:** 2026-08-28

**Package:** R13-A

**Status:** PASS

**Validation:** V0 in E0/E2; no hardware or person data used

**Rollback:** `ble-r12-local-sessions-pass` / commit `464da22543af00d483a9f88000c19f707567ed61`

## Scope and outcome

R13-A is a read-only characterization and contract checkpoint before changing the
camera, fusion, feature, or inference runtime. It freezes the current producers,
consumers, artifacts, and deterministic replay boundary so later R13 packages can
replace one layer at a time without calling prototype behavior product-ready.

R13-A changed no camera, BLE, firmware, GPIO, session, database, model, API, or UI
runtime behavior. It did not choose the final camera owner, alter the 40-feature
contract, reinterpret the lower-back IMU, or run the compatibility model.

The machine-readable snapshot is
`docs/evidence/r13a-baseline-manifest.json`. It binds 20 relevant source files, the
model manifest, and the synthetic replay artifacts to SHA256 identities. The
checkpoint validator is `scripts/validate_r13a_baseline.py`.

## Current end-to-end trace

The supported migration launcher is:

```text
scripts/run_server.py
  -> scripts.dashboard.main:app
```

The current live prototype branches instead of having one canonical processing
path:

```text
camera control/API
  -> legacy FrameProcessor
  -> CameraReader (RTSP first, V4L2 fallback)
  -> legacy MediaPipe PoseEngine
  -> AngleCalculator + RepSegmenter
  -> latest annotated frame for Python MJPEG

manual POST /predict
  -> a second hand-written 40-feature builder
  -> hand-written three-phase + delta matrix
  -> legacy LSTMRunner
  -> Pi GPIO and legacy MQTT result feedback

legacy SessionManager.process_frame_result (not dispatched by FrameProcessor)
  -> latest legacy MQTT/mock IMU sample at rep-event arrival
  -> legacy FeatureEngineer + SequenceBuffer
  -> legacy LSTMRunner
  -> legacy database row and callback

R9 BLE agent
  -> canonical IMUSample envelope
  -> R12 session/core UDS receiver
  -> bounded in-memory IMU ring + aggregate-only SQLite summary
```

The last branch is the proven R11/R12 path. It is not yet connected to the legacy
camera/inference branch. `FrameProcessor._processing_loop()` discards the return
from `process()`, and repository search finds no caller of
`SessionManager.process_frame_result()`. Therefore the active camera does not
automatically drive the legacy session inference path.

## Contracts retained for migration

R13 continues to use the already executable M1 contracts:

- `PoseSample` and `IMUSample` carry Pi monotonic measurement timestamps;
- `FusedSample` represents explicit `good`, `vision_degraded`, `imu_degraded`,
  `unsynchronized`, or `unavailable` quality rather than silent substitution;
- missing/stale IMU must not be replaced with zeros for production scoring;
- replay data is always synthetic, non-real, and non-persistable;
- the current compatibility input remains `(1, 4, 40)`: three named phase rows
  followed by phase-3 minus phase-1;
- feature order is exactly `COMPATIBILITY_FEATURE_ORDER`;
- the manifest threshold is `0.35947465896606445`;
- lower-back MPU6500 data is not direct barbell velocity or power evidence.

These are compatibility boundaries, not approval of the current model or its
feature semantics.

## Confirmed blockers

| ID | Confirmed current fact | Required later gate |
|---|---|---|
| B01 | No live dispatch from processed camera result to session processing | R13-D automatic-dispatch regression |
| B02 | Legacy fusion reads the latest IMU at rep-event arrival | R13-B measurement-time clock/alignment |
| B03 | `/predict` and `FeatureEngineer` separately construct 40 features and disagree on formulas | R13-F one canonical golden feature builder |
| B04 | Missing pose/IMU/artifacts and runtime failures can become zeros, random mocks, or a default good-form result | R13-D/F explicit unavailable/degraded behavior |
| B05 | Camera stop releases the pose owner but start does not recreate it | R13-C/D camera lifecycle gate |
| B06 | Legacy frame timestamps use wall-clock processing time, not monotonic capture time | R13-C/D capture contract |
| B07 | Model is compatibility-only, unsigned, unevaluated, provenance-incomplete, Flex-dependent, and has no approved exercise | R13-F shadow-only gate; M5 for production |
| B08 | Bar velocity, bar power, jerk, and velocity-deceleration semantics are unvalidated for a lower-back IMU | owner-approved future feature/model decision |
| B09 | MediaPipe/OpenCV/model runtimes are not in the canonical production dependency lock | R13-C/F Pi dependency decision |

Additional facts kept visible:

- `config/config.py` rounds the manifest threshold to `0.359`;
- the legacy MQTT bridge can silently switch to random mock IMU data;
- the pose engine can silently switch to random mock landmarks;
- `SequenceBuffer` pads/truncates wrong-length feature vectors with zeros;
- `LSTMRunner` may return a mock/default result after model load or inference
  failure;
- existing pose/inference tests permit mocks and therefore do not prove real
  person tracking or real model latency;
- the current model requires TensorFlow Flex. This WSL environment has no
  `tensorflow`, `ai_edge_litert`, or `tflite_runtime`, so real inference was not
  attempted here.

## Ordered R13 slices

R13 must progress without combining architecture replacement and UI redesign:

1. **R13-B — measurement-time alignment:** map R9 sensor time to Pi monotonic time,
   expose clock quality/reset/gap state, and prove deterministic alignment.
2. **R13-C — camera ownership spike:** benchmark the two accepted Pi camera-owner
   candidates with a person, then resolve ADR-014 from measured evidence.
3. **R13-D — canonical vision worker:** one restartable camera/pose owner, bounded
   latest-frame semantics, monotonic capture timestamps, explicit pose quality,
   and automatic event dispatch.
4. **R13-E — fusion and rep pipeline:** align bounded Pose/IMU streams, publish
   explicit degraded states, and segment reps without network-arrival fusion.
5. **R13-F — canonical compatibility inference:** one golden feature/preprocessing
   path; reject missing modalities; compatibility model is shadow-only and cannot
   persist user-facing analysis or trigger wearable feedback as production truth.
6. **R13-G — offline integration gate:** real camera/person + real R9/R11 IMU +
   R12 SQLite, with one result per completed rep, failure modes, latency/resource
   evidence, and no cloud dependency.

R14 responsive browser/PWA redesign starts only after R13 establishes stable API
and event boundaries.

## Validation evidence

Commands for this checkpoint:

```bash
.venv/bin/python scripts/validate_r13a_baseline.py
.venv/bin/python -m pytest \
  tests/contract/test_event_contracts.py \
  tests/contract/test_model_manifest.py \
  tests/replay/test_replay_fixtures.py -q
.venv/bin/python -m pytest tests -q
git diff --check
```

The validator is designed to fail if this specific baseline changes; it is
checkpoint evidence, not a permanent assertion that the legacy sources must never
be replaced.

Observed results:

- baseline validator: `PASS`; 20 source files verified, model artifacts/order/
  shape/threshold valid for compatibility, production readiness `false`, replay
  event count 7 with the expected digest and no failures;
- focused contract/replay tests: `34 passed in 5.16s`;
- full regression suite: `215 passed, 7 warnings in 118.02s`;
- `git diff --check`: passed with no output.

The seven warnings are existing Python/FastAPI deprecations; the model runtime also
emitted its existing MediaPipe feedback-manager diagnostic. Neither is treated as
real model execution or person-in-frame evidence.

## Evidence classification

- **Real hardware:** none used for R13-A.
- **Mock data:** no random mock runtime executed.
- **Replay:** the existing immutable synthetic, no-person replay fixture was used.
- **Performance:** no new performance measurement; prior R9/R11/R12 hardware
  evidence remains historical and unchanged.
- **Security/data:** no credential, security profile, schema, or user-data change.
- **Production claim:** none. The current model remains blocked from production.
