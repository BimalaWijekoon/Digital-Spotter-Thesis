"""IMU-only, physically coupled synthetic research data; never a hardware oracle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parent
IMU_COLUMNS = (
    "IMU_Acc_X", "IMU_Acc_Y", "IMU_Acc_Z",
    "IMU_Gyro_X", "IMU_Gyro_Y", "IMU_Gyro_Z",
)
GRAVITY = 9.80665


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    for name, expected in {
        "sample_hz": 50, "gravity_m_s2": GRAVITY, "accel_range_g": 2,
        "gyro_range_dps": 250, "accel_lsb_per_g": 16384, "gyro_lsb_per_dps": 131,
        "phase_fractions": [0., .35, .45, 1.],
    }.items():
        if config.get(name) != expected:
            raise ValueError(f"Unsupported R1 sensor/phase contract: {name}")
    if not isinstance(config.get("seed"), int):
        raise ValueError("An integer random seed is required")
    for name in (
        "rep_duration_s", "pose_rate_hz", "squat_sensor_vertical_travel_m",
        "deadlift_sensor_vertical_travel_m", "sensor_horizontal_travel_m",
        "trunk_to_sensor_pitch_factor",
    ):
        pair = config[name]
        if (len(pair) != 2 or not all(math.isfinite(x) for x in pair)
                or pair[0] <= 0 or pair[1] < pair[0]):
            raise ValueError("Invalid simulation prior: " + name)
    for name in (
        "mount_max_angle_deg", "cross_plane_max_angle_deg", "accel_bias_max_m_s2",
        "gyro_bias_max_rad_s", "accel_noise_std_m_s2", "gyro_noise_std_rad_s",
        "gyro_rep_drift_max_rad_s",
    ):
        if not math.isfinite(config[name]) or config[name] < 0:
            raise ValueError("Invalid simulation prior: " + name)
    if config["pose_rate_hz"][0] < 4 or config["rep_duration_s"][0] < 1.5:
        raise ValueError("Insufficient pose samples for three phase summaries")
    for exercise in ("0", "1"):
        angles = config["fallback_trunk_inclination_deg"][exercise]
        if len(angles) != 3 or not all(math.isfinite(x) and 0 <= x <= 180 for x in angles):
            raise ValueError("Invalid fallback trunk angles")
    return config


def smooth_trajectory(
    times: np.ndarray, knots: Sequence[float], values: Sequence[Sequence[float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Piecewise C2 quintic interpolation and its analytic first/second derivatives."""
    knots = np.asarray(knots, dtype=float)
    values = np.asarray(values, dtype=float)
    times = np.asarray(times, dtype=float)
    if (len(knots) < 2 or values.ndim != 2 or len(values) != len(knots)
            or np.any(np.diff(knots) <= 0) or np.any(times < knots[0])
            or np.any(times > knots[-1]) or not np.isfinite(values).all()):
        raise ValueError("Invalid smooth-trajectory knots, values or times")
    segment = np.clip(np.searchsorted(knots, times, side="right") - 1, 0, len(knots) - 2)
    duration = (knots[segment + 1] - knots[segment])[:, None]
    u = ((times - knots[segment])[:, None] / duration).clip(0, 1)
    delta = values[segment + 1] - values[segment]
    position = values[segment] + delta * (10*u**3 - 15*u**4 + 6*u**5)
    velocity = delta * (30*u**2 - 60*u**3 + 30*u**4) / duration
    acceleration = delta * (60*u - 180*u**2 + 120*u**3) / duration**2
    return position, velocity, acceleration


def rotation_matrices(euler: np.ndarray) -> np.ndarray:
    """Right-handed sensor/body-to-world Rz(yaw) Ry(pitch) Rx(roll)."""
    roll, pitch, yaw = np.asarray(euler, dtype=float).T
    sr, cr = np.sin(roll), np.cos(roll)
    sp, cp = np.sin(pitch), np.cos(pitch)
    sy, cy = np.sin(yaw), np.cos(yaw)
    return np.stack((
        cp*cy, sr*sp*cy-cr*sy, cr*sp*cy+sr*sy,
        cp*sy, sr*sp*sy+cr*cy, cr*sp*sy-sr*cy,
        -sp, sr*cp, cr*cp,
    ), axis=1).reshape(-1, 3, 3)


def ideal_signals(
    euler: np.ndarray, euler_rates: np.ndarray, world_acceleration: np.ndarray,
    mount: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Specific force and body angular velocity, consistently mapped to the sensor."""
    euler = np.asarray(euler, dtype=float)
    rates = np.asarray(euler_rates, dtype=float)
    world_acceleration = np.asarray(world_acceleration, dtype=float)
    if (euler.ndim != 2 or euler.shape[1] != 3 or rates.shape != euler.shape
            or world_acceleration.shape != euler.shape
            or not all(np.isfinite(x).all() for x in (euler, rates, world_acceleration))):
        raise ValueError("Signals must have finite matching (N,3) shapes")
    mount = np.eye(3) if mount is None else np.asarray(mount, dtype=float)
    if (mount.shape != (3, 3) or not np.allclose(mount.T @ mount, np.eye(3), atol=1e-8)
            or not np.isclose(np.linalg.det(mount), 1.)):
        raise ValueError("Mount must be a proper rotation, not an axis reflection")
    sensor_to_world = rotation_matrices(euler) @ mount
    specific_world = world_acceleration - np.array([0, 0, -GRAVITY])
    acceleration = np.einsum("nji,nj->ni", sensor_to_world, specific_world)
    roll, pitch, _ = euler.T
    roll_dot, pitch_dot, yaw_dot = rates.T
    omega_body = np.column_stack((
        roll_dot - yaw_dot*np.sin(pitch),
        pitch_dot*np.cos(roll) + yaw_dot*np.sin(roll)*np.cos(pitch),
        -pitch_dot*np.sin(roll) + yaw_dot*np.cos(roll)*np.cos(pitch),
    ))
    return acceleration, omega_body @ mount


def quantize_signals(
    acceleration: np.ndarray, gyro: np.ndarray, config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    accel_raw = np.rint(acceleration / config["gravity_m_s2"] * config["accel_lsb_per_g"])
    gyro_raw = np.rint(np.rad2deg(gyro) * config["gyro_lsb_per_dps"])
    if not np.isfinite(accel_raw).all() or not np.isfinite(gyro_raw).all():
        raise ValueError("Non-finite simulated measurement")
    saturation = {
        "acceleration_axes": int(np.count_nonzero((accel_raw < -32768) | (accel_raw > 32767))),
        "gyro_axes": int(np.count_nonzero((gyro_raw < -32768) | (gyro_raw > 32767))),
    }
    acceleration = np.clip(accel_raw, -32768, 32767) / config["accel_lsb_per_g"] * GRAVITY
    gyro = np.deg2rad(np.clip(gyro_raw, -32768, 32767) / config["gyro_lsb_per_dps"])
    return acceleration, gyro, saturation


def _rng(seed: int, *keys: str) -> np.random.Generator:
    payload = json.dumps([seed, *keys], ensure_ascii=True).encode("utf-8")
    return np.random.default_rng(int.from_bytes(hashlib.sha256(payload).digest()[:8], "little"))


def _number(value: str) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _simulate_rep(rows: list[dict[str, str]], config: dict[str, Any]) -> dict[str, Any]:
    """Use only exercise, trunk summaries and IDs; no target/error-conditioned means."""
    first = rows[0]
    exercise = int(first["Exercise_ID"])
    session_rng = _rng(config["seed"], first["Subject_ID"], first["Session_ID"], "session")
    rng = _rng(config["seed"], first["Subject_ID"], first["Session_ID"], first["Rep_ID"], "rep")
    mount_angles = np.deg2rad(session_rng.uniform(
        -config["mount_max_angle_deg"], config["mount_max_angle_deg"], size=3
    ))
    mount = rotation_matrices(mount_angles[None, :])[0]
    accel_bias = session_rng.uniform(-config["accel_bias_max_m_s2"], config["accel_bias_max_m_s2"], 3)
    gyro_bias = session_rng.uniform(-config["gyro_bias_max_rad_s"], config["gyro_bias_max_rad_s"], 3)
    duration = round(rng.uniform(*config["rep_duration_s"]) * config["sample_hz"]) / config["sample_hz"]
    times = np.arange(round(duration * config["sample_hz"]) + 1) / config["sample_hz"]
    pose_hz = rng.uniform(*config["pose_rate_hz"])
    pose_times = np.arange(0, duration, 1 / pose_hz)
    edges = [0, int(len(pose_times)*.35), int(len(pose_times)*.45), len(pose_times)]
    if not all(a < b for a, b in zip(edges, edges[1:])):
        raise ValueError("A simulated phase has no pose samples")
    trunks = np.array([_number(row["Angle_Trunk_Inclination"]) for row in rows], dtype=float)
    valid = np.isfinite(trunks)
    missing = int(np.count_nonzero(~valid))
    if valid.any():
        trunks = np.interp(np.arange(3), np.flatnonzero(valid), trunks[valid])
    else:
        trunks = np.array(config["fallback_trunk_inclination_deg"][str(exercise)])
    raw_bend = 180 - trunks
    clipped = int(np.count_nonzero((raw_bend < 0) | (raw_bend > 100)))
    bends = np.deg2rad(raw_bend.clip(0, 100)) * rng.uniform(*config["trunk_to_sensor_pitch_factor"])
    knots = np.array([0., .175, .4, .725, 1.]) * duration
    cross = np.deg2rad(rng.uniform(-config["cross_plane_max_angle_deg"], config["cross_plane_max_angle_deg"], (5, 2)))
    cross[[0, -1]] = 0
    pitch = np.array([bends[2], *bends, bends[2]]) if exercise == 0 else np.array([bends[0], *bends, bends[2]])
    euler_knots = np.column_stack((cross[:, 0], pitch, cross[:, 1]))
    euler, rates, _ = smooth_trajectory(times, knots, euler_knots)
    vertical = rng.uniform(*config["squat_sensor_vertical_travel_m" if exercise == 0 else "deadlift_sensor_vertical_travel_m"])
    horizontal = rng.uniform(*config["sensor_horizontal_travel_m"])
    z = np.array([0., -.55, -1., -.10, 0.]) if exercise == 0 else np.array([-1., -1., -.5, 0., 0.])
    x = np.array([0., .55, 1., .10, 0.]) if exercise == 0 else np.array([1., 1., .5, 0., 0.])
    positions, _, world_accel = smooth_trajectory(times, knots, np.column_stack((x*horizontal, np.zeros(5), z*vertical)))
    acceleration, gyro = ideal_signals(euler, rates, world_accel, mount)
    acceleration += accel_bias + rng.normal(0, config["accel_noise_std_m_s2"], acceleration.shape)
    drift = rng.uniform(-config["gyro_rep_drift_max_rad_s"], config["gyro_rep_drift_max_rad_s"], 3)
    gyro += gyro_bias + times[:, None]/duration*drift + rng.normal(0, config["gyro_noise_std_rad_s"], gyro.shape)
    acceleration, gyro, saturation = quantize_signals(acceleration, gyro, config)
    channels = np.column_stack((acceleration, gyro))
    associated = np.column_stack([np.interp(pose_times, times, channels[:, axis]) for axis in range(6)])
    summaries = np.array([np.median(associated[a:b], axis=0) for a, b in zip(edges, edges[1:])])
    return {
        "times_s": times, "channels": channels, "positions_m": positions,
        "euler_rad": euler, "pose_times_s": pose_times, "phase_edges": edges,
        "summaries": summaries, "saturation": saturation,
        "missing_trunk_values": missing, "clipped_bend_values": clipped,
    }


def regenerate_rows(
    source: list[dict[str, str]], config: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    if not source or any(column not in source[0] for column in IMU_COLUMNS):
        raise ValueError("Non-empty phase dataset with six IMU channels required")
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(source):
        groups[(row["Subject_ID"], row["Session_ID"], row["Rep_ID"])].append(index)
    output = [row.copy() for row in source]
    report: dict[str, Any] = {
        "rows": len(source), "repetitions": len(groups), "protected_cells_changed": 0,
        "real_world_calibrated": False, "synthetic_samples": 0,
        "acceleration_saturated_axes": 0, "gyro_saturated_axes": 0,
        "missing_trunk_values": 0, "clipped_bend_values": 0,
        "missing_imu_cells_preserved": 0, "repetitions_with_phase_label_disagreement": 0,
    }
    phase_manifest: list[dict[str, Any]] = []
    example: dict[str, Any] | None = None
    for indices in groups.values():
        indices = sorted(indices, key=lambda i: int(source[i]["Rep_Phase"]))
        rows = [source[index] for index in indices]
        if ([int(row["Rep_Phase"]) for row in rows] != [1, 2, 3]
                or len({row["Exercise_ID"] for row in rows}) != 1
                or int(rows[0]["Exercise_ID"]) not in (0, 1)):
            raise ValueError("Each supported repetition requires exactly phases [1,2,3]")
        trace = _simulate_rep(rows, config)
        if example is None: example = trace
        report["synthetic_samples"] += len(trace["times_s"])
        report["acceleration_saturated_axes"] += trace["saturation"]["acceleration_axes"]
        report["gyro_saturated_axes"] += trace["saturation"]["gyro_axes"]
        report["missing_trunk_values"] += trace["missing_trunk_values"]
        report["clipped_bend_values"] += trace["clipped_bend_values"]
        report["repetitions_with_phase_label_disagreement"] += int(len({row.get("Class_Binary") for row in rows}) > 1)
        for phase, index in enumerate(indices):
            row = output[index]
            for axis, name in enumerate(IMU_COLUMNS):
                if _number(source[index][name]) is None:
                    report["missing_imu_cells_preserved"] += 1
                else:
                    row[name] = format(float(trace["summaries"][phase, axis]), ".10g")
            if "IMU_Acc_Magnitude" in row:
                acc = [_number(row[name]) for name in IMU_COLUMNS[:3]]
                row["IMU_Acc_Magnitude"] = "" if None in acc else format(math.sqrt(sum(x*x for x in acc)), ".10g")
            begin, end = trace["phase_edges"][phase:phase+2]
            phase_manifest.append({
                **{name: row[name] for name in ("Subject_ID", "Session_ID", "Rep_ID", "Rep_Phase")},
                "simulated_first_pose_s": float(trace["pose_times_s"][begin]),
                "simulated_last_pose_s": float(trace["pose_times_s"][end-1]),
                "pose_samples": end-begin,
                "reducer": "median_of_imu_interpolated_at_pose_times",
            })
    mutable = set(IMU_COLUMNS) | {"IMU_Acc_Magnitude"}
    report["protected_cells_changed"] = sum(
        old[name] != new[name] for old, new in zip(source, output) for name in old if name not in mutable
    )
    if report["protected_cells_changed"]:
        raise ValueError("Protected source cells changed")
    return output, report, {"example_trace": example, "phase_manifest": phase_manifest}


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_bundle(source_dir: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    source_dir, output_dir = source_dir.resolve(), output_dir.resolve()
    if output_dir.exists(): raise FileExistsError("Refusing to overwrite: " + str(output_dir))
    if source_dir in output_dir.parents or output_dir in source_dir.parents:
        raise ValueError("Source and generated output must not overlap")
    names = ["master_dataset.csv", "vision_data.csv", "subject_meta.csv"]
    source_hashes = {name: file_hash(source_dir/name) for name in names}
    with (source_dir/"master_dataset.csv").open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        source = list(reader)
    rows, report, details = regenerate_rows(source, config)
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir/"master_dataset.csv", columns, rows)
    for name in ["vision_data.csv", "subject_meta.csv"]:
        shutil.copyfile(source_dir/name, output_dir/name)
    phase_columns = ["Subject_ID", "Session_ID", "Rep_ID", "Rep_Phase", "Exercise_ID", "Timestamp_ms", *IMU_COLUMNS]
    _write_csv(output_dir/"imu_data.csv", phase_columns, [{name: row[name] for name in phase_columns} for row in rows])
    phases = details["phase_manifest"]
    _write_csv(output_dir/"phase_manifest.csv", list(phases[0]), phases)
    example = details["example_trace"]
    trace_rows = [dict(relative_time_s=float(t), **dict(zip(IMU_COLUMNS, map(float, values))))
                  for t, values in zip(example["times_s"], example["channels"])]
    _write_csv(output_dir/"example_trace_50hz.csv", ["relative_time_s", *IMU_COLUMNS], trace_rows)
    (output_dir/"imu_simulation.json").write_text(json.dumps(config, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    copied_spec = output_dir/"IMU_GENERATION_SPEC.md"
    shutil.copyfile(ROOT/"docs/IMU_GENERATION_SPEC.md", copied_spec)
    if source_hashes != {name: file_hash(source_dir/name) for name in names}:
        raise RuntimeError("Source changed during generation; do not use this output")
    if any(file_hash(output_dir/name) != source_hashes[name] for name in ["vision_data.csv", "subject_meta.csv"]):
        raise RuntimeError("Protected CSV copy differs")
    report["provenance"] = "synthetic_unvalidated_motion_model"
    report["version"] = config["version"]
    report["source_sha256"] = source_hashes
    report["config"] = config
    report["generator_sha256"] = file_hash(Path(__file__))
    report["specification_sha256"] = file_hash(copied_spec)
    report["software"] = {"python": platform.python_version(), "numpy": np.__version__}
    report["units"] = {"acceleration": "m/s² (specific force)", "gyro": "rad/s"}
    report["sensor_frame_status"] = "assumed; physical PCB-to-body transform not verified"
    report["deployment_ready"] = False
    report["outputs"] = {path.name: {"sha256": file_hash(path), "size_bytes": path.stat().st_size}
                         for path in sorted(output_dir.iterdir()) if path.is_file()}
    report["limitations"] = [
        "Unmeasured motion/noise/mounting priors; not a real-world calibrated dataset",
        "Trunk angle is only an approximate sensor-pitch constraint, not pelvis reconstruction",
        "Vision and inherited labels are preserved, not independently validated",
        "Synthetic phase timing is not historical or measured camera/IMU synchronization",
        "Real mounted evaluation and runtime compatibility are still pending",
    ]
    (output_dir/"DATASET_MANIFEST.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"config/imu_simulation.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/"data/generated").resolve()):
        parser.error("Output must be a new directory under this workspace's data/generated")
    report = generate_bundle(ROOT/"reference/dataset", output, load_config(args.config))
    print(json.dumps({name: report[name] for name in (
        "version", "rows", "repetitions", "synthetic_samples", "protected_cells_changed",
        "missing_imu_cells_preserved", "acceleration_saturated_axes", "gyro_saturated_axes",
        "real_world_calibrated", "deployment_ready",
    )}, indent=2))
    print("Generated candidate:", output)


if __name__ == "__main__":
    main()
