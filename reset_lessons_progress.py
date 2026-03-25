#!/usr/bin/env python3
"""
reset_lessons_progress.py — Reset Daily Lessons upload progress.

Clears the lessons_log table so the next run starts from lesson 1.

Usage:
    python reset_lessons_progress.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "acim.db"

def reset():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return False

    conn = sqlite3.connect(str(DB_PATH))

    # Check current progress
    count = conn.execute("SELECT COUNT(*) FROM lessons_log WHERE success = 1").fetchone()[0]
    print(f"Current progress: {count} lessons uploaded")

    # Clear the log
    conn.execute("DELETE FROM lessons_log")
    conn.commit()
    conn.close()

    print("Upload history cleared — will start from lesson 1")
    return True

if __name__ == "__main__":
    print("\n=== Reset Daily Lessons Progress ===\n")
    reset()
