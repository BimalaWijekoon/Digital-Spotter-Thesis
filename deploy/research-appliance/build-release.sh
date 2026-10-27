#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 EMPTY_DESTINATION" >&2
  exit 2
fi

destination=$1
if [ -e "$destination" ]; then
  echo "destination already exists: $destination" >&2
  exit 2
fi

repository=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
model="$repository/models/digital_spotter_v5_imu_synthetic_r1"
test -f "$model/MODEL_MANIFEST.json"

mkdir -p "$destination/scripts" "$destination/deploy" "$destination/model"
cp -a "$repository/src" "$destination/src"
find "$destination/src" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$destination/src" -type d -name __pycache__ -empty -delete
cp -a "$repository/scripts/run_workout.py" \
  "$repository/scripts/research_camera_publisher.py" \
  "$repository/scripts/research_camera_publisher.sh" \
  "$destination/scripts/"
cp -a "$repository/deploy/research-appliance" "$destination/deploy/"
cp -a "$repository/deploy/mediamtx.research-on-demand.yml" "$destination/deploy/"
cp -a "$repository/pyproject.toml" "$destination/"
cp -a "$model/." "$destination/model/"

# WSL-mounted workspaces may report every file as executable. Normalize release
# data/config first, then opt in only the scripts systemd/MediaMTX execute.
find "$destination" -type f -exec chmod 0644 {} +
chmod 0755 \
  "$destination/scripts/research_camera_publisher.sh" \
  "$destination/deploy/research-appliance/build-release.sh" \
  "$destination/deploy/research-appliance/configure-tailscale-serve.sh" \
  "$destination/deploy/research-appliance/run-core.sh" \
  "$destination/deploy/research-appliance/run-imu.sh" \
  "$destination/deploy/research-appliance/run-media.sh"

(
  cd "$destination"
  find . -type f ! -name RELEASE_MANIFEST.sha256 -print0 \
    | sort -z \
    | xargs -0 sha256sum > RELEASE_MANIFEST.sha256
)
