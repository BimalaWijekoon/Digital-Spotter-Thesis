# M6-D02 — Actual V5 calculation from frozen synthetic replay

2026-10-23. PASS for the local reference-only model/UI slice, not the complete
Pi/wearable viva demonstration or real-world classifier validation.

## Delivered

- Existing Demo tab now calculates after each completed six-second animated rep.
  Pause/resume/reset remain; a run has three reps. The same selected fixture is
  reused on each rep, not represented as three new measured examples.
- Real canonical V5 preprocessing, LiteRT inference, frozen Platt calibration
  and threshold. The result panel uses the actual response, not the form selector.
  A disagreement with the source label is retained and shown.
- Load is the recorded replay context, read-only. Animation is illustrative and
  does not feed MediaPipe or construct model features. Right-hand IMU plots remain
  separate real wearable telemetry; this local process has no hardware producer.
- Opt-in `--enable-demo` on the existing core launcher, dedicated private API
  and exact Origin/header guard. One core-loop interpreter owner. Demo is denied
  during a live workout or person-pose test. No sensor injection, actuator command,
  scored workout record or production-readiness change.

## Source and integrity

Read-only package:
`training/v5_imu_retraining/outputs/main_v5_imu_r1_20261020/package/`.
Version `digital_spotter_v5_imu_synthetic_r1`.
The existing candidate loader verifies the package inventory and contract.
Demo additionally anchors the fixed `inference_fixture.npz` SHA256:
`95c4064fda91714272f57bc8afb397fae895ce39750abf5abc8e70238db04106`.

Source labels were read from
`training/v5_imu_retraining/data/generated/imu_r1_20261020/master_dataset.csv`,
SHA256 `934925aa40ad7e24e6f34ff12075d76d70d0a97ba1f200374508505323d620ff`.
Grouped in the training order `(Session_ID, Rep_ID, Subject_ID)`, phases 1/2/3.
Select the first complete fixture case per scenario with consistent three-phase
labels: correct uses error type 0; incorrect uses lean/rounding types 2 or 3.
Selection did not inspect model output. These are synthetic training replays,
not held-out or real-human accuracy evidence. No CSV is needed by the runtime.

| Scenario | Fixture index | Source class | Error type | Recorded kg |
|---|---:|---:|---:|---:|
| Squat, correct | 5 | 0 | 0 | 35 |
| Squat, incorrect | 1 | 1 | 3 | 45 |
| Deadlift, correct | 42 | 0 | 0 | 50 |
| Deadlift, incorrect | 45 | 1 | 2 | 50 |

No model retraining, package alteration, label/feature/threshold change or dataset
copy. Preprocessor and interpreter are shared, not reimplemented in the browser.

## Focused verification only

New checks first failed on the absent demo modules, then passed after implementation:

```text
.venv/bin/python -m pytest tests/test_v5_demo.py tests/contract/test_workout_http.py -q -x
7 passed in 97.04s

node --test tests/web/test_demo_inference.mjs tests/web/test_demo_motion.mjs tests/web/test_ui_camera_connection.mjs
8 passed, 0 failed

git diff --check
PASS
```

These cover four actual model fixture calls, source/context/decision/provenance,
dedicated Origin/header, rejected forced class and active-live-session isolation,
one in-flight browser request, reset invalidation and existing camera UI boundary.
They do not constitute a broader model, hardware, timeout, reconnect or endurance
matrix. No full test suite or benchmark was run.

One real Chromium software-WebGL laptop check, 1366x768, played one rep through
the actual local API. Result displayed and screenshot visually inspected:

```text
scenario: squat / correct, fixture 5, 35 kg
model: digital_spotter_v5_imu_synthetic_r1
raw probability: 0.06076481193304062
calibrated bad-form probability: 0.12908328534088956
threshold: 0.3976007923801824
actual class: 0 (Good form)
UI: 12.9%, rep 1 / 3; page height 768 (no scrolling)
```

Temporary screenshot: `/tmp/ds-demo-model-result.png`; only the generated avatar,
no participant imagery. The owner requested no unnecessary tests; no additional
test runs followed this one browser check. WSL G: filesystem waits delayed local
Python startup; other workspace processes were not interrupted.

## Local launch, changes and remaining work

Local URL `http://127.0.0.1:4176/ui-preview/#demo`, opened in the PC browser.
Isolated run `/tmp/ds-demo-inference-rOEixk/core`, with a new local SQLite file,
no migration of an existing database. Uses the existing `.venv`, no installs.
The static-only 4173 UI is historical preview, not the model endpoint.

Implementation: new `inference/v5_demo.py`, `ui-preview/demo-inference.mjs`,
focused Python/JS tests; narrow updates to core workout construction, private
HTTP routing, launcher opt-in, demo controller/markup/colors and the earlier
animation contract check. PLAN, CURRENT_STATE, INTERFACES, SECURITY, ARCHITECTURE,
PRODUCT_REQUIREMENTS, DECISIONS, TEST_STRATEGY and OPERATIONS updated.

No Pi source/service or ESP firmware/pin/serial/BLE state changed. Physical
feedback, dense replay transport and Pi activation remain pending. Real camera
pose and assembled-system calibration/testing remain separate work. Existing
security/credential-rotation work is not closed by this feature.

Changes remain uncommitted and unpushed in the preserved dirty worktree.
Rollback: stop this isolated local launcher or omit `--enable-demo`. Workout and
the immutable model packages remain unchanged in behavior; no Pi rollback needed.
