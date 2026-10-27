# M6-D14 partial-body pose acquisition — 2026-10-27

## Trigger

The owner observed that the live tracker appeared to start only when the face
was visible. Release r14 detected 133 poses in 218 frames but produced zero
quality-approved frames and only one completed rep in the requested three-rep
protocol.

## Change

- MediaPipe detection and tracking defaults changed from 0.70 to 0.50, matching
  the existing FYP video extractor.
- Tracking confidence now uses the stronger complete left/right
  shoulder-hip-knee-ankle chain. Face visibility and the hidden far side do not
  reduce this value.
- V5 phase features now independently require all bilateral landmarks used by
  the model, including both foot landmarks, at visibility 0.70 or higher.
- No missing landmark is invented, extrapolated or zero-filled.

## Focused verification

```text
MediaPipe adapter checks: 4 passed
vision worker checks: 4 passed
rep phase checks: 5 passed
```

Two unrelated local socket-helper cases cannot execute inside the restricted
workspace sandbox (`socket.sendall`: operation not permitted). Their failure is
environmental and they were not changed.

## Pi activation

```text
release: digital-spotter-research-appliance-20261027-r15
archive SHA256: 9f1111083d3b98924ad2c1d79451f1c7280b10c84f7406d6cfcf416b3a5803e0
manifest entries: 251, all verified
core service: active
IMU service: active
media service: active
startup state: idle; model loaded; live scoring unavailable
```

One owner-operated real-person check remains pending.
