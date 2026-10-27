"""
config/config.py
Purpose: Master configuration — all settings in one place.
         All other modules import from here. Zero hardcoded values anywhere else.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_environment(path: Path = ENV_PATH) -> bool:
    """Load project defaults without overriding process-level configuration.

    Explicit systemd/container/shell environment values always take precedence.
    The small fallback keeps the Pi migration runtime usable if python-dotenv is
    absent; M1 dependency locking will make the normal parser mandatory.
    """
    if not path.is_file():
        return False

    try:
        from dotenv import load_dotenv
    except ImportError:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.partition("=")[::2]
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)
    else:
        load_dotenv(path, override=False)
    return True


ENV_FILE_LOADED = load_environment()


class _Camera:
    """Camera hardware configuration for IMX219 module."""
    WIDTH = 1280
    HEIGHT = 720
    FPS = 30
    SENSOR = "imx219"


class _Stream:
    """mediamtx WebRTC/RTSP streaming configuration."""
    MEDIAMTX_HOST = os.getenv("DS_STREAM_HOST", "192.168.1.8")
    WEBRTC_PORT = int(os.getenv("DS_WEBRTC_PORT", "8889"))
    RTSP_PORT = int(os.getenv("DS_RTSP_PORT", "8554"))
    STREAM_PATH = "picam"


class _API:
    """FastAPI migration-server configuration."""
    HOST = os.getenv("DS_API_HOST", "0.0.0.0")
    PORT = int(os.getenv("DS_API_PORT", "8000"))
    DEBUG = os.getenv("DS_DEBUG", "false").lower() == "true"
    SECRET_KEY = os.getenv(
        "DS_SECRET_KEY", "digital-spotter-dev-key-change-in-prod"
    )


class _Frontend:
    """Frontend static file server configuration."""
    HOST = os.getenv("DS_FRONTEND_HOST", "0.0.0.0")
    PORT = int(os.getenv("DS_FRONTEND_PORT", "8080"))
    STATIC_DIR = "frontend"


class _Paths:
    """All filesystem paths used by the application.
    Uses pathlib.Path for cross-platform compatibility.
    """
    ROOT = PROJECT_ROOT
    BASE_DIR = ROOT
    MODELS_DIR = ROOT / "models"
    LOGS_DIR = ROOT / "logs"
    DATA_DIR = ROOT / "data"
    FRONTEND_DIR = ROOT / "frontend"
    MODEL_TFLITE = MODELS_DIR / "model_quantized.tflite"
    MODEL_FULLPREC = MODELS_DIR / "model_fullprec.tflite"
    SCALER_PKL = MODELS_DIR / "scaler.save"
    WINSOR_BOUNDS = MODELS_DIR / "winsor_bounds.save"
    FEATURE_MEDIANS = MODELS_DIR / "feature_medians.save"
    DEPLOYMENT_CONFIG = MODELS_DIR / "deployment_config.save"
    DATABASE = DATA_DIR / "sessions.db"
    SCHEMA_SQL = ROOT / "database" / "schema.sql"


class _MediaPipe:
    """MediaPipe BlazePose model configuration."""
    MODEL_COMPLEXITY = 2  # Heavy model
    MIN_DETECTION_CONFIDENCE = 0.7
    MIN_TRACKING_CONFIDENCE = 0.7
    VISIBILITY_THRESHOLD = 0.15


class _Inference:
    """LSTM inference pipeline configuration."""
    from config.constants import TOTAL_FEATURES, SEQUENCE_LENGTH_RAW, SEQUENCE_LENGTH_MODEL
    SEQUENCE_LENGTH = SEQUENCE_LENGTH_RAW       # 3 — phases pushed into buffer
    SEQUENCE_LENGTH_MODEL = SEQUENCE_LENGTH_MODEL  # 4 — what actually goes into the model
    NUM_FEATURES = TOTAL_FEATURES               # 40
    DECISION_THRESHOLD = 0.359                  # from deployment_config.save['threshold'], NOT 0.5
    BAD_FORM_LABEL = "Bad Form"
    GOOD_FORM_LABEL = "Good Form"


class _RepSegmentation:
    """Rep segmentation algorithm parameters."""
    SAVITZKY_GOLAY_WINDOW_RATIO = 0.4
    POLYNOMIAL_ORDER = 2
    PROMINENCE_THRESHOLD = 15
    MIN_INTER_PEAK_RATIO = 1.2
    PHASE_BOUNDARIES = [0.35, 0.45]


class _Exercises:
    """Supported exercise types."""
    SQUAT = {"id": 0, "name": "Barbell Back Squat"}
    DEADLIFT = {"id": 1, "name": "Conventional Deadlift"}

    @classmethod
    def get_by_id(cls, exercise_id):
        """Get exercise dict by its numeric ID.

        Args:
            exercise_id: Integer exercise identifier (0=Squat, 1=Deadlift).

        Returns:
            dict with 'id' and 'name' keys, or None if not found.
        """
        for attr in [cls.SQUAT, cls.DEADLIFT]:
            if attr["id"] == exercise_id:
                return attr
        return None

    @classmethod
    def get_name(cls, exercise_id):
        """Get exercise name by its numeric ID.

        Args:
            exercise_id: Integer exercise identifier.

        Returns:
            Exercise name string, or 'Unknown' if not found.
        """
        ex = cls.get_by_id(exercise_id)
        return ex["name"] if ex else "Unknown"


class _IMU:
    """IMU configuration."""
    BLE_ADDRESS = os.getenv("DS_BLE_ADDRESS", "00:11:22:33:44:55")
    SAMPLE_RATE_HZ = int(os.getenv("DS_IMU_SAMPLE_RATE", "50"))


class _MQTT:
    """MQTT configuration for HiveMQ Cloud (TLS)."""
    BROKER   = os.getenv("DS_MQTT_BROKER",   "localhost")
    PORT     = int(os.getenv("DS_MQTT_PORT",  "8883"))
    USERNAME = os.getenv("DS_MQTT_USERNAME",  "")
    PASSWORD = os.getenv("DS_MQTT_PASSWORD",  "")
    TOPIC    = "digitalspotter/imu"
    RESULT_TOPIC = "digitalspotter/result"
    ENABLED  = os.getenv("DS_MQTT_ENABLED",   "false").lower() == "true"


class _Buzzer:
    """Active/Passive buzzer GPIO configuration."""
    GPIO_PIN = int(os.getenv("DS_BUZZER_PIN", "18"))
    ENABLED = os.getenv("DS_BUZZER_ENABLED", "true").lower() == "true"
    # Triple rapid beep: [on, off, on, off, on] in seconds
    BAD_FORM_PATTERN = [0.1, 0.08, 0.1, 0.08, 0.1]
    # Tuning frequency for passive buzzers (find resonant frequency for max volume)
    FREQUENCY = int(os.getenv("DS_BUZZER_FREQ", "2500"))


class _RgbLed:
    """RGB 5050 SMD LED GPIO configuration."""
    PIN_R = int(os.getenv("DS_RGB_PIN_R", "27"))
    PIN_G = int(os.getenv("DS_RGB_PIN_G", "17"))
    PIN_B = int(os.getenv("DS_RGB_PIN_B", "22"))
    ENABLED = os.getenv("DS_RGB_ENABLED", "true").lower() == "true"
    COMMON_ANODE = os.getenv("DS_RGB_COMMON_ANODE", "false").lower() == "true"


class _Logging:
    """Application logging configuration."""
    LEVEL = os.getenv("DS_LOG_LEVEL", "INFO")
    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    FILE = "logs/app.log"
    MAX_BYTES = 10485760  # 10 MB
    BACKUP_COUNT = 5


class Config:
    """Master configuration class.

    Usage:
        from config.config import Config
        port = Config.API.PORT
        model_path = Config.PATHS.MODEL_TFLITE
    """
    VERSION = "1.0.0"
    CAMERA = _Camera()
    STREAM = _Stream()
    API = _API()
    FRONTEND = _Frontend()
    PATHS = _Paths()
    MEDIAPIPE = _MediaPipe()
    INFERENCE = _Inference()
    REP_SEGMENTATION = _RepSegmentation()
    EXERCISES = _Exercises()
    IMU = _IMU()
    MQTT = _MQTT()
    BUZZER = _Buzzer()
    RGB_LED = _RgbLed()
    LOGGING = _Logging()
