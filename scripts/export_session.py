#!/usr/bin/env python3
"""
scripts/export_session.py
Purpose: Export session data to CSV for analysis.
Author: bimalawijekoon
Version: 1.0.0
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import init_db
from database.queries import get_session, get_session_reps, get_recent_sessions


def export_session(session_id, output_path=None):
    init_db()
    session = get_session(session_id)
    if not session:
        print(f"Session {session_id} not found.")
        return

    reps = get_session_reps(session_id)
    if not output_path:
        output_path = Path(f"session_{session_id}_export.csv")

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'rep_number', 'phase', 'timestamp_ms',
            'inference_label', 'inference_confidence',
            'angles_json',
        ])
        for rep in reps:
            writer.writerow([
                rep.rep_number, rep.phase, rep.timestamp_ms,
                rep.inference_label, rep.inference_confidence,
                rep.angles_json if hasattr(rep, 'angles_json') else '',
            ])

    print(f"Exported {len(reps)} reps to {output_path}")


def list_sessions():
    init_db()
    sessions = get_recent_sessions(limit=20)
    print(f"{'ID':>5} {'Exercise':<25} {'Started':<20} {'Reps':>5}")
    print("-" * 60)
    for s in sessions:
        print(f"{s.id:>5} {s.exercise_name:<25} {s.started_at:<20} {s.total_reps:>5}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            list_sessions()
        else:
            export_session(int(sys.argv[1]))
    else:
        print("Usage:")
        print("  python export_session.py list        — list all sessions")
        print("  python export_session.py <ID>         — export session to CSV")
