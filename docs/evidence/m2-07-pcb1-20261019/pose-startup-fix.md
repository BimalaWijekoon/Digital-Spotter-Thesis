# Pose startup isolation — M2-07 follow-up

Dates: 2026-10-19–20. Status: scoped pose-startup fix PASS on the Pi; the
controlled-person/mounted-model gate remains open.

## Failure evidence and cause

The first pose-enabled MediaMTX request timed out after 30 seconds, before
Picamera2 started. The preserved traceback in the Pi's initial
`live/camera-relay.log` shows `mediapipe.tasks.python.core.optional_dependencies`
importing `tensorflow.tools.docs`, followed by TensorFlow/Keras/scikit-learn/
SciPy imports. MediaPipe was 0.10.18; its shared environment enabled
`include-system-site-packages=true` and exposed the full model environment.

A targeted pre-change environment assertion failed immediately:
`assert importlib.util.find_spec('tensorflow') is None`. No camera or TensorFlow
was imported to establish this failure. The launcher regression also failed
before the patch because the hook still executed the core interpreter rather
than the explicitly selected pose interpreter.

The upstream [MediaPipe 0.10.18 optional-dependency source](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v0.10.18/mediapipe/tasks/python/core/optional_dependencies.py)
confirms TensorFlow is optional for documentation generation, not a required
pose dependency. [Python's venv documentation](https://docs.python.org/3.12/library/venv.html)
describes the package isolation used here. This diagnosis is based on both the
installed source and the actual Pi traceback, not an assumption that the camera
or BLE transport is broken.

## Scoped change

- `scripts/research_camera_publisher.sh`: when pose delivery is enabled, require
  and execute `DS_RESEARCH_POSE_PYTHON`. Camera-only mode stays unchanged.
- `deploy/requirements-pi-vision.txt`: pinned Python 3.12/aarch64 pose dependencies;
  keep MediaPipe 0.10.18, OpenCV 4.11.0.86 and NumPy 1.26.4 unchanged. Bound the
  declared JAX dependencies to the NumPy-1.x-compatible line.
- New Pi `.venv-pose`, created without system site-packages. No existing Python
  environment or installed TensorFlow/model library is removed or modified.
- Picamera2 remains in the system-Python helper; one vision worker still owns
  camera capture, H.264 publication and pose evaluation. No pose thresholds,
  feature formulas, model artifacts or BLE firmware changed.

The original Pi hook is preserved at
`~/pcb1-before-20261019.vi9L9t/research_camera_publisher.sh.before-pose-isolation`,
SHA256 `c51bca13b633996820795e19f2a1564b9ed4c42837d49aca5e27ee9f0cc9c3d5`.
The relay's 30-second deadline is unchanged.

## Verification

- Focused launcher checks: **3 passed in 0.38 s**. They cover the distinct pose
  interpreter, a missing required pose interpreter and unchanged camera-only
  behavior. The interpreter-selection check first failed against the old hook.
- Shell syntax and `git diff --check`: PASS.
- Pi isolated environment: no TensorFlow module visible/imported; the real
  MediaPipe 0.10.18 pose estimator initialized in **4.999 s**, with the unchanged
  complexity-1 / detection-0.7 / tracking-0.7 configuration. No camera was opened
  for that import check. `pip check` then reported no broken requirements and no
  invalid-metadata warnings. The initial installation had been interrupted
  before the Pi restart; it was completed only inside the new `.venv-pose`.
- The exact installed dependency snapshot is pinned in
  `deploy/requirements-pi-vision.txt`. All other environments remain unchanged.
- One real on-demand browser check opened H.264 video approximately nine seconds
  after the viewer request, within the unchanged 30-second deadline. Chromium
  decoded 1280×720 video, advanced media time by 3.048 s in the short observation,
  and stopped cleanly. Its dropped-frame counter is retained; this is not a
  display-loss/latency benchmark.
- The same normal session received real MediaPipe pose events and a bounded
  100-sample IMU window: sequences 836–935, zero gaps within that window and
  1,979.29 ms capture span. No fake pose or IMU data was used. The BLE agent
  reported the expected connection/GATT contract verified; no separate transport
  or reconnect matrix was run.
- On-demand shutdown recorded **94 real frames / 94 pose events**, zero
  processing failures, zero read timeouts and zero health-publication failures.
  All 94 frames reported pose not found; **person detection/pose accuracy has
  not passed**. The source dropped 310 frames under latest-frame semantics.
  No person-in-frame performance claim is made. Pi `throttled=0x0`, 56.9 C.

Evidence: [environment check](pose-environment-check.log),
[browser check](pose-browser-check.json),
[simultaneous pose/IMU status](pose-imu-joint-check.json),
[worker shutdown summary](pose-worker-summary-20261020.json).
The `cpuinfo` SVE capability warning and MediaPipe feedback-tensor warnings are
retained in the import log; they did not prevent initialization or the real run.
The "TensorFlow Lite XNNPACK" backend log is MediaPipe's inference backend, not
an import of the full Python TensorFlow package.

Current runtime state is under `~/pcb1-before-20261019.vi9L9t/live-20261020/`.
Yesterday's database/sockets/logs were preserved rather than overwritten. The
existing dashboard/core, single BLE receiver and corrected on-demand relay were
restarted after the Pi reboot; they are still detached research processes, not
the final boot launcher. Pose and IMU samples remain truthfully degraded where
person visibility/calibration are absent. V5 scoring is still disabled.

No endurance, BLE reconnect matrix, new pairing, human exercise test, dataset
test or model benchmark is part of this fix. The host launcher checks use
command stand-ins, not simulated sensor or pose data. The mounted-person gate,
calibration, live V5 eligibility and owner-observed PCB cues remain separate.

## Rollback and scope

Stop only the identified relay/vision process, restore the backed-up hook if
needed, and start the prior camera-only launcher without the vision socket.
Existing core/BLE source, previous summary databases and SSH settings are intact.
The isolated environment can remain unused; no cleanup/deletion is required.
No system/network/BlueZ configuration, credentials, database migration or raw
video retention is introduced. Changes are uncommitted and unpushed.
