from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from training.v5_imu_retraining.imu_generator import (
    IMU_COLUMNS,
    generate_bundle,
    ideal_signals,
    load_config,
    quantize_signals,
    regenerate_rows,
    smooth_trajectory,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_rows():
    return [
        {
            "Subject_ID": "synthetic-A", "Session_ID": f"S{exercise}",
            "Rep_ID": "1", "Rep_Phase": str(phase), "Exercise_ID": str(exercise),
            "Timestamp_ms": str(phase * 1300), "Angle_Trunk_Inclination": str(trunk),
            "Vis_L_Hip_X": "", "Class_Binary": str(phase % 2),
            "Error_Type_Major": "4", "Load_kg": "40", "Sensor_Location": "Lower_Back",
            **{name: ("" if phase == 2 else "999") for name in IMU_COLUMNS},
        }
        for exercise, trunks in [(0, [160, 135, 172]), (1, [108, 122, 173])]
        for phase, trunk in enumerate(trunks, 1)
    ]


class IMUGenerationTests(unittest.TestCase):
    def test_specific_force_and_angular_rate_obey_sensor_frame(self):
        euler = np.array([[0., 0., 0.], [0., np.pi / 2, 0.]])
        acceleration, gyro = ideal_signals(euler, np.zeros((2, 3)), np.zeros((2, 3)))
        np.testing.assert_allclose(acceleration[0], [0, 0, 9.80665], atol=1e-10)
        np.testing.assert_allclose(acceleration[1], [-9.80665, 0, 0], atol=1e-10)
        np.testing.assert_allclose(gyro, 0, atol=1e-10)
        np.testing.assert_allclose(np.linalg.norm(acceleration, axis=1), 9.80665)
        mount = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        _, rotating = ideal_signals(np.zeros((1, 3)), np.array([[0., 1., 0.]]),
                                   np.zeros((1, 3)), mount)
        np.testing.assert_allclose(rotating, [[1., 0., 0.]], atol=1e-10)

    def test_bend_and_return_has_signed_rate_and_smooth_endpoints(self):
        times = np.linspace(0, 2, 101)
        angle, rate, acceleration = smooth_trajectory(times, [0, 1, 2], [[0], [0.5], [0]])
        self.assertGreater(float(rate[:50].max()), 0)
        self.assertLess(float(rate[51:].min()), 0)
        np.testing.assert_allclose(rate[[0, 50, 100]], 0, atol=1e-10)
        np.testing.assert_allclose(acceleration[[0, 50, 100]], 0, atol=1e-10)
        self.assertAlmostEqual(float(angle[50, 0]), .5)

    def test_quantization_uses_actual_range_not_chip_maximum(self):
        config = load_config(ROOT / "config/imu_simulation.json")
        accel, gyro, saturation = quantize_signals(
            np.array([[100., -100., 0.]]), np.array([[20., -20., 0.]]), config
        )
        self.assertLess(float(np.abs(accel).max()), 20)
        self.assertLess(float(np.abs(gyro).max()), np.deg2rad(251))
        self.assertEqual(saturation, {"acceleration_axes": 2, "gyro_axes": 2})

    def test_regeneration_preserves_cells_missingness_and_ignores_labels(self):
        config = load_config(ROOT / "config/imu_simulation.json")
        source = fixture_rows()
        rows, report, _ = regenerate_rows(source, config)
        again, _, _ = regenerate_rows(source, config)
        self.assertEqual(rows, again)
        self.assertEqual(len(rows), len(source))
        self.assertEqual(report["protected_cells_changed"], 0)
        for old, new in zip(source, rows):
            self.assertEqual({k: v for k, v in old.items() if k not in IMU_COLUMNS},
                             {k: v for k, v in new.items() if k not in IMU_COLUMNS})
            for name in IMU_COLUMNS:
                if old[name] == "": self.assertEqual(new[name], "")
                else: self.assertNotEqual(new[name], "999")
        relabelled = [dict(row, Class_Binary="0", Error_Type_Major="0") for row in source]
        relabelled_rows, _, _ = regenerate_rows(relabelled, config)
        self.assertEqual([[row[c] for c in IMU_COLUMNS] for row in rows],
                         [[row[c] for c in IMU_COLUMNS] for row in relabelled_rows])

    def test_bundle_preserves_sources_and_refuses_overwrite(self):
        config = load_config(ROOT / "config/imu_simulation.json")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "baseline"
            source.mkdir()
            rows = fixture_rows()
            with (source / "master_dataset.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            for name in ["vision_data.csv", "subject_meta.csv"]:
                (source / name).write_bytes(b"synthetic_reference\r\nunchanged\r\n")
            before = {path.name: path.read_bytes() for path in source.iterdir()}
            output = directory / "candidate"
            report = generate_bundle(source, output, config)
            self.assertEqual(report["rows"], 6)
            self.assertEqual(report["repetitions"], 2)
            self.assertFalse(report["real_world_calibrated"])
            self.assertEqual({path.name: path.read_bytes() for path in source.iterdir()}, before)
            self.assertEqual((output / "vision_data.csv").read_bytes(), before["vision_data.csv"])
            manifest = json.loads((output / "DATASET_MANIFEST.json").read_text())
            self.assertEqual(manifest["provenance"], "synthetic_unvalidated_motion_model")
            with self.assertRaises(FileExistsError): generate_bundle(source, output, config)


if __name__ == "__main__":
    unittest.main()
