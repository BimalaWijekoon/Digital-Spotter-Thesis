#!/bin/sh
set -eu

: "${DS_RELEASE_DIR:?}"
: "${DS_BLE_PYTHON:?}"
: "${DS_RUNTIME_DIR:?}"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$DS_RELEASE_DIR/src"

attempt=0
while [ ! -S "$DS_RUNTIME_DIR/imu.sock" ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 100 ]; then
    echo "core IMU socket did not become ready" >&2
    exit 1
  fi
  sleep 0.2
done

exec "$DS_BLE_PYTHON" -B -m digital_spotter.imu.r9_runtime \
  --device-id "${DS_IMU_DEVICE_ID:-dsimu-r9-50787d92611a}" \
  --device-name "${DS_IMU_DEVICE_NAME:-ESP32-C3-Test}" \
  --device-address "${DS_IMU_DEVICE_ADDRESS:-50:78:7D:92:61:1A}" \
  --socket "$DS_RUNTIME_DIR/imu.sock" \
  --control-socket "$DS_RUNTIME_DIR/imu-control.sock"
