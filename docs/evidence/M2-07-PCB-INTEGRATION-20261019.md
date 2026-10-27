# M2-07 assembled wearable PCB integration

Status: IN PROGRESS, 2026-10-19. New-PCB startup and short real BLE stream PASS;
Pi dashboard/graph data and camera playback restored. Owner cue replay and the
mounted person/rep/model checks remain separate pending observations.

## Starting point and preservation

- Base Git commit: `1896ecd`; the pre-existing modified/untracked work is retained.
- R9 source/checkpoint SHA256:
  `5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b`.
- The frozen checkpoint under `firmware/esp32_c3_research/checkpoints/r9/pass/`
  is unchanged and describes the old wiring.
- The previously tested PCB actuator binary remains at
  `.arduino-temporary/Actuator_Power_Test.auto.bin`, SHA256
  `4524064988b974514950327478b8eb67b823251dabbc0552143456c89c5f3efc`.
- The Pi parser before deployment is saved at
  `~/pcb1-before-20261019.vi9L9t/r9_protocol.py`, original SHA256
  `b8dfff42043fa378e60e88668d2a25c68e675f99bdd12b81414adf70d64eae72`.

## Software changes

The main Arduino application now identifies as `0.9.1-pcb1`, uses IMU
SDA18/SCL19, hardware PWM external RGB red1/green0/blue3, and a bounded 500 ms
GPIO10 HIGH/LOW active-buzzer command. Sensor settings are read back at startup;
±2 g, ±250 °/s, 50 Hz and the 20-byte protocol remain unchanged. The stale
synthetic R4 startup message was corrected to describe real raw MPU6500 data.

The host parser and portable validator explicitly allow the old R9 and PCB1
identities and retain strict rejection of unknown versions/changed profiles.
The canonical host reports the actual accepted version. The isolated Pi parser
is deployed; a Pi import check returned `0.9.0-r9` and `0.9.1-pcb1` for their
respective exact values. No BlueZ configuration, bonds, network configuration,
device identity, model artifact, or existing database was changed.

## Verification so far

- The new identity regression first failed because PCB1 was rejected, confirming
  the compatibility issue before changing the parser.
- `pytest tests/imu/test_r9_protocol.py tests/imu/test_r9_agent.py
  tests/imu/test_r9_runtime.py -q -x`: **17 passed**.
- The portable validator passed Python compilation; `git diff --check` passed.
- Live Pi inventory: SSH reachable; Bluetooth powered, discovery off;
  `throttled=0x0`, 45.2 C; project UI/camera/BLE processes stopped after boot.
- Windows enumerated COM7. The PCB1 application was then flashed at `0x10000`
  using esptool 5.0.2; 664,224 bytes written and the data hash verified. NVS,
  bootloader and partition table were retained. Flash summary:
  [flash-summary.log](m2-07-pcb1-20261019/flash-summary.log).
- Firmware compile: **PASS**, Arduino-ESP32 3.3.10, Arduino CLI 1.5.1,
  FQBN `esp32:esp32:esp32c3`. Program storage 664,069/1,310,720 bytes; globals
  19,596/327,680 bytes. The cached toolchain/core headers were copied to temporary
  Linux storage to reduce Windows-mount lookup time; versions were unchanged.
  An initial collision with the board's `RGB_BRIGHTNESS` macro was corrected by
  renaming the local constant. The final compile reported no code warnings; the
  CLI's deprecated build-cache flag warning is tooling only.
- Application binary: `.arduino-temporary/esp32_c3_research.pcb1.bin`,
  664,224 bytes, SHA256
  `e6d1842ab5cb97612d8c2a3fcf16d37f292d1b5b3c1de594657173646d4011b7`.
  The generated partition CSV confirms app0 offset `0x10000`, size `0x140000`.
- Main source SHA256:
  `0f51c15f68e4b14be3dd1dedb9fd654b3fb61bd37559846b2a708565186873f9`.
  Board header SHA256:
  `721251dd3de0a4ddddc8e1b9262be22ef66f873372ed641a961d4b25810dd8c4`.

## Uploaded firmware startup — PASS

The owner confirmed USB-only power with the converter disconnected and JP1 cap
off. One normal reset/serial boot capture then reported:

- Firmware `0.9.1-pcb1`, external RGB R1/G0/B3, `PWM_ready=1`.
- MPU6500 at 0x68 on SDA18/SCL19, exact identity 0x70.
- Verified register readbacks: power 0x01, axes enabled 0x00, DLPF 0x03,
  sample divider 0x13, gyro and accel ranges 0x00 (±250 °/s and ±2 g).
- Real MPU6500 acquisition configured at 50 Hz; after five seconds the firmware
  reported 250 acquired samples, zero retries/errors/bus failures.
- BLE advertising returned with the expected name, address and UUIDs. No reset
  loop appeared in the seven-second serial capture.

Full log: [esp-boot.log](m2-07-pcb1-20261019/esp-boot.log). These are firmware-side
startup observations; the Pi-delivered measurements are below. The previous
automatic actuator-only image is no longer flashed.

## External-power BLE/IMU check — PASS

After the owner confirmed the USB-to-external-power handoff, one portable Pi
validator run connected to the exact PCB1 device and exercised the existing
stream/control interface. Measured results:

| Item | Observed result |
|---|---|
| Measured duration | 30.000815 s |
| Real notifications | 1,499 |
| Average rate | 49.965309 Hz |
| Payload | Valid 20-byte MPU6500 packets |
| Sequence gaps / invalid packets | 0 / 0 |
| Sensor interval | 15,011–24,988 us |
| I2C errors / unexpected disconnects | 0 / 0 |
| Acceleration magnitude | 0.9895–1.0104 g |

The board was effectively stationary; this was not an owner-cued tilt/rotation
and final-settle validation. The bounded buzzer command and deferred identify
command completed during streaming without interrupting delivery. The colour
test was correctly rejected while streaming and accepted after stream stop.
The final idle state was notification-silent and the client disconnected
cleanly. Full output:
[pi-ble-actuator-validation.log](m2-07-pcb1-20261019/pi-ble-actuator-validation.log).

**Physical cue limitation:** software accepted/completed the commands, but the
owner missed this run and requested replay later. Sound/colour observation for
PCB1 is not marked passed from these command acknowledgements. The earlier
actuator-only external-power observation remains historical evidence only.

## Existing Pi dashboard/camera restoration

The normal canonical BLE agent then connected successfully after the validator
disconnected. This is the scoped normal reconnect, not a new recovery matrix.
The existing research status/UI was restarted with a new isolated summary-only
SQLite database and socket paths under `~/pcb1-before-20261019.vi9L9t/live/`;
the previous session database and stale sockets were not overwritten.

The graph endpoint returned its bounded 100-sample window with advancing
sequences and real acceleration/gyro vectors. `wearable=degraded` is expected
because the existing R9 adapter explicitly sets uncalibrated samples to
`Quality.IMU_DEGRADED`; it does not mean a disconnected BLE link. No calibration
or quality flag was fabricated to make the indicator green.

The first camera attempt used the canonical pose-enabled on-demand branch.
MediaMTX stopped it after 30 seconds while MediaPipe was still importing its
optional TensorFlow documentation dependency. Capture had not begun. That
failure is retained in
[browser-camera-initial.json](m2-07-pcb1-20261019/browser-camera-initial.json).
The October 14 log confirmed that the last working camera path was the existing
camera-only publisher. Restoring that launcher environment, without changing
source, packages or relay configuration, restored live H.264/WebRTC video.

One short real Chromium playback observation decoded 1280×720 video and 88
frames over three seconds, advanced media time and stopped cleanly. The browser
reported dropped frames; this is a functional playback observation, not a
latency/frame-loss acceptance result. No images/video were saved. The existing
portrait viewport and mirrored display are unchanged. The BLE agent remained
connected throughout. Camera-only mode does not emit pose events, so live pose,
rep and V5 model validation are **not** established by this playback result.
Numeric evidence:
[browser-camera-restored.json](m2-07-pcb1-20261019/browser-camera-restored.json),
[pi-integration-summary.json](m2-07-pcb1-20261019/pi-integration-summary.json).
The latter window spans 1,979.97 ms across 100 consecutive samples; its sequence
advanced to 11,977 after the earlier window ended at 993. Pi throttling remained
`0x0`. The displayed camera pose status remains unavailable in camera-only mode;
the browser's decoded-video state is reported independently.

The dashboard is available through the restored private SSH tunnel at
`http://127.0.0.1:4174/ui-preview/`; use **Connect camera** to start the on-demand
camera. All Pi UI/RTSP/WHEP/ICE listeners remain loopback-only. These research
processes are not installed as boot services and need restarting after reboot.

## Pose startup follow-up, 2026-10-20

The initial timeout described above is now resolved. A separately pinned pose
environment keeps full Python TensorFlow out of MediaPipe's optional docgen
import, while the existing system-Python helper retains camera ownership.
Initialization took 4.999 s; on-demand video began within the existing deadline.
One combined real run delivered 94 pose events with no processing failures and
a gap-free 100-sample IMU window. Every frame lacked a detected person, so this
is a startup/data-flow pass, not a full-body pose or model pass. No ESP firmware
or V5 artifact changed. Full evidence:
[pose-startup-fix.md](m2-07-pcb1-20261019/pose-startup-fix.md).

## New recovery checkpoint

`firmware/esp32_c3_research/checkpoints/pcb1/stream-pass/` retains the exact
PCB1 source, board header, host parser, portable validator, flashable application,
sdkconfig, partition CSV and SHA256 manifest. It is a **stream-pass checkpoint**,
not a claim that the entire mounted system has passed. The original R9
checkpoint remains untouched.

## Remaining work

Replay the brief physical cues when the owner is ready. Complete the cued
tilt/rotation/settle observation and mounted person/pose/rep checks last. Retain the
existing V5 feature-contract/calibration gates rather than treating raw IMU or
camera playback as validated model input. No long soak is scheduled.

Real hardware used so far: Pi/Windows inventory, Pi Python import, ESP32-C3
application flash, serial MPU6500/PWM/BLE startup, externally powered BLE/IMU
notifications, and Pi camera/WebRTC playback with the live BLE receiver.
The 17 automated checks are host checks, including existing fakes; they are not
sensor/actuator evidence. Packet rate/intervals and short browser playback were
measured; no inference benchmark, full endurance test or live model scoring was
performed. No security/data migration was applied to existing state. All
workspace changes remain uncommitted and unpushed.

The focused 17-test set was confirmed again after checkpoint creation (17 passed
in 5.23 s); no full suite or model benchmark was run. The implementation skill
kept the version-acceptance regression and checks scoped to the affected IMU
adapter rather than expanding into unrelated validation.
