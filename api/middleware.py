"""
api/middleware.py
Purpose: Request middleware — CORS, logging, rate limiting.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter
_request_counts = defaultdict(list)
RATE_LIMIT = 60  # requests per minute
RATE_WINDOW = 60  # seconds


def log_request(response):
    """Log every API call with timing.

    Args:
        response: Flask response object.

    Returns:
        response: Unchanged response.

    Side Effects:
        Logs request method, path, status, and timing.
    """
    from flask import request, g
    duration = time.time() - g.get("start_time", time.time())
    logger.debug(
        "%s %s %d (%.1fms)",
        request.method, request.path,
        response.status_code, duration * 1000,
    )
    return response


def before_request():
    """Set request start time for timing.

    Side Effects:
        Sets g.start_time.
    """
    from flask import g
    g.start_time = time.time()


def rate_limit():
    """Simple in-memory rate limiter per IP.

    Returns:
        None if allowed, or (response, status_code) if rate limited.
    """
    from flask import request, jsonify
    ip = request.remote_addr
    now = time.time()

    # Clean old entries
    _request_counts[ip] = [
        t for t in _request_counts[ip] if now - t < RATE_WINDOW
    ]

    if len(_request_counts[ip]) >= RATE_LIMIT:
        return jsonify({
            "error": "Rate limit exceeded",
            "retry_after": RATE_WINDOW,
        }), 429

    _request_counts[ip].append(now)
    return None


def register_middleware(app):
    """Register all middleware on a Flask app.

    Args:
        app: Flask application instance.

    Side Effects:
        Registers before_request and after_request hooks.
    """
    app.before_request(before_request)
    app.after_request(log_request)
