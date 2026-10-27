# M6-D12 visible set finish and JSON export — 2026-10-27

## Reason

After starting a real set, the owner could not find a visible way to finish it
and obtain JSON. The camera panel had a small Stop action, but the primary Set
action became disabled while active.

The already-running owner set was stopped through the existing API before the
upgrade. It was saved with 486.41 seconds, 2,084 camera frames, 279 frames with a
detected pose, zero quality-approved pose frames and zero completed reps. These
facts are preserved as observed; they are not reported as successful rep/model
analysis.

## Change

- The primary Set button becomes `Finish + JSON` while active or paused.
- Both that action and the camera-panel Finish action stop and save the set, then
  download `digital-spotter-set-<session_id>.json`.
- A separate `Download JSON` action allows another download until a new set starts.
- The core emits a bounded `completed_set` summary containing context, duration,
  counts and explicit readiness/analysis warnings.
- No raw video, pose landmarks, raw IMU samples or fabricated probabilities are
  included.

## Verification

```text
Node workout/UI checks: 6 passed
Focused Python export contract: 1 passed
git diff --check on touched files: PASS
release: digital-spotter-research-appliance-20261027-r13
archive SHA256: 008a3386df363ac96a8fabb63e16e9449782bdfc58c29e27eaccc20d5f4dabe3
manifest entries: 251, all verified
Pi services: core active, IMU active, media active
served Download JSON control: present
live empty start/stop: PASS; saved=true and completed_set returned
```

The older SQLite-backed workout test did not complete within a bounded 35-second
run and produced no assertion failure. The new export contract was therefore
verified with a focused no-database unit test plus the real Pi HTTP boundary.
No extended workout, BLE, model, camera, performance or endurance test was run.

## Boundary and rollback

This is a research summary export, not validated live form scoring. The deployed
model continues to report `live_inputs_verified=false` and the export retains
that state. Rollback is to point `current` back to release `r12` and restart only
the core service. Repository changes remain uncommitted in the existing dirty
working tree.
