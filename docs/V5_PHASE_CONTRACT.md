# V5 phase contract — recorded-video rule and live research adaptation

Status: **recorded-video source rule identified; bounded local adaptation and
V5 candidate feature bridge implemented** (2026-09-30). This is not a claim
that live V5 scoring has been validated.

| Exercise_ID | Exercise | Phase 1 | Phase 2 | Phase 3 |
| --- | --- | --- | --- | --- |
| 0 | Squat | Descent | Bottom | Lockout |
| 1 | Deadlift | Setup | Mid-pull | Lockout |

Evidence: the read-only V5 source `../FYP/Datasets v2 Model v5/master_dataset.csv`
has 1,010 rows for each squat phase and 1,008 for each deadlift phase, with the
labels above in `Exercise_ID`, `Exercise_Name`, `Rep_Phase`, and
`Rep_Phase_Description`. The frozen package's
`documentation/FEATURE_CONTRACT.md:3` requires exactly three ordered phase
**aggregates**, not dense video/IMU windows. The training code
`../FYP/outputs/v5/v5_stage1_6_pipeline.py:314-321` validates `[1, 2, 3]`
on input; it does not detect boundaries in raw measurements. These paths are
relative to this workspace and point to the separate, read-only model workspace.

The owner confirmed that `../FYP/Vision/vision.py` was used to extract vision
phase data from all recorded videos. Its present 27-row CSV is only the available
local output snapshot; it is not evidence that the script processed one video.
The exact derivation of every V2 master/IMU row remains separately unverified.

## Recorded-video rule

`../FYP/Vision/vision.py:96-144,517-562,569-625` computes left and right 2D knee
flexion from MediaPipe landmarks (180 degrees minus hip-knee-ankle angle), averages
them, forward-fills missing interior values, applies a 0.4-second quadratic
Savitzky-Golay filter, and finds knee-angle peaks with at least 15 degrees
prominence and 1.2 seconds separation. A rep spans the nearest samples below
45% of its peak on either side. It divides that interval at 35% and 45% of its
frame count, then takes per-field medians of valid vision coordinates/angles and
the median frame timestamp for each phase. The same boundary algorithm is used
for squat and deadlift; their phase *names* differ as shown above.

The historical script fabricates a whole-video rep when no peak is found
(`vision.py:569-573`). The live research adapter deliberately omits that fallback:
an incomplete or undetected rep produces no completed event.

## Local research implementation

`src/digital_spotter/core/rep_phases.py` uses the source peak/split/vision-median
rule on a bounded 300-frame history and waits for a completed return below the
threshold. `LocalSessionService.poll_completed_reps()` emits newly completed
reps once, outside the high-rate callback. Three ordered phase records retain
Pi-monotonic capture ranges, vision medians, and optional medians of safely
interpolated lower-back IMU samples. The IMU median is a **research adaptation**:
the video script has no IMU phase aggregation rule, and the V2 IMU provenance
does not establish one. IMU values remain in `m/s²` and `rad/s`; V5 unit parity is
not claimed. If a phase has no valid vision row, no rep is emitted. If its IMU
alignment is missing or degraded, the phase and completed event are unavailable,
not zero-filled or scoreable.

## Remaining gate

2026-10-20 clarification: the owner disclosed synthetic dataset provenance.
M5-R02's separate offline candidate now defines a new explicit simulated
35%/45%-split, pose-associated IMU median policy. This is an experimental
generation choice, not recovery of the missing historical IMU reducer or proof
that fixed proportions identify physiological phases. The existing live detector
and frozen V5 package are unchanged. See
`training/v5_imu_retraining/docs/IMU_GENERATION_SPEC.md`; training and physical
feature equivalence remain pending.

The offline code reuses the FYP rule but is not a byte-for-byte replay of original
video processing: the live camera uses a different MediaPipe adapter and may have
variable frame intervals/drops. Local synthetic replay is a narrow code check,
not accuracy or source-data parity. A later fixed-median Pi model-loading check
passed, but it does not verify live feature coordinates, IMU units/axes or
source-equivalent aggregation. Do not enable V5 scoring on that basis.
Human-camera and mounted-wearable acceptance remains the final integrated test.

The local `v5_features.py` bridge now constructs the exact frozen temporal field
order and context from the three phase summaries. Its asymmetry, coupling and
magnitude calculations follow the read-only Stage 8 training script. This proves
code-level arithmetic and shape only, not equivalence of real camera coordinates,
mounted IMU units/axes, or training-source phase aggregation.
