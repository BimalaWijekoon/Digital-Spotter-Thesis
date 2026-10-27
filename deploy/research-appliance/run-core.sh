#!/bin/sh
set -eu

: "${DS_RELEASE_DIR:?}"
: "${DS_CORE_PYTHON:?}"
: "${DS_MODEL_PACKAGE:?}"
: "${DS_STATE_ROOT:?}"
: "${DS_RUNTIME_DIR:?}"

run_id=$(date -u +%Y%m%dT%H%M%SZ)-$$
run_dir="$DS_STATE_ROOT/runs/$run_id/core"
mkdir -p "$DS_STATE_ROOT/runs" "$DS_RUNTIME_DIR"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$DS_RELEASE_DIR/src"

set -- "$DS_CORE_PYTHON" -B "$DS_RELEASE_DIR/scripts/run_workout.py" \
  --run-dir "$run_dir" \
  --socket-dir "$DS_RUNTIME_DIR" \
  --model-package "$DS_MODEL_PACKAGE" \
  --model-version digital_spotter_v5_imu_synthetic_r1 \
  --enable-demo \
  --enable-demo-feedback \
  --edge-device-id "${DS_EDGE_DEVICE_ID:-pi4-digital-spotter}" \
  --imu-device-id "${DS_IMU_DEVICE_ID:-dsimu-r9-50787d92611a}" \
  --wifi-interface "${DS_WIFI_INTERFACE:-wlan0}" \
  --port "${DS_HTTP_PORT:-8766}" \
  --allowed-origin "${DS_ALLOWED_ORIGIN:-http://127.0.0.1:4174}"

if [ "${DS_PI_RGB_COMMON_ANODE:-false}" = "true" ]; then
  set -- "$@" --pi-rgb-common-anode
fi

exec "$@"
