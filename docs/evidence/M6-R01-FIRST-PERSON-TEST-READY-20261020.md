# M6-R01 — Ready for the first person-in-frame test

2026-10-20. Bring-up PASS; human pose quality and live model scoring NOT PASSED.

## Running scope

New Pi run: `~/digital-spotter-v5-imu-r1-20261020.E7L664/live-20261020.8qqaRH/`.
Uses the unchanged M5-R05 staged canonical source and candidate package.
No firmware, model artifact, source application code, old database, system
service, BlueZ configuration or network setting was changed by this bring-up.

| Component | Existing interpreter / process |
| --- | --- |
| UI/core, new isolated SQLite file | research-status-20261003 `.venv/bin/python`, PID 1892 |
| Real BLE receiver | digital-spotter-r11-candidate `.venv/bin/python`, PID 2754 |
| MediaMTX | `~/mediamtx`, existing v1.9.1, PID 1903 |
| On-demand MediaPipe | research-status-20261003 `.venv-pose/bin/python`, MediaPipe 0.10.18, no TensorFlow visible |
| Picamera2 helper | `/usr/bin/python3`, actual imx219 camera index 0 |

Three private SSH forwards expose Pi loopback 8766/8889/8189 as PC loopback
4174/8889/8189. UI opened at `http://127.0.0.1:4174/ui-preview/`.
No public listener or new service installation was introduced.

## Focused verification actually performed

- Pi `vcgencmd get_throttled`: `throttled=0x0` before and after bring-up.
- UI: HTTP 200 through the private tunnel.
- One real Chromium playback check through the UI: decoded H.264 1280x720;
  video media time advanced 3.005 s; player state Camera live; clean stop PASS.
  Probe recorded 102 decoded / 100 dropped frames and 89 frames counted during
  its observation. These browser counters are retained, not interpreted as a
  latency or frame-loss benchmark. Finite browser capture-time metadata: zero;
  end-to-end capture latency was not measured.
- The same core received 96 real Picamera2/MediaPipe pose events, 96 person-not-
  found, zero processing failures, zero read timeouts and zero health-publication
  failures. Source dropped 311 frames under latest-frame semantics. This was an
  unattended startup check: no human detection/pose accuracy claim.
- Real R9 BLE connection and GATT contract verified. One current IMU window:
  100 samples, sequences 1901–2000, capture span 1980.24 ms, zero sequence gaps;
  approximately 50 Hz in this window, not an endurance result.
- IMU state is degraded, not absent. Existing R9 adapter intentionally emits
  `Quality.IMU_DEGRADED`, calibration version 0; no new calibration or physical
  body-frame verification was claimed.
- Candidate `digital_spotter_v5_imu_synthetic_r1` loaded through canonical
  preprocessing and LiteRT; its fitted-median reference inference succeeded.
  `live_inputs_verified=false`; actual athlete predictions remain unavailable.
- `git diff --check`: PASS. No new unit suite, model training, pairing,
  reconnect matrix, endurance run, RGB/buzzer test or raw recording was run.

## Initial startup issues preserved

The first BLE launch used the core environment, which lacks Bleak; its
`ModuleNotFoundError` is preserved in `imu.log`. Selected the existing R11 BLE
environment rather than installing or changing packages. Its first connection
attempt timed out without an error message, then its existing backoff reached
verified GATT. A diagnostic stop coincided with that successful connection;
logs remain in `imu-ble.log`. Resumed exactly one receiver as PID 2754;
`imu-live.log` records verified GATT and real samples arrived. No pair/remove,
Bluetooth restart or firmware adjustment was used. A later repeated transport
timeout would require diagnosis, not be treated as proven reliable recovery.
Unprivileged Bluetooth journal query returned no entries; sudo kernel/HCI
capture was unavailable without authentication, so no current HCI-trace claim
is made.

## First owner action — not automatically started

1. Open the UI and click **Connect camera** if video is not already visible.
2. When ready, click **Test pose · 30 s**. There is a **20-second countdown**.
3. Move far enough back that shoulders, hips, knees and ankles remain visible;
   stand normally during the 30-second capture. No exercise/load required yet.
4. Test stops automatically; aggregate result appears in the UI and is saved
   to `core/person-pose-latest.json`. Owner reports completion for inspection.

Idle camera status becomes stale after the viewer closes: the existing on-demand
relay releases the camera. This is distinct from a failed active preview.
No human-test countdown was started by the agent.

## Preservation and rollback

New files are the private run's logs, PID files, sockets, SQLite file and copies
of the existing relay config/publisher hook. Previous runs and source packages
are untouched. Stop only the identified new core/BLE/relay after checking their
current command lines; stopping MediaMTX releases its owned on-demand worker.
Stop the corresponding local SSH forwarding process to close PC access. No
deletion or database restore is needed. Processes are detached, not boot-enabled.

Local changes in this step: PLAN, CURRENT_STATE, OPERATIONS and this evidence
report only. Existing dirty worktree preserved; uncommitted and unpushed.
Real hardware: Pi, imx219 and USB-powered PCB1 wearable over BLE. No sensor/pose
mock. Model reference is synthetic, explicitly not a real exercise prediction.
