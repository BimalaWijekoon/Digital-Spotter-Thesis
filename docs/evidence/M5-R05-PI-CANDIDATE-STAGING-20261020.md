# M5-R05 — isolated Pi candidate staging and one inference

2026-10-20. **PASS for transfer integrity and target-runtime compatibility.**
This is not live camera/IMU inference, model accuracy, UI launch or production
activation. Existing Pi configuration and services were not changed.

## Staged release

New, private Pi directory:

```text
/home/pibimalawijekoon/digital-spotter-v5-imu-r1-20261020.E7L664/
  src/digital_spotter/
  scripts/run_workout.py
  scripts/validate_v5_candidate.py
  package/
  STAGE_SHA256SUMS.txt
  candidate.tar.gz
```

The source bundle excludes Python caches; the package contains only the final
model/fitted state, metadata and small provided fixtures—not training datasets,
inner/outer checkpoints, training environments or training scripts. No existing
Pi source/model directory was overwritten. No current symlink was switched.

Archive: **1,808,315 bytes**, SHA256
`6ffd63d49ecd904c0a2b19e6f6d5c3e42359ffa021a596322c279d117c38c499`.
The archive hash matched before extraction; **107/107 staged file hashes**
matched afterward. Extraction refused overwrites. The candidate runtime also
verified its complete model-package inventory before loading.

Model version: `digital_spotter_v5_imu_synthetic_r1`. FP32 TFLite: **497,416
bytes**, SHA256
`c3da4c5b03461e2e2ecceadfd4081f921777676b4342e87f0153558af71a941c`.

## Exact scope of the target check

`scripts/validate_v5_candidate.py` uses the canonical candidate runtime and its
provided synthetic repetition-zero fixture. It verifies frozen preprocessing,
then performs **one reference-only model invocation** and compares probability
and class against the exported Keras reference. It does not open a camera,
connect BLE, create a session database or enable feedback.

```bash
cd /home/pibimalawijekoon/digital-spotter-v5-imu-r1-20261020.E7L664
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" \
  /home/pibimalawijekoon/digital-spotter-research-status-20261003/.venv/bin/python \
  -B scripts/validate_v5_candidate.py --package package
```

The same check was run once on the PC. No model retraining, repeated timing
loop, BLE reconnect, camera, fallback or endurance matrix was run.

| Check | Actual Pi result |
| --- | --- |
| CPU / Python | aarch64 / 3.12.0 |
| NumPy / existing backend | 1.26.4 / ai-edge-litert 2.1.5 |
| Tensor inputs | float32 `(1,3,29)` and `(1,2)` |
| Raw probability | `0.9668163657188416` |
| Calibrated probability | `0.9334300539972048` |
| Threshold / synthetic-fixture class | `0.3976007923801824` / `1` |
| Pi–PC raw/calibrated/class difference | exactly equal on this fixture |
| Absolute error vs exported Keras reference | raw `5.960464477539063e-8`; calibrated `1.8598166229288893e-8` |
| Reference-only / live scoring | true / false |
| Full Python TensorFlow imported | false |
| Single adapter call | 9.286757 ms; one call, **not a latency benchmark** |

The reused core venv can discover an already installed TensorFlow package, but
this check did not import it or change any dependency. The separate pose venv
was not touched. The PC used LiteRT 2.2.0/Python 3.12.13; the target passed with
its existing 2.1.5 backend, so no package upgrade was needed.

Pi health before/after: **throttled=0x0**; **41.3°C → 42.3°C**; 13 GB free at
preflight. Those snapshots are not a thermal soak. Core/research processes and
the expected UI/relay listeners were absent after this reboot both before and
after the check; no service was started/stopped by this step. Stale socket/PID
files and previous databases were preserved, not interpreted as live processes.

One historical legacy-model path check returned “not found”; this step therefore
does not claim a verified legacy-model hash on the Pi. No old Pi tree was edited,
and the unchanged original model remains available locally for rollback.

## Evidence and next step

- [Pi result](m5-r05-pi-candidate-20261020/pi-inference.json)
- [PC result](m5-r05-pi-candidate-20261020/local-inference.json)
- [Target stderr](m5-r05-pi-candidate-20261020/pi-inference.stderr.log)
- [Transferred file inventory](m5-r05-pi-candidate-20261020/STAGE_SHA256SUMS.txt)
- [Post-check health/listeners](m5-r05-pi-candidate-20261020/pi-postcheck.log)

Next is deliberate launcher/UI/producer integration using the explicit staged
package and preserving previous run data. Physical sensor frame, units and
synchronized phase equivalence must be checked before a separate live-scoring
decision. Synthetic-fixture success is not evidence of real-world accuracy.

Rollback: leave this new directory unselected. Nothing was promoted or deleted.
No network, SSH, Tailscale, BlueZ, firmware, credential, existing database/schema
or system-package changes occurred. Real hardware used: Pi CPU only; synthetic
model fixture, no real pose/IMU data or sensor simulation passed off as hardware.
Local code addition is the narrow validator; plan/current-state/operations/test/
decision/progress documents were updated. Changes remain uncommitted/unpushed.
