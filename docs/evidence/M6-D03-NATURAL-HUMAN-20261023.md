# M6-D03 — Bad-squat diagnosis and natural human

2026-10-23. Local UI/renderer PASS. A model miss is documented, not hidden or fixed
by changing labels, thresholds or examples. No Pi/ESP work or training.

## Reported prediction

Read the existing local `/api/research/demo/predict` response for
`exercise=squat, form=incorrect, rep_id=1`:

| Field | Observed value |
|---|---|
| Fixture | 1, original 45 kg context |
| Source label | 1 (incorrect), error type 3 |
| Raw probability | 0.35316163301467896 |
| Calibrated probability | 0.39154328994402116 |
| Frozen threshold | 0.3976007923801824 |
| Actual class | 0, Good form |
| matches_source_label | false |
| Model | digital_spotter_v5_imu_synthetic_r1 |

39.1543% is below 39.7601% by about 0.606 percentage points. This is a false
negative against the synthetic source label, not an inverted UI selector. It
does not establish a population false-negative rate or real-world accuracy.
The 3D drawing is not the feature source; the complete frozen three-phase
fixture goes through canonical preprocessing/inference/calibration/thresholding.

UI now retains Good form as the actual model output and explicitly shows
`Label: incorrect · 39.15% < 39.76% threshold`. No example was replaced with one
the model classifies correctly. No threshold/calibration, weights, labels,
preprocessing, firmware or live-scoring policy changed. Any later model-quality
work needs separate representative evidence, not tuning to this one demo case.

## Research and selected human

Publisher: [Quaternius Universal Base Characters](https://quaternius.com/packs/universalbasecharacters.html),
[official free pack and CC0 declaration](https://quaternius.itch.io/universal-base-characters).
Publisher documents humanoid rigs, glTF and approximately 13k triangles per
character. Compared with the separate primitive body, a continuous skin is the
relevant improvement: face, anatomical proportions and articulated limbs/hands.
The publisher's [older modular character pack](https://quaternius.com/packs/ultimatemodularcharacters.html)
also has animated humans, but the newer base rig suits a neutral gym renderer.

Selected: Superhero Male full-body base, compact GLB redistribution pinned at
`programasweights/avatar` commit `5df3cb35c8c93e59a3c545e2ca1edd13b77e4240`.
This is not a direct publisher download. Distributor provenance, original
license, actual file sizes and SHA256 are preserved in
`src/digital_spotter/web/static/vendor/quaternius-human/SOURCE.md` and `LICENSE.txt`.
Only the asset/license were used from that repository, not its application code.
Binary 741320 bytes, 65 skin joints, three meshes, no external buffers/images;
SHA256 `d6f3b64cab629f6ddca9ba063811aeffd3663a8a4e49ade47cd9505dc2bbd70f`.

Matching unchanged r180 `GLTFLoader.js` / `BufferGeometryUtils.js` are vendored
with existing Three.js MIT license and hashes. A local import map resolves the
bare module specifier. No CDN, account, Blender/npm install or runtime internet
connection. Asset binary is unchanged; gym colours are applied during rendering.

## Implementation and checks

`demo-human-rig.mjs`: explicit bone mapping, fixed-length two-segment limb posing,
planted feet, distributed spine inclination, hand/finger posing and barbell
placement. The asset's shorter arm reach is handled by setup posture, not bone
stretching. Mesh/skin is natural-looking but stylized; movements are authored
illustrations, not motion capture, measured biomechanics or detected MediaPipe.

Updated `demo-avatar.mjs`, `demo-page.mjs`, `demo-inference.mjs`, `index.html`.
Added rig test and mismatch-description regression in the existing client test.
PLAN, CURRENT_STATE, ARCHITECTURE, TEST_STRATEGY and OPERATIONS updated.

The new checks first failed on missing rig/description exports. Final focused run:

```text
node --test tests/web/test_demo_human_rig.mjs tests/web/test_demo_inference.mjs tests/web/test_demo_motion.mjs
7 passed, 0 failed
git diff --check
PASS
```

One short 1366x768 local Chromium software-WebGL run rendered both exercises,
played one incorrect-squat rep through the actual existing API, and displayed
the exact mismatch above. Page height 768, no scrolling. Visual inspection then
adjusted deadlift reach and belt size; final static setup frame inspected without
another model call. No broad tests, model accuracy evaluation or benchmark.

Generated, non-participant screenshots remain temporary:
`/tmp/ds-natural-human-squat.png`, `/tmp/ds-natural-human-result.png`,
`/tmp/ds-natural-human-deadlift.png`, `/tmp/ds-natural-human-setup-final.png`.

Existing local dashboard: `http://127.0.0.1:4176/ui-preview/#demo`; refresh to load
the new human. No launcher/service restart, database migration, credential change,
model retraining, deployment or actuator command. The earlier Pi/hardware and
model-provenance gates remain open. Changes are uncommitted/unpushed.
Rollback: retain the same frozen package and use Workout; renderer-only changes
are additive/reversible without changing the Pi, ESP or persisted user data.
