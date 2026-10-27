#!/bin/sh
set -eu

: "${DS_RELEASE_DIR:?}"
: "${DS_MEDIAMTX_BIN:?}"
: "${DS_RUNTIME_DIR:?}"
: "${DS_POSE_PYTHON:?}"
: "${DS_CAMERA_PYTHON:?}"

export DS_RESEARCH_PYTHON="${DS_CAMERA_PYTHON}"
export DS_RESEARCH_POSE_PYTHON="${DS_POSE_PYTHON}"
export DS_RESEARCH_CAMERA_PYTHON="${DS_CAMERA_PYTHON}"
export DS_RESEARCH_VISION_SRC="$DS_RELEASE_DIR/src"
export DS_RESEARCH_VISION_SOCKET="$DS_RUNTIME_DIR/vision.sock"
export DS_RESEARCH_CAMERA_ID="${DS_CAMERA_ID:-imx219-001}"
export DS_DEVICE_ID="${DS_EDGE_DEVICE_ID:-pi4-digital-spotter}"
export DS_RESEARCH_EXTRA_SITE_PACKAGES="${DS_CAMERA_SITE_PACKAGES:-/usr/lib/python3/dist-packages}"

webrtc_host=${DS_TAILSCALE_IP:-127.0.0.1}
allowed_origin=${DS_ALLOWED_ORIGIN:-http://127.0.0.1:4174}
case "$webrtc_host" in
  ''|*[!0-9.]*) echo "invalid DS_TAILSCALE_IP" >&2; exit 2 ;;
esac
old_ifs=$IFS
IFS=.
set -- $webrtc_host
IFS=$old_ifs
if [ "$#" -ne 4 ]; then echo "invalid DS_TAILSCALE_IP" >&2; exit 2; fi
for octet in "$@"; do
  case "$octet" in ''|*[!0-9]*) echo "invalid DS_TAILSCALE_IP" >&2; exit 2 ;; esac
  if [ "$octet" -gt 255 ]; then echo "invalid DS_TAILSCALE_IP" >&2; exit 2; fi
done

case "$allowed_origin" in
  http://127.0.0.1:[0-9]*)
    origin_port=${allowed_origin#http://127.0.0.1:}
    case "$origin_port" in ''|*[!0-9]*) echo "invalid DS_ALLOWED_ORIGIN" >&2; exit 2 ;; esac
    ;;
  https://*.ts.net)
    origin_host=${allowed_origin#https://}
    case "$origin_host" in ''|*[!a-z0-9.-]*|.*|*.) echo "invalid DS_ALLOWED_ORIGIN" >&2; exit 2 ;; esac
    ;;
  *) echo "invalid DS_ALLOWED_ORIGIN" >&2; exit 2 ;;
esac

media_config="$DS_RUNTIME_DIR/mediamtx.research-on-demand.yml"
sed \
  -e "s/webrtcLocalTCPAddress: 127\.0\.0\.1:8189/webrtcLocalTCPAddress: $webrtc_host:8189/" \
  -e "s/webrtcAdditionalHosts: \[127\.0\.0\.1\]/webrtcAdditionalHosts: [$webrtc_host]/" \
  -e "s|webrtcAllowOrigin: .*|webrtcAllowOrigin: $allowed_origin|" \
  "$DS_RELEASE_DIR/deploy/mediamtx.research-on-demand.yml" > "$media_config"

cd "$DS_RELEASE_DIR/scripts"
exec "$DS_MEDIAMTX_BIN" "$media_config"
