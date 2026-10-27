# M6-D11 Tailnet-only research URL — 2026-10-26

## Authorization and boundary

The owner explicitly approved exposing the unauthenticated research UI/API,
WHEP and WebRTC transport to authorized devices in the private tailnet, and
explicitly prohibited public Funnel access. HTTPS certificates were enabled with
acknowledgement that the Pi hostname enters public certificate-transparency logs.

Application listeners remain on Pi loopback. Tailscale Serve routes only:

- HTTPS 443 → `127.0.0.1:8766`;
- HTTPS 8443 → `127.0.0.1:8889`;
- tailnet TCP 8189 → `127.0.0.1:8189`.

This was the initial r9-r11 design. The r12 correction below keeps UI/API, WHEP
and RTSP on loopback, removes the TCP proxy, and binds ICE-TCP only to the Pi's
Tailscale IPv4.

## Release

```text
release: digital-spotter-research-appliance-20261026-r9
archive SHA256: d2f4515ab2873690fa93308943f94eae39b95f91d5df129e4503bc61c4598ea9
manifest entries: 251, all verified
```

The failed `r8` activation is retained as evidence: it rejected the HTTPS Origin
because the core still enforced loopback-only origins. `r7` was restored while a
focused server contract was added. `r9` permits only loopback HTTP or HTTPS
`.ts.net` origins; ordinary HTTPS and HTTP tailnet origins remain rejected.

The first owner camera attempt exposed an incomplete r9 integration: the UI
resolved the correct private WHEP URL, but the shared preview wrapper still
rejected every non-loopback host. The generated MediaMTX configuration also
retained the old loopback-only browser Origin. Focused release `r10` repairs
both boundaries without changing BLE, firmware, model or public exposure:

```text
release: digital-spotter-research-appliance-20261026-r10
archive SHA256: b5c3966a909081b216104b1bda3a72e28d5c95d8f9883f0479069656fe84ad6a
manifest entries: 251, all verified
```

Release `r11` then removes one misleading browser-console error without changing
camera behavior. The UI no longer fetches the optional saved-result route while
the pose-test state is `idle`; the main status response already contains the
result and reports `complete` when one exists.

```text
release: digital-spotter-research-appliance-20261026-r11
archive SHA256: df1b49acb7e45b13691d165def784032003430f160c99994af4a8243515d2423
manifest entries: 251, all verified
```

Live diagnosis then established that r11 WHEP signaling succeeded while the SDP
advertised only `127.0.0.1:8189`. The remote browser reached `checking` and then
`disconnected`, causing the repeated black-screen reconnect. Release `r12` binds
ICE-TCP directly to the configured Tailscale IPv4 and removes only the obsolete
Serve TCP proxy:

```text
release: digital-spotter-research-appliance-20261027-r12
archive SHA256: 0d0c7ea7f39719b525db50a3da6218a7067e42258653843df98beb2080448a8e
manifest entries: 251, all verified
```

## Focused verification

- Python origin/deployment contracts: 5 passed.
- Browser private-access/camera/WHEP contracts: 3 passed.
- UI through MagicDNS HTTPS: HTTP 200.
- Invalid-body demo POST with exact HTTPS Origin/header: HTTP 400, proving the
  request passed the origin guard but was rejected by payload validation; no cue.
- WHEP HTTPS proxy root: HTTP 404 as expected for a path-only WHEP service.
- Target/core/IMU/media: all active after the r9 switch.
- IMU: current 100-sample window, sequences 548–647; status remains degraded.
- `tailscale serve status`: all three routes labelled `tailnet only`.
- Funnel: not enabled.
- r10 preview/private-access/UI checks: 11 passed.
- r10 deployment launcher checks: 3 passed.
- r11 focused UI/preview/launcher checks: 12 passed.
- r12 focused launcher checks: 3 passed.
- r12 MediaMTX listener: `100.104.28.69:8189` for ICE-TCP; WHEP and RTSP remain
  on loopback; Tailscale Serve retains only HTTPS 443 and 8443.
- One bounded real-hardware headless-browser check decoded 1280x720 H.264,
  advanced 98 frames in three seconds, reached ICE/peer `connected`, and stopped
  cleanly. Its selected remote candidate was TCP `100.104.28.69:8189`.
- r10 generated MediaMTX Origin:
  `https://pidigitalspotter.taile5c9b9.ts.net`.
- r10 UI, versioned camera module and WHEP path checks: HTTP 200, HTTP 200 and
  HTTP 405 respectively; 405 is expected for GET on a POST-only WHEP endpoint.

Real on-demand browser decoding now passes through r12. Owner visual confirmation
of stable, non-flickering rendering remains the final human-visible check.

## Rollback

For the immediate rollback, point `current` back to `r11`, run
`tailscale serve --bg --yes --tcp=8189 tcp://127.0.0.1:8189`, and restart media.
For the full direct-access rollback, run `tailscale serve reset`, restore
`~/.config/digital-spotter-research/appliance.env.before-r9-tailscale`, point
`~/digital-spotter-research/current` back to `r10` (harmless initial 404 retained),
`r9` (camera regression retained), or `r7` (pre-Serve access), and restart
core/media.
