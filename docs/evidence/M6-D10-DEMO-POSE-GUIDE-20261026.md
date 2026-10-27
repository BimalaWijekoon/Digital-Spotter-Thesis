# M6-D10 Demo pose guide — 2026-10-26

## Scope

Add a real-time visual skeleton to the existing four authored squat/deadlift Demo
animations. Match the live camera guide's 33-point cyan presentation without
claiming MediaPipe detection or changing the inference path.

## Implementation

- Shared the live pose connection and drawing style constants.
- Mapped named GLB arm, hand, leg and foot bones to MediaPipe-compatible indices.
- Derived presentation-only head/face and heel points from the authored skeleton.
- Projected bone world positions through the active Three.js camera every frame.
- Added the explicit on-screen label `Simulated pose guide`.

The projected points are never emitted as pose events and never reach fusion or
inference. Demo predictions remain driven by the existing frozen replay fixtures.

## Focused verification

Command:

```text
node --test tests/web/test_demo_pose_guide.mjs tests/web/test_pose_overlay.mjs tests/web/test_pose_guide.mjs tests/web/test_demo_motion.mjs tests/web/test_demo_review_clips.mjs
```

Result: **16 passed, 0 failed**.

The checks establish that all four active GLBs contain the required named bones,
the Demo draws the shared 33-point cyan guide contract, the simulated label is
present, and existing live-pose and Demo playback contracts still pass.

## Deployment

Prepared release archive:

```text
/tmp/digital-spotter-research-appliance-20261026-r7.tar.gz
SHA256 ddcc09f079380ac083931a755b14dccf35e3251c34cd57d402b663b9c7d8e23e
```

The first reachability attempt found the Pi offline. After the owner brought it
online, the archive and its 250-file release manifest verified successfully. The
`current` link was moved from `r6` to `r7` and only the core/UI service was
restarted. Corrected bounded checks established:

- UI document: HTTP 200 and the `Simulated pose guide` label present;
- pose-guide module: HTTP 200 and the shared drawing contract present;
- target, core, IMU and media services: all `active`;
- core service restart count: zero before the switch check.

The initial post-switch shell check exited nonzero because it searched the module
for label text that correctly resides in the HTML; service inspection showed the
core remained active with a successful result. No rollback was required.

Owner visual confirmation of overlay placement and motion remains pending.

## Reboot auto-start check

After the owner rebooted the Pi and moved the wearable to its tested battery
power path:

- Pi boot timestamp: `2026-10-26 21:02:27 +0530`;
- target, core, IMU and media entered `active` at `21:02:28`;
- all three component services reported `NRestarts=0`;
- release link still resolved to `digital-spotter-research-appliance-20261026-r7`;
- Wi-Fi status was `connected` and the V5 research model was loaded;
- the IMU endpoint returned 100 consecutive samples, sequences 4542–4641, with
  approximately 20 ms spacing and finite acceleration/gyro values.

The application status reports `wearable=degraded` even while those samples are
arriving. That state is preserved as an unresolved health/status issue rather
than being relabelled as healthy. Camera `unavailable` before an on-demand viewer
request is expected.

The research UI and video/mutation surfaces remain loopback-only under the
repository security policy. Direct Tailscale Serve exposure was not enabled.
