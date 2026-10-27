# M3-04 custom research viewer — 2026-09-15

**Scoped result: PASS, E0 + E3. M3-04 as a whole remains in progress.**

The new private preview page composes the existing `MediaMtxWhepPlayer` with the
official MediaMTX v1.12.3 standalone reader. Real playback works with the Pi's
unchanged v1.9.1 server; a server upgrade was not necessary. This run used our
page/wrapper, not MediaMTX's built-in viewer or an iframe.

## Real evidence

| Measurement | Result |
|---|---|
| Camera/server | Real Pi Picamera2 hardware H.264 -> MediaMTX v1.9.1 |
| Reader | Official v1.12.3, unmodified local asset with MIT license |
| Browser | Headless Chromium 151.0.0.0 on Linux x86_64 |
| Video dimensions | 1280 x 720 |
| New frames during approximately 3 seconds | 89 (approximately 29.7 fps) |
| Total frames at observation | 99 |
| Reported total dropped frames | 4 |
| Media time advance | 3.006 seconds |
| readyState / wrapper state | 4 / playing |
| Stop button | stopped state and `video.srcObject === null` |
| Probe result | `passed=true`, `clean_stop=true`, exit 0 |
| Capture diagnostic | 1669 lores frames, no recording, clean stop, exit 0 |
| Power | `throttled=0x0` before/after |
| Temperature | 54.5 C during run, 55.5 C after cleanup |

Exact browser output: `M3-04-CUSTOM-VIEWER-20260915.json`.
Relay evidence shows one published H264 track, one established ICE/TCP peer,
one H264 reader and peer closure. Local server logs show HTTP 200 for the custom
page, page controller, composition, canonical player and pinned reader. The only
asset 404 was the browser's optional favicon request; playback succeeded.

The final capture was stopped using SIGTERM to its verified diagnostic PID.
The camera helper and relay then closed. A final Pi process/listener inspection
showed no preview/camera/MediaMTX process and no preview listeners. The local
static server and SSH forwards also stopped. No service was installed or enabled.

## Implementation and controls

- `research-preview.html`: minimal diagnostic page with endpoint input, Start,
  Stop, safe status and a muted inline video. Explicitly no exercise analysis.
- `research-preview-page.mjs`: DOM events only, using the composition below.
- `research-preview.mjs`: existing canonical player plus official reader,
  loopback-only endpoint restriction, two-minute deadline and explicit cleanup.
- `vendor/mediamtx-v1.12.3/`: unmodified reader, MIT license and hash/source pin.
- `scripts/video_browser_probe.mjs`: optional WHEP argument drives the custom
  page's real form and Stop button; checks advancing decoded frames and cleanup.

This pinned reader does not support bearer tokens. The research composition
rejects nonempty tokens; no authentication guarantee is claimed. Existing player
validation rejects embedded credentials/query strings; errors shown in the page
do not expose upstream detail. No secrets, provisioned keys or camera images were
added. Upstream codec probes contain synthetic SDP constants, not real credentials.

Reader SHA256:
`1d899415b8065a5cb2602cdeb968dd07497d2a3f009e904809435202f8c44bce`.
Server binary SHA256 (unchanged from preceding step):
`647a051408edf0def091e389e0ba8657f5b860dca05c233a558bf818d75e0305`.
Official source: [reader v1.12.3](https://github.com/bluenviron/mediamtx/blob/v1.12.3/internal/servers/webrtc/reader.js),
[MIT license](https://github.com/bluenviron/mediamtx/blob/v1.12.3/LICENSE).

## Reproduction boundary

Reuse the preceding playback report's isolated camera/relay launch. Set only the
temporary relay's `MTX_WEBRTCALLOWORIGIN=http://127.0.0.1:8765`. Keep RTSP, WHEP and
ICE-TCP listeners on Pi loopback, SSH forwarding local TCP ports 8889 and 8189.
No public endpoints, no direct LAN UDP, no permanent configuration changes.

On the workstation, serve only the static asset directory:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory src/digital_spotter/web/static
```

Open `http://127.0.0.1:8765/research-preview.html`, enter
`http://127.0.0.1:8889/picamera2/whep`, and press Start. The local static page alone
does not start the Pi camera or relay. For the numeric automated probe:

```text
node scripts/video_browser_probe.mjs CHROMIUM_EXECUTABLE http://127.0.0.1:8765/research-preview.html http://127.0.0.1:8889/picamera2/whep
```

The actual static server had a 180-second outer timeout; camera and relay had
their previous bounded timeouts and were stopped early. No preview remains live
after handoff. The remote relay log is retained in the preceding isolated preview
directory as `relay-custom-viewer.log`, without overwriting the earlier result.

## Verification and remaining gates

The first new test failed on the intentionally missing composition module.
After implementation, four new tests pass: asset/license pins, composition and
timeout, prohibited endpoints/credentials, and manual cleanup/error redaction.
The complete browser module command `node --test tests/web/*.mjs` passed
**24/24**. These use deterministic fakes; the Chromium check above is separate
real-hardware evidence. Node syntax and `git diff --check` pass.

No full Python/model suite was rerun: no Python runtime or model implementation
changed. No BLE test, ESP upload, reboot, package/server upgrade, database change,
security migration, cloud call or camera-image retention occurred.

Not proven: human-viewed visual quality, physical overlay alignment, pose/clock
message transport, video captureTime semantics, browser network-loss recovery,
direct-LAN p95 latency, offline/multi-client operation or production access control.
Four dropped browser frames are recorded, not hidden as loss-free delivery.

Next bounded task: connect canonical pose/health and clock messages to this
research browser and verify explicit unavailable/stale states without a person.
Keep human-camera and mounted acceptance last. Changes are uncommitted; no push.
