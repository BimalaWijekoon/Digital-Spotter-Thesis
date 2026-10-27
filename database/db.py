"""
database/db.py
Purpose: Database connection manager — thread-safe SQLite access.
         Provides connection pooling via threading.local() for safe
         multi-threaded Flask usage.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import sqlite3
import threading
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config

logger = logging.getLogger(__name__)

# Thread-local storage for database connections
_local = threading.local()


def get_connection():
    """Get a thread-local SQLite connection.

    Returns:
        sqlite3.Connection: A connection to the sessions database.
        Each thread gets its own connection for thread safety.

    Side Effects:
        Creates the data directory if it doesn't exist.
        Creates a new connection if one doesn't exist for the current thread.
    """
    if not hasattr(_local, "connection") or _local.connection is None:
        db_path = Config.PATHS.DATABASE
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _local.connection = sqlite3.connect(
            str(db_path),
            check_same_thread=False
        )
        _local.connection.row_factory = sqlite3.Row
        _local.connection.execute("PRAGMA journal_mode=WAL")
        _local.connection.execute("PRAGMA foreign_keys=ON")
        logger.debug("Database connection opened: %s", db_path)

    return _local.connection


def init_db():
    """Initialize the database schema from schema.sql.

    Reads and executes the SQL schema file to create all tables.
    Safe to call multiple times — uses CREATE IF NOT EXISTS.

    Returns:
        bool: True if initialization succeeded, False otherwise.

    Side Effects:
        Creates all tables defined in database/schema.sql.
    """
    try:
        conn = get_connection()
        schema_path = Config.PATHS.SCHEMA_SQL

        if not schema_path.exists():
            logger.error("Schema file not found: %s", schema_path)
            return False

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Database initialized successfully")
        return True

    except sqlite3.Error as e:
        logger.error("Database initialization failed: %s", e)
        return False


def close_connection():
    """Close the thread-local database connection.

    Returns:
        None

    Side Effects:
        Closes and removes the connection for the current thread.
    """
    if hasattr(_local, "connection") and _local.connection is not None:
        _local.connection.close()
        _local.connection = None
        logger.debug("Database connection closed")
