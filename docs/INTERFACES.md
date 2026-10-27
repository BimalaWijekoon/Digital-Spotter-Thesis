# Digital Spotter interface contracts

**Status:** Version 1 design baseline; fields marked provisional require the named
decision/test before firmware or model freeze
**Last reviewed:** 2026-09-28

This document defines boundaries between firmware, Pi services, model, local
clients, persistence, and cloud. Implementations may change internally without
changing these contracts. Breaking changes require a new version and migration.

## 1. Contract rules

- Every wire/event/model/database payload has an explicit schema version.
- Unknown major versions are rejected. Unknown optional fields in the same major
  version may be ignored.
- Units and clock domains are part of field names/types or schema documentation.
- IDs are stable and globally unique where data can reach the cloud.
- Production parsers reject wrong length, wrong range, non-finite numbers, invalid
  enum values, and oversized input.
- Measurement timestamp and arrival timestamp are distinct.
- Missing/stale data is a quality state, not a zero value.
- Commands are idempotent by command ID where possible.

## 2. Common internal event envelope

Internal MessagePack events use this logical envelope:

```text
schema_version: u16             # major in high byte, minor in low byte
event_type: enum/string
event_id: UUIDv7
source: enum                    # imu, vision, core, api, sync
device_id: string|null
session_id: UUID|null
captured_monotonic_ns: u64|null # measurement time in Pi clock domain
created_monotonic_ns: u64       # producer event creation time
created_utc_ms: i64|null        # display/cloud only
quality: enum
trace_id: UUID|null
payload: map
```

Maximum internal serialized event size is 64 KiB. Camera frames never travel in
this event envelope. Raw video uses the camera/encoder path; replay files use an
explicit fixture format.

### 2.1 Local event framing and vision health

The active research bridge and additive M3-03 vision publisher frame an event as
one four-byte unsigned big-endian payload length followed by one MessagePack
envelope over an `AF_UNIX` stream. A producer or consumer rejects zero-length,
truncated, mismatched, or greater-than-64-KiB payloads. The target socket remains
under `/run/digital-spotter/`; production ownership may allow the dedicated group
but must grant no permissions to other users. A configured Linux peer-UID allow
list is checked after connection.

The vision publisher has a fixed queue (default four, accepted range one to 16).
When full, it discards the oldest queued event so camera processing cannot wait
for stale transport work. A failed send is accounted as a transport drop; the
publisher closes the failed connection and uses bounded backoff before later
events reconnect. It does not replay an uncertain failed frame.

Vision health uses the existing `HealthState` payload with
`component="vision"`, state `starting|ready|degraded|stopping`, bounded reason
codes and counters, `since_monotonic_ns`, `last_success_monotonic_ns`, versions,
and `is_simulated`. State transitions are immediate and unchanged state is
published periodically (one second by default). Watchdog evaluation uses the Pi
monotonic timestamp, rejects backward heartbeats, and treats silence beyond its
configured timeout as expired. Replay health is always marked simulated. Step 5
component-tested this interface; Step 6 wires the producer into an explicitly
selected standalone vision-agent runtime. No Pi product service has been installed.

The research core now has an additive `UnixVisionEventServer` for that same
length-prefixed MessagePack socket. It accepts only typed real `PoseSample`
events from `Source.VISION`, checks the active edge-device identity when present,
and keeps a bounded in-memory latest-pose ring (default four). Simulated,
wrong-device, malformed, and backward-capture-time poses are rejected. Vision
`HealthState` frames are counted separately and do not enter the pose ring.
The existing R12 IMU ring and aggregate SQLite summary remain independent;
no raw pose or scored analysis is persisted by this join. One temporary Pi
session proved both existing producers reach the same core session. A later
on-demand fusion function uses their measurement timestamps, but there is no
installed core service or live scored pipeline yet. See
`docs/evidence/JOINT-CAPTURE-20260928.md`.

The M3-03 migration integration switch is the typed non-secret setting
`vision_pipeline=legacy|canonical`, exposed as `DS_VISION_PIPELINE`. It defaults to
`legacy`; selecting `canonical` is required before the standalone vision agent can
open camera/pose resources. The agent additionally requires `vision_adapter=real`
and refuses simulated/replay selection. Production configuration rejects the
legacy pipeline and requires an explicit allowed core peer UID at agent launch.
This switch does not cause both camera owners to run together.

### 2.2 Encoded-video relay contract

When explicitly selected, the canonical Picamera2 owner publishes its already
hardware-encoded H.264 main stream to the configured `video.publish_url`. The URL
must be RTSP on `127.0.0.1` or `localhost`, include an explicit port and non-empty
path, and contain no credentials, query, or fragment. The canonical development
configuration uses:

```text
rtsp://127.0.0.1:8554/picamera2
```

`deploy/mediamtx.yml` binds that RTSP input to loopback and permits only a publisher
for path `picamera2`. MediaMTX relays the encoded stream to WHEP; it never opens the
camera and video frames never enter the internal MessagePack event channel. The
browser-facing stream/grant API remains a later authenticated M6 contract.

### 2.3 Browser video and pose synchronization contract

The M6-D01 Demo tab is a browser-only animation slice, not another camera or
sensor owner. Existing UI clients dispatch transient `ds-workout-status` and
`ds-imu-window` events to mirror real status/current vectors into Demo. No new
HTTP/firmware command or server schema is introduced. `ds-preview-page-change`
selects the page and pauses animation on exit; `#demo` opens the same dashboard
directly. Generated body joint coordinates are drawing inputs only, not a
MediaPipe detection, model feature vector or synchronized sensor measurement.

M6-D02, explicitly enabled with `run_workout.py --enable-demo`, adds private
`GET /api/research/demo` for a four-case synthetic replay catalog and
`POST /api/research/demo/predict` with exactly
`{exercise: squat|deadlift, form: correct|incorrect, rep_id: 1..3}`. Mutation
requires an exact configured loopback Origin, JSON, `X-DS-Demo: 1` and the existing
4096-byte body limit. Browser features, load overrides and predicted classes are
not accepted. Execution is on the core loop, only when the live session and
person-pose test are idle. Disabled means unavailable, never fallback inference.

The response contains raw/calibrated probabilities, threshold, actual class,
model version, fixture index/source label, recorded load, rep ID and compute ms.
It always declares `source=synthetic_training_replay`, `reference_only=true`,
`live=false`, `animation_drives_features=false`, `actuators_enabled=false`.
Mismatch with the source label is reported, not repaired. One browser request
may be in flight; reset/scenario changes invalidate late responses. Three
animation repetitions reuse the selected fixed fixture, not three new measured
repetitions. Right-hand IMU plots remain actual wearable telemetry, not inputs
to this inference. No dense replay stream or MediaPipe detection is implied.

M6-D04 owner-authorized curation replaces only bad-squat fixture 1 with fixture 6
(original 35 kg context), selected after confirming the model recognises it.
Catalog includes `selection_policy=curated_demonstration_not_accuracy_evaluation`
and `known_false_negative_fixture_index=1`. The form selector still cannot set a
class. Other cases and the prediction schema/policy remain unchanged. Captured
squat rendering coordinates are separate from these synthetic replay features.

M6-D05 adds `imu_replay` to each fixed catalog case (also included in its
prediction metadata): `version=demo_phase_imu_v1`,
`source=synthetic_training_replay`, `representation=phase_medians`,
`measured_timestamps=false`, units `{acceleration_m_s2: "m/s^2",
angular_velocity_rad_s: "rad/s"}`, and exactly three `phases` in order 1,2,3.
Each phase contains the phase number and two finite XYZ arrays, copied directly
from the raw fixture's IMU feature fields before model preprocessing. There are
no fabricated timestamps, sequence counters or interpolated high-rate samples.
The browser rejects incompatible units/order. Chart points are revealed in
equal playback slots for presentation only, not measured sensor synchronization.
The live chart selector continues to consume the independent `ds-imu-window`
event and never replaces replay model inputs.

M6-D06 changes only the browser renderer. The four user-selected scenarios map
to distinct complete GLB scenes and their named shared human/barbell clips.
Authored 5.3-second timelines map uniformly to the existing six-second replay
cycle; that is presentation timing, not sensor synchronization. Correct/incorrect
selection and model requests remain unchanged. Specific fault names label
predefined examples, not diagnoses inferred from a binary model result. No new
HTTP/BLE contract, arbitrary model inputs or physically simulated sensor events.

M6-D10 adds a browser-only visual overlay above each authored demonstration GLB.
The overlay uses 33 MediaPipe-compatible indices and the same cyan drawing style
as the live pose guide, but its coordinates are projections of named animation
bones. It is labelled `Simulated pose guide`, is not emitted on the pose event
interface, and must not be consumed by fusion, inference or readiness logic.

M6-D11 adds an owner-approved private transport in front of the unchanged
loopback HTTP application listeners. Tailscale Serve maps tailnet-only HTTPS 443
to core/UI `127.0.0.1:8766` and HTTPS 8443 to WHEP `127.0.0.1:8889`. MediaMTX
binds ICE-TCP 8189 directly and only to the configured Tailscale IPv4 so its SDP
contains a reachable candidate. The browser accepts only loopback HTTP or an
HTTPS hostname ending in `.ts.net`; it derives the WHEP hostname from that page
origin. The server still requires the exact configured Origin and custom mutation
header. No LAN listener, Funnel route, public URL or application login was added.

The research-appliance `workout_v1` status adds one bounded `network` object:

```json
{"state":"connected|disconnected|unavailable","interface":"wlan0","has_local_address":true}
```

`has_local_address` reports only presence, never the address or SSID. The Pi reads
the local Linux interface; it does not ping the internet. The browser rejects a
missing or unknown state instead of inventing connectivity. The Pi GPIO renderer
uses dim blue for connected and a slow amber pulse otherwise only while a demo is
inactive. Demo start/result/complete cues take priority. Network state is never
sent to the BLE wearable and never drives either buzzer.

When `POST /api/workout/command` successfully handles `action=stop`, the
`workout_v1` response includes `completed_set` with
`schema_version=1`, `kind=digital_spotter_research_set`, real session ID and UTC
times, exercise/load, elapsed time, rep count, per-set camera frame counts,
current wearable state, model identity, analysis availability and warnings. It
sets `hardware_simulated=false` and never fabricates probabilities. It contains
no raw video, pose landmarks or raw IMU samples. The core retains this bounded
summary in status until the next set or process restart; the browser downloads
it as `digital-spotter-set-<session_id>.json`.

The temporary loopback research UI also has a separate person-pose diagnostic:
`POST /api/research/person-pose-test` starts one 20-second countdown followed by
30 seconds of real Picamera2/MediaPipe processing; `GET` on the same path returns
`phase=idle|countdown|running|complete|failed`, remaining seconds, and a final
summary. `GET /api/research/person-pose-test/latest` returns the last saved
summary. The POST requires the exact configured browser origin and
`X-DS-Person-Test: 1`; parallel starts return 409. This research endpoint does
not create a workout session, produce V5 scores, or retain frames/landmarks.

M6-R02 adds a separate local-only diagnostic `GET /api/research/pose-latest`
with `version=research_pose_latest_v1`, `frame_aligned=false`,
`state=unavailable|stale|not_found|detected`, `age_ms`, and `pose=null` or one
33-landmark pose. A pose contains frame sequence, capture timestamp in integer
Pi-monotonic **microseconds** (JavaScript-safe), source dimensions, unchanged
quality and x/y/z/visibility for every landmark. At request time the server
rechecks capture age; negative or >500 ms age suppresses landmarks. The client
also budgets request duration and clears expired poses, even during a stalled
request. No history, raw frames, identities or scores are returned/retained.
Polls are bounded and non-overlapping, only while the camera is visible.

For the research rep counter, knee motion is a separate diagnostic signal from
V5 feature eligibility. Rep segmentation may use either complete
hip-knee-ankle side when each of those three landmarks has visibility at least
0.50. This supports a side view whose far leg is occluded. A completed rep built
from degraded/one-side tracking is reported with `quality=unavailable` and empty
model-feature phases; it cannot enter V5 preprocessing or produce analysis
feedback. The bilateral quality-approved feature path remains unchanged.

The canonical research pose adapter uses MediaPipe video detection and tracking
thresholds of 0.50. `pose_confidence` is the higher of the minimum landmark
visibility across the left and right shoulder-hip-knee-ankle chains. Face
visibility and the occluded far side therefore do not control tracking quality.
This confidence is only a tracking/readiness signal. V5 phase feature extraction
has a separate fail-closed gate requiring both shoulders, hips, knees, ankles and
feet at visibility 0.70 or higher.

This is an explicitly labelled latest-pose visual guide, NOT the synchronized
overlay below. Visibility 0.15 is a drawing-only choice from FYP, not a change
to the quality gate, fusion eligibility or model feature contract. The normal
matched-pose renderer still rejects degraded or unmatched results. Test result
display distinguishes `frames_received - poses_not_found` detections from
`good_pose_frames`; zero quality-approved poses does not mean zero detections.
M6-R02 is locally verified but not yet activated on the Pi.

M3-04 defines a strict JSON-safe projection of a canonical vision `PoseSample`.
Internal timestamps remain integer nanoseconds. The browser projection uses
integer microseconds, bounded to JavaScript's exact integer range, and contains:

```text
schema_version: 1
message_type: pose_sample
event_id: UUIDv7
frame_sequence: integer
captured_monotonic_us: integer        # Pi monotonic clock
image_width/image_height: integer
landmark_schema_version: integer
landmarks: [{x, y, z, visibility}]
angles: {name: degrees}
pose_confidence: float
quality: enum
processing_latency_us: integer
frames_dropped_since_previous: integer
is_simulated: boolean
```

Clock synchronization uses a correlated four-timestamp exchange:

```text
browser -> core:
  schema_version: 1
  message_type: clock_sync_request
  request_id: bounded opaque string
  client_sent_ms: browser performance-clock milliseconds

core -> browser:
  schema_version: 1
  message_type: clock_sync_response
  request_id: exact request echo
  client_sent_ms: exact timestamp echo
  server_received_monotonic_us: Pi monotonic microseconds
  server_sent_monotonic_us: Pi monotonic microseconds
```

The browser retains at most eight recent clock exchanges and selects the
lowest-round-trip estimate. Pose lookup retains at most 120 samples and accepts a
nearest sample only when its absolute capture-time difference is at most 80 ms.
Decoded video is matched only when `requestVideoFrameCallback` metadata supplies a
finite `captureTime`; network arrival time and display time are not substitutes.
Missing capture time, an unsynchronized clock, missing/stale pose, any non-`good`
quality, or simulated data clears the overlay and remains explicit.

These are payload and rendering contracts only. The authenticated WSS endpoint,
short-lived stream grant, origin policy, and pinned MediaMTX/browser deployment
version are not implemented by this slice. A later isolated research preview pins
the official browser reader to v1.12.3 and proves playback against server v1.9.1;
this is a tested research pairing, not an authenticated production deployment.
The pinned asset and license hashes are recorded under
`web/static/vendor/mediamtx-v1.12.3/README.md` in the canonical package.

The isolated Pi-hosted `ui-preview/` research shell now reads its private WHEP
endpoint from `camera-config.json` and starts playback from a Workout-panel
button; it does not accept a user-entered video URL. A separate loopback-only
MediaMTX research config launches the existing Picamera2 owner on demand while
a viewer reads path `picamera2` and stops it after the last viewer leaves. This
is a development-only transport, not the authenticated M6 stream-grant API.

The Pi-hosted page may additionally serve a static `test-input-result.json`
generated by one explicit local run of the frozen V5 fitted-median input. Its
`v5_test_input_v1` payload requires `source=frozen_fitted_medians`, `live=false`,
`reference_only=true`, the exact V5 model version, raw/calibrated probabilities,
threshold and matching binary class. The browser validates those fields and
renders them only in Devices → Analysis under **Test input**. This file is not a
session-status API, scored rep, feedback event, or durable user analysis.

The later M3-04 **research-only** bridge serves `GET /api/pose-events?after=N`
as `{cursor, events}` (bounded to the latest 120 projected samples) and
`POST /api/clock-sync` with the request/response above. It binds only to Pi
loopback, requires the research page's same origin for clock POST, and is never
an authenticated product API. The viewer fails closed on transport errors,
stale clock, missing video `captureTime`, or degraded pose. Live browser
`captureTime` availability is not yet verified.

### 2.2 Read-only research session status

The opt-in `scripts/run_research_session.py` serves
`GET /api/research/session-status` on **127.0.0.1 only**, alongside the existing
`/ui-preview/` assets. It accepts no browser mutation request and is not the
M6 authenticated product API. No CORS permission is added. The response is
`research_status_v1`:

```text
version: research_status_v1
session: {state, rep_count}                 # process-local detected count
wearable: {state}                           # receiving|degraded|stale|unavailable
camera: {state}                             # receiving|degraded|stale|unavailable
analysis: {state: unavailable,
           reason: v5_live_feature_contract_unverified}
latest_rep: {number, quality}|null          # detected, never model-scored
```

Sensor freshness is display-only and uses recent local receive/process time,
not the capture-time fusion policy. A missing or stale status publication returns
HTTP 503. The server publishes no model probability, threshold, or safety claim;
the UI clears status on invalid/failed responses and does not infer a BLE link
state from an IMU event. This status is neither a durable rep record nor live
V5 scoring evidence. The camera WebRTC preview remains a separate opt-in path.

The same loopback-only research process serves `GET /api/research/imu-window`
(`research_imu_window_v1`). It returns `{version, state, samples}` with at most
100 recent samples from the canonical IMU ring, restricted to the current ESP
boot ID. Each sample has `sequence`, relative Pi-monotonic capture `t_ms`, and
three-axis `acceleration_m_s2` and `angular_velocity_rad_s` vectors. Stale or
unavailable input returns no samples; a missing/stale publication returns 503.
This is display-only motion telemetry, not calibrated/model-ready input.

An optional terminal-only V5 shadow observer may consume the same completed
reps when the runner is started with an explicit model package and load. It
calls the frozen runtime's `predict_reference_only()` after the candidate
feature gate, and reports only execution/unavailable state to the terminal.
No probability, class, threshold, or shadow result enters this HTTP contract,
SQLite analysis/outbox, or wearable feedback. It is not a live-feature parity
claim; IMU units, mounting and pose equivalence remain unverified.

## 3. BLE GATT protocol v1

### 3.1 Roles

- ESP32-C3: BLE peripheral/GATT server.
- Raspberry Pi: BLE central/GATT client.
- Active research firmware stack: Arduino-ESP32 BLE API on ESP32-C3.
- Native ESP-IDF/NimBLE remains a future implementation option after the research
  contract is stable; framework migration is not part of early bring-up.
- Pi stack: BlueZ, initially through Bleak.

The service and characteristic UUIDs must be generated for the product and stored
in one firmware/Pi contract module. Do not use demonstration UART-service UUIDs in
production.

The active R9 contract is implemented by
`firmware/esp32_c3_research/esp32_c3_research.ino` and validated by its matching
Pi client. Earlier diagnostic and intermediate firmware trees were removed after
R9 passed; their measured lineage remains in `docs/evidence/` and Git history.

The active staged research UUID registry is:

| Role | UUID | Current status |
|---|---|---|
| service | `4fafc201-1fb5-459e-8fcc-c5c9c331914b` | retained from R0 to preserve the passing link |
| legacy R1/R2 test | `beb5483e-36e1-4688-b7f5-ea07361b26a8` | retired by R3C |
| `device_info_v1` | `e193acb8-25ef-422c-b3e5-972eae75b8ea` | read-only, expanded with bounded hardware/IMU/rate fields in R8 and retained in R9 |
| `control_v1` research controls | `7f725422-d560-4852-96d8-3407f417b1d8` | read + write with response, bounded R9 commands |
| `imu_stream_v1` research stream | `772af3c3-f1f9-43b0-8230-4dff401446ea` | notify-only, active with real raw MPU6500 values in R9 |
| `status_v1` research status | `7f07eb06-7be4-49a1-b952-1ed033b0dfc7` | read-only bounded ASCII, introduced in R8 |

The frozen R9 firmware returns the exact bounded ASCII device value
`protocol=1;firmware=0.9.0-r9;hardware=esp32-c3;imu=mpu6500;rate_hz=50`.
The assembled-PCB revision returns the same fields with `firmware=0.9.1-pcb1`;
the current feedback revision returns `firmware=0.9.2-demo-feedback`.
The canonical parser accepts only these three exact values
and reports the actual accepted version. Protocol, UUIDs, sensor scale profile,
device identity, and 20-byte packet layout are unchanged.

R9 control accepts at most 48 printable ASCII bytes. `stream:start` and
`stream:stop` return `ok:streaming` and `ok:idle` and are idempotent. `identify`
returns `ok:identify`; while streaming its NeoPixel transition is deferred until
stop to protect the sensor schedule. `buzzer:test` returns `ok:buzzer_test` and
starts a 120 ms tone on archived R9 or a timed 500 ms GPIO10 HIGH pulse on PCB1.
PCB1 drives the external RGB on red1/green0/blue3 through hardware PWM.
`cue:test` returns `ok:cue_test` only in connected idle state
and exercises the bounded state-color sequence; while streaming it returns
`error:busy_streaming`. If cues are compiled out, both actuator-test commands
return `error:actuators_disabled`. Oversized, non-printable, and unknown requests
return `error:too_long`, `error:invalid_text`, and `error:unknown_command`.

R9 status is read-only and no longer than 96 bytes:
`state=<idle|streaming|error>;i2c_errors=N;samples_sent=N;uptime_ms=N`.

R9 preserves the R6 20-byte packet below at 50 Hz and fills the six axis fields
with the latest real MPU6500 raw counts and uses the actual monotonic I2C capture
time. Unavailable, stale, or duplicate samples are skipped rather than silently
replaced. The sequence advances so transport loss remains explicit. R6 values are
uncalibrated and are not yet approved model inputs.

The active R9 recovery contract remains open research BLE. After disconnect, the
ESP waits 100 ms and makes at most three non-blocking advertising-start attempts,
500 ms apart after a rejected attempt. The standalone Pi validator makes at most
three scan/connect attempts with 0, 0.5, and 1.0 second backoff and requests no
pairing.

The passing R11 Pi adapter is implemented by `r9_protocol.py`, `r9_agent.py`,
`r9_transport.py`, and `r9_runtime.py` under `src/digital_spotter/imu/`. It:

- verifies the exact R9 name, public address, service, characteristic set, and
  device-info value before streaming;
- uses `pair=False` and does not modify BlueZ bond state;
- sends `stream:start`, requires `ok:streaming`, discards only data queued before
  that acknowledgement, and then begins a raw-sequence epoch;
- accounts for R9 resetting its raw u16 sequence to zero on every stream start;
- uses a bounded 16-packet drop-oldest callback queue and a one-value latest slot;
- reconnects with capped 2, 4, 8, and 15 second backoff;
- timestamps each on-demand status read at Pi request/response boundaries, treats
  ESP `uptime_ms` as a one-millisecond-resolution clock observation, and maps the
  packet's wrapping `sensor_time_us` into Pi monotonic capture time;
- counts but withholds samples from the core event publisher while clock state is
  not `SYNCHRONIZED`;
- emits uncalibrated samples with `IMU_DEGRADED` quality even when their independent
  clock state is `SYNCHRONIZED`; calibration/model eligibility remains open.

Health reports device/stream state, measured rate, latest age, sequence gaps,
duplicates, invalid packets, callback drops, I2C errors, connection failures,
reconnects, publisher failures, ESP status counters, clock state/drift/error/fit,
exchange counts, exchange age, and pre-sync clock-gate drops. Recovery-transition
loss or stale clock state is not silently converted into valid samples or
steady-state success.

### 3.2 Target secure-product characteristics

The following MessagePack/authenticated characteristic contract is a deferred
product target, not active R9/R11 behavior under ADR-019.

| Name | Property | Maximum logical payload | Purpose |
|---|---|---:|---|
| `control_v1` | write with response + indicate | 512 bytes | authentication, session, calibrate, time-sync, config and logical responses |
| `imu_stream_v1` | notify | negotiated ATT payload | one or more fixed IMU samples |
| `status_v1` | notify/indicate | 512 bytes | state, battery, counters, calibration, errors |
| `device_info_v1` | read | 512 bytes | identity, firmware, hardware, protocol capabilities |

Critical transitions such as session start/stop and calibration completion require
an ATT write response plus one authenticated logical response indication on the
same characteristic. The client subscribes before its first write and permits only
one outstanding command. IMU streaming uses notifications to avoid head-of-line
blocking. The v1 preferred MTU is 517 bytes; all currently defined commands and
responses fit one negotiated ATT payload even though the logical parser remains
bounded at 512 bytes.

### 3.3 Baseline IMU sample

One sample is exactly 20 bytes and uses little-endian fields:

| Offset | Type | Field | Meaning |
|---:|---|---|---|
| 0 | `u8` | `protocol_version` | `1` |
| 1 | `u8` bitset | `flags` | calibrated, saturation, low-battery, sensor-error bits |
| 2 | `u16` | `sequence` | increments per sample; wraps modulo 65536 |
| 4 | `u32` | `sensor_time_us` | ESP monotonic sample time; wraps modulo 2^32 |
| 8 | `i16` | `acc_x_raw` | calibrated/raw count under active scale profile |
| 10 | `i16` | `acc_y_raw` | same |
| 12 | `i16` | `acc_z_raw` | same |
| 14 | `i16` | `gyro_x_raw` | calibrated/raw count under active scale profile |
| 16 | `i16` | `gyro_y_raw` | same |
| 18 | `i16` | `gyro_z_raw` | same |

The active sensor range and conversion factors are read from `device_info_v1` and
identified by `scale_profile_version`. The accepted sensor is MPU6500 with exact
`WHO_AM_I=0x70`; MPU9250 identity `0x71` is not accepted by this contract. The current
prototype firmware assumes +/-2 g and +/-250 degrees/s at 50 Hz, but the production
range, filtering, unit conversion, body-frame orientation, and calibration profile
remain provisional until lower-back field testing. They must not change during a
session.

BLE link-layer integrity protects the fixed sample. Session establishment and
control commands are additionally authenticated. If gym threat testing requires
per-batch application authentication, v2 may add a batch header/tag after MTU
negotiation; v1 correctness must not depend on a larger MTU.

### 3.4 Status payload

Status uses a strictly bounded MessagePack map:

```text
protocol_version: 1
device_id: string
boot_id: random u64
state: booting|unprovisioned|pairing|idle|calibrating|streaming|error|updating
firmware_version: semantic version
hardware_revision: string
imu_model: string
scale_profile_version: u16
calibration_version: u32
battery_mv: u16
battery_percent: u8|null
sample_rate_hz: u16
samples_sent: u64
sensor_errors: u32
sensor_retries: u32
actuator_commands: u32
actuator_rejections: u32
actuator_rate_limits: u32
actuator_driver_errors: u32
last_error_code: enum|null
heap_free_bytes: u32
heap_minimum_free_bytes: u32
uptime_ms: u32
```

`boot_id` distinguishes a restarted device from clock-counter wrap. `pairing`
means the sustained physical action opened the bounded controller-binding window;
it does not mean application authentication has been bypassed.

### 3.5 Authenticated control command

Control maps are canonical MessagePack and are bounded to 512 bytes:

```text
protocol_version: 1
command_id: random u64
command: authenticate|start|stop|calibrate|time_sync|set_rate|identify|feedback|sleep|status
session_nonce: 16 bytes
issued_sensor_window: u32|null
arguments: bounded map
auth_tag: HMAC-SHA-256 truncated to 16 bytes
```

The top-level keys appear in exactly the order shown. `arguments` contains at most
eight ASCII string keys in lexicographic order and only bounded unsigned integer,
string, binary, or nil values. Parsers reject alternate integer widths, reordered
maps, extra fields, trailing bytes, and values outside their command schema.

`identify` has no arguments. `feedback` has exactly one argument, `cue`, whose v1
value is `good` or `bad`. The Pi client must reject feedback locally unless the
source is real, the analysis quality gate passed, and the wearable clock is
synchronized. Firmware independently authenticates the command and applies its
bounded scheduler/rate limit. `rate_limited` is an authenticated logical response;
it is not a transport failure.

The `auth_tag` covers the domain `DS-BLE-CMD-V1\\0` followed by canonical
MessagePack of the first six fields, excluding `auth_tag`. `authenticate` is signed
with the unique 32-byte provisioned device key, has a nil sensor window, and carries
the current `boot_id`. Its response proves possession of the same device key and
returns `boot_id` and `sensor_time_us`. Both sides then derive a 32-byte session key
with HKDF-SHA-256 using the 16-byte session nonce as salt and
`DS-BLE-SESSION-V1\\0 || device_id || boot_id_be64` as info. Other commands use that
session key and accept only the current or immediately previous five-second sensor
counter window.

Responses use canonical field order `protocol_version`, `command_id`, `result`,
`session_nonce`, `arguments`, `auth_tag`. Their tag covers
`DS-BLE-RSP-V1\\0` plus the first five fields. They echo `command_id` and return
`accepted`, `already_applied`, or a stable error code. The ESP retains a bounded
per-boot command-ID cache and returns `replayed` without applying a captured
command. Authentication/session state and the replay cache are cleared on link
loss. Physical creation/transfer/destruction of the unique device key remains the
separate provisioning flow; there is no fleet key or unauthenticated `pair`
command.

The v1 physical binding flow opens for 120 seconds after a 2-second BOOT-button
hold. The local acknowledgement is a 900 ms cyan/blue pulse with two short 2.5 kHz
buzzer pulses; absence of that acknowledgement means the operator must release the
button and must not start pairing. A previously unbound device stores the encrypted
peer identity only after that peer also proves the unique application key. Once
bound, an exact peer-identity match is required and reopening the physical window
does not authorize a second controller. The confidential `DSIMU1:` claim and
destructive reset/recovery procedure are specified in
`WEARABLE_PROVISIONING.md`.

### 3.6 Time synchronization

The active R9 research implementation has no dedicated time-sync command. It uses
the existing on-demand status read as a bounded exchange: Pi records `t1_pi_ns`,
ESP generates `uptime_ms` in the read callback, and Pi records `t4_pi_ns`. The
millisecond value is converted into the same wrapping microsecond domain as R9
sample capture, with one millisecond added to the uncertainty budget. Multiple
low-RTT reads estimate offset/drift; high RTT, stale exchange, wrap, reboot, future
projection, and nonmonotonic correction remain explicit.

The target secure protocol may later use the higher-resolution authenticated
exchange below without changing the internal `IMUSample` contract.

The Pi sends `t1_pi_ns` and a nonce. ESP records receive/send sensor counters and
returns them with the nonce; Pi records `t4_pi_ns`. The IMU agent estimates RTT,
offset, and drift across multiple exchanges, rejects high-RTT outliers, handles
wrap/boot change, and publishes:

```text
mapped_pi_monotonic_ns
estimated_error_ns
clock_state: acquiring|synchronized|degraded|reset
```

## 4. Internal domain events

### 4.1 `IMUSample`

```text
device_id
boot_id
sequence
sensor_time_us
captured_monotonic_ns
arrival_monotonic_ns
acceleration_m_s2: [x, y, z]
angular_velocity_rad_s: [x, y, z]
calibration_version
quality
gap_count_since_previous
estimated_clock_error_ns
```

### 4.2 `PoseSample`

```text
camera_id
frame_sequence
captured_monotonic_ns
processed_monotonic_ns
image_width
image_height
landmark_schema_version
landmarks: bounded list of x/y/z/visibility
angles: versioned map
pose_confidence
quality
processing_latency_ns
frames_dropped_since_previous
```

Landmarks are normalized to the documented image coordinate system. Mirroring,
camera orientation, and left/right semantics must be explicit.

For the provisional Picamera2 adapter, `captured_monotonic_ns` is the request's
monotonic `SensorTimestamp` minus `ExposureTime` converted from microseconds to
nanoseconds. It represents the first pixel's exposure start. RTSP decode-arrival
time is not a valid substitute for this field and must remain explicitly
unavailable.

### 4.3 `FusedSample`

```text
pose_event_id
captured_monotonic_ns
interpolated_imu
imu_before_sequence
imu_after_sequence
alignment_error_ns
calibration_version
quality
quality_reasons: list[enum]
```

The current research `FusionEngine` returns a `FusionOutcome` containing this
sample only when the pose has safe, clock-synchronized IMU neighbors in the
same Pi-monotonic domain. Without them, `sample` is absent and a reason such as
`imu_unavailable`, `imu_stale`, `imu_gap_rate_high`, `clock_unsynchronized`, or
`pose_stale` is explicit. A numeric sample can still be `vision_degraded` or
`imu_degraded`; calibration version zero reports `calibration_required`, and
such a sample must not be scored. Research defaults are: pose age at most
250 ms, each IMU neighbor within 30 ms, IMU bracket at most 40 ms, and R13-B
clock-error estimate at most 20 ms. These configurable bounds are provisional
association policy, not measured camera/IMU alignment accuracy. The reported
`alignment_error_ns` is the larger of the two R13-B clock-error estimates; it
does not include camera timestamp uncertainty or motion-interpolation error.
`LocalSessionService.fuse_latest_pose()` exposes this on demand from its bounded
rings. It does not publish, persist, or score a fused event automatically.

### 4.4 `RepEvent`

```text
rep_id
rep_number
exercise_contract_version
event: started|phase|completed|aborted
phase: eccentric|bottom|concentric|lockout|null
captured_monotonic_ns
quality
phase_snapshot_refs
```

The current M4-02 research adapter additionally exposes
`LocalSessionService.poll_completed_reps() -> tuple[CompletedRep, ...]`.
Each completed item holds exactly three ordered `PhaseRecord`s with exercise-
specific labels, capture-time boundaries, median vision values, optional
synchronized IMU medians in source units, and explicit quality. This is an
in-process core result, not a persisted analysis or a claim of V5 feature
equivalence. The generic `RepPhase` enum above is a migration contract and is
not used to mislabel deadlift Setup/Mid-pull as eccentric/bottom. Polling emits
each completed event once; no peak yields no event.

The local `build_v5_candidate_inputs()` bridge accepts a good completed rep,
explicit exercise ID and load, and the verified Stage 8 preprocessor registry.
It returns three ordered phase maps with exactly the 29 frozen temporal fields
and context `[Exercise_ID, Load_kg]`, or raises `V5FeatureUnavailable` for
missing/degraded required data. These are candidate inputs, not authorization
to score or persist a result; source-unit/axis and live-pose equivalence gates
remain open.

### 4.5 `AnalysisEvent`

```text
analysis_id
rep_id
model_package_id
model_version
feature_contract_version
input_hash
label
bad_form_probability
threshold
latency_ns
quality
quality_reasons
is_simulated: false in production persistence
```

### 4.6 Offline synthetic retraining candidate (not a runtime contract)

M5-R02 defines `v5-imu-synthetic-r1` only inside
`training/v5_imu_retraining/`. It preserves existing source vision, labels,
context/IDs and phase order; replaces six IMU channels in m/s²/rad/s; and uses
simulated 50 Hz acquisition followed by medians of pose-associated IMU values.
The virtual X-forward/Y-left/Z-up sensor/body transform and all motion/noise
parameters are explicitly assumed, not measured physical mounting. Old source
timestamps are retained metadata, not new synchronization evidence. See
`training/v5_imu_retraining/docs/IMU_GENERATION_SPEC.md` for exact semantics.
This changes no live event, firmware, inference-readiness or deployed model
contract. A future model package must version these assumptions and validate its
actual mounted feature path before activation.

M5-R04's local `V5CandidateRuntime` consumes the new `MODEL_MANIFEST.json`,
`SHA256SUMS.csv`, JSON preprocessing/calibration/threshold and FP32 TFLite.
It requires the exact existing ordered 29/2/3 contract and explicit candidate
version `digital_spotter_v5_imu_synthetic_r1`. `predict_reference_only()` returns
the common `V5Prediction` with that version and `reference_only=True`;
`predict()` refuses live scoring. It shares the existing frozen numeric
transform and canonical feature builder, never refits or imports training code.
The workout launcher accepts `--model-version` plus `--model-package`; omitting
the version still selects the legacy model, with no candidate fallback. Model
version is propagated to session state/log/context, while score availability
and `live_inputs_verified=False` remain unchanged.

## 5. Model package v1

A model is distributed as an immutable directory:

```text
model-package/
  manifest.json
  model.tflite
  scaler.save
  winsor_bounds.save
  feature_medians.save
  model_card.md
  signature
```

The manifest contains:

- package/model/feature-contract semantic versions;
- SHA-256 for each artifact;
- signature identity and timestamp;
- input/output tensor name, shape, dtype, and quantization;
- exact ordered feature list and units;
- coordinate and sensor scale assumptions;
- missing-data policy;
- preprocessing operations and order;
- label/output meaning and threshold with full precision;
- supported exercises, sensor, mount, camera orientation, and population scope;
- required LiteRT/TFLite operator set and minimum runtime;
- training/evaluation provenance and sealed-test metrics.

The current compatibility input is `(1, 4, 40)`: three phase feature vectors plus
one phase-3-minus-phase-1 delta vector. This is frozen only for migration parity;
any corrected future contract receives a new feature-contract version and model.

## 6. Local HTTP/WebSocket API v1

Exact payload schemas will be generated from typed code in M6. The target surface
is intentionally small:

| Method/path | Purpose | Idempotency/auth |
|---|---|---|
| `GET /api/v1/health` | liveness and component states | paired reader |
| `GET /api/v1/readiness` | detailed pre-session gates | paired reader |
| `POST /api/v1/pair` | physical-mode local client pairing | one-time proof |
| `POST /api/v1/calibrations` | start/confirm guided calibration | owner + command ID |
| `POST /api/v1/sessions` | start session | owner + idempotency key |
| `POST /api/v1/sessions/{id}/stop` | stop session | owner + idempotency key |
| `GET /api/v1/sessions` | local history | authorized reader |
| `GET /api/v1/sessions/{id}` | session/reps | authorized reader |
| `GET /api/v1/stream-config` | authorized WebRTC information | short-lived grant |
| `WS /api/v1/events` | coalesced status/pose/rep/analysis | short-lived token |

The current manual `/predict` endpoint is not a product endpoint. A future
diagnostic replay endpoint, if retained, must call the canonical model service and
be restricted to development/support authorization.

All errors use:

```text
request_id
code: stable enum
message: safe human-readable text
retryable: bool
details: bounded non-secret map|null
```

## 7. SQLite and outbox contract

Internal schema is migration-controlled rather than public, but these invariants
are stable:

- UUIDs are generated before persistence and reused as cloud idempotency keys.
- Completed rep, analysis, and outbox insert are one transaction.
- Outbox payload is a versioned immutable event, not a query-time reconstruction.
- Upload acknowledgment records gateway receipt/version/time.
- Retry scheduling is durable across reboot.
- A migration version and model package ID are stored with every session/analysis.

R12 migration 0003 adds one active-session uniqueness guard and an aggregate
`session_imu_summaries` record keyed by the session UUID. The summary contains the
wearable ID, accepted sample/gap/degraded/reset/boot/ring-eviction/duplicate counts,
first/last sequence and capture times, last boot ID, and checkpoint time. It does
not contain raw accelerometer or gyroscope samples. Active-session checkpoints and
completion use explicit transactions; an existing database must be backed up
before migration.

## 8. Cloud ingestion v1

```text
POST /v1/devices/{device_id}/events:batch
Authorization: short-lived device credential
X-Request-Id: UUID
Content-Type: application/json or application/cbor
```

The bounded batch contains event schema versions, IDs, local timestamps, payload
hashes, and payloads. The gateway verifies device ownership, signature/token,
nonce/replay policy, size, schema, and idempotency before writing. The response
acknowledges each event independently as accepted, already accepted, retryable, or
permanently rejected.

The Pi never writes Firestore/Storage directly with an Admin key.

## 9. Stable quality/error enums

Initial cross-component reasons include:

```text
ok
starting
simulated
camera_unavailable
pose_not_found
pose_low_visibility
pose_stale
imu_unavailable
imu_stale
imu_gap_rate_high
imu_saturated
calibration_required
clock_acquiring
clock_unsynchronized
model_unavailable
model_contract_mismatch
storage_unavailable
storage_pressure
cloud_offline
unauthorized
protocol_mismatch
internal_error
```

Adding a reason in v1 is backward-compatible. Renaming or changing its meaning is
not.
