# Pi-hosted research UI camera feed — Step 2 (2026-10-03)

**Narrow result: PASS for real video playback in the redesigned research page.**
This does not close M3-04 or M6-03, prove visual quality/latency, or enable pose,
IMU, model scoring, sessions, or feedback.

- Pi hardware: real IMX219 camera enumerated by `rpicam-hello`; power status
  `throttled=0x0` at the final check. No competing camera/relay owner was running.
- Reused the existing Picamera2 dual-stream adapter and hardware H.264 publisher,
  installed MediaMTX v1.9.1, and the already-copied `ui-preview/` page. No new
  camera package, firmware, or Pi service was installed.
- The temporary relay was limited to `127.0.0.1` RTSP `8554`, WHEP `8889`, and
  ICE/TCP `8189`; an SSH tunnel carried all three browser-facing paths. Its
  process-local allow-origin was the tunnelled page origin. The camera process
  has a 300-second limit and the relay a 600-second limit; neither auto-starts.
- Relay log confirmed one real H.264 publisher and one WebRTC reader over
  host/TCP loopback. A bounded headless Chromium run against the **redesigned
  Pi-hosted page**, not the old diagnostic viewer, reported 1280x720 video,
  90 additional video frames and 3.022 seconds of media advance over roughly
  three seconds. The page showed `Preview live`; its Stop control closed the
  peer and cleared the video source. Probe exit was 0.
- The same headless run reported 92 dropped frames at observation and no finite
  video `captureTime` values. This is not a visual-quality, overlay timing, or
  latency pass; an owner-viewed image and the planned mounted-system checks
  remain separate. No screenshot or raw video was saved.

`scripts/video_browser_probe.mjs` was narrowly extended to operate the
redesigned page's existing Devices → Research camera setup controls while
retaining its older diagnostic-page path. JavaScript syntax and the real
browser probe passed. No source camera/UI runtime behavior was changed.

The static page remains on Pi loopback `8766` from Step 1. Its research status
API is absent (404) and analysis remains unavailable. The temporary camera and
relay expire automatically; a fresh, explicitly started private preview is
needed for later viewing. No long soak, person-in-frame, BLE, ESP, model
inference, database, or cloud test was run.
