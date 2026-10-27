# M6-R01 — Keep video visible during the pose test

2026-10-20. Scoped UI fix deployed; pose-quality gate remains open.

The timer used `inset: 0` and an almost-opaque background over the entire video.
The live-camera branch did not stop playback, but the overlay hid it visually.
Changed only CSS to a bottom-left, pointer-transparent badge with a 26px timer,
plus the HTML stylesheet cache version. Countdown remains 20 seconds, capture
30 seconds, with automatic aggregate saving. No detector/threshold, camera
capture, BLE, firmware, model or scoring change.

Files: `src/digital_spotter/web/static/ui-preview/styles.css`, `index.html`,
`tests/web/test_ui_camera_connection.mjs`, and plan/current-state/operations docs.

Verification: the new regression check failed before the patch because the
timer covered the camera. Afterward,
`node --test tests/web/test_ui_camera_connection.mjs` passed **3/3**;
`git diff --check` passed. Pi HTTP serves the updated CSS and cache URL. No new
person recording, real-camera playback benchmark or full suite was run for this
CSS-only fix. Pose detection is not claimed fixed by this change.

The prior owner test is preserved on the Pi: 175 frames, 90 detected but low
visibility, 85 not found, zero quality-approved. Existing UI labels only the
quality-approved count as "detected"; that separate reporting problem is not
changed here. No new test was automatically started.

Pi source root: `~/digital-spotter-v5-imu-r1-20261020.E7L664/`.
Pre-change CSS/HTML are preserved under
`live-20261020.8qqaRH/ui-before-countdown.iji23K/` in that root. Their SHA256s:

- CSS: `e3afb00c2f550f1276a232750a3eb413220005f3763738b4ebb571ba85381a20`.
- HTML: `2b02b583b34ca8a0f5841742b2474c3b455ac2d22c70805e519859c38a45a2c4`.

New local/deployed files:

- CSS: `7d56332a811baa4d9ce84d14110216ed39a5f91a321bdda42060a1f8eac4095f`.
- HTML: `3a204f3550ec439d207da7f08defdadd78e8ccac24d056623139fa6abb2b924f`.

The original M5-R05 staged manifest describes the pre-update snapshot; these
two UI files now deliberately differ. Model artifacts are untouched. Rollback:
restore these two files from the named backup and refresh the browser. No
process restart or database change is required. Changes uncommitted/unpushed;
existing worktree changes preserved. The owner must refresh the existing page
to load the new stylesheet; browser-visible confirmation is pending.
