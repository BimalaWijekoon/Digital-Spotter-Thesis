#!/bin/sh
set -eu

# Tailscale Serve keeps the HTTP application upstreams on Pi loopback. MediaMTX
# binds ICE-TCP directly to the configured Tailscale IPv4 address so its SDP
# advertises a browser-reachable candidate. Never use Funnel.
command -v tailscale >/dev/null 2>&1
tailscale serve --bg --yes --https=443 http://127.0.0.1:8766
tailscale serve --bg --yes --https=8443 http://127.0.0.1:8889
tailscale serve --yes --tcp=8189 off
tailscale serve status
