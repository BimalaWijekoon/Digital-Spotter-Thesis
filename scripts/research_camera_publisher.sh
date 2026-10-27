#!/bin/sh
# MediaMTX runOnDemand hook for the private research UI.
set -eu
: "${DS_RESEARCH_PYTHON:?Set the isolated Pi Python path}"
: "${DS_RESEARCH_VISION_SRC:?Set the existing vision source directory}"
: "${DS_RESEARCH_EXTRA_SITE_PACKAGES:?Set the Pi OpenCV site-packages directory}"
: "${RTSP_PORT:?MediaMTX must provide RTSP_PORT}"
: "${MTX_PATH:?MediaMTX must provide MTX_PATH}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$DS_RESEARCH_VISION_SRC"
if [ -n "${DS_RESEARCH_VISION_SOCKET:-}" ]; then
  : "${DS_RESEARCH_POSE_PYTHON:?Set an isolated pose Python without TensorFlow}"
  : "${DS_RESEARCH_CAMERA_PYTHON:?Set the system Picamera2 Python path}"
  : "${DS_RESEARCH_CAMERA_ID:?Set the camera identifier}"
  : "${DS_DEVICE_ID:?Set the research Pi identifier}"
  export DS_VISION_PIPELINE=canonical
  export DS_VISION_ADAPTER=real
  exec "$DS_RESEARCH_POSE_PYTHON" -m digital_spotter.vision.runtime \
    --camera-id "$DS_RESEARCH_CAMERA_ID" \
    --camera-python "$DS_RESEARCH_CAMERA_PYTHON" \
    --socket "$DS_RESEARCH_VISION_SOCKET" \
    --core-uid "$(id -u)" \
    --publish-url "rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}"
fi
exec "$DS_RESEARCH_PYTHON" "$script_dir/research_camera_publisher.py" \
  --publish-url "rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}" \
  --extra-site-packages "$DS_RESEARCH_EXTRA_SITE_PACKAGES"
