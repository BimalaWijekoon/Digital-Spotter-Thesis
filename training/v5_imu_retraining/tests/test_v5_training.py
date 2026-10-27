from __future__ import annotations

import json
import unittest

import numpy as np

from training.v5_imu_retraining.v5_training import (
    FEATURES, Preprocessor, apply_calibration, choose_threshold,
    cross_calibrate, grouped_folds, monitor_split, phase_features,
)


class V5TrainingTests(unittest.TestCase):
    def test_exact_features_and_engineered_formulas(self):
        self.assertEqual(len(FEATURES), 29)
        row = {name: "1" for name in FEATURES}
        row.update(Angle_Hip_Flexion_L="40", Angle_Hip_Flexion_R="20",
                   Angle_Knee_Flexion_L="80", Angle_Knee_Flexion_R="30",
                   Angle_Ankle_Dorsiflexion_L="10", Angle_Ankle_Dorsiflexion_R="8",
                   IMU_Acc_X="3", IMU_Acc_Y="4", IMU_Acc_Z="0")
        result = dict(zip(FEATURES, phase_features(row)))
        self.assertAlmostEqual(result["IMU_Acc_Magnitude"], 5)
        self.assertAlmostEqual(result["Knee_Hip_Coupling_L"], 80 / (40 + 1e-6))
        self.assertEqual(result["Hip_Flexion_Asymmetry"], 20)
        self.assertEqual(result["Knee_Flexion_Asymmetry"], 50)
        self.assertEqual(result["Ankle_Dorsiflexion_Asymmetry"], 2)
        self.assertFalse(any("Bar" in name or "Jerk" in name for name in FEATURES))

    def test_train_only_preprocessing_is_frozen_and_serializable(self):
        x = np.arange(12*3*29, dtype=float).reshape(12, 3, 29)
        c = np.column_stack((np.arange(12) % 2, np.arange(12) * 5))
        x[0, 1, 0] = np.nan
        processor = Preprocessor().fit(x, c)
        before = json.dumps(processor.state, sort_keys=True)
        a, b = processor.transform(x, c)
        np.testing.assert_allclose(a.mean(axis=(0, 1)), 0, atol=1e-6)
        self.assertEqual(a.shape, (12, 3, 29))
        self.assertEqual(b.shape, (12, 2))
        validation = np.full((2, 3, 29), 1e9)
        validation[0, 1, 0] = np.nan
        z, _ = processor.transform(validation, c[:2])
        self.assertGreater(float(z[1, 0, 0]), 1e4)
        self.assertTrue(np.isfinite(z).all())
        self.assertEqual(before, json.dumps(processor.state, sort_keys=True))
        restored = Preprocessor.from_state(json.loads(before))
        np.testing.assert_array_equal(restored.transform(x, c)[0], a)

    def test_original_nested_grouped_folds_never_share_identities(self):
        groups = np.repeat([f"synthetic-{i}" for i in range(25)], 4)
        labels = np.tile([0, 0, 1, 1], 25)
        coverage = np.zeros(len(labels), dtype=int)
        folds = grouped_folds(labels, groups)
        self.assertEqual(len(folds), 5)
        for development, test, inner in folds:
            self.assertFalse(set(groups[development]) & set(groups[test]))
            coverage[test] += 1
            self.assertEqual(len(inner), 4)
            validated = []
            for train, validation in inner:
                self.assertFalse(set(groups[train]) & set(groups[validation]))
                self.assertFalse(set(train) & set(test))
                self.assertFalse(set(validation) & set(test))
                validated.extend(validation)
            self.assertEqual(sorted(validated), sorted(development))
        np.testing.assert_array_equal(coverage, 1)

    def test_cross_fitted_calibration_and_threshold_contract(self):
        y = np.tile([0, 1], 16)
        raw = np.tile([.2, .8], 16)
        ids = np.repeat([f"g{i}" for i in range(8)], 4)
        fold = np.repeat(np.arange(4), 8)
        result = cross_calibrate(y, raw, fold, ids)
        self.assertEqual(result["subject_overlap"], 0)
        self.assertTrue(np.isfinite(result["decision_probability"]).all())
        self.assertEqual(choose_threshold(np.array([0, 1]), np.array([.2, .8])), .8)
        predicted = apply_calibration(raw, result["deployment_policy"])
        self.assertTrue(((0 <= predicted) & (predicted <= 1)).all())

    def test_early_stopping_monitor_is_separate_from_validation(self):
        groups = np.repeat([f"synthetic-{i}" for i in range(25)], 4)
        labels = np.tile([0, 0, 1, 1], 25)
        exercises = np.tile([0, 1, 0, 1], 25)
        development, test, inner = grouped_folds(labels, groups)[0]
        train, validation = inner[0]
        fit, monitor, seed = monitor_split(train, labels, groups, exercises, 0, 0)
        self.assertEqual(len(set(groups[fit])), 12)
        self.assertEqual(len(set(groups[monitor])), 3)
        self.assertFalse(set(groups[fit]) & set(groups[monitor]))
        self.assertFalse(set(groups[monitor]) & set(groups[validation]))
        self.assertFalse(set(groups[monitor]) & set(groups[test]))
        self.assertEqual(set(fit) | set(monitor), set(train))
        self.assertEqual(seed, 42)


if __name__ == "__main__":
    unittest.main()
