# Digital Spotter — Latest System Modifications and Thesis Evidence

**Evidence cut-off:** 27 October 2026
**Purpose:** concise thesis handoff for the final Raspberry Pi, camera, wearable,
UI and owner-reported gym evaluation. This document separates software/hardware
evidence from owner observations and unverified claims.

## 1. Final research prototype configuration

- **Edge computer:** Raspberry Pi 4 Model B, 8 GB.
- **Vision sensor:** IMX219 Raspberry Pi Camera v2.
- **Wearable:** ESP32-C3 on the assembled carrier PCB with a lower-back MPU6500.
- **MPU6500 identity:** I2C address `0x68`, `WHO_AM_I=0x70`.
- **Current PCB signal mapping:** SDA GPIO18, SCL GPIO19, external RGB red GPIO1,
  green GPIO0, blue GPIO3, and active buzzer GPIO10.
- **Wearable data contract:** real 20-byte little-endian MPU6500 packets at
  approximately 50 Hz over local BLE.
- **Pi feedback hardware:** RGB red BCM27, green BCM17, blue BCM22 and buzzer
  BCM18.
- **Network role:** Wi-Fi/Tailscale is used for private browser access and
  administration. The wearable remains BLE-only.

The PCB application baseline is `0.9.1-pcb1`; the later demonstration-feedback
revision reports `0.9.2-demo-feedback` while retaining the same BLE UUIDs,
20-byte packet and 50 Hz acquisition contract.

## 2. Verified wearable and PCB changes

The earlier development-board wiring was replaced by the assembled-PCB mapping.
The application was updated for the GPIO18/19 I2C bus, three-channel PWM RGB and
timed active buzzer. Startup reads back the configured MPU6500 profile.

Verified PCB evidence includes:

- exact MPU6500 identity `0x70`;
- accelerometer range ±2 g and gyroscope range ±250 degrees/second;
- 50 Hz sampling configuration;
- 250 samples acquired in five seconds with zero acquisition errors;
- a 30-second BLE run containing 1,499 packets at 49.965 Hz;
- zero sequence gaps, I2C errors and unexpected disconnects in that run;
- owner-observed RGB sequence and audible buzzer operation.

The live IMU values remain **uncalibrated**, so the runtime correctly presents
the wearable as degraded even when data is arriving.

## 3. Raspberry Pi appliance and browser access

The research system now starts automatically through three systemd user
services:

1. core/API/UI;
2. BLE wearable owner;
3. MediaMTX camera relay.

Release `digital-spotter-research-appliance-20261027-r15` is the latest recorded
Pi release. Its 251 manifest entries were verified and the core, IMU and media
services were active. The UI/API and WHEP listener remain on Pi loopback. Private
HTTPS access is provided through Tailscale Serve, with ICE-TCP bound only to the
Pi's Tailscale address. Public Funnel access is disabled.

This is a research deployment convenience, not production authentication.

## 4. Camera, pose and repetition-processing changes

- Camera publication uses hardware H.264/WebRTC rather than a Python MJPEG path.
- The UI uses a portrait-oriented, mirrored camera presentation suitable for
  standing squat/deadlift exercises.
- MediaPipe acquisition/tracking defaults were reduced from 0.70 to 0.50 so
  tracking can start from a visible body chain without requiring the face.
- Repetition segmentation can use either complete hip-knee-ankle side with
  visibility at least 0.50. This improves side-view and partial-occlusion
  tracking.
- Model feature eligibility remains stricter: all required bilateral
  shoulder/hip/knee/ankle/foot landmarks require visibility at least 0.70.
- Missing body parts are not extrapolated or replaced with zeros.
- Rep counting and model-quality eligibility are separate. A rep may be counted
  while scoring remains unavailable if model-quality features are incomplete.

Focused verification for the latest pose revision passed 13 adapter, worker and
rep-phase checks. This is software verification, not a claim of perfect
real-world pose accuracy.

## 5. User-interface and operational changes

The final research dashboard contains:

- Workout and Devices navigation plus an isolated demonstration page;
- live camera with pose overlay;
- live acceleration and gyroscope graphs;
- camera, wearable, IMU, network and model status;
- exercise and load selection;
- Start, Pause, Finish and Stop controls;
- prominent model-result/feedback presentation;
- a `Finish + JSON` action and repeat `Download JSON` action;
- a privacy-bounded set summary without raw video, landmarks or raw IMU samples;
- Pi network indication: dim blue when Wi-Fi has a local address and slow amber
  otherwise, with no network-status buzzer.

The Demo page is isolated from live analysis. Its animated pose guide and replay
inputs are explicitly simulated and cannot be treated as measured participant
data.

## 6. Model status and limitation

The Pi loads `digital_spotter_v5_imu_synthetic_r1`, a V5 BiLSTM/attention
candidate using three phases, 29 temporal features and two context inputs. The
candidate was trained from synthetic IMU assumptions while preserving the V5
vision/label structure. Its synthetic-profile grouped outer-fold result was
85.4807% accuracy and 0.815839 F1; numerical TFLite parity passed.

Those training metrics are **not real-world validation**. The current release
metadata still marks live inputs as unverified. The gym results below are
owner-reported observations without retained raw probabilities or machine logs;
they must not be presented as software-audited model evidence.

## 7. Owner-reported gym evaluation

Five anonymous participants (`P01`–`P05`) each performed squat and deadlift
sets, producing 10 sets and 42 attempted repetitions. Loads ranged from 20 kg to
120 kg.

### Integration observations

- Repetitions detected: **36/42 (85.7%)**.
- Squat detection: **17/19 (89.5%)**.
- Deadlift detection: **19/23 (82.6%)**.
- Mean reported pose detection across sets: **81.7%**.
- Mean reported quality-approved pose frames: **80.8%**.
- Camera continuous without reported error: **10/10 sets**.
- IMU reported continuously at 50 Hz: **10/10 sets**.
- BLE disconnections reported: **0**.
- Three phases were reported for all 36 detected repetitions.
- LED and buzzer feedback were observed during all sets.
- Perceived result response was approximately **500–1000 ms**, but this was not
  instrumented.
- The camera profile was 30 FPS and appeared smooth to the owner; actual
  MediaPipe processing FPS was not measured.
- Exact camera-to-IMU synchronization error was not measured.

### Per-repetition classification summary

Among the 36 detected repetitions:

| Measure | Result |
|---|---:|
| Correct classifications | 31/36 (86.1%) |
| End-to-end correct, counting missed reps as failures | 31/42 (73.8%) |
| Bad-form true positives | 2 |
| Bad-form false negatives | 3 |
| Good-form true negatives | 29 |
| Good-form false positives | 2 |
| Bad-form precision | 50.0% |
| Bad-form recall | 40.0% |
| Bad-form F1 | 44.4% |

The detected-only accuracy is strongly influenced by the predominance of good
repetitions. The low bad-form recall is the more important safety/research
limitation: three of five bad repetitions were classified as good.

## 8. Thesis-safe conclusions

The evidence supports these statements:

- A Raspberry Pi, camera and wireless ESP32-C3/MPU6500 wearable were integrated
  into an edge-based research prototype.
- The assembled wearable produced a stable real 50 Hz BLE stream in the bounded
  hardware test.
- The browser interface, device status, IMU graphs, repetition workflow and
  physical LED/buzzer feedback operated during owner-observed field trials.
- Repetition detection reached 85.7% across the small five-person field sample.
- Classification of detected repetitions reached 86.1%, but bad-form detection
  was weak (40.0% recall) and requires better real-world training data and
  validation.

Do **not** claim:

- clinically validated or production-ready form assessment;
- real-world validation from the synthetic training metrics;
- a measured 30 FPS MediaPipe processing rate;
- verified millisecond camera/IMU synchronization;
- calibrated lower-back IMU orientation;
- production-grade BLE or application authentication;
- statistical generalization from five participants.

## 9. Remaining thesis evidence

Physical system photographs already exist in the source materials. Add one
privacy-safe dashboard screenshot showing a completed result without an
identifiable participant. Engineering stress tests, long soaks, injected packet
gaps and production security validation are outside the present research scope.

## 10. Primary supporting files

- `docs/evidence/Gym_Spotter_Final_Real_World_Testing_Questionnaire.xlsx`
- `docs/evidence/M2-07-PCB-INTEGRATION-20261019.md`
- `docs/evidence/M6-D11-TAILSCALE-PRIVATE-URL-20261026.md`
- `docs/evidence/M6-D12-SET-JSON-EXPORT-20261027.md`
- `docs/evidence/M6-D13-REP-TRACKING-SEPARATION-20261027.md`
- `docs/evidence/M6-D14-PARTIAL-BODY-POSE-ACQUISITION-20261027.md`
- `training/v5_imu_retraining/docs/TRAINING_REPORT.md`

The completed workbook contains the 42 per-repetition owner-reported labels and
predictions. Where no raw measurement exists, the workbook retains `Not
measured`, `Not run`, `Partial`, or an explicit owner-observation label rather
than inventing evidence.
