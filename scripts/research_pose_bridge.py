"""Launch the temporary M3-04 loopback-only pose/clock research bridge."""

from __future__ import annotations

import argparse
from pathlib import Path

from digital_spotter.api.research_telemetry import run_research_bridge


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--static-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_research_bridge(static_dir=args.static_dir, socket_path=args.socket, port=args.port)


if __name__ == "__main__":
    main()
