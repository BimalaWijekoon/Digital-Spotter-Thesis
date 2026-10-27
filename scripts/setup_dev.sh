#!/usr/bin/env bash
# Temporary M0 development bootstrap. M1-01 will replace this with a locked package.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV_VENV="${DS_DEV_VENV:-${PROJECT_ROOT}/.venv}"
DEV_UV_CACHE="${DS_UV_CACHE_DIR:-/tmp/digital-spotter-uv-cache}"
PYTHON_BIN="${DEV_VENV}/bin/python"
POSE_MODEL_SHA256="59e42d71bcd44cbdbabc419f0ff76686595fd265419566bd4009ef703ea8e1fe"
POSE_MODEL_URL="https://storage.googleapis.com/mediapipe-assets/pose_landmark_heavy.tflite"

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is required; install it from https://docs.astral.sh/uv/" >&2
    exit 1
fi

mkdir -p "${DEV_UV_CACHE}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    UV_CACHE_DIR="${DEV_UV_CACHE}" uv venv --python 3.12 "${DEV_VENV}"
elif ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
    echo "error: existing environment is not Python 3.12: ${DEV_VENV}" >&2
    echo "remove it or choose another path with DS_DEV_VENV" >&2
    exit 1
fi

UV_CACHE_DIR="${DEV_UV_CACHE}" uv pip install \
    --python "${PYTHON_BIN}" \
    -r "${PROJECT_ROOT}/requirements.txt"

POSE_MODEL_PATH="$(${PYTHON_BIN} -c 'from pathlib import Path; import mediapipe; print(Path(mediapipe.__file__).parent / "modules/pose_landmark/pose_landmark_heavy.tflite")')"

if [[ -f "${POSE_MODEL_PATH}" ]]; then
    INSTALLED_SHA256="$(sha256sum "${POSE_MODEL_PATH}" | awk '{print $1}')"
else
    INSTALLED_SHA256=""
fi

if [[ "${INSTALLED_SHA256}" != "${POSE_MODEL_SHA256}" ]]; then
    MODEL_TMP="${POSE_MODEL_PATH}.download"
    mkdir -p "$(dirname "${POSE_MODEL_PATH}")"
    curl --fail --location --retry 3 --output "${MODEL_TMP}" "${POSE_MODEL_URL}"
    DOWNLOADED_SHA256="$(sha256sum "${MODEL_TMP}" | awk '{print $1}')"
    if [[ "${DOWNLOADED_SHA256}" != "${POSE_MODEL_SHA256}" ]]; then
        rm -f "${MODEL_TMP}"
        echo "error: MediaPipe model checksum mismatch" >&2
        exit 1
    fi
    mv "${MODEL_TMP}" "${POSE_MODEL_PATH}"
fi

echo "Development environment ready: ${DEV_VENV}"
echo "Run tests: ${PYTHON_BIN} -m pytest tests -q"
