# Pi research camera button and on-demand relay — Step 2B (2026-10-03)

**Scope result: PASS for a private, button-operated real camera preview.** This
does not close M3-04/M6-03, prove human-viewed quality or latency, or enable
live V5 scoring.

The owner reported repeated `channel 6: open failed: connect failed: Connection
refused` while forwarding UI/video ports. Read-only Pi inspection showed the
static UI listener still on `127.0.0.1:8766`, but no MediaMTX or camera process.
The prior Step 2 camera was explicitly limited to 300 seconds and its relay to
600 seconds. Their expiry explains the refused forwarded video channels; it was
not evidence of an ESP/BLE fault.

The redesigned Workout camera panel now owns the Connect/Stop controls and has
no URL input. A local static `camera-config.json` supplies the WHEP address;
the existing browser wrapper still accepts only a loopback endpoint. A separate
MediaMTX v1.9.1 research config binds RTSP 8554, WHEP 8889 and ICE/TCP 8189 to
Pi loopback with one allowed browser origin. Its `runOnDemand` hook starts the
existing Picamera2 dual-stream/H.264 owner only when a viewer requests the
stream, then stops it five seconds after the last reader leaves. The static UI
and relay are research processes, not boot services or authenticated product
endpoints. The prior Pi UI copy is preserved as
`~/digital-spotter-research-step1-20261003/ui-preview-before-on-demand-20261003/`.

Focused checks:

- `node --test tests/web/test_ui_camera_connection.mjs tests/web/test_research_preview.mjs`: exit 0.
- `node --check scripts/video_browser_probe.mjs`, `python3 -m py_compile
  scripts/research_camera_publisher.py`, `sh -n
  scripts/research_camera_publisher.sh`, and `git diff --check`: exit 0.
- Pi listener inspection after installing the relay: UI 8766, RTSP 8554,
  WHEP 8889 and ICE/TCP 8189 all on `127.0.0.1`; no camera/helper process
  before a viewer connected.
- One final short headless Chromium interaction through a private SSH tunnel:
  clicked the new camera button, decoded real 1280x720 H.264, observed 88 new
  frames and 2.948 seconds of media advance over approximately three seconds,
  reached `Preview live`, clicked Stop, and cleared the video source. Exit 0.
- Relay log showed `runOnDemand command started`, one H.264 publisher and one
  WebRTC reader, then `runOnDemand command stopped: not needed by anyone` five
  seconds after disconnect. The camera helper had exited and the relay stayed
  ready for a later viewer. The first check exposed a shutdown traceback; the
  publisher was corrected and the final check ended with `clean_stop: true`.

The final browser probe also reported 92 dropped frames and no finite WebRTC
`captureTime` values. Do not infer glass-to-glass latency, pose alignment, or
visual quality from this probe. No person, wearable, model inference, mock
sensor, database migration, raw-video recording, cloud write, or endurance
test was involved. Owner visual review in the normal browser is still pending.

Rollback: stop only the verified research MediaMTX process on Pi loopback;
restore the preserved Pi UI copy if needed. Source changes are uncommitted.
This preview remains private to the owner-controlled SSH tunnel and must not
be exposed on LAN/Tailscale without the future authenticated stream boundary.
