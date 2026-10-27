# UI redesign layers (research preview)

This is a separate design preview for the M6-03 dashboard direction. It does not
complete M6-03, replace the migration dashboard, or establish live readiness.
Every layer is shown to the owner before the next layer is built. The preview
originally did not write sessions, start Pi hardware, perform inference, or
expose a public mutation endpoint. Later isolated Pi research slices added an
on-demand camera, a fixed non-live model input, and a read-only live status
viewer; those are documented below and do not complete the product dashboard.

| Layer | Scope | Review checkpoint |
|---|---|---|
| 01 — Foundation | Light white/grey/clay/blue palette, compact responsive shell, page hierarchy, labelled placeholder zones, mobile panel switching | Desktop, laptop, and phone browser preview; approve placement and visual direction |
| 02 — Setup | Squat/deadlift and load inputs; explicit unchecked device states; disabled session start | Review layout and validation at laptop size; live checks remain for Layer 06 |
| 03 — Live set | Camera/pose placeholder, rep count, timer, and disabled Pause/Stop controls | Review visual priority at laptop size; live wiring remains for Layer 06 |
| 04 — Rep result | Model-result and bad-form-probability placeholders; recent-rep strip deferred by owner | Review unavailable state at laptop size; no example scores or error types |
| 05 — Review and diagnostics | Deferred until the owner chooses whether a review area belongs in this view | Decide information depth and privacy wording later |
| 06 — Real integration | Authenticated status/session API and existing WebRTC/pose primitives | Only after required core/API gates; verify real vs simulated and local persistence |

## Layer 01 boundary

The new page is `src/digital_spotter/web/static/ui-preview/index.html` with
`styles.css` and a local-only `preview.js` for mobile panel switching. Its palette
direction comes from the owner's Realaize frontend (white surfaces, quiet grey,
light clay and blue), without importing that project's code or branding. There
is no network API, camera, BLE, model, data storage, or simulated score. The
camera image and feedback data areas still reserve positions only.
The active FastAPI dashboard and research WebRTC viewer are unchanged.

## Layer 02 preview boundary

The Set panel now accepts Squat or Deadlift and a non-negative load in kilograms.
Its short message distinguishes incomplete input from unavailable device checks.
Camera, wearable, and analysis remain explicitly **Not checked**; Start set stays
disabled. Inputs remain browser-local and do not start or save a session. This
layer is for laptop layout review, not a claim of live readiness or M6-03
completion.

## Layer 03 preview boundary

The camera panel now reserves space for pose status and a compact in-set strip.
Reps and time show unavailable placeholders, while Pause and Stop remain disabled.
No clock runs, no camera opens, and no session command is sent. Only the requested
laptop viewport is checked for this layer.

## Layer 04 preview boundary

Feedback now separates the model result, bad-form probability, and model version.
All three remain unavailable placeholders; no inference, score, or error category
is fabricated. The earlier empty recent-rep strip was removed at the owner's
request; whether and where to show history remains undecided. Only the laptop
viewport is checked for this layer.

## Layout correction before Layer 05

The owner identified that the wide camera placeholder was wrong for standing
exercises and that the IMU graph was missing. The first portrait pass was too
narrow, so the 1366×768 preview now gives the camera a larger 3:4 portrait frame
and removes the recent-rep footer to maximize its height. Separate empty
acceleration and gyroscope graph areas remain beside it. No trace, axis value,
or IMU sample is invented. The owner then requested less width for IMU, a more
prominent model result, and smaller inputs. Feedback now takes the larger middle
area, with a compact Set card below it; IMU moves to a narrow right column.
The graph and camera remain preview-only; this does not start Layer 05 or connect
hardware.

## Top-level navigation correction

The top bar beside the Digital Spotter logo now has Workout and Devices tabs.
Workout is selected by default; Devices shows Camera, Wearable, and Analysis
without claiming product readiness. Selection changes the preview view. History remains
deferred, and the live dashboard is unchanged. The preview assets use a versioned
URL so an already-open browser does not keep the older layout CSS.

The Devices view is now a compact three-card preview: Camera (video feed and
pose tracking), Wearable (BLE link and IMU data), and Analysis (model and sync).
All checks begin as **Not checked**; the optional research camera preview only
updates the Camera and Video feed labels. It does not imply pose, wearable, or
model readiness. This remains UI-only and does not complete M6-03.

## Camera-only research option

The Workout camera panel has **Connect camera** and **Stop camera** buttons,
with no endpoint field. It reads a private WHEP endpoint from the page's static
`camera-config.json`; the existing reader still rejects non-loopback endpoints.
The Pi-hosted research relay launches the existing Picamera2 camera owner only
while a viewer requests the stream. Stop/page exit/hidden page/Devices switch
ends the reader, then the relay releases the camera. The full landscape frame
is contained in the portrait area without cropping. A playing video changes
only the camera status to **Preview live**; wearable, pose, model, and set state
remain unavailable. No video is recorded or uploaded by this page. This is not
M6-03 product integration.

The subsequent Pi-hosted slice uses plain Digital Spotter branding: no
page-wide preview or research badge. The camera button now reads **Stop camera**.
One V5 fitted-median reference calculation appears only in the Devices →
Analysis card under **Test input**; the Workout Feedback panel remains
unavailable. This does not imply a measured rep or live scoring. See
`docs/evidence/M6-03-PI-UI-TEST-INPUT-20261003.md`.

The current Pi copy reads a same-origin unscored session status. Camera/pose
freshness and detected rep count come from the canonical local session; one
on-demand camera owner also supplies H.264. If the wearable is absent, IMU
status stays unavailable. Workout Feedback and Start set remain disabled;
the isolated research session is not a product workout. See
`docs/evidence/M6-03-PI-UNSCORED-STATUS-20261003.md`.

Earlier local and Pi checks verified the pinned reader and real H.264 playback.
The Step 2B button/on-demand path passed one short real Pi/Chromium playback and
clean-release check, but visual quality, latency, pose overlay and production
access control remain open. See
`docs/evidence/M6-03-PI-RESEARCH-UI-STEP2B-20261003.md`.

Layer 01 fit without scrolling at desktop (1440×900), laptop (1366×768), and
portrait phone (390×844) sizes. After Layers 02–04 and the layout correction,
only the requested laptop
viewport was rechecked. The phone now has Movement, IMU, Set, and Feedback panels,
but its updated fit is not re-verified. Very short or heavily zoomed screens may
scroll rather than clip required content.

For layout-only review, this file can still be opened directly in a browser:

```text
G:\Digital Spotter\src\digital_spotter\web\static\ui-preview\index.html
```

For the camera option, serve the shared static directory on loopback so the
preview can load the existing pinned reader and WHEP modules:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory src/digital_spotter/web/static
```

Open `http://127.0.0.1:4173/ui-preview/` for layout-only review. If the earlier
4173 server is still running with `ui-preview` as its root, stop it first;
otherwise the shared modules will return 404. The installed Pi research relay
allows the Pi-hosted origin `http://127.0.0.1:4174`, not this local layout origin.
Use the Pi-hosted page and private SSH tunnel in `docs/OPERATIONS.md` for camera
video. The page keeps a visible preview/no-analysis disclosure.
