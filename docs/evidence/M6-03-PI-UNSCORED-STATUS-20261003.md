# Pi page: live unscored sensor status (2026-10-03)

**Narrow result: PARTIAL.** The existing page now reads the canonical research
session's same-origin, read-only `research_status_v1` endpoint on Pi loopback.
The real Pi camera/MediaPipe path reached the session. The expected ESP32-C3 was
not discovered, so real IMU receipt remains **unverified**. No model-derived
result, feedback command, or scored analysis was produced.

The isolated runtime is
`/home/pibimalawijekoon/digital-spotter-research-status-20261003/` on the Pi.
It contains a copy of the canonical source/UI, a new disposable summary-only
SQLite database, and a Python 3.12 environment with the one missing runtime
dependency (`msgpack==1.1.1`). The earlier working Step 1 copy remains intact.
The existing R11 BLE environment runs one R9 agent; it requests no pairing.
The existing `ResearchStatusProjector` is the only source for session count and
IMU/pose freshness. The UI does not equate an IMU sample with a verified BLE
bond, and it keeps V5 analysis unavailable.

At the time of the check, the Pi listeners were only on `127.0.0.1`: status/UI
`8766`, RTSP `8554`, WHEP `8889`, and ICE/TCP `8189`. The static server on
`8766` was replaced by the already-implemented status/page server; the page URL
and SSH tunnel ports are unchanged. The MediaMTX on-demand hook now starts the
canonical vision agent, which owns Picamera2, publishes H.264, and emits pose
events to the session from that same camera owner. It releases the camera after
the last reader disconnects. No second camera owner or public listener was added.

Focused evidence:

- The read-only status endpoint returned HTTP 200 with an active unscored
  session, zero reps, `analysis=unavailable`, and no probability or class.
- A short direct Pi camera check produced 167 real Picamera2 frames and 167
  MediaPipe pose events with no processing failure. The empty scene correctly
  appeared as `camera=degraded`; it was not a human-pose or rep test.
- One on-demand RTSP read returned a 1280×720 frame. Its vision agent emitted
  44 real pose events and stopped when the reader left. The status then became
  `camera=stale`; no camera process remained.
- The R9 agent logged that the expected wearable was not discovered. The
  endpoint consequently reported `wearable=unavailable`; no pairing or BLE
  reset was attempted.
- The same Pi port served the page, private camera configuration, and fixed
  V5 Test input JSON with HTTP 200. The fixed input remains separate from the
  unscored live status and Workout Feedback.

Local checks: the focused Python status, HTTP and on-demand-hook checks passed
7/7; the three browser status cases passed 3/3. The new hook check first failed
for the missing opt-in branch. `sh -n` and `git diff --check` passed. The HTTP
test's first sandboxed attempt could not bind a test port, then passed with
local socket access; the actual Pi HTTP route was also checked. No full suite,
long run, mounted-person test, live IMU rate test, or browser visual check ran.

Rollback is to stop only the new research status, R9 agent, and MediaMTX
processes after resolving their exact PIDs, then restart the intact Step 1
static page and camera-only relay. The new SQLite file is isolated and must not
be substituted for product session history. None of these research processes
is installed as a boot service; after a Pi reboot their state must be checked
before use. Source changes remain uncommitted.
