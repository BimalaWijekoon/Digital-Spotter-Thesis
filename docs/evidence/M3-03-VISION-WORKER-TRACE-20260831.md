# M3-03 isolated vision-worker implementation trace

**Date:** 2026-08-31

**Package:** M3-03 / R13-D

**Status:** IN PROGRESS; implementation Steps 1-7 and the E3 camera-loss/recovery
gate complete, controlled-person acceptance deferred

**Evidence level:** V0 / E0 contract checks, E1 deterministic process isolation,
and a bounded E3 real Pi/camera adapter run

**Rollback:** remove the additive `vision` worker/replay modules and their tests,
then restore the spike's local frame primitives; the supported migration launcher
and legacy camera path are unchanged

## Step 1 outcome

The M3-03 implementation boundary is now explicit. The new worker will be added
under `src/digital_spotter/vision/` and will not be implemented inside the active
FastAPI dashboard. It will own Picamera2 and MediaPipe, keep at most one unprocessed
frame, construct canonical `PoseSample` events, and publish them over a bounded
local Unix socket. It will not own session state, rep detection, inference,
persistence, BLE, feedback, the browser overlay, or cloud synchronization.

R13-C provisionally selected Picamera2 as the sole camera owner. That decision is
sufficient to develop the worker behind a rollback switch, but M3-03 and ADR-014
cannot be marked accepted until the deferred controlled-person gate is completed.

## Step 2 outcome

The R13-C capture-time and capacity-one buffer behavior is now shared from the
canonical `digital_spotter.vision.frames` module. The spike imports that code
through a compatibility wrapper, so its accepted tests remain the rollback oracle
instead of maintaining a duplicate implementation.

`digital_spotter.vision.pose_events` now converts an adapter-neutral pose
evaluation into the existing M1 `PoseSample` contract. It enforces:

- a real measurement-time capture timestamp; arrival-only timestamps are rejected;
- processing completion after receipt and capture;
- explicit capacity-one overwrite counts;
- `good` only when a pose is found at or above the configured confidence;
- `vision_degraded` plus `pose_not_found` for no pose;
- `vision_degraded` plus `pose_low_visibility` below the threshold;
- no generated landmarks, angles, or confidence for a missing pose;
- the existing bounded, versioned vision event envelope.

This step adds no camera, MediaPipe, worker process, UDS connection, service,
database, API, UI, or Pi deployment behavior.

Focused deterministic validation:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose/test_vision_primitives.py \
  tests/test_02_pose/test_camera_spike.py \
  tests/contract/test_event_contracts.py -q

38 passed in 2.94s
```

The complete pose-focused and shared event-contract regression set then passed:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose \
  tests/contract/test_event_contracts.py -q --disable-warnings

55 passed, 2 warnings in 32.12s
git diff --check: PASS
```

The warnings are existing MediaPipe/protobuf diagnostics. No real camera, person,
mock pose generator, replay fixture, performance measurement, or Pi deployment was
used in Step 2.

## Step 3 outcome

`digital_spotter.vision.worker` now provides a one-shot, adapter-injected worker
lifecycle. It serially evaluates frames, delegates latest-frame/drop behavior to
the source, emits the canonical bounded pose envelope, records deterministic
counters, and always closes the evaluator and started source. A processing failure
sets the worker state to `failed` and is re-raised rather than silently falling
back.

`digital_spotter.vision.replay` provides a finite, size-bounded Y4M source and a
fixed pose evaluator for component tests. It accepts only the repository's
grayscale (`Cmono`) or 4:2:0 fixture formats, requires a one-to-one increasing
capture timestamp for every frame, performs no sleeping, and is permanently
identified as replay/simulated. Every pose event produced through this path is
therefore `quality=simulated`, including pose-missing and low-visibility cases;
the specific reason code remains available separately.

The deterministic checks prove:

- two independent runs produce byte-identical MessagePack envelopes;
- all three fixture frames are processed in order and output is explicitly
  simulated;
- frame/timestamp cardinality mismatch is rejected before the worker starts;
- an injected evaluator failure makes the worker fail and closes both adapters;
- an intentionally crashing spawned worker exits non-zero while an active
  disposable SQLite session remains active, its row counts remain unchanged, and
  `PRAGMA quick_check` returns `ok`.

The first focused run exposed that the existing Y4M fixture is `Cmono`; the parser
was narrowed to explicitly support bounded mono and 4:2:0 inputs. The corrected
focused gate then passed:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose/test_vision_worker.py \
  -q --disable-warnings --tb=short

4 passed in 4.81s
```

The combined affected regression set passed:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose \
  tests/replay/test_replay_fixtures.py \
  tests/core/test_local_sessions.py \
  tests/contract/test_event_contracts.py \
  -q --disable-warnings --tb=short

77 passed, 2 warnings in 43.43s
```

No real camera, MediaPipe inference, BLE/IMU device, UDS publisher, product
runtime, database migration, service installation, or Pi deployment was used or
changed in Step 3.

## Step 4 outcome

`digital_spotter.vision.adapters` is now the single implementation of the real
vision adapters:

- `Picamera2FrameSource` supervises the existing stdlib-only system-Python helper,
  validates a bounded private frame protocol, produces exposure-start monotonic
  timestamps, and fails with `camera_unavailable` after a configured consecutive
  timeout limit;
- the helper is executed directly rather than through `python -m`, preventing
  system Python from importing project-only MessagePack/Pydantic dependencies;
- its temporary Unix socket is mode `0600`, and an optional RTSP publication URL
  is restricted to loopback;
- `MediaPipePoseAdapter` requires the real MediaPipe/OpenCV runtime, converts all
  33 returned landmarks into the canonical contract, calculates visibility from
  the required shoulders/hips/knees/ankles, and has no mock/default-pose path;
- no joint angles are invented here. The adapter leaves `angles={}` until the
  canonical feature/angle semantics are frozen in the later model slice;
- camera unavailable, local protocol mismatch, pose-runtime unavailable, and pose
  inference failure are typed and surfaced in `VisionWorkerSummary` through a
  machine-readable reason code.

The R13-C camera benchmark now uses these canonical adapters through compatibility
wrappers, eliminating its duplicate Picamera2 and MediaPipe implementations.

Deterministic adapter tests cover bounded camera stalls, a fresh-owner recovery,
frame protocol/shape validation, all-33-landmark conversion, missing-pose output,
inference failure, cleanup, and loopback-only publication. A local smoke test also
ran the installed real MediaPipe 0.10.14 runtime on a blank synthetic image and
correctly returned no pose and no landmarks.

### E3 real Pi/camera result

An additive candidate was copied to:

```text
/home/pibimalawijekoon/digital-spotter-m303-step4-20260831
```

It did not replace or enable a product service. The bounded test used the real Pi
4, IMX219 camera, system-Python Picamera2, OpenCV 4.11.0, and MediaPipe 0.10.18.
No image or video frame was retained.

```text
camera-owner restart:                 3/3 PASS
canonical frames/events:              30/30
capture timestamps strictly monotonic: yes
worker state:                         stopped
read timeouts:                        0
processing failures:                  0
source frames dropped:                235
pose missing:                         30
quality=vision_degraded:              30
Pi throttling after test:             throttled=0x0
Pi temperature after test:            50.6 C
```

The available scene did not contain a usable person, so real landmark accuracy is
not claimed. The gate importantly produced explicit missing-pose events instead of
mock landmarks. Its 10.104-second wall interval, including worker/camera startup,
was 2.969 events/s. An immediate five-second run of the frozen R13-C comparator
measured 3.905 pose FPS and 268.895 ms p50 inference on the same current host,
also without throttling. Both are below the earlier historical 7.332 FPS result,
so performance variability remains open and this run is not a final throughput or
controlled-person acceptance claim.

The first E3 invocation failed before opening the camera because the direct helper
launcher omitted its required `os` import. That isolated code defect was restored,
the focused tests passed again, and the unchanged E3 command then passed. No camera
or device state was modified by the failed attempt.

Tracked evidence:

```text
docs/evidence/m3-03-step4-20260831/step4-real-camera-worker.json
  SHA256 c95263d31780556f6b721223ca30a3eea478a2e1c611615397d0ad9e621b10bf
docs/evidence/m3-03-step4-20260831/step4-real-camera-worker.log
  SHA256 a6471bcec892dc30fe25b378af8aee6f90fbbef06343d822d92d99434d4d4988
```

Final affected regression gate:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose \
  tests/replay/test_replay_fixtures.py \
  tests/core/test_local_sessions.py \
  tests/contract/test_event_contracts.py \
  -q --disable-warnings --tb=short

85 passed, 2 warnings in 50.12s
```

No BLE/IMU behavior, UDS event publisher, product runtime, database schema, API,
UI, systemd service, or cloud behavior was changed in Step 4.

## Step 5 outcome

`digital_spotter.vision.uds` now provides a separate vision event transport and a
background publisher. The publisher has a bounded queue (default four, accepted
range one to 16), applies drop-oldest semantics under backpressure, never blocks
the vision worker on socket I/O, accounts queue and transport drops separately,
and reconnects later events after bounded backoff. A send whose completion is
uncertain is not replayed.

The `AF_UNIX` stream uses the already accepted four-byte big-endian length plus
MessagePack framing and enforces the shared 64-KiB event limit. Before connecting,
the transport requires an actual Unix socket with no permissions for other users;
after connecting it can enforce a Linux peer-UID allow list with `SO_PEERCRED`.
Connection and send timeouts are bounded. No LAN listener or camera frame is
introduced.

`digital_spotter.vision.health` now constructs canonical `HealthState` envelopes
and supplies a monotonic consumer watchdog. The worker emits immediate
`starting`, `ready`, `degraded`, and `stopping` transitions and periodic heartbeat
events for unchanged state. Health includes typed reason codes, worker counters,
state age, last successful pose time, contract version, and explicit simulation
identity. Missing and low-visibility poses stay degraded; a replay success is
ready but remains simulated. Failure health publication is best-effort on the
exception path and cannot replace the original adapter error.

Focused E0/E1 validation covered canonical health round trips, lifecycle and
periodic heartbeats, watchdog expiry/order checks, real local Unix framing,
socket-mode and peer-UID rejection, malformed and oversized frame rejection,
deterministic drop-oldest backpressure, and reconnect after one failed send:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose/test_vision_health.py \
  tests/test_02_pose/test_vision_uds.py \
  tests/test_02_pose/test_vision_worker.py \
  tests/test_02_pose/test_vision_primitives.py \
  tests/contract/test_event_contracts.py \
  -q --disable-warnings --tb=short

40 passed in 5.82s
```

The broader affected regression set passed:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose \
  tests/replay/test_replay_fixtures.py \
  tests/core/test_local_sessions.py \
  tests/contract/test_event_contracts.py \
  -q --disable-warnings --tb=short

100 passed, 2 warnings in 29.23s
```

The complete repository test suite also passed:

```text
.venv/bin/python -m pytest tests -q --disable-warnings --tb=short

275 passed, 7 warnings in 56.19s
git diff --check: PASS
```

The separate legacy model validator was invoked but could not load the existing
model because this local Python environment contains neither TensorFlow nor
`ai_edge_litert`. It exited with `RuntimeError: No TFLite runtime could load the
model.` No dependency was installed and no model artifact was changed. This is an
existing model-runtime environment limitation, not evidence for or against the
Step 5 UDS/health behavior.

This was deterministic/local E0/E1 evidence. No Pi, real camera/person, BLE/IMU
hardware, performance measurement, database migration, service installation,
runtime switch, UI, or cloud behavior was used or changed in Step 5.

## Step 6 outcome

The canonical configuration now has an explicit `vision_pipeline` selection with
the values `legacy|canonical`. It defaults to `legacy`, so the existing
`scripts/run_server.py` dashboard and its `FrameProcessor` remain the rollback and
no canonical camera resource is constructed by default. Production configuration
fails closed unless the canonical pipeline and real vision/IMU adapters are
selected.

`digital_spotter.vision.runtime` is the standalone component entry point. After
the canonical and real-adapter gates pass, it assembles exactly one
`Picamera2FrameSource`, one real `MediaPipePoseAdapter`, and one bounded UDS
publisher used for both pose and health envelopes. Camera Python, camera ID,
socket path, optional loopback publication URL, queue size, and allowed core UID
are launch inputs. Production additionally requires an allowed core UID and an
absolute socket path. The console entry is `ds-vision-agent`; direct module
invocation remains available before package installation.

The runtime owns publisher-before-worker startup, signal-driven worker stop, and a
bounded publisher close. Step 5's sender loop was correspondingly tightened to
drain its already bounded queue during normal close so a final `stopping` health
event is not discarded merely because the worker ended. Worker failures still
close the publisher without replacing the original exception.

An E1 test joined the actual runtime, deterministic replay worker, background
publisher, and a mode-`0600` local Unix receiver. It received all three canonical
pose events and all five simulated lifecycle/quality health events, including the
final `stopping` state. Publisher results were eight sent, zero queue drops, and
zero transport drops. This validates orchestration and framing, not real camera or
person behavior. Separate selection tests prove the default legacy setting cannot
construct the canonical runtime and the explicit canonical setting can.

The affected Step 6 regression set passed:

```text
.venv/bin/python -m pytest \
  tests/unit/test_product_config.py \
  tests/test_02_pose \
  tests/replay/test_replay_fixtures.py \
  tests/core/test_local_sessions.py \
  tests/contract/test_event_contracts.py \
  -q --disable-warnings --tb=short

131 passed, 7 warnings in 44.63s
```

After updating the existing production-settings contract fixture for the new
explicit pipeline setting, the full repository regression gate passed:

```text
.venv/bin/python -m pytest tests -q --disable-warnings --tb=short

282 passed, 7 warnings
```

No dashboard, FastAPI route, legacy frame processor, core session/fusion logic,
database, Pi service, BLE/IMU firmware, UI, or cloud path was replaced. No Pi,
camera, or person was used. The canonical socket still needs a reviewed core
consumer and service deployment in later work; these are not claimed here.

## Step 7 outcome

The hash-matched Step 6 package and a bounded black-box recovery harness were
copied to the isolated Pi candidate directory:

```text
/home/pibimalawijekoon/digital-spotter-m303-step7-20260912
```

No installed service or existing Step 4 checkpoint was replaced. Preflight found
no dashboard, camera, MediaPipe, or stale Python process owning the camera. The
harness started a real canonical agent and mode-`0600` event receiver, waited for
a processed IMX219 frame event, and sent `SIGTERM` specifically to that agent's
direct `picamera2_helper.py` child. This process-level loss test did not disconnect
the CSI cable or retain any frame.

The failed owner emitted both degraded and stopping health with
`camera_unavailable`, then returned the CLI's expected failure exit code `2`. The
helper was reaped. A new canonical agent then acquired the same real camera,
emitted two more frame events, reported starting/ready/stopping health, and exited
cleanly with code `0`; its helper was also reaped. The event receiver reported no
decode errors and no related process remained after the test.

```text
environment:                         E3 Pi hardware bench
camera:                              real IMX219
hardware simulated:                  no
initial real frame events:           1
camera-unavailable degraded health:  yes
camera-unavailable stopping health:  yes
failure agent exit:                  2 (expected)
fresh-owner real frame events:       2
fresh-owner clean exit:              0
camera helpers reaped:               yes
event decode errors:                 0
frames retained:                     no
throttled before/after:              0x0 / 0x0
temperature before/after:            61.3 C / 63.3 C
result:                              PASS
```

The recovery agent summary recorded both of its real frame events as pose missing,
and no person was staged. This is correct fail-explicit behavior, but it does not
satisfy the remaining controlled full-body landmark/quality gate.

Sanitized evidence:

```text
docs/evidence/m3-03-step7-20260912/camera-loss-recovery.json
  SHA256 8d48f59ba5fe28480e483c5c6e8f38a1896fd622ddccfb2d9595d8bc8efe82d9
docs/evidence/m3-03-step7-20260912/failure-agent.stderr.log
  SHA256 8e45e519d7c0069c0dbf01678c6d2e4c182c8aea048697abccf52351499ca0e7
docs/evidence/m3-03-step7-20260912/recovery-agent.stdout.log
  SHA256 7ccb0ad9fbe7e483868d1e66c17658aab1bac495e44ee7d5c7d838d15c21d53a
```

The executed harness SHA256 was
`47a35bbe34ec62e34f0f4eb78babfbfc4452711d2652edaa085618c4079a31a9`.
After evidence collection, four duplicate identical log-write calls were removed;
the current harness SHA256 is
`ef1c07ee24f61570cd4df4c1798002a7dc9ff741e96932e6f3379c303280d0e6`.
No camera, process, event, assertion, or pass/fail behavior changed. The current
harness was recopied to the isolated Pi candidate for future use.

Post-run regression checks:

```text
.venv/bin/python -m pytest \
  tests/test_02_pose/test_vision_runtime.py \
  tests/test_02_pose/test_vision_uds.py \
  tests/test_02_pose/test_vision_worker.py \
  -q --disable-warnings --tb=short

19 passed in 4.89s
git diff --check: PASS
```

## Current runtime trace

The supported migration launcher currently follows this path:

```text
scripts/run_server.py
  -> scripts.dashboard.main:app
  -> SessionManager
  -> legacy FrameProcessor
  -> CameraReader
       -> MediaMTX RTSP first
       -> OpenCV/V4L2 fallbacks
  -> legacy PoseEngine
  -> AngleCalculator
  -> RepSegmenter
```

The additive canonical component can be selected explicitly and follows this
separate path:

```text
DS_VISION_PIPELINE=canonical + vision_adapter=real
  -> ds-vision-agent
  -> Picamera2FrameSource
  -> MediaPipePoseAdapter
  -> canonical PoseFrame + vision HealthState envelopes
  -> bounded UnixVisionEventTransport
```

No product-core socket consumer or systemd service exists yet. The legacy and
canonical camera owners must not be launched together.

The dashboard starts and stops the legacy `FrameProcessor` through
`/toggle-camera`. Its WebSocket, `/capture`, and MJPEG generator read private
`FrameProcessor` state directly. The legacy processor draws landmarks on the Pi
and encodes annotated frames as JPEG for `/video_feed`.

`FrameProcessor._processing_loop()` calls `process(frame)` but discards its return
value. No active caller dispatches that result to
`SessionManager.process_frame_result()`. Consequently the active camera path does
not automatically enter the legacy inference/session path. M3-03 will publish pose
events only; fusion, rep processing, and inference remain later packages.

The legacy path also uses wall-clock processing time, permits a random synthetic
pose fallback when MediaPipe is absent, and releases the pose estimator on stop
without recreating it on restart. None of those behaviors may enter the canonical
worker.

## Reusable canonical assets

- `digital_spotter.contracts.PoseSample` already defines the versioned pose event,
  monotonic capture/processing timestamps, bounded landmarks and angles, quality,
  latency, and dropped-frame count.
- `digital_spotter.vision.camera_spike.picamera2_capture_timestamp()` converts
  Picamera2 request metadata into exposure-start time in the Pi monotonic domain.
- `digital_spotter.vision.camera_spike.LatestFrameSlot` proves capacity-one
  overwrite semantics and explicit drop accounting.
- `digital_spotter.vision.camera_bench.Picamera2ProcessSource` and
  `picamera2_helper` prove the dual-stream camera configuration and the narrow
  local process boundary.
- The IMU `UnixEventPublisher` provides the accepted bounded length-prefixed UDS
  framing pattern. Vision may share the framing implementation, but it must have a
  separate socket and independent health/counters.
- The deterministic replay contract already distinguishes replay from real
  hardware and forbids replay data from becoming production evidence.

The R13-C helper code is measurement/spike code, not the finished service. Runtime
ownership, process supervision, structured health, restart classification, and
event publication must be implemented deliberately rather than renaming the
benchmark command.

## Fixed runtime boundary

```text
system Python 3.13 Picamera2 helper
  -> Picamera2 dual stream
       main: 1280x720 hardware H.264 (publication remains M3-04)
       lores: 640x360 YUV with exposure metadata
  -> capacity-one local frame handoff

project Python 3.12 vision worker
  -> real MediaPipe only; unavailable is explicit, never random mock
  -> canonical PoseSample + HealthState envelopes
  -> bounded local UDS publisher
  -> ds-core consumer in a later integration slice
```

The split runtime is retained initially because the installed Raspberry Pi camera
bindings target system Python 3.13 while the pinned MediaPipe environment is Python
3.12. The helper is local-only, sends no frames over the LAN, and must be stopped
and reaped with the worker. Aligning Python runtimes is not part of M3-03 unless
separate compatibility evidence supports it.

## Implementation slices

1. **Complete:** trace the active path, define the boundary, and freeze rollback.
2. **Complete:** promote production-neutral frame/timestamp primitives and
   canonical pose-event policy.
3. **Complete:** add deterministic replay and the adapter-injected worker lifecycle,
   including isolated crash evidence.
4. **Complete:** add the supervised Picamera2 adapter, real MediaPipe adapter, and
   explicit camera/pose failure states without silent fallback.
5. **Complete:** add a separate bounded vision UDS publisher, structured health
   counters, and watchdog heartbeat.
6. **Complete:** integrate the standalone component behind an explicit
   development/migration feature switch. The legacy processor remains the default
   rollback path until M3-03 acceptance evidence is complete.

Each slice is independently tested and reviewed before the next begins.

## Acceptance matrix defined before implementation

| Claim | Environment | Required evidence |
|---|---|---|
| Only newest frame is processed | E0 | deterministic overwrite/drop/close tests |
| Capture time is exposure based and monotonic | E0/E3 | metadata validation plus real Pi samples |
| Pose missing/low visibility is explicit | E0/E2/E3 | no synthetic fallback; quality/reason assertions |
| Pose event contract is bounded and versioned | E0 | contract round trip, malformed/range/size rejection |
| Replay cannot claim real hardware | E2 | deterministic replay identity and persistence denial |
| UDS is bounded and local | E1 | frame-size, peer/socket-mode, reconnect/backpressure tests |
| Worker crash leaves active SQLite state intact | E1 | disposable active session plus forced worker exit/integrity check |
| Camera loss and recovery are bounded | E3 | controlled stop/loss/restart with health transitions |
| Real-person pose meets the gate | E3 | controlled full-body comparison; currently deferred |

The deterministic and component checks can advance now. The final real-person row
remains mandatory before M3-03 is called complete.

## Explicit non-scope

- no UI redesign, WebRTC browser overlay, or MJPEG removal (M3-04/R14);
- no fusion, rep segmentation, feature building, or model inference (M4/R13-E/F);
- no BLE/ESP firmware or IMU changes;
- no database migration or high-rate frame persistence;
- no cloud/Firebase work;
- no raw still/video retention;
- no Pi service installation or enablement during the additive implementation
  slices.

## Assumptions and open evidence

- Picamera2 remains the provisional owner from R13-C/ADR-014.
- The real Pi currently supplies system Python Picamera2 and project-Python
  MediaPipe; package versions may drift and must be re-inventoried before E3.
- Browser glass-to-glass latency belongs to M3-04 and remains open.
- Controlled full-body pose accuracy/FPS remains physically deferred by the owner.
- No current model, sensor-semantic, database, security, or retention decision is
  changed by M3-03.
