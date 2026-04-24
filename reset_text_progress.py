#!/usr/bin/env python3
"""
reset_text_progress.py — Reset ACIM Text Series upload progress.

Clears the text_upload_log table so the next run starts from section 1.
Does NOT delete generated video/audio files — they will be reused to save
ElevenLabs TTS costs.

Usage:
    python reset_text_progress.py
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
    try:
        count = conn.execute(
            "SELECT COUNT(DISTINCT section_id) FROM text_upload_log WHERE success = 1"
        ).fetchone()[0]
        print(f"Current progress: {count} sections uploaded")
    except sqlite3.OperationalError:
        print("text_upload_log table not found")
        conn.close()
        return False

    # Clear the log
    conn.execute("DELETE FROM text_upload_log")
    conn.commit()
    conn.close()

    print("Upload history cleared — will start from section 1")
    print("\nNote: Existing video/audio files are preserved and will be reused.")
    return True

if __name__ == "__main__":
    print("\n=== Reset ACIM Text Series Progress ===\n")
    reset()
