# Owner-pasted Generate.py v5.1 — reference review

Received 2026-10-20 in the conversation while preparing M5-R01. The supplied
code was reviewed as an additional reference; it was not executed. A full v5.1
source file was not found in the inspected FYP Python files and is not claimed
to have been copied. `reference/generators/historical_v1_Generate.py` is the
different, existing V1 reference, not this pasted revision or proven V2 source.

## Useful structure to retain

- Squat/deadlift scope, three phase identities and seeded randomness.
- Session/repetition identifiers and explicit metadata tables.
- Separate vision and IMU streams and non-destructive timestamped output idea.

## Do not adopt unchanged

| Area | Finding | Required treatment |
| --- | --- | --- |
| Vision preservation | The main loop regenerates landmarks, angles, sessions, labels and missing values. | Use existing master rows as immutable inputs; replace IMU values only. |
| Units | `get_imu()` emits degrees/second; the current receiver emits rad/s. The claim that Adafruit events are universally degrees/second is incorrect. | Choose one explicit SI contract; do not alter firmware or apply duplicate conversions. |
| Sensor identity | Text claims MPU6050 calibration; this wearable is MPU6500. | Use actual configured MPU6500 ranges and separately mark unmeasured noise assumptions. |
| Coordinate frame | Comments call X anterior-posterior but also assign sagittal rotation to Gyro_X. Sagittal forward bending rotates about a mediolateral axis. Chip-face wording does not establish the three physical axes. | Define a right-handed sensor/body transform; no assumed mounting identification. |
| Motion physics | Independent per-axis draws keep Z near +9.81 and positive gyro means across opposing motions. Descent/ascent velocity alone does not determine acceleration sign. | Derive specific force and signed angular velocity from one consistent position/orientation trajectory. |
| Error shortcuts | Valgus, asymmetric load and hip shift directly select large lower-back gyro means. | Do not encode deterministic label fingerprints or pretend knee motion guarantees a particular lumbar signal. |
| Phases/timing | Comments describe midpoints, but `vis_ts` adds preceding phase durations only. No half-phase offset is calculated. Deadlift mid-pull is treated as isometric squat bottom. | Freeze the same actual phase boundaries and reducer for generated and live data. |
| Sample rate | Comments assume 100 Hz; the current accepted wearable stream is 50 Hz. | Match the active stream unless a separately approved change is needed. |
| Sensor limits | Gyro spikes of 400–1200 degrees/second exceed the current configured +/-250 degrees/second measurement range. The chip's optional +/-2000 mode is not the active profile. | Model saturation/quantization for the actual profile; model flagged digital corruption separately if needed. |
| Label noise | Per-row flips create contradictions within a repetition and do not represent actual reviewer evidence. | Preserve current labels for this IMU-only revision; any label-policy change needs a separate decision. |
| Sequence diversity | Varying repetitions per session does not change V5's fixed three-phase input length. | Keep repetition grouping and model shape explicit; group related variants during splitting. |
| Unsupported claims | Calibration, accuracy forecasts, clinical risk thresholds and ferromagnetic gyro effects are asserted without measured support in the supplied code. | Identify assumptions as synthetic; do not turn them into clinical or observed-performance claims. |

The raw MPU6500 decoder is `src/digital_spotter/imu/protocol.py:79-110` in the
main repository. The current reducer is documented in `docs/V5_PHASE_CONTRACT.md`;
its IMU medians are explicitly a research adaptation, not established historical
collection semantics. Neither this review nor the pasted comments settle the
future reducer or mount frame. No generated replacement data exists yet.
