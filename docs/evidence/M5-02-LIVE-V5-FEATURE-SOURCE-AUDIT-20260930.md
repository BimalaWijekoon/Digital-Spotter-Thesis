# M5-02 live V5 feature-source audit — 2026-09-30

**Result: NOT READY for live V5 scoring.** This was a read-only source and Pi
service inventory, not a person-camera, mounted-wearable, BLE, or model accuracy
test. The existing candidate bridge and V5 model package were not changed.

| Input or boundary | Evidence | Conclusion |
|---|---|---|
| V5 field order and arithmetic | `../FYP/Datasets v2 Model v5/documentation/FEATURE_CONTRACT.md:5-45`; `src/digital_spotter/inference/v5_features.py:27-45,71-124`; `../FYP/outputs/v5/v5_stage1_6_pipeline.py:282-294` | **CODE-CONFIRMED:** the local candidate selects 29 ordered temporal fields and two context fields, with Stage 8 asymmetry, coupling, and acceleration-magnitude formulas. This proves construction, not live measurement equivalence. |
| Training IMU provenance | `../FYP/audit_v5/V5_COMPLETE_AUDIT_REPORT.md:15-19,43-58,86-90`; `../FYP/Datasets v2 Model v5/documentation/FEATURE_CONTRACT.md:31-37` | **UNKNOWN:** the V2 source has 6,054 phase-level IMU rows but no dense raw capture or exact V2 capture/aggregation/merge program. The older V1 generator has similar statistical signatures but is not the V2 generator. Do not call V2 sensor provenance verified or synthetic as a settled fact. |
| Gyro units | `../FYP/IMU/IMU.cpp:30-35,55-74`; `src/digital_spotter/imu/protocol.py:49-56,91-101`; `src/digital_spotter/core/rep_phases.py:278-285`; `src/digital_spotter/inference/v5_features.py:27-34` | **CONFLICT / UNKNOWN:** the historical MPU6050 sketch intends degrees/sec in its serial CSV; current ESP raw counts are decoded to radians/sec and placed into V5 `IMU_Gyro_*` without conversion. Whether the V2 training rows came from that sketch, and their actual unit, is unproven. Neither a blind conversion nor the present direct mapping is authorized for live scoring. |
| IMU range and mounting | `../FYP/IMU/IMU.cpp:30-35`; `firmware/esp32_c3_research/esp32_c3_research.ino:305-317`; `src/digital_spotter/imu/protocol.py:49-56`; `docs/CURRENT_STATE.md:151-156` | **CODE-CONFIRMED DIFFERENCE:** the historical sketch selects MPU6050 ±16g/±1000°/s, while R9 configures the MPU6500 range registers to `0x00` and the Pi uses the 16,384-count/g and 131-count/(°/s) scale profile. The lower-back body-frame orientation and calibration are not established by this code. Do not assume equivalent axis signs, clipping, or noise. |
| Vision source | `../FYP/Vision/vision.py:35-36,96-144,523-547,614-625`; `src/digital_spotter/vision/adapters.py:375-435`; `src/digital_spotter/core/rep_phases.py:81-129,255-303` | **PARTIAL:** angle equations, coordinate rounding, and vision phase medians closely follow the recorded-video extractor. Training extraction uses the heavy MediaPipe Tasks PoseLandmarker in VIDEO mode at 0.50 confidence settings; live Pi code uses legacy `mp.solutions.pose.Pose` at 0.70/0.70 and a 640×360 analysis frame. Landmark/angle distribution equivalence has not been measured. |
| Phase IMU aggregation | `../FYP/Vision/vision.py:614-625`; `../FYP/audit_v5/V5_COMPLETE_AUDIT_REPORT.md:18,43-58`; `src/digital_spotter/core/rep_phases.py:255-303` | **RESEARCH ADAPTATION:** current code takes medians of synchronized/interpolated IMU samples per vision frame. The FYP video script documents vision medians, not the V2 IMU aggregation rule. This may be reasonable for research, but is not source-parity evidence. |
| Runtime attachment on Pi | Read-only SSH inventory on `pidigitalspotter`, 2026-09-30: no `ds-*` systemd unit listed; `ds-imu`, `ds-vision`, `ds-core` inactive; no matching process. `src/digital_spotter/inference/v5_features.py` has no active runtime caller (`rg` source search). | **OBSERVED NOW:** no live V5 service was running or deployed during this audit. The earlier Pi fixed-fixture result remains separate evidence; it did not exercise these live inputs. |

## FYP workspace recheck — 2026-09-30

The separate `/mnt/g/FYP` workspace was inspected read-only after the owner
pointed to it. `IMU/IMU.cpp:1-5,20-41,44-74` is a historical MPU6050/Adafruit
serial sketch: it schedules a 10 ms loop, emits seven timestamp/axis columns,
uses accelerometer values described as m/s², and multiplies gyroscope output
by 57.2958 for intended degrees/s. `IMU/IMU.py:4-22` merely copies serial
lines to `real_imu_data.csv`; that output file was not found in the FYP tree.
Neither file defines V2 phase aggregation, axis mounting, or an MPU6500 capture.

`Datasets v2/imu_data.csv` has 6,054 data rows and 13 columns including
`Session_ID`, `Subject_ID`, `Sensor_Location`, and historical bar proxy fields;
it is not the seven-column serial output. Its SHA256 is
`f1826a11784f6557ffe667147900f33e07203ccb65045fcf9d238400c9a738f2`,
identical to `Datasets v2 Model v5/imu_data.csv`. The V5 package README:21
identifies that CSV as copied upstream provenance while final training reads
`master_dataset.csv`. The only found generator, `Datasets v1/Generate.py:417-452,
665-718`, explicitly constructs phase-level IMU values with random draws and
merges them with vision rows; its V1 output is 1,008 data rows, not the V2
6,054-row source. This establishes V1 generation behavior, **not** V2 lineage.
The prior FYP audit (`audit_v5/V5_COMPLETE_AUDIT_REPORT.md:15-19,43-58`)
likewise records no dense V2 capture or exact V2 IMU creator/merge program.

**Decision boundary unchanged:** V2 gyro unit, axis orientation, physical
capture provenance, and phase aggregation remain **UNKNOWN**. The historical
sketch's intended degrees/s cannot authorize converting the current Pi's
rad/s features or declaring live V5 input parity. No FYP/model/firmware source
was modified, and no hardware test was run for this recheck.

## Next narrow action

1. Obtain or identify the **exact V2 IMU capture/phase-generation source**, its
   gyro unit, axis orientation, and relation to the trained V2 rows. If it does
   not exist, record that limitation and choose a separately approved research
   validation/model decision; do not guess a conversion or silently retrain.
2. Keep the live candidate builder disconnected from `V5ModelRuntime.predict()`
   and user-facing result persistence until the input policy is resolved.
3. The person-camera and mounted-wearable comparison remains the agreed **last**
   integrated test, after the local result path is prepared. No extra soak or
   BLE reconnect campaign is called for by this audit.

No firmware, model, Pi service, or FYP source file was modified. This report
does not claim V5 generalisation, accuracy, sensor parity, or deployability.
