# Pi UI wording and V5 Test input — Step 3 (2026-10-03)

**Narrow result: PASS for a fixed-input Pi calculation and isolated UI output.**
This is not a measured rep, live model scoring, workout feedback, or product
dashboard acceptance.

The page now uses plain **Digital Spotter** branding without a global PREVIEW,
demo, or research banner. Camera controls say **Connect camera** and **Stop
camera**. The Pi camera/WebRTC setup was unchanged. The Workout Feedback panel
continues to say live inputs are unavailable; set actions remain disabled.

A one-shot, owner-side command verified every file in the copied V5 manifest,
loaded the existing built-in-ops FP32 LiteRT model, constructed three ordered
phase records and context solely from the package's frozen fitted medians, then
called the canonical `V5ModelRuntime.predict_reference_only()` once. It did not
refit preprocessing or invent sensor readings. The command was:

```bash
cd /home/pibimalawijekoon/digital-spotter-research-step1-20261003
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/pibimalawijekoon/digital-spotter-research-step1-20261003/src \
  .venv/bin/python write_v5_test_input.py \
  --package models/digital_spotter_v5 \
  --output src/digital_spotter/web/static/ui-preview/test-input-result.json
```

The resulting static `v5_test_input_v1` file declares
`source=frozen_fitted_medians`, `live=false`, and `reference_only=true`.
The Pi returned model `digital_spotter_v5_scope_faithful`, raw probability
`0.030402589589357376`, calibrated probability `0.0675515117021965`, threshold
`0.20549274582373653`, and class `0`, matching the earlier dated Pi fixed-input
check. These numbers measure this fitted-median input only, not exercise form or
model accuracy. The browser validates the source, version, probabilities and
class/threshold consistency before showing a compact **Test input** card under
Devices → Analysis. It does not write this result to Workout Feedback, SQLite,
cloud storage, or the wearable.

Focused checks: the new UI-input parser/wording test, existing camera-control
contract and research-status test passed; JavaScript syntax, Python compile and
`git diff --check` passed. The Pi served the updated HTML, input JSON and JS
module over loopback. A short headless Chromium render of the Pi-hosted page
showed the Digital Spotter title, the visible **Test input** card, `Class 0`,
`6.8%`, and `V5 scope-faithful`; no global PREVIEW/research text appeared.
Ports 8766/8889/8189 remained loopback-only. No real camera stream, ESP,
sensor, person or long-duration check was rerun for this wording/static-output
change. The owner has not yet visually reviewed this updated card in a normal
browser.

The prior working Pi UI is retained at
`~/digital-spotter-research-step1-20261003/ui-before-test-input-20261003/`.
Source edits are uncommitted. After a Pi reboot, the static UI and relay still
require explicit restart because they are not boot services.
