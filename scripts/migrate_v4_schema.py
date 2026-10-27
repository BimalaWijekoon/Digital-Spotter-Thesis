#!/usr/bin/env python3
"""
scripts/migrate_v4_schema.py
Applies ALTER TABLE to existing data/sessions.db to add v4 metadata columns.
"""

import sqlite3
from pathlib import Path
import sys

# Add project root to path so we can import Config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.config import Config

DB_PATH = Path(Config.PATHS.DATABASE)

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}, nothing to migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    columns_to_add = [
        ("height_cm", "REAL"),
        ("weight_kg", "REAL"),
        ("ftr", "REAL")
    ]

    # Check existing columns
    cursor.execute("PRAGMA table_info(sessions)")
    existing_columns = {col[1] for col in cursor.fetchall()}

    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to sessions table.")
            except Exception as e:
                print(f"Failed to add {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
