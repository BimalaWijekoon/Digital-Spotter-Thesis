# M3-04 bounded real-browser playback — 2026-09-15

## Outcome and boundary

**Transport/playback PASS; custom viewer integration remains pending.**

Real Pi camera -> unchanged canonical Picamera2 helper/H264Encoder -> loopback
RTSP -> installed MediaMTX v1.9.1 -> its matching built-in WHEP viewer -> local
headless Chromium. No BLE operations, firmware changes, pose inference, model
inference, person/mounting test, mock stream or video recording.

This proves decoding and advancing live video, not visual quality, an empty scene
confirmed by a person, overlay alignment, or glass-to-glass latency. No image was
saved or inspected. The run was intended for the user-approved empty-scene check.

## Measured evidence

| Check | Result |
|---|---|
| Browser | HeadlessChrome/151.0.0.0, Linux x86_64 |
| Stream dimensions | 1280 x 720 |
| Browser total video frames at measurement | 92 |
| Additional frames in 3 seconds | 89 (approximately 29.7 fps) |
| Reported dropped frames | 1 |
| Media time advance | 2.974 s |
| Video readyState | 4 |
| Probe result / exit | `passed=true` / 0 |
| Final camera run | 2002 lores frames received; `clean_stop=true`; exit 0 |
| Power flags | `throttled=0x0` before and after |
| Temperature | 56.4 C during final run, 54.5 C after cleanup |
| Cleanup | No remaining camera, Python preview or MediaMTX processes; preview listeners closed |

The final publication ran approximately 67 seconds (relay log 16:30:42 to
16:31:49 Pi local time), stopped early using SIGTERM to its verified capture PID.
It was bounded to 120 seconds independently. The earlier publication-only run
completed 60 seconds and 1786 lores frames. These are capture counts, not browser
frame counts or end-to-end loss measurements.

The exact final numeric browser result is retained in
`M3-04-BROWSER-PLAYBACK-20260915.json`.

The final relay log confirms one H264 track published, a WebRTC peer connection
over host/TCP loopback, one H264 reader, peer closure and graceful relay shutdown.
No direct-LAN UDP, WAN-offline, multi-client, browser-reconnect, `captureTime`,
thermal endurance or human acceptance was tested.

## Artifacts and versions

- MediaMTX v1.9.1 already installed; unchanged binary SHA256:
  `647a051408edf0def091e389e0ba8657f5b860dca05c233a558bf818d75e0305`.
- Picamera2 0.3.37 from system Python; parent OpenCV 4.11.0 from the existing
  Python 3.12 installation. No packages installed/upgraded.
- Existing `digital-spotter-m303-step7-20260912/src` candidate supplied the adapter.
  Local and Pi hashes match:
  - `src/digital_spotter/vision/adapters.py`:
    `53f1d05364a41d4340ab9538ec1ac3ea124f824b952b992cb0548455ea7ea1c4`
  - `src/digital_spotter/vision/picamera2_helper.py`:
    `cc7fd21d2e086d5fd494ea76e70badd4e5d9c1f0010da32f8b1a1a4e237b3795`
- New reusable diagnostic scripts: `scripts/video_preview_capture.py` and
  `scripts/video_browser_probe.mjs`. The first owns the existing adapter for a
  bounded duration; the second asserts decoded video/time advance through CDP.
  Neither implements a new camera or WHEP stack.
- A separate owner-home staging directory `ds-video-preview-CjpOu6i9` contains
  the copied diagnostic/configuration and `relay-final.log`. Existing source and
  deployment configurations were not overwritten.

## Isolation and launch parameters

The repository `deploy/mediamtx.yml` was copied to the staging directory. These
process-local overrides restricted the temporary instance:

```text
MTX_RTSPADDRESS=127.0.0.1:8554
MTX_PROTOCOLS=tcp
MTX_WEBRTCADDRESS=127.0.0.1:8889
MTX_WEBRTCLOCALUDPADDRESS=
MTX_WEBRTCLOCALTCPADDRESS=127.0.0.1:8189
MTX_WEBRTCIPSFROMINTERFACES=no
MTX_WEBRTCADDITIONALHOSTS=127.0.0.1
MTX_WEBRTCALLOWORIGIN=http://127.0.0.1:8889
```

SSH forwarded localhost TCP 8889 and 8189 to the same Pi loopback ports. No LAN
or public video listener, firewall, Tailscale, SSH configuration, authentication
scheme or system service was changed. This is a private diagnostic connection,
not a production video access-control implementation. TCP-over-SSH means this
result cannot validate the intended direct-WebRTC latency budget.

Run the capture diagnostic with the existing R11 virtual-environment Python,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` selecting only the staged source tree:

```text
python scripts/video_preview_capture.py --publish-url rtsp://127.0.0.1:8554/picamera2 --duration 120 --extra-site-packages EXISTING_PYTHON312_SITE_PACKAGES
node scripts/video_browser_probe.mjs CHROMIUM_EXECUTABLE http://127.0.0.1:8889/picamera2/
```

The probe requires Node >=22 with native WebSocket and an existing Chromium.
It uses a fresh temporary profile, no screenshots, a 60-second process timeout,
and terminates only its own browser. Chromium `--no-sandbox` applies solely to
this isolated headless diagnostic; it is not a product/browser security setting.
Temporary browser profiles remain outside the repository. No raw video is saved.

## Failures preserved and correction

1. The initial launch put Python 3.12 binary-wheel directories in `PYTHONPATH`,
   which the system-Python camera helper inherited. It exited before capture.
   The existing adapter surfaced `CameraUnavailableError`. The diagnostic now
   uses `site.addsitedir` in its parent only, matching the earlier split-runtime
   workflow. No dependency or camera implementation was changed.
2. The first browser correctly reported `no_decoded_video` while no camera was
   publishing; the built-in viewer retried during its bounded probe lifetime.
3. A subsequent CDP evaluation raced initial page navigation. The probe now
   attaches to about:blank and waits for `Page.loadEventFired` before evaluating.
   One attempt then encountered the expired preview window; it was not counted
   as playback evidence. The final coordinated run produced the PASS above.

## Compatibility discovery and next step

Our `whep-player.mjs` expects an injectable `MediaMTXWebRTCReader` class. The
installed v1.9.1 instead embeds its reader inside `read_index.html`; it does not
serve the standalone reader module used by newer documentation. Therefore the
custom wrapper was **not** activated, and no version upgrade was attempted.

Next: select and pin a compatible official reader/server combination in an
isolated candidate, then connect the existing custom player. Keep the installed
v1.9.1 binary and this measured playback path as rollback. Telemetry/overlays and
authenticated product launch remain separate gates; human-camera acceptance last.

Official references: [v1.9.1 HTTP server routes](https://github.com/bluenviron/mediamtx/blob/v1.9.1/internal/servers/webrtc/http_server.go),
[v1.9.1 built-in viewer](https://github.com/bluenviron/mediamtx/blob/v1.9.1/internal/servers/webrtc/read_index.html),
[v1.9.1 configuration](https://github.com/bluenviron/mediamtx/blob/v1.9.1/mediamtx.yml),
[current browser embedding guide](https://mediamtx.org/docs/read/web-browsers).

## Verification and handoff

- New diagnostics were exercised against real Pi/Chromium; failures above guided
  the two narrow harness corrections. Existing product source was unchanged.
- `node --test tests/web/*.mjs`: **20 passed**, using deterministic fakes.
- `python -m pytest tests/contract/test_mediamtx_relay.py tests/test_02_pose/test_vision_adapters.py -q`:
  **10 passed in 1.36 s**. Initial sandbox run could not create pytest temporary
  files; the permission-enabled run above completed normally.
- Node syntax check, Python AST check and `git diff --check`: PASS.
- Full suite/model validation not rerun: no model or product runtime logic changed.
- Files changed: two new diagnostic scripts, this evidence, `PLAN.md`,
  `docs/CURRENT_STATE.md`, and operations guidance. Uncommitted; no push.
- No security/data migration, device reset, firmware update or BLE retesting.
