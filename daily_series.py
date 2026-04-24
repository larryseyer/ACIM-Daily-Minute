#!/usr/bin/env python3
"""
daily_series.py — Smart orchestrator for ACIM daily series.

Automatically runs the appropriate series based on completion status:
1. If Daily Lessons (365) are not complete → run lessons.py
2. If Daily Lessons are complete → run text_chapters.py

This script should be called by launchd AFTER the Daily Minute completes.

Usage:
    python daily_series.py              # Auto-select and run appropriate series
    python daily_series.py --status     # Show status of both series
    python daily_series.py --dry-run    # Show what would run without running it
    python daily_series.py --force-text # Force run text series (for testing)
"""

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
DB_PATH = DATA_DIR / "acim.db"
LOG_DIR = BASE_DIR / os.getenv("LOG_DIR", "logs")

# Configure logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "daily_series.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def get_lessons_status() -> tuple[int, int]:
    """Get lessons completion status. Returns (completed, total)."""
    if not DB_PATH.exists():
        return 0, 365
    
    conn = sqlite3.connect(str(DB_PATH))
    try:
        completed = conn.execute(
            "SELECT COUNT(DISTINCT lesson_id) FROM lessons_log WHERE success = 1"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
        return completed, total
    except sqlite3.OperationalError:
        return 0, 365
    finally:
        conn.close()


def get_text_status() -> tuple[int, int]:
    """Get text series completion status. Returns (completed, total)."""
    if not DB_PATH.exists():
        return 0, 0
    
    conn = sqlite3.connect(str(DB_PATH))
    try:
        completed = conn.execute(
            "SELECT COUNT(DISTINCT section_id) FROM text_upload_log WHERE success = 1"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM text_sections").fetchone()[0]
        return completed, total
    except sqlite3.OperationalError:
        return 0, 0
    finally:
        conn.close()


def are_lessons_complete() -> bool:
    """Check if all 365 lessons have been posted."""
    completed, total = get_lessons_status()
    return completed >= total and total > 0


def show_status():
    """Display status of both series."""
    lessons_completed, lessons_total = get_lessons_status()
    text_completed, text_total = get_text_status()
    
    lessons_done = lessons_completed >= lessons_total and lessons_total > 0
    
    print("\n=== ACIM Daily Series Status ===\n")
    
    print("--- Daily Lessons ---")
    print(f"Progress:    {lessons_completed}/{lessons_total} ({lessons_completed/lessons_total*100:.1f}%)" if lessons_total > 0 else "Progress:    Not set up")
    print(f"Status:      {'COMPLETE' if lessons_done else 'In progress'}")
    if not lessons_done and lessons_total > 0:
        remaining = lessons_total - lessons_completed
        weeks = remaining / 5  # 5 days/week
        print(f"Remaining:   {remaining} lessons (~{weeks:.0f} weeks)")
    
    print("\n--- Text Series ---")
    print(f"Progress:    {text_completed}/{text_total} ({text_completed/text_total*100:.1f}%)" if text_total > 0 else "Progress:    Not set up")
    if text_total > 0:
        if text_completed >= text_total:
            print(f"Status:      COMPLETE")
        elif lessons_done:
            print(f"Status:      ACTIVE (lessons complete)")
            remaining = text_total - text_completed
            weeks = remaining / 7  # 7 days/week
            print(f"Remaining:   {remaining} sections (~{weeks:.0f} weeks)")
        else:
            print(f"Status:      WAITING (lessons not complete)")
    
    print("\n--- Next Action ---")
    if lessons_done:
        print("Will run:    text_chapters.py")
    else:
        print("Will run:    lessons.py")
    print()


def run_series(force_text: bool = False, dry_run: bool = False, extra_args: list = None):
    """Run the appropriate series based on completion status."""
    extra_args = extra_args or []
    
    if force_text or are_lessons_complete():
        script = "text_chapters.py"
        series_name = "Text Series"
    else:
        script = "lessons.py"
        series_name = "Daily Lessons"
    
    script_path = BASE_DIR / script
    
    if not script_path.exists():
        log.error(f"Script not found: {script_path}")
        return False
    
    log.info(f"=== Running {series_name} ({script}) ===")
    
    if dry_run:
        log.info(f"DRY RUN: Would execute: python {script} --run {' '.join(extra_args)}")
        return True
    
    # Build command
    cmd = [sys.executable, str(script_path), "--run"] + extra_args
    
    try:
        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        if result.returncode == 0:
            log.info(f"=== {series_name} completed successfully ===")
            return True
        else:
            log.error(f"=== {series_name} exited with code {result.returncode} ===")
            return False
    except Exception as e:
        log.error(f"Failed to run {script}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="ACIM Daily Series — Smart orchestrator"
    )
    parser.add_argument("--status", action="store_true", help="Show status of both series")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without running")
    parser.add_argument("--force-text", action="store_true", help="Force run text series")
    parser.add_argument("--skip-tiktok", action="store_true", help="Pass --skip-tiktok to series")
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    extra_args = []
    if args.skip_tiktok:
        extra_args.append("--skip-tiktok")
    
    # Default behavior: run the appropriate series
    run_series(
        force_text=args.force_text,
        dry_run=args.dry_run,
        extra_args=extra_args,
    )


if __name__ == "__main__":
    main()
