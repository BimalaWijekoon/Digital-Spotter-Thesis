# M6-D04 — Recognised bad-squat example and capture-driven squat

2026-10-23. Owner explicitly requested a correctly recognised example and an
animation correction. Local model/API/UI check passes; final motion quality is
for the owner's review. This does not repair or validate overall model accuracy.

## Curated example

The frozen package remains
`training/v5_imu_retraining/outputs/main_v5_imu_r1_20261020/package/`.
No labels, raw feature values, preprocessing, weights, calibration or threshold
were edited. A bounded inspection of complete, source-labelled incorrect squat
fixtures found multiple recognised cases. Chose fixture 6: the first recognised
case with consistent forward-lean labels and synthetic severity at least 0.6,
matching the illustrated error type. It is intentionally curated using the model
response, not independent evaluation.

| Field | Previous fixture 1 | Curated fixture 6 |
|---|---:|---:|
| Original load kg | 45 | 35 |
| Three original phase labels | 1,1,1 | 1,1,1 |
| Error type | 3, forward lean | 3, forward lean |
| Synthetic severity | 0.54 | 0.69 |
| Raw model probability | 0.35316163301467896 | 0.7873481512069702 |
| Calibrated bad-form probability | 0.39154328994402116 | 0.8506134321850672 |
| Frozen threshold | 0.3976007923801824 | 0.3976007923801824 |
| Actual model class | 0 (miss) | 1 (Check form) |

Synthetic severity is not a measured clinical grade. The previous case has not
been proven physically correct; it remains a documented false negative against
its source label. Source-to-fixture audit confirmed all its 87 temporal values
and original context match the training table. It was not silently relabelled.

Catalog declares `curated_demonstration_not_accuracy_evaluation` and retains
`known_false_negative_fixture_index=1`. UI says Curated replay. Form selection
still selects data, not a forced model decision; canonical V5 performs inference.

## Motion correction

Retain the CC0 skinned human. Squat is now driven by public CMU trial 13_29,
31.5–34.5 seconds, rather than the old cosine hip descent. The baked 90-frame
clip has captured hip/knee trajectories and separate spine/head directions.
Normalize height/heading, remove endpoint drift for an in-place loop, interpolate
and retime to the existing six-second UI repetition. Incorrect form adds an
authored forward-lean overlay; it is not a recording of clinically bad technique.
Illustrative arms/bar are retained; this is not captured barbell biomechanics.

Camera is closer; waist belt is a thin ring instead of the protruding solid box.
The capture does not enter MediaPipe or produce the model's inputs. Deadlift
remains illustrative and is labelled as such; no unsuitable CMU bending clip was
misrepresented as a deadlift. Rejected Mixamo-derived GLB was not incorporated.

Reproducible adapter: `scripts/build_demo_squat_motion.mjs`.
Clip, provenance/custom CMU terms and adapter's original MIT license:
`src/digital_spotter/web/static/vendor/cmu-squat/`.
Full source/output SHA256 recorded in `SOURCE.md`; clip size 23900 bytes.
No renderer, Python environment or model dependency upgrade.

## Focused evidence

New replay check first failed because fixture 1 was still selected. New motion
check first failed on its absent module. After implementation:

```text
.venv/bin/python -m pytest tests/test_v5_demo.py::test_owner_requested_curated_bad_squat_is_a_real_correctly_recognised_example -q -x
1 passed in 23.75s

node --test tests/web/test_demo_captured_motion.mjs tests/web/test_demo_human_rig.mjs tests/web/test_demo_inference.mjs tests/web/test_demo_motion.mjs
8 passed, 0 failed

node --test tests/web/test_demo_captured_motion.mjs tests/web/test_demo_human_rig.mjs
2 test files passed after applying captured motion to the rig check

git diff --check
PASS
```

One local browser run (1366x768, Chromium software WebGL) viewed correct/incorrect
squat motion and completed one incorrect-squat repetition. Actual UI:
Check form, 85.1%, 35 kg, rep 1/3; underlying threshold unchanged. Document height
768, no scrolling. Screenshots visually inspected:
`/tmp/ds-captured-squat-correct.png`, `/tmp/ds-captured-squat-incorrect.png`,
`/tmp/ds-captured-squat-result.png`. Only rendered avatars, no participant imagery.
No accuracy study, full suite, training, hardware or endurance tests.

## Local run and scope

Existing local port 4176 had no listener, so no running service was stopped.
Started the normal opt-in launcher with new isolated run
`/tmp/ds-demo-curated-fa6UJp/core`; same frozen model and private origin guard.
Open `http://127.0.0.1:4176/ui-preview/#demo` and refresh.
No Pi/ESP, firmware, serial, BLE, physical cue, credential, existing database or
live-scoring policy changed. No simulated workout analysis was persisted.

Changed replay metadata/case and its targeted tests; new small motion asset,
source/license, bake script and motion sampler; narrow rig/renderer/UI updates;
PLAN, CURRENT_STATE, INTERFACES, DECISIONS, TEST_STRATEGY and OPERATIONS.
All changes remain uncommitted/unpushed in the preserved dirty worktree.
Rollback: omit `--enable-demo` or use Workout. Previous package and documented
fixture 1 remain intact; no model or hardware rollback is necessary.
