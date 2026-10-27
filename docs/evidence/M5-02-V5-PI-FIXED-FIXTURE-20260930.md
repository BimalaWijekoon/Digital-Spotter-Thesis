# M5-02 narrow Pi V5 fixed-fixture check — 2026-09-30

Status: **PASS for one temporary backend-compatibility check only.** This is E3
Pi execution of a deterministic, fitted-median reference input, not a live
camera/IMU rep, model accuracy result, production deployment, or thermal gate.

The Pi 4B 8 GB ran Debian aarch64, Python 3.13.5, NumPy 2.2.4 and pinned
`ai-edge-litert==2.2.0` in a temporary virtual environment under `/tmp`.
The official package publishes a CPython 3.13/aarch64 wheel at
<https://pypi.org/project/ai-edge-litert/2.2.0/>. No system Python package,
existing service, camera, BLE client, or ESP firmware was changed. The temporary
model/source copy remains under `/tmp/ds-v5-m502-20260930/` for this boot only.

Procedure: `scripts/validate_v5_pi_fixture.py` verified all 24 copied artifact
hashes, loaded the selected FP32 built-ins model, transformed the three frozen
phase-median records and context medians, then invoked the same reference-only
input 3 times for warm-up and 20 timed times. This input is fitted-state data,
not a measured exercise or independent evaluation fixture. The local x86_64
run used the same model and script as a numerical comparator.

The bounded Pi invocation after the temporary copy was:

```bash
PYTHONPATH=/tmp/ds-v5-m502-20260930/src \
  /tmp/ds-v5-m502-20260930/.venv/bin/python \
  /tmp/ds-v5-m502-20260930/scripts/validate_v5_pi_fixture.py \
  --package /tmp/ds-v5-m502-20260930/models/digital_spotter_v5
```

| Check | Pi result |
|---|---|
| Model SHA-256 | `8a1d308c2596e571b2840673c1b437bbd2ccdbef5c590ebdb6dbbd40a7a4f9ab` |
| Tensor shapes | float32 `(1,3,29)` and `(1,2)` |
| Raw probability | `0.030402589589357376` |
| Platt-calibrated probability | `0.0675515117021965` |
| Frozen threshold / binary class | `0.20549274582373653` / `0` |
| Reference-only flag | `true` |
| Local x86 raw / calibrated | `0.03040258027613163` / `0.06755150834188481` |
| Pi–local absolute difference | raw `9.313225746e-9`; calibrated `3.36031169e-9`; same class |
| 20-call adapter latency | median `2.389709 ms`; nearest-rank p95 `2.444969 ms` |
| Peak process RSS | `48,340 KiB` (short process, not full service memory) |
| Pi status immediately afterward | `throttled=0x0`, temperature `54.5 C` |

The 20-call p95 is a small compatibility smoke measurement, not a sustained
classifier latency distribution or proof of the final `<25 ms` product target.
One post-run temperature is not thermal characterization. Source units/axes,
live pose/phase equivalence, mounted IMU behavior, camera/IMU fusion under load,
result persistence, UI wiring, and the final human-camera test remain open.
V5 live scoring remains disabled; no V4 fallback was activated.

Rollback: the Pi product state was unchanged. The temporary `/tmp` directory
can be removed after evidence review or will disappear on reboot. No cleanup or
reboot was performed as part of this check.
