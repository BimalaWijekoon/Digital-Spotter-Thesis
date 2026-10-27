# M3-04 pose telemetry and browser timing — 2026-09-28

**Status: PARTIAL.** The temporary research bridge received real canonical pose
events from the Pi; the browser capture-time/overlay check did not complete.
Do not treat this as M3-04 acceptance or a human-camera test.

## Implemented slice

- `research_telemetry.py` receives bounded length-prefixed vision UDS frames,
  validates/projects canonical `PoseSample` events, and exposes the latest 120
  browser-safe events plus a correlated monotonic clock response. It binds HTTP
  only to `127.0.0.1`; its UDS socket is mode `0600`. No product API, database,
  cloud or BLE path was changed.
- The isolated research page polls those **same-origin** endpoints, draws only
  timestamp-matched `good` pose over decoded WebRTC frames, and clears on missing
  capture time, stale/poor pose, failed telemetry or stale clock exchange.
- The bridge is temporary and unauthenticated beyond loopback/SSH isolation;
  it is **not** a product endpoint. No model inference or wearable cue is used.

## Focused evidence

| Check | Result |
|---|---|
| Python browser/bridge contract | 8/8 passed, including localhost HTTP clock response, cross-origin clock-POST rejection and SIGTERM socket cleanup. |
| Focused browser composition/timing tests | 14/14 passed using deterministic fakes; 5-second clock-expiry and bridge-cursor reset states covered. |
| Real Pi event delivery | Temporary canonical worker published **537 real** pose events from Picamera2/MediaPipe, with zero processing failures and zero health-publish failures. Bridge polling reached cursor 113 during the run and returned browser-safe `vision_degraded` samples. Empty-scene `poses_not_found=537` is expected; no pose was fabricated. |
| Pi stability at preflight | `throttled=0x0`, temperature 54.0 C before the short diagnostic. This is not a thermal run. |
| Browser `captureTime` / visual alignment | **NOT VERIFIED.** The first browser attempt began after the bridge's hard timeout and found no page. The second attempt was blocked by the stale UDS socket from that timeout. No capture-time availability, overlay alignment or latency result is claimed. |

The timeout exposed a cleanup defect in the temporary bridge: default SIGTERM
exited without removing its Unix socket. The local source now handles SIGTERM
through normal cleanup and passed one focused local subprocess test; that
correction was **not rerun on Pi**. No third live
attempt was made. The exact temporary Pi staging directory
`/tmp/ds-m304-telemetry-DtWGdH` was verified to contain only copied diagnostic
files and removed after all named camera/relay processes and listeners stopped.
No service was installed, no firmware flashed, no raw video saved.

Next, only when useful: one coordinated, short E3 check of the corrected bridge
and real browser `captureTime` values. A person-in-frame alignment test remains
the owner-directed **last** validation stage. Authenticated stream/API delivery,
direct-LAN latency and product access control remain separate gates.

## Bounded follow-up, 2026-09-28

One further isolated attempt used the corrected bridge, the existing Pi camera
and MediaMTX binary, and a single headless Chromium probe. The Pi was reachable,
`throttled=0x0`, and the diagnostic ports were free before launch. The research
page, its modules, `GET /api/pose-events`, and `POST /api/clock-sync` returned
successfully. The real worker published 387 pose events and 52 health events with
zero processing or health-publish failures; the empty scene again yielded no
landmarks. The relay accepted one H.264 RTSP publisher.

The browser probe returned `passed=false`, `reason=no_decoded_video`; therefore
`captureTime` and overlay alignment remain **NOT VERIFIED**. The relay's 95-second
outer timeout was almost exhausted when publication began, leaving only a few
seconds before shutdown while the browser was starting. This run does not isolate
a WebRTC or overlay defect. No second probe was attempted. The bridge's corrected
SIGTERM path removed its own Unix socket. All bounded camera/relay/bridge processes
and localhost forwards exited; no diagnostic listeners remained. Only the
verified temporary directory `/tmp/ds-m304-final-ReBVvNeC` was removed. No
service, firmware, configuration, model, or raw video was changed or retained.

The next useful check, if requested, needs a single coordinated browser run with
a capture/relay lifetime that starts **after** the camera publishes. Do not count
this follow-up as a pass or repeat setup blindly. The human-camera test remains
last.
