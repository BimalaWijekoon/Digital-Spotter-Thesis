"""
tests/test_01_config/test_config_layer.py
Purpose: Test Config and Constants immutability and values.
Author: bimalawijekoon
Version: 1.0.0
"""
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config, load_environment
from config.constants import (
    JOINT_NAMES, MEDIAPIPE_LANDMARKS, REP_PHASES,
    WEBSOCKET_EVENTS, TOTAL_FEATURES,
)


class TestConfig:
    def test_version_exists(self):
        assert hasattr(Config, 'VERSION')
        assert Config.VERSION == "1.0.0"

    def test_paths_exist(self):
        assert hasattr(Config.PATHS, 'BASE_DIR')
        assert hasattr(Config.PATHS, 'DATABASE')

    def test_api_defaults(self):
        assert Config.API.PORT == 8000
        assert Config.API.HOST == "0.0.0.0"

    def test_camera_settings(self):
        assert Config.CAMERA.FPS == 30
        assert Config.CAMERA.WIDTH == 1280
        assert Config.CAMERA.HEIGHT == 720

    def test_pi_rgb_defaults_match_observed_wiring(self):
        env = os.environ.copy()
        for key in ("DS_RGB_PIN_R", "DS_RGB_PIN_G", "DS_RGB_PIN_B"):
            env.pop(key, None)
        result = subprocess.run(
            [sys.executable, "-c", (
                "from config.config import Config; "
                "print(Config.RGB_LED.PIN_R, Config.RGB_LED.PIN_G, Config.RGB_LED.PIN_B)"
            )],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "27 17 22"

    def test_inference_settings(self):
        assert Config.INFERENCE.NUM_FEATURES == 40
        assert Config.INFERENCE.SEQUENCE_LENGTH == 3

    def test_exercise_name_lookup(self):
        assert Config.EXERCISES.get_name(0) == "Barbell Back Squat"
        assert Config.EXERCISES.get_name(1) == "Conventional Deadlift"

    def test_environment_file_never_overrides_process_values(
        self, monkeypatch, tmp_path
    ):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DS_TEST_FROM_FILE=file-value\n"
            "DS_TEST_PROCESS_WINS=file-value\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("DS_TEST_FROM_FILE", raising=False)
        monkeypatch.setenv("DS_TEST_PROCESS_WINS", "process-value")

        assert load_environment(env_file) is True
        assert os.environ["DS_TEST_FROM_FILE"] == "file-value"
        assert os.environ["DS_TEST_PROCESS_WINS"] == "process-value"

    def test_explicit_launcher_environment_is_evaluated_before_config(self):
        env = os.environ.copy()
        env.update(
            DS_API_HOST="127.0.0.1",
            DS_API_PORT="8124",
            DS_BUZZER_ENABLED="false",
            DS_RGB_ENABLED="false",
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from config.config import Config; "
                    "print(Config.API.HOST, Config.API.PORT, "
                    "Config.BUZZER.ENABLED, Config.RGB_LED.ENABLED)"
                ),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "127.0.0.1 8124 False False"


class TestConstants:
    def test_joint_names_7(self):
        assert len(JOINT_NAMES) == 7

    def test_mediapipe_landmarks(self):
        assert "LEFT_HIP" in MEDIAPIPE_LANDMARKS
        assert MEDIAPIPE_LANDMARKS["LEFT_HIP"] == 23

    def test_rep_phases(self):
        assert len(REP_PHASES) == 3
        assert REP_PHASES[1] == "Eccentric/Descent"

    def test_websocket_events(self):
        assert "POSE_DATA" in WEBSOCKET_EVENTS
        assert WEBSOCKET_EVENTS["POSE_DATA"] == "pose_data"

    def test_total_features(self):
        assert TOTAL_FEATURES == 40
