# Research appliance deployment

This package makes the already validated research demonstration start at Pi
boot without changing Wi-Fi, Tailscale, SSH, BlueZ pairing, or ESP firmware.

Services:

- `digital-spotter-research-core`: private UI/API, model replay and Pi GPIO;
- `digital-spotter-research-imu`: the single BLE owner and wearable cue bridge;
- `digital-spotter-research-media`: private MediaMTX with on-demand camera/pose;
- `digital-spotter-research.target`: starts the three services together.

UI/API, WHEP and RTSP listeners remain on loopback. For direct private access,
Tailscale Serve proxies the two HTTPS listeners while MediaMTX binds ICE-TCP only
to the configured Tailscale IPv4. It never binds ICE to LAN/wildcard addresses or
enables Funnel. The camera starts only when a browser requests it. Configure the
exact MagicDNS HTTPS origin and stable Tailscale IPv4 address in `appliance.env`
before enabling direct access. The older SSH-tunnel path requires a release whose
ICE listener is on loopback.
The Pi RGB is dim blue while `wlan0` has a local IPv4 address and slowly pulses
amber while disconnected. Demo feedback temporarily overrides this status. The
network indicator never buzzes. The wearable remains BLE-only and dark at idle.

This is a research demonstration appliance. It does not make synthetic replay
predictions into calibrated live form assessment, and it does not close the
production authentication/security gates in `PLAN.md`.

The Pi account uses systemd user lingering so this starts at boot without storing
a sudo password. Rollback is to disable the user target, restore the previous
`~/digital-spotter-research/current` symlink (if one existed), and restart that
earlier target. Preserve the prior symlink target before activation.
