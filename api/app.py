"""
api/app.py
Purpose: Flask app factory — creates and configures the Flask application.
         Single entry point for the backend server.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from config.config import Config
from database.db import init_db

logger = logging.getLogger(__name__)

# Global SocketIO instance — shared across modules
socketio = SocketIO()

# Server start time for uptime calculation
_start_time = time.time()


def get_uptime():
    """Get server uptime in seconds.
    Returns:
        int: Seconds since server start.
    """
    return int(time.time() - _start_time)


def create_app(config=None):
    """Flask application factory.

    Args:
        config: Optional config object to override defaults.

    Returns:
        Flask: Configured Flask application instance.

    Side Effects:
        Initializes database, registers blueprints and error handlers.
    """
    app = Flask(__name__)

    app.config["SECRET_KEY"] = Config.API.SECRET_KEY
    app.config["DEBUG"] = Config.API.DEBUG

    # CORS for local network access
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize database
    with app.app_context():
        init_db()

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    @app.route("/")
    def index():
        return {"message": "Dashboard moved to Vercel. This Pi serves the API and WebSocket only."}, 200

    # Initialize SocketIO
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        logger=False,
        engineio_logger=False,
    )

    # Register socket events
    register_socketio()

    logger.info("Flask app created (port=%d)", Config.API.PORT)
    return app


def register_blueprints(app):
    """Attach route blueprints to the app.

    Args:
        app: Flask application instance.

    Side Effects:
        Registers the API blueprint.
    """
    from api.routes import api_bp
    app.register_blueprint(api_bp)


def register_socketio():
    """Attach WebSocket event handlers.

    Side Effects:
        Registers all socket event handlers.
    """
    from api.socket_events import register_events
    register_events(socketio)


def register_error_handlers(app):
    """Register HTTP error handlers.

    Args:
        app: Flask application instance.

    Side Effects:
        Adds handlers for 404, 500, etc.
    """
    from flask import jsonify

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found", "code": 404}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal server error", "code": 500}), 500

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad request", "code": 400}), 400


# Entry point for direct execution
if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, Config.LOGGING.LEVEL),
        format=Config.LOGGING.FORMAT,
    )
    app = create_app()
    socketio.run(
        app,
        host=Config.API.HOST,
        port=Config.API.PORT,
        debug=Config.API.DEBUG,
    )
