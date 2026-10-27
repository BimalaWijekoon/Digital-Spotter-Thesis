# Digital Spotter — Performance Benchmark (Raspberry Pi 4B 8GB)

**Date:** 2026-07-19/20  ·  **Device:** Raspberry Pi 4B 8GB, Raspberry Pi OS Trixie (64-bit)
**Goal:** reduce CPU/thermal load of the live dashboard on the Pi **without** degrading
camera quality or breaking any part of the working system (camera, IMU/MQTT, inference).

Reproduce with `scripts/benchmark_pipeline.py` (`--mode pose` = isolated pipeline,
`--mode sysmon` = whole-system monitor).

---

## 1. Method

- **Isolated pose benchmark** (`--mode pose`): reads the live mediamtx RTSP stream and
  times `decode → resize → cvtColor → MediaPipe` per frame, at a given `model_complexity`
  and processing width. Run with the dashboard stopped to isolate pose cost.
- **Integrated system monitor** (`--mode sysmon`): with the full stack running (dashboard
  + camera ON + session active), samples aggregate CPU%, per-process CPU%/RSS, CPU temp,
  and throttle flags over a 12 s window.
- CPU% is computed from `/proc/stat` and `/proc/<pid>/stat` deltas. Per-process CPU% can
  exceed 100 (multi-core; Pi 4B has 4 cores). Aggregate system CPU% is 0–100.

---

## 2. Baseline (as-shipped: complexity=2 Heavy, 1280×720, 30 fps)

### Isolated pose pipeline
| complexity | proc width | pose infer (median) | decode | resize+cvt | effective FPS |
|---|---|---|---|---|---|
| 2 | 1280 | 122.5 ms | 7.4 ms | 2.5 ms | 7.5 |
| 2 | 640  | 120.3 ms | 6.1 ms | 2.2 ms | 7.7 |
| 1 | 1280 | 121.9 ms | 8.6 ms | 2.4 ms | 7.5 |
| 1 | 640  | 122.0 ms | 6.1 ms | 2.3 ms | 7.6 |
| 0 | 1280 | 122.4 ms | 7.5 ms | 2.3 ms | 7.5 |
| 0 | 640  | 119.8 ms | 6.2 ms | 2.3 ms | 7.7 |

### Integrated system (camera ON + session active)
| metric | value |
|---|---|
| System CPU (aggregate) | **47.9 %** (~1.9 of 4 cores) |
| Dashboard process CPU | **174.4 %** (~1.74 cores) |
| Dashboard RSS | 815 MB |
| mtxrpicam CPU | 10.2 % |
| mediamtx CPU | 6.0 % |
| CPU temp | 57 °C |
| Throttle flags | `0xe0000` |

---

## 3. Findings

1. **MediaPipe is the hard bottleneck: ~122 ms/frame → ~7.5 FPS ceiling**, consuming
   ~1.2 CPU cores by itself. Everything else (H.264 decode ~7 ms, resize/cvt ~2.5 ms) is
   an order of magnitude cheaper.
2. **Resolution barely affects pose cost.** 1280 vs 640 changes only the tiny decode/resize
   terms, not the 122 ms pose step (MediaPipe resizes to its own fixed input internally).
   → **We can keep the camera at full 720p for clear quality essentially for free.**
3. **`model_complexity` could not be ranked here** because the test scene had no person
   (`valid_pct = 0`), so only MediaPipe's *detector* ran — that stage is
   complexity-independent. The complexity-sensitive *landmark* model only runs once a body
   is detected. Ranking 0/1/2 requires a subject in frame + a landmark-accuracy check.
4. **Wasted work at 30 fps:** the camera captured/decoded 30 fps and the MJPEG endpoint
   re-encoded at ~30 fps, but the pose pipeline only produces ~7.5 unique frames/sec — so
   ~3/4 of the decode and encode work was thrown away. The displayed video is pose-rate
   limited (~7.5 fps) regardless, so cutting capture fps is **invisible to the viewer**.
5. **Thermal:** `throttled=0xe0000` = *soft-temp-limit / freq-cap / throttling have occurred
   since boot* (no under-voltage bit). The Pi runs near the 60 °C soft limit under sustained
   load → active cooling recommended.

---

## 4. Changes applied (kept)

| # | Change | Rationale | Cam-quality impact |
|---|---|---|---|
| A | mediamtx `rpiCameraFPS` **30 → 15** | pose only consumes ~7.5 fps; halves H.264 decode + capture work | none (video is pose-rate limited) |
| B | MJPEG **encode caching** (`generate_mjpeg_frames`) — re-encode only when the frame changes (by `FrameResult.timestamp_ms`) instead of every poll | eliminates ~4× redundant JPEG encodes | none |

**Kept as-is (deliberately not changed):**
- **Resolution 1280×720** — proven cheap for pose; preserves clear camera quality.
- **`model_complexity = 2`** — no empirical basis to lower it without a subject-in-frame
  accuracy test; changing it risks a silent accuracy regression. See Recommendations.

---

## 5. Optimized result (complexity=2, 1280×720, 15 fps + encode cache)

| metric | baseline | optimized | Δ |
|---|---|---|---|
| System CPU (aggregate) | 47.9 % | **39.4 %** | −8.5 pts (−18 %) |
| Dashboard process CPU | 174.4 % | **149.3 %** | −25 pts (~0.25 core freed) |
| mtxrpicam CPU | 10.2 % | **4.5 %** | −56 % |
| mediamtx CPU | 6.0 % | **3.9 %** | −35 % |
| CPU temp | 57 °C | 55 °C | −2 °C |
| Load avg (1m) | 0.90 | 0.74 | −18 % |
| Camera quality | 720p clear | **720p clear (unchanged)** | ✓ |

**Functional validation (nothing broke):** `esp32_online=True`, `mqtt_connected=True`,
`model_mock=False`, `all_ready=True`; `/predict` → "Good Form", 20.5 ms, real model;
`/video_feed` streaming; camera frame verified sharp.

**Decision: KEEP both changes.** Measurable CPU/thermal reduction, zero quality or
functional regression. Nothing to revert. (mediamtx 30 fps config backed up on the Pi at
`~/mediamtx.yml.bak30fps`.)

---

## 6. Recommendations (not yet applied — need validation or larger changes)

1. **`model_complexity` 2 → 1 (Full)** is the single highest-leverage lever *when a subject
   is in frame*: in video-tracking mode the landmark model dominates and complexity 1 can
   roughly double FPS vs Heavy, with accuracy that is generally sufficient for joint angles.
   Validate with a person in frame + a quick angle-accuracy check before adopting. One-line,
   reversible (`config/config.py MEDIAPIPE.MODEL_COMPLEXITY`).
2. **Active cooling** (heatsink + fan): the Pi has already hit the soft thermal limit; a few
   °C of headroom prevents frequency capping under sustained sessions.
3. **Bigger structural win:** serve the browser WebRTC **directly from mediamtx**
   (`:8889/picam`, hardware path — no software decode/encode on the Pi) and draw the skeleton
   client-side on a canvas from the WS landmark data. Removes the entire software
   decode → JPEG re-encode chain (~0.4–0.5 core) from the dashboard process.
