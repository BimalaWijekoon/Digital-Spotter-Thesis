# M6-D13 rep tracking and model-quality separation — 2026-10-27

## Trigger

The first exported real set contained 272 camera frames and 213 frames with a
detected pose, but only four quality-approved frames and zero completed reps.
The detector was therefore operating; the rep builder was discarding every
degraded pose before deriving its knee-motion signal.

## Change

- Rep segmentation uses one or both hip-knee-ankle sides with visibility at
  least 0.50.
- Strict quality-approved bilateral pose extraction remains the only source for
  V5 phase features.
- When tracking can complete a rep but approved features are unavailable, the
  rep is counted with `quality=unavailable`, empty phase feature maps and no
  model result.
- No detector, model, BLE, camera, firmware or feedback threshold changed.

## Focused verification

```text
tests/core/test_rep_phases.py: 5 passed
new regression: one visible side counts exactly one unavailable rep
existing good bilateral rep: PASS
existing flat-motion no-fabricated-rep rule: PASS
existing missing-IMU no-zero-fill rule: PASS
```

## Pi activation

```text
release: digital-spotter-research-appliance-20261027-r14
archive SHA256: e4ed0ad37dcfca75adff5dd208237ead3d5d657e2f4a5a9c1efb064533f17ed5
manifest entries: 251, all verified
core service: active
IMU service: active
media service: active
startup state: idle; model loaded; live scoring still unverified/unavailable
```

## Owner-operated movement result

Source JSON:
`digital-spotter-set-0e72e9b7-70ed-45d1-87f4-a735c139a937.json`

```text
SHA256: 9fd121a4409b1ca7075128275259059bbe997f45a10e2868d5b2cbe03b3fce86
duration: 38.45 s
camera frames: 218
detected-pose frames: 133 (61.0%)
quality-approved pose frames: 0
completed reps: 1
latest rep quality: unavailable
wearable: degraded
analysis: unavailable (phase_or_calibrated_imu_unavailable)
```

The narrow M6-D13 behavior passes: degraded one-side pose data can now produce a
nonzero rep count, while model scoring remains correctly blocked. Full rep-count
reliability does not pass: the requested three-rep protocol produced only one
recorded rep. Pose quality and calibrated IMU/model eligibility also remain open.
