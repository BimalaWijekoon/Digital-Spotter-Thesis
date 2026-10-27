# M6-R02 — Local pose diagnostics ready, not activated

2026-10-20. Owner asked for other pose work while checking the visible camera.
The live Pi/core/relay, test results and wearable are left running unchanged.
No new timed person capture was started.

## Implemented locally

- Correct the test result: 175 total / 85 missing / zero quality-approved now
  displays **Detected 90/175 · quality OK 0 · saved**, not zero detections.
  Unknown counters produce an unavailable result rather than invented zeros.
- Add cumulative detected-pose count independently of quality-approved count.
- Add private read-only `research_pose_latest_v1` at
  `/api/research/pose-latest`. One current pose, all 33 landmarks, original
  quality, capture time in JavaScript-safe Pi-monotonic microseconds. No history,
  participant identifiers, raw video, model probabilities or disk retention.
- Suppress missing, future-timestamped and >500 ms-old poses. The HTTP snapshot
  rechecks age rather than trusting an earlier hub refresh. The client budgets
  network request duration and expires previously drawn data while a request is
  stalled. Polls are bounded/non-overlapping and skipped for hidden video/pages.
- Reuse the existing pose canvas renderer; add optional cover-crop geometry and
  horizontal mirroring. The diagnostic guide uses MediaPipe's standard 35
  connections and all 33 points, drawing individually visible landmarks with
  a 0.15 drawing cutoff. Off-image landmarks are not pinned to image edges.
- Label it **Pose guide · unsynced**: these latest landmarks are NOT matched to
  the currently decoded WebRTC frame. This is a visual diagnostic, not measured
  overlay latency or a frame-aligned feedback claim. The existing synchronized
  render path still rejects unmatched/degraded poses; scoring gates unchanged.

Main changed files: canonical `core/workout.py`, `api/workout.py`, shared
`web/static/pose-overlay.mjs`, UI `camera-preview.mjs`, `index.html`, `styles.css`,
new `pose-test-result.mjs` / `pose-guide.mjs`; corresponding focused tests and
PLAN/CURRENT_STATE/INTERFACES/SECURITY/TEST_STRATEGY/OPERATIONS documentation.
No detector settings, BLE behavior, firmware, training code or model changed.

## FYP comparison — evidence, not an untested detector replacement

Read-only source: `/mnt/g/fyp/Vision/vision.py`, with an identical preserved
copy under `Data_Collection_Provenance/candidate_processing_code/vision.py`.

| Setting | FYP source | Active Pi source |
| --- | --- | --- |
| Detector | Tasks API, `pose_landmarker_heavy.task`, VIDEO | Solutions Pose, complexity 1 / Full |
| Detection/tracking configuration | 0.50 detection/presence/tracking, lines 523–529 | 0.70 detection/tracking, adapters.py 375–378 |
| Input | Decoded source video frame, BGR→RGB, lines 538–547 | 640×360 lores YUV→BGR→RGB |
| Detected-pose handling | Explicitly removed strict all-visible rejection, lines 549–557 | Confidence is minimum visibility of eight key joints; good-quality gate 0.70 |
| Landmark count | First detected pose, 33-point model | Already requires and retains all 33 points |
| Drawing | Selected body skeleton, visibility >0.15, lines 173–187 | No guide in the active UI; this local change prepares it |

FYP's Heavy asset exists locally (30,664,242 bytes); it was NOT copied, replaced
or initialized on the live Pi. Standard connection definitions were read from
the installed isolated MediaPipe 0.10.18 `pose_connections.py` without opening
the camera or importing a second estimator. No FYP source was changed.

The saved owner test establishes rejection of 90 detected low-visibility poses,
not why detection was absent for the other 85 frames. Neither a heavier model
nor lower thresholds is proven to solve that. After this diagnostic is activated,
one controlled comparison using the same input is the next detector decision.
No classifier retraining or automatic quality-gate relaxation is indicated.

## Focused verification

New missing-method/module checks failed against the baseline. After implementation:

```text
.venv/bin/python -m pytest tests/core/test_workout_pose_diagnostics.py tests/contract/test_workout_http.py -q
4 passed

node --test tests/web/test_pose_test_result.mjs tests/web/test_pose_guide.mjs tests/web/test_pose_overlay.mjs tests/web/test_ui_camera_connection.mjs
13 passed

git diff --check
PASS
```

Inputs are deterministic test stand-ins, not real people/hardware. Existing
renderer checks protect the normal matched-pose path. No full suite, model
training/inference benchmark, BLE/reconnect matrix or human test was repeated.
Real browser/Pi/person validation of this new guide is still pending.

## Activation boundary / rollback

Do not update the active Pi source or restart its core while the owner is checking
video or running a timed test. The currently deployed small-timer fix remains
available. After the owner finishes, preserve the active files and latest saved
summary, then activate this UI/API slice together with an isolated new run if
needed. The new API requires a core restart; copying UI files alone would not
provide landmark data. Keep the existing detector/environment for this slice.

Local changes are uncommitted/unpushed, existing user changes preserved. There
is no Pi rollback action for this step because nothing was activated there.
