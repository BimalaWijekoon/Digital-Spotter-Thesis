#!/usr/bin/env python3
"""
scripts/benchmark_pipeline.py
Purpose: Reproducible performance benchmark for the Digital Spotter vision
         pipeline on the Raspberry Pi. Two modes:

           --mode pose    Isolated pose-pipeline benchmark. Reads the live RTSP
                          stream, runs decode -> resize -> cvtColor -> MediaPipe
                          at a given model_complexity, and reports effective FPS
                          and per-stage latency. Run with the dashboard STOPPED
                          so the numbers isolate the pose cost.

           --mode sysmon  Whole-system monitor. Samples aggregate CPU%, per-proc
                          CPU% (dashboard / mediamtx / mtxrpicam), RSS, CPU temp,
                          and throttle flags over a window. Run WITH the full
                          system up (dashboard + camera on + session active) to
                          capture real integrated load.

Outputs one JSON object to stdout (plus a human summary to stderr).
Author: bimalawijekoon
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE_KB = os.sysconf("SC_PAGE_SIZE") / 1024.0
FRAME_WAIT_TIMEOUT_S = 3.0
MAX_CONSECUTIVE_FRAME_TIMEOUTS = 3


# ── helpers ────────────────────────────────────────────────────────────────
def cpu_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return None


def throttled_flag():
    try:
        import subprocess
        out = subprocess.check_output(["vcgencmd", "get_throttled"], text=True).strip()
        # e.g. throttled=0x0 ; nonzero => throttling occurred
        val = out.split("=")[-1]
        return val
    except Exception:
        return "n/a"


def read_proc_stat_total():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = list(map(int, parts))
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    total = sum(vals)
    return total, idle


def find_pids():
    """Return {label: pid} for the running system processes of interest."""
    wanted = {}
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p / "comm").read_text().strip()
            cmd = (p / "cmdline").read_text().replace("\x00", " ")
        except Exception:
            continue
        if "run_server.py" in cmd:
            wanted["dashboard"] = int(p.name)
        elif comm == "mediamtx":
            wanted["mediamtx"] = int(p.name)
        elif comm == "mtxrpicam":
            wanted["mtxrpicam"] = int(p.name)
    return wanted


def proc_ticks(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().split()
        # fields[13]=utime fields[14]=stime (0-indexed after pid/comm handling;
        # standard positions 14/15 → indices 13/14)
        return int(fields[13]) + int(fields[14])
    except Exception:
        return None


def proc_rss_mb(pid):
    try:
        with open(f"/proc/{pid}/statm") as f:
            resident_pages = int(f.read().split()[1])
        return round(resident_pages * PAGE_KB / 1024.0, 1)
    except Exception:
        return None


# ── sysmon mode ────────────────────────────────────────────────────────────
def run_sysmon(seconds):
    pids = find_pids()
    t0_total, t0_idle = read_proc_stat_total()
    t0_proc = {k: proc_ticks(v) for k, v in pids.items()}
    t0 = time.time()
    time.sleep(seconds)
    elapsed = time.time() - t0
    t1_total, t1_idle = read_proc_stat_total()
    t1_proc = {k: proc_ticks(v) for k, v in pids.items()}

    dt_total = t1_total - t0_total
    dt_idle = t1_idle - t0_idle
    sys_cpu = round(100.0 * (dt_total - dt_idle) / dt_total, 1) if dt_total else None

    per_proc = {}
    for k, pid in pids.items():
        a, b = t0_proc.get(k), t1_proc.get(k)
        if a is None or b is None:
            continue
        cpu_pct = round(100.0 * (b - a) / (elapsed * CLK_TCK), 1)
        per_proc[k] = {"pid": pid, "cpu_pct": cpu_pct, "rss_mb": proc_rss_mb(pid)}

    try:
        load1 = round(os.getloadavg()[0], 2)
    except Exception:
        load1 = None

    result = {
        "mode": "sysmon",
        "window_s": round(elapsed, 1),
        "ncpu": os.cpu_count(),
        "system_cpu_pct": sys_cpu,          # 0-100 aggregate across all cores
        "load_avg_1m": load1,
        "cpu_temp_c": cpu_temp_c(),
        "throttled": throttled_flag(),
        "processes": per_proc,              # cpu_pct can exceed 100 (multi-core)
    }
    return result


# ── pose mode ──────────────────────────────────────────────────────────────
class LatestFrameReader:
    """Continuously drain a capture into a one-frame latest-only buffer."""

    def __init__(self, capture):
        self._capture = capture
        self._condition = threading.Condition()
        self._frame = None
        self._sequence = 0
        self._capture_ms = 0.0
        self._read_failures = 0
        self._running = False
        self._thread = None

    @property
    def is_opened(self):
        return self._capture.isOpened()

    @property
    def read_failures(self):
        with self._condition:
            return self._read_failures

    def start(self):
        if self._running or not self.is_opened:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._drain,
            daemon=True,
            name="BenchmarkLatestFrameReader",
        )
        self._thread.start()

    def _drain(self):
        while self._running:
            started = time.perf_counter()
            ok, frame = self._capture.read()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            with self._condition:
                if ok and frame is not None:
                    self._frame = frame
                    self._sequence += 1
                    self._capture_ms = elapsed_ms
                else:
                    self._read_failures += 1
                self._condition.notify_all()
            if not ok:
                time.sleep(0.02)

    def wait_after(self, sequence, timeout=FRAME_WAIT_TIMEOUT_S):
        """Return the newest frame after ``sequence`` or None on timeout."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._running and self._sequence <= sequence:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if self._frame is None or self._sequence <= sequence:
                return None
            return self._sequence, self._frame.copy(), self._capture_ms

    def stop(self):
        self._running = False
        self._capture.release()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None


def run_pose(complexity, width, frames, rtsp):
    # Match the app's RTSP decode flags for a fair decode-cost comparison.
    os.environ.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
    )
    os.environ["GLOG_minloglevel"] = "2"
    import cv2
    import mediapipe as mp

    pose = mp.solutions.pose.Pose(
        model_complexity=complexity,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        static_image_mode=False,
    )
    cap = cv2.VideoCapture(rtsp)
    reader = LatestFrameReader(cap)
    if not reader.is_opened:
        cap.release()
        pose.close()
        return {"mode": "pose", "error": "rtsp open failed"}
    reader.start()

    # Warm up the decoder and inference graph on fresh frames.
    last_sequence = 0
    for warmup_index in range(30):
        item = reader.wait_after(last_sequence)
        if item is None:
            reader.stop()
            pose.close()
            return {
                "mode": "pose",
                "error": "stream stalled during warmup",
                "warmup_frames": warmup_index,
                "read_failures": reader.read_failures,
            }
        last_sequence, frame, _ = item
        if warmup_index >= 25:
            if width and frame.shape[1] != width:
                height = int(frame.shape[0] * width / frame.shape[1])
                frame = cv2.resize(frame, (width, height))
            pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    t_read, t_prep, t_pose = [], [], []
    src_wh = None
    valid = 0
    self_pid = os.getpid()
    ticks0 = proc_ticks(self_pid)
    wall0 = time.perf_counter()

    n = 0
    dropped = 0
    consecutive_timeouts = 0
    try:
        while n < frames:
            item = reader.wait_after(last_sequence)
            if item is None:
                consecutive_timeouts += 1
                if consecutive_timeouts >= MAX_CONSECUTIVE_FRAME_TIMEOUTS:
                    return {
                        "mode": "pose",
                        "error": "stream stalled during benchmark",
                        "frames": n,
                        "read_failures": reader.read_failures,
                    }
                continue
            consecutive_timeouts = 0
            sequence, frame, capture_ms = item
            dropped += max(0, sequence - last_sequence - 1)
            last_sequence = sequence

            prep_started = time.perf_counter()
            if src_wh is None:
                src_wh = (frame.shape[1], frame.shape[0])
            if width and frame.shape[1] != width:
                h = int(frame.shape[0] * width / frame.shape[1])
                frame = cv2.resize(frame, (width, h))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_started = time.perf_counter()
            res = pose.process(rgb)
            finished = time.perf_counter()
            if res.pose_landmarks is not None:
                valid += 1
            t_read.append(capture_ms)
            t_prep.append((pose_started - prep_started) * 1000)
            t_pose.append((finished - pose_started) * 1000)
            n += 1
    finally:
        reader.stop()
        pose.close()

    wall = time.perf_counter() - wall0
    ticks1 = proc_ticks(self_pid)

    def stats(xs):
        xs = sorted(xs)
        k = len(xs)
        return {
            "mean_ms": round(sum(xs) / k, 1),
            "median_ms": round(xs[k // 2], 1),
            "p95_ms": round(xs[int(k * 0.95)], 1),
        }

    result = {
        "mode": "pose",
        "complexity": complexity,
        "proc_width": width or (src_wh[0] if src_wh else None),
        "source_res": f"{src_wh[0]}x{src_wh[1]}" if src_wh else None,
        "frames": n,
        "source_frames_dropped": dropped,
        "read_failures": reader.read_failures,
        "effective_fps": round(n / wall, 2),
        "self_cpu_pct": round(100.0 * (ticks1 - ticks0) / (wall * CLK_TCK), 1),
        "valid_pct": round(100.0 * valid / n, 1) if n else 0,
        "read_decode": stats(t_read),
        "resize_cvt": stats(t_prep),
        "pose_infer": stats(t_pose),
        "cpu_temp_c": cpu_temp_c(),
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pose", "sysmon"], required=True)
    ap.add_argument("--complexity", type=int, default=2)
    ap.add_argument("--width", type=int, default=0, help="resize width for pose (0=native)")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--seconds", type=int, default=12)
    ap.add_argument("--rtsp", default="rtsp://127.0.0.1:8554/picam")
    args = ap.parse_args()

    if args.mode == "pose":
        r = run_pose(args.complexity, args.width, args.frames, args.rtsp)
    else:
        r = run_sysmon(args.seconds)

    if r is not None:
        print(json.dumps(r))
        print(json.dumps(r, indent=2), file=sys.stderr)
    return 2 if r is None or r.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
