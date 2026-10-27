# IMU-only synthetic revision R1

Work package M5-R02. This specification defines an **approximate synthetic
research experiment**, not recovered collection-time physics or a calibrated
model of the purchased belt. No real recording is currently available.

## Preservation and ownership

Read `reference/dataset/master_dataset.csv` without modification. Retain its
6,054 rows, 2,018 three-phase repetitions, row order and exact string value of
every non-IMU cell, including missing vision, old labels, identity/context and
historical timestamps. Change only `IMU_Acc_X/Y/Z`, `IMU_Gyro_X/Y/Z` and
`IMU_Acc_Magnitude` **if already present**. V5 normally computes magnitude from
the three resulting acceleration summaries rather than storing this column.
Preserve each original missing-IMU cell; do not replace missing data with zero.
Copy the original vision and subject-meta CSV files byte-for-byte into each run.
No new people, reviewers, labels, vision values or bar-motion proxies are created.

The published master remains a synthetic source. Holding vision fixed is an
experimental control, not independent validation of those vision values/labels.

## Units and coordinate system

- Raw simulated stream: 50 Hz; acceleration in m/s² including specific force;
  angular velocity in rad/s.
- Virtual body frame: right-handed X forward, Y left, Z up. A forward bend is
  rotation about Y. This is **not** identification of the physical PCB axes.
- World gravity: `(0, 0, -9.80665)` m/s². Define rotation `R` from sensor to
  world. Ideal acceleration is `R.T @ (sensor_world_acceleration - gravity)`.
- Euler convention: body-to-world `Rz(yaw) @ Ry(pitch) @ Rx(roll)`; use the
  corresponding body angular-rate equations, not Euler derivatives as three
  independent gyro axes. Apply one proper session-level sensor mounting rotation
  consistently to acceleration and gyro.
- Quantize and saturate using the existing configured +/-2 g, +/-250 degrees/s
  profile (16,384 LSB/g and 131 LSB/(degrees/s)). Do not emit analogue readings
  outside that profile or inject arbitrary magnetic/ESD "gyro effects".

Firmware/decoder evidence: `firmware/esp32_c3_research/esp32_c3_research.ino`
and `src/digital_spotter/imu/protocol.py`. No firmware change is part of R1.

## Motion assumptions (not measurements)

The numeric configuration is recorded in `config/imu_simulation.json`. Travel,
duration, pose cadence, mounting variation, noise, bias and trunk-to-sensor
coupling are **explicit modelling priors**. None was fitted to real belt data,
validated for a population or presented as a manufacturer's complete noise model.

Construct continuous C2 position/orientation trajectories with piecewise quintic
interpolation; analytic first/second derivatives produce rate/acceleration. Each
source repetition provides three trunk-inclination summaries. The approximate
image-space conversion `pitch = factor * (180 - trunk_inclination)` is a modelling
assumption, not an exact pelvis reconstruction. Finite angles are limited to a
0–100 degree bend for the simulator; missing values are interpolated from that
rep's available phases, or use fixed documented priors if all are absent. Count
every missing/clipped angle without modifying the original vision cells.

Squat motion starts standing, bends/lowers toward the middle, then returns.
Deadlift starts in the setup position, moves through the pull and finishes
standing; it is not generated as a squat descent/bottom. Mild roll/yaw variations
and sensor translations are sampled independently of error/class labels.

Do not read `Class_Binary`, `Error_*`, experience, load or subject measurements
to select IMU means/noise. Labels are copied, not simulator inputs. Session and
rep IDs serve only as reproducible random-stream keys; session mounting/bias is
shared within each session and is not fitted using held-out data.

## Three-phase reduction and timestamps

Use the current research adapter's 35%/45% frame-count split policy. Simulate
pose timestamps at an independently varied 6–12 Hz, associate the 50 Hz IMU
stream by interpolation, and take the per-channel median of the associated
values in each phase. No synthetic fourth timestep is added. Derive acceleration
magnitude from the resulting three acceleration medians, as V5 does.

This reuses the **type of reduction** in `core/rep_phases.py`; it does not prove
that the fixed proportions describe real deadlift phases, or that simulated
pose cadence/drop patterns are equal to the actual Pi. The existing phase
detector is not changed or validated here.

Old `Timestamp_ms` values remain untouched provenance fields, **not newly
measured synchronization evidence**. `phase_manifest.csv` separately records
simulated relative times/frame ranges. `imu_data.csv` is a new explicit
phase-level table keyed by subject/session/rep/phase. It must not be re-merged
using guessed historical timestamps. A single 50 Hz example trace is retained;
the full synthetic stream need not be stored for every repetition.

## Required focused checks

1. Stationary/tilted ideal acceleration has magnitude g; ideal stationary gyro
   is zero; a bend-and-return has correctly signed rates under the fixed frame.
2. Sensor quantization stays within the configured representable range.
3. Same inputs/config/seed give identical regenerated values; changing only a
   class/error label cannot change the simulated IMU.
4. All protected source cells, vision/meta hashes, phase groups and original
   source hashes remain unchanged after generation. All available new IMU values
   are finite; report missingness and saturation, not a blanket accuracy pass.

## Training boundary

The new data is a candidate for the **same final V5 BiLSTM + two-head attention**,
29 temporal features and 2 context fields. Retain train-only fitted winsorization,
phase-specific imputation, scalers, regularization, calibration, threshold
selection and TFLite parity. Do not run RF, architecture ablations or a parameter
search. The owner explicitly selected the original grouped cross-validation
(multiple fits of this one architecture), not a single holdout split. New synthetic metrics
cannot be described as accuracy on actual people. Runtime promotion and physical
mount equivalence remain separate later steps.

## Physics references

- OpenSim's official IMU example subtracts gravity and expresses acceleration
  in sensor coordinates: https://opensim-org.github.io/opensim-moco-site/docs/1.3.0/html_user/exampleIMUTracking_answers_8m-example.html
- Synthetic IMU research uses motion trajectories and compares simulated/model
  outputs with real measurements; this is not support for arbitrary class means:
  https://doi.org/10.3390/s21175876
- A lumbar squat study used consistent L5 belt placement and pilot-selected
  acquisition settings: https://doi.org/10.1109/BSN.2015.7299380

The priors above are not claimed to be numerical results from these papers.
