# M6-D06 — Complete four-scenario demonstration assets

Owner supplied `Custom_Exercise_Animations_Review_01.zip`, then the superseding
`Four_Exercise_Demonstration_Scenarios.zip` during this implementation session.
No original ZIP was changed and no supplied authoring script was executed.

## Initial four-scenario source (superseded by the character revision below)

Four-scenario ZIP SHA256:
`9cae2611060cfc9637a8f58f017fc7bb0ed3813398a2be90e1bfdb18313c3fe7`.
All 21 inventoried files match their supplied SHA256SUMS.txt entries.
Runtime directory: `src/digital_spotter/web/static/vendor/exercise-scenarios-v2/`.
Its SOURCE.md and asset manifest preserve provenance and exact sizes. Four GLBs,
MIT license and author-supplied contact/scenario reports are copied unchanged.
Source programs/previews stay in the original archive, not the runtime.

| Selection | Asset / embedded clip |
|---|---|
| Squat correct | squat_correct.glb / Squat_Correct |
| Squat incorrect | squat_forward_lean.glb / Squat_ExcessiveForwardLean |
| Deadlift correct | deadlift_correct.glb / Deadlift_Correct |
| Deadlift incorrect | deadlift_spinal_rounding.glb / Deadlift_SpinalRounding |

## Implementation and isolation

New `ui-preview/demo-review-clips.mjs` registers assets/hashes and authored time.
New `demo-review-avatar.mjs` plays one complete skinned human/equipment scene
with one AnimationMixer. No bar detachment, separate motion, body retargeting,
cross-fades or procedural bad-form distortion. The 5.3-second clip maps uniformly
to each six-second UI cycle. Camera fits complete animated scene bounds.
`demo-page.mjs`, index and CSS select this player. Old `demo-avatar.mjs`, its
rig/motion modules, original vendor assets and correct-only Review 01 are retained.

Specific fault captions are selected demonstrations, not errors diagnosed by the
binary model. Existing replay fixtures, model weights, preprocessing, calibration,
threshold, HTTP requests and inference path are unchanged. Animation is not pose
detection or a source of sensor/model features. No Pi/ESP operations.

## Focused evidence

- Existing motion/inference baseline: six checks passed before initial changes.
- Initial four-scenario check failed with `Missing squat/incorrect review clip`
  against the earlier correct-only registry, confirming the missing behavior.
- Final four focused JS test files passed, zero failures: review clips, motion,
  inference client and IMU replay. Actual GLB bytes, hashes, internal resources,
  named clips and hand/barbell animation/skin membership checked.
- Renderer/controller syntax checks passed.
- Review 01 played both correct motions in Chromium before the replacement ZIP;
  that evidence was not reused as the final-package pass.
- Final-package Chromium check played and paused all four selections at 1366x768:
  correct squat, forward-lean squat, correct deadlift, spinal-rounding deadlift.
  Captions matched, missing-animation notices stayed hidden, no page scroll and
  zero browser exceptions. Screenshot files are
  `/tmp/ds-four-scenarios-{squat,deadlift}-{correct,incorrect}.png`.
- These short rendering checks stopped before a full replay repetition: model
  output correctly remained Not run. No inference reruns or accuracy claims were
  needed for this renderer-only change; existing prediction-client checks passed.
- `git diff --check` passed. Local dashboard returned HTTP 200.

These are AI-assisted, constraint-based review prototypes, not mocap,
biomechanical standards or clinically validated technique. Author-supplied grip/
floor/loop reports do not establish our independent full-body collision checks.
Owner acceptance remains pending. No hardware,
training, performance benchmark, security/data migration, commit or push.

Rollback: restore the former page import and its sampleDemoPose/two-argument
render invocation; previous renderer/assets remain intact. Local URL is
`http://127.0.0.1:4176/ui-preview/#demo`; verify listener reachability separately.

## Later owner-supplied character revision — active

`Four_Exercise_Demonstration_Scenarios (2).zip` SHA256:
`4a28bda578992228cb73282e0284ca8e52c9a907869668ce97249958fbb51338`.
All 43 inventoried files verified. No source programs executed. Active assets
are in `vendor/exercise-scenarios-character-r1/`; old versions are preserved.
SOURCE.md/manifest and the registry record exact sizes/hashes. Four GLBs total
24,802,980 bytes; no Pi transfer or benchmark was performed.

This replaces the procedural character with the supplied Quaternius mesh,
65-bone human rig plus equipment, seven embedded PNGs, articulated fingers and
unchanged scenario names/durations. CC0 character notice and combined CC0/MIT
license are retained. Source/preview/rebuild textures remain in the original ZIP.

The existing two asset checks passed before the swap. With the new pinned
assets they exposed the obsolete `images.length === 0` assumption (seven images
are correctly embedded). Updated the resource contract to require embedded PNG
buffer views with no external URI, and accept the supplied lowercase hand names.
The focused asset test file then passed; renderer syntax/diff checks passed.
Added deterministic texture/ImageBitmap disposal for the newly textured scenes.
No model, labels, preprocessing, thresholds, inference flow, hardware or firmware
changes. Changes remain uncommitted/unpushed.

Fresh Chromium playback of all four character-revision scenes passed at
1366x768: correct captions, no missing-animation notice, no page scroll and zero
browser exceptions. New screenshots:
`/tmp/ds-character-r1-{squat,deadlift}-{correct,incorrect}.png`.
Earlier screenshots were not reused as proof. This is basic playback, not
independent contact/biomechanical validation or a model/hardware test.
