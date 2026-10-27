"""
integration/main_loop.py
Purpose: Main application loop — starts all services and runs forever.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from api.app import create_app, socketio
from api.routes import set_session_manager
from integration.session_manager import SessionManager

logger = logging.getLogger(__name__)


def main():
    """Main entry point — initializes and starts all services.

    Side Effects:
        - Creates Flask app + SocketIO
        - Initializes SessionManager (loads model)
        - Starts camera frame processing loop
        - Runs Flask-SocketIO server (blocks)
    """
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, Config.LOGGING.LEVEL),
        format=Config.LOGGING.FORMAT,
    )
    logger.info("=" * 60)
    logger.info("Digital Spotter v%s Starting", Config.VERSION)
    logger.info("=" * 60)

    # Create Flask app
    app = create_app()

    # Initialize session manager
    session_mgr = SessionManager(socketio=socketio)

    # Share session manager with API routes
    set_session_manager(session_mgr)

    # Graceful shutdown
    def shutdown_handler(sig, frame):
        logger.info("Shutdown signal received")
        session_mgr.frame_processor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start background frame processing
    session_mgr.frame_processor.start()

    # Run Flask-SocketIO (blocks)
    logger.info(
        "Server running at http://%s:%d",
        Config.API.HOST, Config.API.PORT
    )
    socketio.run(
        app,
        host=Config.API.HOST,
        port=Config.API.PORT,
        debug=Config.API.DEBUG,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
