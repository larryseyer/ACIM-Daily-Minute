#!/usr/bin/env python3
"""
migrate_db_lessons.py — Database migration for ACIM Daily Lessons.

Creates the lessons and lessons_log tables for the sequential workbook
lesson posting system. Safe to run multiple times (idempotent).

Usage:
    python migrate_db_lessons.py
"""

import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
DB_PATH = DATA_DIR / "acim.db"


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def migrate():
    """Run database migration for Daily Lessons support."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))

    try:
        migrations_run = 0

        # Create lessons table
        if not table_exists(conn, "lessons"):
            log.info("Creating lessons table...")
            conn.execute("""
                CREATE TABLE lessons (
                    id          INTEGER PRIMARY KEY,  -- Lesson number 1-365
                    title       TEXT NOT NULL,        -- Lesson affirmation (quoted text)
                    text        TEXT NOT NULL,        -- Full lesson content
                    word_count  INTEGER,
                    created_at  TEXT DEFAULT (datetime('now'))
                )
            """)
            migrations_run += 1
        else:
            log.info("lessons table already exists, skipping")

        # Create lessons_log table
        if not table_exists(conn, "lessons_log"):
            log.info("Creating lessons_log table...")
            conn.execute("""
                CREATE TABLE lessons_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id       INTEGER REFERENCES lessons(id),
                    upload_date     TEXT NOT NULL,
                    youtube_id      TEXT,
                    youtube_url     TEXT,
                    tiktok_id       TEXT,
                    success         INTEGER DEFAULT 0,
                    tiktok_success  INTEGER DEFAULT 0,
                    error_msg       TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                )
            """)
            migrations_run += 1
        else:
            log.info("lessons_log table already exists, skipping")

        conn.commit()

        if migrations_run > 0:
            log.info(f"Migration complete: {migrations_run} table(s) created")
        else:
            log.info("No migrations needed, database is up to date")

        # Show current tables
        log.info("\n--- Database tables ---")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        for row in cursor.fetchall():
            log.info(f"  {row[0]}")

        return True

    except sqlite3.Error as e:
        log.error(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("\n=== ACIM Daily Lessons — Database Migration ===\n")
    success = migrate()
    if success:
        print("\nMigration successful!")
        print("Next step: python import_lessons.py")
    else:
        print("\nMigration failed. Check the logs above.")
