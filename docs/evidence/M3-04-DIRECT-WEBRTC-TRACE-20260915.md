# M3-04 direct WebRTC trace

**Date:** 2026-09-15
**Scope:** Steps 1-4: relay, browser contract, timestamp matching, and overlay code
**Environment:** E0 local development process; no Pi, camera, browser, or ESP32-C3

## Implemented claim

- `deploy/mediamtx.yml` keeps Picamera2 as the sole camera owner, accepts the
  encoded RTSP publisher only on `127.0.0.1:8554`, and defines publisher-only path
  `picamera2`.
- `video.publish_url` and `DS_VIDEO_PUBLISH_URL` are typed configuration inputs.
  A configured URL must be loopback RTSP with an explicit port and stream path.
- `ds-vision-agent` uses the typed value when `--publish-url` is absent. The
  explicit CLI option retains precedence.
- Defaults remain `vision_pipeline=legacy`, simulated adapters, and no video
  publication URL; this slice cannot start a second camera owner implicitly.
- `whep-player.mjs` wraps MediaMTX's supported reader instead of maintaining a
  second custom WHEP negotiation implementation. It validates an explicit HTTP(S)
  `/whep` endpoint, passes a bounded token separately, ignores stale callbacks,
  and performs deterministic cleanup.
- `digital_spotter.api.video` projects canonical pose events to a strict JSON-safe
  microsecond contract and defines the server half of a correlated monotonic-clock
  exchange. No endpoint is exposed by this slice.
- `pose-sync.mjs` keeps eight clock observations and a 120-pose timeline, selects
  the lowest-RTT clock estimate, and accepts pose matches within 80 ms only.
- `pose-overlay.mjs` projects landmarks into the visible `object-fit: contain`
  video rectangle with device-pixel-ratio scaling. Non-good, simulated, missing,
  or stale pose clears the canvas.
- `live-video-controller.mjs` composes those units around decoded video-frame
  callbacks while leaving the future authenticated message transport injectable.

## Test-driven evidence

The first focused run failed as intended because the canonical deployment files,
typed setting, and runtime wiring did not exist: 9 failed, 9 passed. After the
minimal implementation, the focused relay/config/runtime/adapter gate passed:

```text
26 passed in 2.19s
```

The broader repository regression gate then passed:

```text
286 passed, 7 warnings in 124.75s
```

`git diff --check` passed. `scripts/validate_model.py` could not execute its model
load because this local environment has neither TensorFlow nor `ai_edge_litert`;
the exact error was `RuntimeError: No TFLite runtime could load the model.` This
slice did not change model code or artifacts.

Each Steps 2-4 behavior was also introduced behind a failing focused test. Missing
modules produced the expected import/collection failures; the additional stale
WHEP callback and malformed-reader checks failed 2/6 before lifecycle hardening.
The combined local browser suite passed:

```text
20 passed in 0.26s
```

The affected Python relay/config/vision/browser-contract gate passed:

```text
92 passed, 2 warnings in 71.80s
```

The first repository-wide run hit the existing ten-second timeout in
`test_crashed_worker_process_does_not_mutate_active_database` under full-suite
load after 290 tests passed. That exact test then passed alone in 5.54 seconds; no
unrelated timeout or vision-worker code was changed. One clean full-suite retry
passed:

```text
291 passed, 7 warnings in 95.90s
```

The warnings are existing protobuf/FastAPI deprecations. Final `git diff --check`
also passed.

## Explicitly not proven

- MediaMTX configuration parsing/startup on the Pi;
- real hardware-H.264 publication or WHEP playback;
- authenticated local video access, TLS, origin, or firewall policy;
- a real browser receiving WHEP or providing `captureTime` metadata;
- observed canvas alignment with a person in the camera frame;
- p95 glass-to-glass latency, WAN-disconnected behavior, or multi-client limits.

These require M6 authentication/API work plus E3 hardware/browser evidence. The
migration MJPEG dashboard and historical frontend remain unchanged as rollback;
neither was promoted by this work.
