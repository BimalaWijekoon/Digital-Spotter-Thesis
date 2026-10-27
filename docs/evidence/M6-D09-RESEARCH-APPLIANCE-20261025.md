# M6-D09 research appliance deployment — 2026-10-25

## Scope

Prepare, but do not falsely claim deployment of, a bootable research demonstration
from the owner-accepted Pi/ESP demo. Preserve model, BLE, camera and UI behavior;
add only truthful Pi network state, an idle Pi RGB indication, and native service
packaging. No Wi-Fi/Tailscale/SSH/BlueZ setting or ESP firmware was changed.

## Implemented

- `LinuxWiFiProbe` reads only `wlan0` operstate and local IPv4 presence. It emits
  connected/disconnected/unavailable and never exposes an address or contacts the
  internet.
- `workout_v1.network` is validated by the browser. A compact header chip and one
  Devices row show it without changing the approved workout layout.
- Pi GPIO is dim blue while locally connected and slowly pulses amber otherwise.
  No network buzzer is used. Model-selected demo cues retain priority.
- Stable runtime sockets are separated from fresh per-start SQLite state.
- Core/UI, single BLE owner, and on-demand MediaMTX/camera are separate systemd
  services under one research target.
- The wearable remains BLE-only and its already working
  `0.9.2-demo-feedback` firmware is unchanged.

The first `r4` activation failed closed before opening any core socket because the
wrapper created the exact directory that the core requires to create atomically.
The services were stopped, the foreground traceback was preserved, and `r5`
removed only that pre-creation. A focused launcher regression test confirms the
exact run directory is absent when the core receives it. Release `r6` additionally
makes the core unit part of the target so appliance lifecycle operations include
all three services; application behavior is otherwise unchanged.

## Focused checks

```text
tests/core/test_network_status.py + tests/core/test_demo_feedback.py: 7 passed
tests/core/test_workout.py::test_workout_status_exposes_bounded_pi_network_state: 1 passed
tests/deploy/test_research_appliance_launcher.py: 1 passed
tests/web/test_workout_client.mjs: 1 suite passed
Python compile check: PASS
POSIX shell syntax check: PASS
git diff --check: PASS at candidate preparation
release manifest: 247 files, all SHA256 verified
secret-pattern scan: clear
```

Release archive prepared outside the repository:

```text
/tmp/digital-spotter-research-appliance-20261025-r6.tar.gz
size: 23 MB
SHA256: d833ec0ba0335f8483cec9cca407bce585b65af94e85ee7e1e1a6c8840f63cd7
```

## Deployment state

**DEPLOYED — SOFTWARE BOOT GATE PASS.** Release `r6` is the active immutable
release. The archive SHA256 and all 247 manifest entries matched on the Pi. The
target, core, BLE/IMU and media services were active with `Result=success` and
zero restarts. The loopback UI returned HTTP 200; `workout_v1.network` reported
connected `wlan0` with a local address; and the IMU endpoint returned a fresh
bounded 100-sample real MPU6500 window. The synthetic reference model loaded, but
live inputs remain explicitly unverified and live analysis remains unavailable.
After the post-install Pi reboot, core, BLE/IMU and media entered `active` one
second after boot. A single bounded local RTSP decode request started the on-demand
camera and published 75 real frames; no person was visible, so pose quality
truthfully remained degraded. MediaMTX remained active with zero restarts after
the client stopped. Owner visual confirmation of the Pi RGB network colour remains
separate from software evidence. This is intentionally not an endurance/reconnect
matrix.

## Research boundary

The frozen synthetic replay model remains reference-only. This release does not
validate mounted live form scoring, pose quality, IMU/body calibration, production
BLE security, authenticated product APIs, or G5/G7 readiness.
