# Digital Spotter operations and recovery

**Status:** Target operating model; not yet implemented
**Last reviewed:** 2026-09-28

This document defines how a product device should install, boot, report health,
update, recover, and support field incidents. Current prototype service files do
not yet satisfy it.

## 1. Operating principles

- The local exercise loop has no WAN dependency.
- Application releases are immutable; device data/configuration is separate.
- Services are unprivileged, supervised, bounded, and independently diagnosable.
- A device always reports `starting`, `ready`, or `degraded` with reasons.
- Updates are signed, atomic, health-gated, and rollback-capable.
- Database backup occurs before migration/update.
- Logs/support bundles are bounded and redacted.
- Recovery avoids source-code edits on a customer device.

## 2. Target filesystem

```text
/opt/digital-spotter/releases/<version>/
/opt/digital-spotter/current -> releases/<version>
/etc/digital-spotter/config.toml
/etc/digital-spotter/secrets.env
/var/lib/digital-spotter/db/digital-spotter.sqlite3
/var/lib/digital-spotter/models/<package-id>/
/var/lib/digital-spotter/identity/wearable-device-id
/var/lib/digital-spotter/identity/wearable-device-key
/var/lib/digital-spotter/backups/
/var/cache/digital-spotter/updates/
/run/digital-spotter/*.sock
```

Ownership and modes:

- code/releases: root-owned, read-only to services;
- config: root-owned, readable only as needed;
- secrets/identity: root or narrow service identity, mode `0600`/directory `0700`;
- database/model/cache: dedicated `digital-spotter` service user/group;
- runtime sockets: service group, restrictive umask;
- logs: journald or bounded files with redaction/rotation.

Do not deploy from a mutable Git checkout or repository-local virtual environment
in the final image.

In the deferred secure-product profile, `wearable-device-key` is exactly 32 raw
random bytes, owned by the IMU service user,
mode `0600`, and never a symlink. It must match the key provisioned into that
wearable's protected NVS. Missing, all-zero, wrong-length, or permissive key files
stop the IMU agent. Key generation, NVS installation, backup policy, rotation, and
destructive reset belong to the approved physical provisioning procedure; operators
must not create a convenient shared/default key.

The deferred manufacturing, confidential claim import, physical controller-binding,
and destructive recovery design is in `WEARABLE_PROVISIONING.md`. No active R9
production-security build exists. Any future first boot that can burn security
eFuses requires a new reviewed implementation and the recorded owner/manufacturing
gate.

## 3. Services and boot order

Target units:

- `digital-spotter-vision.service`
- `digital-spotter-imu.service`
- `mediamtx.service`
- `digital-spotter-core.service`
- `digital-spotter-sync.service`
- `digital-spotter.target`

Suggested ordering:

1. local filesystem/database prerequisites;
2. Bluetooth/camera system services;
3. vision and IMU agents;
4. MediaMTX;
5. core API/session service;
6. sync after network-online, without blocking local readiness.

The core can be `ready` for local history while camera/IMU is degraded, but it
cannot be `ready_for_multimodal_session` until all required gates pass.

Each service defines:

- unprivileged user/group and minimum device/DBus/network access;
- environment/config paths;
- startup/readiness timeout;
- watchdog heartbeat;
- capped restart policy and start-limit behavior;
- graceful stop timeout;
- memory/tasks/file limits based on measured headroom;
- systemd hardening validated against actual hardware access.

## 4. Configuration profiles

`config.toml` has a schema/version and profile:

- `development`: allows explicit fakes/diagnostics and local debug output;
- `test`: deterministic temporary paths and fake/replay adapters;
- `production`: rejects mock adapters, wildcard CORS, missing model/signature,
  default credentials, insecure TLS, and unsafe paths.

Configuration includes only non-secret settings such as rates, ports, paths,
feature flags, retention quotas, allowed origins, and product limits. Secrets come
from protected files/identity storage. Startup validates all cross-field
constraints and records a safe config hash.

## 5. Health model

Every component exposes:

```text
state: starting|ready|degraded|stopping
reason_codes: list
since_monotonic_ns
software/firmware/model/protocol versions
last_success time
error/drop/reconnect counters
is_simulated
```

Top-level readiness dimensions:

- `ready_for_history`
- `ready_for_video`
- `ready_for_vision`
- `ready_for_imu`
- `ready_for_multimodal_session`
- `ready_for_cloud_sync`

No single `all_ready` boolean may hide which real component is mocked, stale, or
incompatible.

## 6. Observability

At minimum collect:

### Core

- sessions/reps by state and result;
- event-loop delay, inference latency, fusion alignment/quality;
- database transaction latency/errors and outbox depth/age;
- storage free/used/quota and schema/model versions.

### Vision

- captured/processed/dropped frames;
- pose found/visibility/latency/FPS;
- camera/encoder/MediaMTX reconnect/restart;
- CPU/RSS/temperature/throttle indicators.

### IMU

- connected/bonded/provisioned state;
- sample rate, sequence gaps/loss/bursts;
- notification/parse errors, RSSI where meaningful;
- clock offset/drift/error, reconnect count/time;
- battery, calibration, saturation, firmware/boot ID.

### Sync/API/security

- request latency/status/rate limiting/auth failures;
- upload success/retry/permanent reject and oldest outbox age;
- pairing/key/update/reset/audit events;
- no secret/raw media/raw stream in logs.

Metrics are kept locally in bounded form; only approved aggregates reach cloud.

## 7. Normal operator checks

Target commands will be packaged as `dsctl`:

```text
dsctl status
dsctl readiness
dsctl versions
dsctl sensor identify
dsctl sensor calibrate
dsctl session list
dsctl storage status
dsctl sync status
dsctl diagnostics collect --redacted
dsctl update status
dsctl rollback
```

These commands are a target interface, not currently implemented. They use the
local authenticated control boundary rather than reaching into Python internals.

## 8. Boot and readiness runbook

1. Verify stable power and active cooling.
2. Mount/position Pi camera and sensor according to the approved hardware guide.
3. Boot and wait for `digital-spotter.target` health timeout.
4. Check top-level and component reason codes.
5. If model/config/schema mismatch occurs, do not start a session; validate signed
   package and rollback if necessary.
6. If BLE is unprovisioned, enter physical pairing rather than using a default key.
7. If WAN/cloud is unavailable, local session may continue and sync remains
   degraded.
8. Verify storage headroom and temperature before a long session.

## 9. Common failure runbooks

### ESP32-C3 disconnected

1. Observe device ID, last sample, battery, gap/reconnect counters, and reason code.
2. Keep session local but suppress multimodal scoring while IMU is stale.
3. Allow bounded automatic reconnect.
4. Use physical identify/re-pair only after identity/bond diagnosis.
5. Do not silently connect to the first advertising sensor.

### Camera/pose unavailable

1. Confirm vision service and camera ownership; no second process may hold camera.
2. Check camera/encoder/MediaMTX states separately.
3. Treat the canonical adapter's consecutive-timeout failure as
   `camera_unavailable`; close/reap its system-Python Picamera2 helper before a
   fresh owner is started.
4. The feature-gated `ds-vision-agent` component entry point can emit structured
   state transitions, heartbeat counters, and typed failure reasons; its consumer
   watchdog can detect missing heartbeats. It is not installed as a product
   systemd service and the product core does not yet consume its socket.
5. For a controlled development run, first stop the legacy camera owner and start
   a restrictive core-side vision event socket. Set `DS_VISION_PIPELINE=canonical`
   and `DS_VISION_ADAPTER=real`, then invoke the module with explicit
   `--camera-id`, `--camera-python`, `--socket`, and `--core-uid` values. Never run
   it concurrently with the legacy `FrameProcessor`.
6. Returning `DS_VISION_PIPELINE` to `legacy` and using the unchanged migration
   dashboard is the rollback. It does not start the canonical camera agent.
7. For the M3-04 development relay, start MediaMTX with
   `deploy/mediamtx.yml` and configure the vision agent with
   `DS_VIDEO_PUBLISH_URL=rtsp://127.0.0.1:8554/picamera2`. The RTSP publisher input
   is loopback-only. The WHEP listener is not yet authenticated and must remain on
   a controlled bench; do not install either process as a product service from this
   example.
   The reusable browser modules are not wired into the supported launcher. Until
   M6 supplies an authenticated stream-config/WSS boundary and E3 browser tests
   pass, rollback is the unchanged migration dashboard. Do not expose the WHEP
   listener or invent a static bearer token to activate these modules.
8. Restart the vision service within the configured restart limit only after a
   reviewed service definition is deployed. In-process endless retry is not
   permitted.
9. Preserve session/history; suppress analysis requiring vision.
10. Escalate repeated restart loops instead of running an endless crash cycle.

### Temporary joined-capture research check

`scripts/validate_joint_capture.py` is a bounded development diagnostic, not
an installed service. With only one real IMU agent and one real vision agent
publishing to its two local sockets, it opens one disposable SQLite session,
waits briefly for both event streams, retains a bounded latest-pose ring, and
reports capture counts and original Pi-monotonic timestamp ranges. It does not
fuse, infer, or save an analysis result. Do not run it beside the legacy camera
owner, repeat BLE pairing, or treat an empty-scene degraded pose as a person
test. The first real Pi invocation and its limitations are recorded in
`docs/evidence/JOINT-CAPTURE-20260928.md`.

### Private M3-04 browser playback diagnostic

For a bounded M3-04 private video diagnostic, see
`docs/evidence/M3-04-BROWSER-PLAYBACK-20260915.md`. The installed MediaMTX v1.9.1
built-in viewer passed real Chromium playback through loopback/SSH ICE-TCP; it
does not expose the standalone reader class expected by the new custom wrapper.
The isolated `research-preview.html` now supplies a locally pinned official
v1.12.3 reader compatible with that existing server for the measured playback
path. Serve only `src/digital_spotter/web/static` on local loopback port 8765;
use a private SSH tunnel for Pi WHEP 8889 and ICE-TCP 8189, with the process-local
relay allow-origin set to `http://127.0.0.1:8765`. Enter the forwarded WHEP URL in
the page and press Start; Stop/page exit or its two-minute deadline closes the
player. There is no video recording, pose overlay, authentication or installed
service in that dated playback run. The subsequent local M3-04 research bridge
adds temporary pose/clock delivery and canvas wiring but remains uninstalled;
the first real Pi event check did not complete the browser timing gate. Run it
only on a controlled loopback/SSH bench with a bounded duration. A timeout must
remove its own Unix socket; verify listeners and camera process cleanup before
any rerun. See `docs/evidence/M3-04-POSE-TELEMETRY-20260928.md`. The earlier
run/evidence commands are in
`docs/evidence/M3-04-CUSTOM-VIEWER-20260915.md`.
`scripts/video_preview_capture.py` reuses
the existing camera adapter and closes it after 10..300 seconds or SIGTERM. Its
`--extra-site-packages` option affects the parent only: never export Python 3.12
binary-wheel directories through `PYTHONPATH` into the system-Python helper.
Do not expose the temporary listener publicly or install it as a service.

The redesigned `ui-preview/` page displays the private WHEP stream inside its
Camera panel. In the Pi-hosted research copy, the button connects to an internal
static configuration and the separate on-demand relay starts the Picamera2 owner
only while a viewer is present. Serve the shared static directory (not only
`ui-preview/`) on loopback; the page origin must match the relay allow-origin.
This remains a research preview, not an installed or authenticated product UI.

### Temporary Pi-hosted Step 1 research shell

The 2026-10-03 isolated copy is under
`~/digital-spotter-research-step1-20261003/` on the Pi.
A temporary static server serves that copy on `127.0.0.1:8766`; it is **not** a
boot service and does not run the camera, session API, or model inference. The
V5 runtime in the directory was separately hash-verified and load-checked.
From the owner's PC, open a private tunnel with
`ssh -N -L 4174:127.0.0.1:8766 <pi-user>@<pi-tailnet-address>`, then visit
`http://127.0.0.1:4174/ui-preview/`. Keep that SSH window open while viewing.
The page intentionally shows unavailable analysis. Before restarting, check
whether port 8766 already has the same static process; never start a second
server or the research-session runner on the same port. To stop this temporary
server, inspect `ss -ltnp` for port 8766, confirm the command points to this
Step 1 directory, then stop that exact PID. Do not expose the listener on LAN.

The original bounded Step 2 camera and relay processes expired and caused
connection refusals. Step 2B now has a separate, research-only on-demand relay
in the same owner-only Pi directory, using
`deploy/mediamtx.research-on-demand.yml` and
`scripts/research_camera_publisher.{sh,py}`. Before running it, verify no other
process owns the camera or ports 8554/8889/8189. It listens only on Pi loopback,
uses the existing Picamera2/H.264 owner, and starts that owner when a WHEP
viewer requests `picamera2`; it stops the owner five seconds after the last
viewer disconnects. The static UI and relay are detached research processes,
not boot services; after a Pi reboot they must be checked/restarted explicitly.
Neither process exposes a LAN endpoint or authenticates video requests.

From the owner's PC, keep this private tunnel open:
`ssh -N -L 4174:127.0.0.1:8766 -L 8889:127.0.0.1:8889 -L 8189:127.0.0.1:8189 <pi-user>@<pi-tailnet-address>`.
Open `http://127.0.0.1:4174/ui-preview/` and press **Connect camera** in the
Workout camera panel. No URL is entered. **Stop camera**, switching to Devices,
or closing/hiding the page ends its reader; MediaMTX then releases the camera.
Ctrl+C in the tunnel terminal only closes the forwarding session; it does not
reset the Pi. To stop the relay itself, identify its exact PID from
`ss -ltnp` on Pi ports 8889/8189 and terminate only that process. A separate
human-viewed quality check is still pending. See
`docs/evidence/M6-03-PI-RESEARCH-UI-STEP2B-20261003.md`.

Step 3 keeps that camera setup but removes the large preview/research badges.
The one-shot `scripts/write_v5_test_input.py` verifies the copied V5 files and
runs one fitted-median reference input on the Pi. Its JSON output is served from
the static `ui-preview/` directory and appears only in Devices → Analysis as
**Test input**. It is not a live session result; Workout Feedback stays
unavailable, and the command makes no SQLite or wearable write. If the file is
absent or invalid the card remains hidden. To update it, use the exact frozen
package and `--output` path documented in
`docs/evidence/M6-03-PI-UI-TEST-INPUT-20261003.md`. The updated Pi UI copy is
reversible from `~/digital-spotter-research-step1-20261003/ui-before-test-input-20261003/`.

### Current isolated unscored status copy

For the 2026-10 assembled wearable PCB, use application version `0.9.1-pcb1`
and its matching allow-listed Pi parser. Pin map: IMU SDA18/SCL19; external
RGB red1/green0/blue3; active-buzzer control10. Program through the USB-UART
bridge with native USB CDC off, converter unplugged, JP1 cap OFF. Unplug USB
before reconnecting the external converter. The old R9 checkpoint binary
expects different sensor/LED wiring; use the passing PCB application checkpoint
once available for functional rollback. Current rollout evidence is
`docs/evidence/M2-07-PCB-INTEGRATION-20261019.md`.

The active 2026-10-03 research copy is
`~/digital-spotter-research-status-20261003/`. It preserves the Step 1 files
and uses the same private tunnel and browser URL above. Port `8766` now serves
the existing read-only `research_status_v1` API alongside the page. The
on-demand relay on loopback `8554/8889/8189` starts the canonical real vision
agent, so one Picamera2 owner supplies both H.264 and pose status. The R9 BLE
agent is a separate single client; if the ESP is absent, wearable status stays
unavailable. The temporary session writes only summary state to its new
isolated SQLite file; it never persists a model analysis or triggers a wearable
cue. No process is installed for boot start, so check listeners/agents after a
Pi reboot. Stop only identified PIDs; the prior Step 1 static page and
camera-only relay remain the rollback. See
`docs/evidence/M6-03-PI-UNSCORED-STATUS-20261003.md`.
The isolated server also supplies `/api/research/imu-window` for the two
display-only browser plots. If the wearable stops, the next publication
contains no graph samples; the UI must not treat an old line as live data.

#### Isolate the pose worker from the model environment

The pose-enabled on-demand hook requires `DS_RESEARCH_POSE_PYTHON`, separate
from the core/camera-only `DS_RESEARCH_PYTHON`. Create its Python 3.12 environment
without `--system-site-packages` and install
`deploy/requirements-pi-vision.txt`. Do not remove TensorFlow or packages from
the existing model/core environments. The system Picamera2 helper remains
`DS_RESEARCH_CAMERA_PYTHON=/usr/bin/python3`; do not install libcamera into the
pose environment or expose system site-packages to make it available there.

Before enabling the pose branch, run the isolated interpreter with
`-c "import importlib.util; assert importlib.util.find_spec('tensorflow') is None; import mediapipe; print(mediapipe.__version__)"`.
MediaPipe 0.10.18 probes optional TensorFlow documentation helpers at import;
exposing a full training environment can therefore consume the relay's
30-second start deadline before opening the camera. Do not mask this by
raising the timeout, patching the third-party package, substituting fake pose,
or changing the trained/live pose configuration. Camera-only mode does not
require the new variable and remains the rollback.

### Short person-in-frame diagnostic

`scripts/run_person_pose_test_ui.py` can replace the temporary static server on
Pi loopback port 8766 while keeping the same SSH tunnel and on-demand camera
relay. It serves the existing UI and one test action. The Camera panel's
**Test pose · 30 s** button stops its WebRTC preview, shows a 20-second countdown
so the operator can walk into frame, then uses the canonical real Picamera2 and
MediaPipe adapters for 30 seconds. The camera cannot be viewed through that
preview during the test because the diagnostic owns it. The test saves only one
aggregate JSON report per run under its configured `--result-dir`; no video,
landmarks, model result, workout session, IMU data, or wearable cue is saved.
Check that no other process owns Picamera2 before starting. This is a private
research bench tool, not a boot service or product API. Stop the identified
port-8766 process before switching back to the prior static/status server.

### Optional local research session-status viewer

`scripts/run_research_session.py` is an **opt-in development process**, not an
installed Pi service. It requires an already migrated SQLite database and the
existing real IMU/vision agents' local socket paths. It refuses an existing
active session and does not migrate a database, launch a camera, connect BLE,
or pair a wearable. It does not load a model by default. From the repository's
Python environment,
provide `--database`, `--imu-socket`, `--vision-socket`, `--edge-device-id`,
`--imu-device-id`, and `--exercise-id 0` (Squat) or `1` (Deadlift). It creates one
local summary-only session, consumes the two event feeds, counts detected reps
outside capture callbacks, and serves the UI at
`http://127.0.0.1:8766/ui-preview/`. A private SSH tunnel is required to view it
from a PC. Stop the process normally to close its sockets and session. The UI's
Start/Pause/Stop buttons remain disabled; it only displays status. No V5 score
or rep analysis event is persisted. For an explicit terminal-only model-path
exercise, add `--shadow-v5-package models/digital_spotter_v5 --load-kg <kg>`.
Both options are required together. The frozen model is loaded before a session
starts; each complete rep invokes reference-only inference off the capture
callback, while the terminal prints only execution/unavailable state. The UI
continues to show analysis unavailable; no probability, class, feedback command,
or SQLite analysis is emitted. This path is experimental until live sensor-unit,
mounting and vision-source calibration is done in the agreed final integrated
test. `--load-kg` is fixed for this research session. Inference currently runs
once per rep on the session loop, not in a high-rate capture callback; its Pi
latency has not been measured. Do not start it alongside another consumer of
the same UDS sockets or present it as a person/mounted validation.

### High temperature/throttling

1. Stop new analysis work safely and report degraded.
2. Verify fan/heatsink, enclosure airflow, ambient temperature, power flags, and
   process CPU.
3. Preserve data and allow cooling; do not hide throttling by reporting average FPS.
4. Repeat the supported soak after corrective action.

### Storage pressure

1. Stop optional raw evidence capture/upload caching first.
2. Preserve database, completed reps, model, identity, and critical logs.
3. Expose remaining space/outbox age and prevent a falsely durable UI state.
4. Apply approved retention; never delete the only unsynchronized user record
   without policy/consent.

### Cloud sync backlog

1. Confirm local session remains healthy.
2. Inspect oldest event, retry reason, gateway response, credentials, and quota.
3. Respect circuit breaker/backoff; do not tight-loop.
4. Rotate/re-authorize only through the device identity workflow.
5. Never bypass the gateway with an Admin key on the Pi.

### Database corruption/migration failure

1. Stop core/sync writers.
2. Preserve the affected file and logs; do not repeatedly mutate it.
3. Verify the pre-migration backup/hash.
4. Restore to a new file/path and run integrity/migration checks.
5. Atomically activate the recovered database after validation.

### Research ESP USB serial monitoring

Arduino serial-monitor defaults can assert DTR/RTS and reset an ESP32-C3. Do not
run the serial monitor during a BLE discovery/reliability gate unless its control
line behavior has been configured and verified. If the monitor leaves the device
non-advertising, close the monitor and use one controlled non-writing hard reset;
do not reflash, erase, or alter BLE configuration as a first response.

### R7 plain-BLE recovery retained by active R9

The active research firmware is intentionally unpaired. After an ordinary client
disconnect it waits 100 ms and attempts to restart advertising at most three
times, with 500 ms between rejected attempts. The retained R9 Pi validator uses
at most three scan/connect attempts with 0, 0.5, and 1.0 second backoff.

Before a recovery test, verify that exactly one Pi BLE client is running. Do not
pair, delete global BlueZ state, erase ESP NVS, or reflash in response to one
timeout. Preserve the attempt log. R7 hardware evidence includes 10/10 ordinary
reconnects, one ESP power-cycle recovery, and one Bluetooth-service restart
recovery. R11 now supplies the boot-capable source/unit; installation remains a
separate controlled deployment check.

### R11 canonical Pi adapter

R11 is now the active source-level Pi adapter. `ds-imu-agent` discovers only
`ESP32-C3-Test` at `50:78:7D:92:61:1A`, validates the exact R9 GATT contract, and
requests no pairing. It uses a bounded 16-packet ingress queue, one-value latest
slot, explicit stream start/stop, and 2/4/8/15-second reconnect backoff. The
research service command requires no wearable key under ADR-019.

The E3 acceptance run used an isolated candidate directory rather than modifying
the Pi system image. Therefore the unit in `scripts/ds-imu.service` is ready for a
later controlled install, but systemd enablement, boot ordering, and reboot
recovery are not yet claimed. Do not install it by overwriting the current Pi
environment ad hoc; use the M8 image/release workflow or a separately reviewed G2
deployment check.

R13-B adds clock acquisition to this same source-level agent without changing the
firmware or installing a service. Normal health must expose clock state, drift,
estimated error, fit points, accepted/rejected exchanges, and exchange age. A
stream may be connected while the clock is still acquiring, but samples are
counted and withheld from the core publisher until clock quality is synchronized.
More than five seconds without an accepted status exchange is degraded and again
closes the publish gate. Do not respond by pairing, reflashing, erasing Bluetooth
state, or substituting arrival time; preserve RTT, gate-drop, and status diagnostics
first.

### Active R9 status, control, and actuator checkpoint

R9 remains intentionally unpaired and unbonded. The standalone Pi validator can
read bounded device/status values and issue only `stream:start`, `stream:stop`,
`identify`, `buzzer:test`, and the idle-only `cue:test`. Unknown, non-printable,
and over-48-byte commands are rejected. Streaming begins only after
`stream:start` and stops idempotently.

The ESP NeoPixel stays steady cyan during the 50 Hz stream because the pinned
driver uses synchronous RMT output. `identify` is accepted during streaming but
its white visual cue is deferred until stream stop. The buzzer test remains
immediate. `cue:test` is rejected while streaming and otherwise shows white boot,
blue advertising, green connected, cyan streaming, orange disconnected, and red
error for 900 ms each. Normal state cues use the same mapping. Nonessential serial
logs are counted and emitted after streaming to avoid perturbing the 20 ms
schedule. Compile with `DS_ENABLE_ACTUATOR_CUES=0` to roll back actuators while
retaining R8 BLE/data behavior.

### Local-only V5 candidate selection (M5-R04)

`scripts/run_workout.py` accepts an explicit `--model-version` alongside
`--model-package`. Default remains `digital_spotter_v5_scope_faithful`; the
opt-in `digital_spotter_v5_imu_synthetic_r1` loader accepts only its matching
verified package and reference-only operation. It does not install/copy models,
start camera/IMU producers or enable live scoring. Use a new run directory to
preserve existing sessions. Local checks and full command syntax are in
`docs/evidence/M5-R04-LOCAL-CANDIDATE-RUNTIME-20261020.md`. Pi deployment and
actual mounted-feature checks remain pending; do not replace the old package.

M5-R05 subsequently staged and checked the candidate in the separate Pi
directory `~/digital-spotter-v5-imu-r1-20261020.E7L664/` without activation. It
reuses the existing core interpreter, not the pose interpreter. Run
`scripts/validate_v5_candidate.py --package package` from that directory with
its `src/` on `PYTHONPATH` for the single provided-fixture compatibility check;
the exact command/result is in
`docs/evidence/M5-R05-PI-CANDIDATE-STAGING-20261020.md`. This starts no services
and establishes no live sensor eligibility. Stale PID/socket files after reboot
are not proof that the UI, relay or capture workers are running.

### First person test on the staged candidate (M6-R01)

The current research run is
`~/digital-spotter-v5-imu-r1-20261020.E7L664/live-20261020.8qqaRH/`.
Core/model use the existing research-status `.venv`; BLE uses the existing
`digital-spotter-r11-candidate/.venv`; pose uses research-status `.venv-pose`
(no TensorFlow visible), and Picamera2 uses system Python. These are separate
processes and interpreters, with the staged `src/` selected through PYTHONPATH.
Do not start BLE in the core environment: it does not contain Bleak.

UI/relay remain loopback-only behind SSH forwards: PC 4174 to Pi 8766,
8889 to 8889, and 8189 to 8189. Open
`http://127.0.0.1:4174/ui-preview/`, choose **Connect camera**, then
**Test pose · 30 s** when ready. The test counts down 20 seconds and captures
30 seconds of aggregate pose quality. Refresh after the 2026-10-20 UI update:
the countdown/capture timer is now a small corner badge, leaving the live
camera visible instead of covering it. The new result is saved under
`core/person-pose-latest.json`; no raw video is saved. A camera marked stale
without a viewer is expected because capture is on demand. A loaded model does
not mean live scoring is authorized.

Runtime PIDs/logs, initial startup evidence and rollback are recorded in
`docs/evidence/M6-R01-FIRST-PERSON-TEST-READY-20261020.md`. These are detached
research processes, not a persistent boot service. Preserve the private run
directory and old runs; verify process identities before stopping recorded PIDs.

M6-R02's detected-versus-quality counter correction and latest-pose guide are
prepared locally, not active on that Pi run. Activate the matching UI/core/API
changes together only after the owner finishes the current camera check; do not
restart a countdown/capture. Back up active source files and preserve the latest
aggregate result. The guide is explicitly unsynchronized and does not change
scoring eligibility. See `docs/evidence/M6-R02-LOCAL-POSE-DIAGNOSTICS-20261020.md`.

### Local Demo UI preview (M6-D01)

Serve `src/digital_spotter/web/static/` on loopback and open
`http://127.0.0.1:4173/ui-preview/#demo`. Select squat/deadlift and correct/incorrect
form scenario, then Start demo; Pause/Resume/Reset control three six-second
animation cycles. Leaving the tab pauses it. This preview uses a pinned local
Three.js renderer and requires WebGL 2, not internet connectivity.

The static preview has no Pi backend: unavailable connections and Not run model
output are intentional, not simulated successes. Do not interpret the animation
as pose inference or generated IMU data. No wearable command, model activation,
service restart or session persistence occurs. Pi activation and later demo
input/inference/feedback slices remain pending; the live Pi was not changed.

### Local Demo model connection (M6-D02)

Use the existing launcher with the explicitly selected synthetic-R1 package:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_workout.py \
  --run-dir /tmp/ds-demo-new-run/core \
  --model-package models/digital_spotter_v5_imu_synthetic_r1 \
  --model-version digital_spotter_v5_imu_synthetic_r1 --enable-demo \
  --edge-device-id local-demo-core --imu-device-id local-demo-wearable \
  --port 4176 --allowed-origin http://127.0.0.1:4176
```

Choose a new run directory each time; the launcher deliberately refuses existing
directories/databases. Open `http://127.0.0.1:4176/ui-preview/#demo`.
This starts a local core, not a Pi connection. No BLE/camera producer is launched;
unavailable hardware and empty live graphs are correct. Demo uses the frozen
replay load (read-only) and runs the real model after each animated rep. Hover the
model result for version/raw/calibrated/threshold metadata. It cannot actuate
hardware or persist scored workout records. Stop this isolated process with
Ctrl+C; no Pi service/configuration was changed. Omit `--enable-demo` to disable.

M6-D03: refresh that same local page for the rigged human. The CC0 GLB, matching
Three.js glTF loader and license/provenance are bundled under `web/static/vendor/`;
no package install or CDN access is needed. Keep that vendor subtree when copying
the UI. A source-label/model disagreement now displays its probability/threshold
comparison; it is not automatically repaired by selecting a different example.

M6-D04 explicitly supersedes that example-selection policy at the owner's request:
bad squat now uses a recognised curated replay (fixture 6, 35 kg). Copy the small
`vendor/cmu-squat/` subtree with UI assets and refresh the page to load capture-
driven squat movement. Deadlift is still illustrative. The real model policy is
unchanged; the known fixture 1 miss is retained in the report/catalog metadata.

M6-D05: refresh the local Demo page and use the IMU source selector. **Replay
inputs** shows three original synthetic phase medians, revealed during playback;
it is not a 50 Hz sensor stream. **Live wearable** shows only actual incoming
telemetry and may correctly say No live data on the PC. These sources never mix.
The local backend must be refreshed together with the UI because its catalog
now includes the phase vectors. Use a fresh temporary run directory; preserve
old runs. The animation's hand/bar contact is still awaiting a better asset.

M6-D06 supersedes that renderer with the owner's four-scenario package. Refresh
`http://127.0.0.1:4176/ui-preview/#demo` (Ctrl+F5 if needed), then choose exercise
and form scenario. Incorrect squat selects the predefined forward-lean clip;
incorrect deadlift selects the predefined spinal-rounding clip. They are not
new model classes or diagnosed errors. Preserve
`vendor/exercise-scenarios-v2/` with its MIT notice when copying the UI. Static
changes need no backend restart. Earlier Review 01 and legacy assets remain
intact but inactive; no supplied authoring programs need to be installed/run.

The later `(2).zip` character revision is now active. Copy
`vendor/exercise-scenarios-character-r1/`, including both license notices, with
the UI instead of relying on the earlier vendor directory. Refresh with Ctrl+F5
to load the new character. Clips/model/controls are unchanged; initial asset
payload is larger (about 24.8 MB across all four GLBs), not a measured Pi result.

### Pi Demo activation with live wearable plots (M6-D07)

The verified 2026-10-23 research run is isolated under:

```text
/home/pibimalawijekoon/digital-spotter-demo-20261023.Yj6ZyB
```

It uses the existing immutable Pi model package at
`/home/pibimalawijekoon/digital-spotter-v5-imu-r1-20261020.E7L664/package`.
The core listens on Pi loopback port 8766 and the single BLE adapter publishes
to that run's `run/core/imu.sock`. View it privately through:

```bash
ssh -N -L 4174:127.0.0.1:8766 <pi-user>@<pi-tailnet-address>
```

Then open `http://127.0.0.1:4174/ui-preview/#demo`. **Live wearable** is the
actual 50 Hz MPU6500 display; **Replay inputs** are the three synthetic fixture
phase values consumed by the reference-only V5 calculation. They never mix.
`degraded` is expected until wearable calibration is certified. Do not treat
this run as a boot service, live-form-scoring release, or camera validation.
The demo endpoint cannot persist analysis or trigger the wearable. Stop the
isolated core and BLE-agent processes before starting another owner of port 8766
or the wearable connection.

### Bootable research appliance candidate (M6-D09)

`deploy/research-appliance/` packages the current research demonstration as three
native user services behind `digital-spotter-research.target`: loopback core/UI,
one BLE owner, and loopback MediaMTX with on-demand camera/pose. Stable UDS files
live under `/run/user/<uid>/digital-spotter-research`; each core start creates
fresh SQLite state under
`~/.local/state/digital-spotter-research/runs/<timestamp>/run/`. Existing runs are
not reused or deleted.

Build a new immutable release directory with `build-release.sh`; verify
`RELEASE_MANIFEST.sha256` before staging it side by side under
`~/digital-spotter-research/releases/`. Review `appliance.env.example` as
`~/.config/digital-spotter-research/appliance.env`, then atomically point
`~/digital-spotter-research/current` to the new release. Do not change Wi-Fi,
Tailscale, SSH, BlueZ pairing, or firmware during installation. The verified Pi
has `loginctl` user lingering enabled, so this user manager starts at boot without
storing or requesting a sudo password.

Install the three units and target in `~/.config/systemd/user`, run
`systemctl --user daemon-reload`, then enable/start only
`digital-spotter-research.target`. Before activation, stop
only identified old manual processes owning the same HTTP port, BLE connection,
or camera. Browser access remains private:

```bash
ssh -N \
  -L 4174:127.0.0.1:8766 \
  -L 8889:127.0.0.1:8889 \
  -L 8189:127.0.0.1:8189 \
  <pi-user>@<pi-tailnet-address>
```

For the owner-approved M6-D11 research exception, `r9` also supports a permanent
tailnet-only HTTPS URL without an SSH forward. Set the appliance environment's
`DS_ALLOWED_ORIGIN` to the exact MagicDNS HTTPS origin and `DS_TAILSCALE_IP` to
the Pi's stable tailnet IPv4 address, restart core/media, then run:

```bash
deploy/research-appliance/configure-tailscale-serve.sh
```

The script creates only HTTPS 443 → loopback 8766 and HTTPS 8443 → loopback 8889,
and removes any former Serve TCP 8189 proxy. MediaMTX binds ICE-TCP 8189 directly
to `DS_TAILSCALE_IP`; it must never bind that port to a LAN address or wildcard.
The script never invokes Funnel. Tailscale Serve and HTTPS certificates must first
be enabled by the tailnet owner; certificate transparency publishes the device
hostname. Verify every `tailscale serve status` entry says `tailnet only`, verify
MediaMTX listens on the exact Tailscale IPv4 for 8189, and verify the exact Origin
guard. The prior r11 plus its TCP Serve mapping is the immediate rollback; the
older SSH-tunnel path requires restoring a loopback-ICE release. To revoke direct
access fully, run `tailscale serve reset`, restore the saved environment/release
link and restart core/media.

The Pi RGB is dim blue while `wlan0` is locally connected and slowly pulses amber
otherwise. It makes no external probe and no sound. Demo cues override network
color until completion. The wearable stays BLE-only and dark at idle. Camera
capture remains on demand when the UI connects.

Rollback: stop/disable the target, restore the recorded previous `current` link,
daemon-reload, and start prior services if any. Preserve the failed release,
journal, and fresh state directory for diagnosis.

## 10. Backup and restore

- Use SQLite online backup/checkpoint semantics, not a blind copy during writes.
- Backup before every schema/application release and on an approved bounded schedule.
- Encrypt backups that contain user data or device identity.
- Record schema/app/model versions and integrity hash.
- Enforce local count/space/age retention without removing the last known-good
  pre-update backup.
- Test restore on a replacement image/device; a created backup is not evidence until
  restored and validated.

## 11. Update lifecycle

1. Download to a bounded cache outside the active release.
2. Verify signed manifest, hashes, product/hardware target, version, and available
   storage.
3. Back up database/config state.
4. Install into a new immutable version directory.
5. Run offline preflight: imports, model manifest, schema plan, config, permissions.
6. Quiesce/stop safely; never interrupt an active session without explicit policy.
7. Run migration and atomically switch `current` symlink.
8. Start services and run bounded health/compatibility smoke.
9. On failure, stop, restore compatible data if necessary, switch back, and record
   rollback audit event.
10. Retain the previous known-good signed release until the observation window ends.

ESP firmware/model updates use the same signed/versioned/rollback principles with
their own compatibility matrix.

## 12. Factory reset and ownership transfer

Factory reset requires physical confirmation and clear warning. It must:

- stop active sessions and sync safely;
- revoke/unbind cloud device authorization when possible;
- delete local user tokens, BLE bonds, device/account bindings, and user data per
  policy;
- preserve only approved manufacturing identity/recovery trust;
- produce a new onboarding state and audit evidence;
- not expose the previous owner's data to the next owner.

Define offline reset behavior and later cloud reconciliation before release.

## 13. Support bundle

A support bundle contains a signed/redacted manifest, versions/config hash, health
states/counters, bounded recent logs, system resource/temperature/throttle data,
database integrity/schema/outbox summary, and update history.

It excludes secrets, authorization headers, Wi-Fi credentials, full device keys,
raw video, raw IMU, unnecessary user attributes, and unbounded database copies. Run
automated redaction/secret tests before release.

## 14. Release checklist summary

- all plan gates through the intended environment pass;
- clean reproducible image and signed artifacts;
- unique device provisioning and revocation tested;
- no secret/default/insecure TLS/wildcard production configuration;
- real camera/IMU/model offline session and 60-minute soak pass;
- backup/restore/update/rollback/power-loss drills pass;
- cloud idempotency/authorization/retention/deletion pass in staging;
- documentation, model card, known limitations, privacy, support, and owner approval
  are current.

Production changes and smoke tests require explicit owner approval.
