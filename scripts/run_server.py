#!/usr/bin/env python3
"""
scripts/run_server.py
Purpose: Production server launcher for Raspberry Pi (Dashboard).
Author: bimalawijekoon
Version: 2.0.0
"""

import sys
from pathlib import Path
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config


def main() -> None:
    """Start the temporary FastAPI migration server from validated config."""
    print("=" * 60)
    print(
        "Starting Digital Spotter migration dashboard on "
        f"{Config.API.HOST}:{Config.API.PORT}..."
    )
    print("=" * 60)
    uvicorn.run(
        "scripts.dashboard.main:app",
        host=Config.API.HOST,
        port=Config.API.PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
