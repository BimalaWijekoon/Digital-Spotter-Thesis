# Capture-driven squat, rendering only

Motion origin: Carnegie Mellon Graphics Lab Motion Capture Database,
subject 13, trial 13_29. https://mocap.cs.cmu.edu/
Original files: `subjects/13/13.asf`, `subjects/13/13_29.amc`.
Database created with support from NSF EIA-0196217. This is an exercise-motion
reference, not clinical evidence of correct technique or training data for V5.

CMU publishes custom reuse terms: research/product use permitted; standalone
resale of the data, including conversions, is not permitted. This is **not CC0**.
The small adapted clip is bundled only within this research dashboard, with no
standalone export/download function. See the original database terms above.

Retrieved 2026-10-23 from a pinned public mirror:
`https://raw.githubusercontent.com/AssiamahS/opengym3d/ea3a60130fdcfb3c4771e44d09f84ebab4ee9bae/motions/cmu/`

| Source | SHA256 |
|---|---|
| 13.asf | eb33390bcbccb739d7622bd583fd9be55020868f68689aa6f2060ad688df10dc |
| 13_29.amc | b8ffec0ea28ea24acc46ac6f4775604378ab1120388c45477c7b436ded00c42c |

`scripts/build_demo_squat_motion.mjs` adapts ASF/AMC parsing from that project's
MIT `pipeline/motion.py`. Original copyright/license retained in
`ADAPTER-LICENSE.txt`. No unrelated application or pipeline was executed.

Rebuild into a new output (refuses to overwrite):

```bash
node scripts/build_demo_squat_motion.mjs /path/13.asf /path/13_29.amc NEW-squat.json 31.5 34.5
```

Processing: trim 31.5–34.5 s, downsample 120 to 30 Hz (90 frames), normalize
heading/height, remove whole-cycle travel and endpoint drift for in-place looping.
Rendering interpolates the clip over the existing six-second repetition.
The incorrect-form version adds an **authored forward-lean overlay**; incorrect
technique was not captured or measured in this source. Arms are posed to the
illustrative barbell; CMU did not record this rendered weighted barbell movement.

Output `squat.json`: 23900 bytes, SHA256
`3fbd502433e597edb1e6ffbf102a09aad4ddf5d2d3aca718725b32202618c307`.
It contains rendering coordinates/directions only, no participant identifiers,
video or V5 input features. It is not connected to pose detection/inference.
No Mixamo assets or the rejected third-party animation GLB were incorporated.
