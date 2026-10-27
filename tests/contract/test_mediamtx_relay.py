from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
RELAY_CONFIG = REPOSITORY_ROOT / "deploy" / "mediamtx.yml"


def test_canonical_mediamtx_config_has_one_loopback_publisher_and_whep_output():
    text = RELAY_CONFIG.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}

    assert "rtspAddress: 127.0.0.1:8554" in lines
    assert "webrtc: yes" in lines
    assert "webrtcAddress: :8889" in lines
    assert "rtmp: no" in lines
    assert "hls: no" in lines
    assert "srt: no" in lines
    assert "picamera2:" in lines
    assert "source: publisher" in lines
    assert "source: rpiCamera" not in lines


def test_canonical_vision_publish_url_matches_the_relay_path():
    example = (REPOSITORY_ROOT / "deploy" / "digital-spotter.example.toml").read_text(
        encoding="utf-8"
    )

    assert 'publish_url = "rtsp://127.0.0.1:8554/picamera2"' in example
