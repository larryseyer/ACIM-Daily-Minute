#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_db_text.py - Database migration for ACIM Text video series.

Creates the text_sections and text_upload_log tables for the complete
Text narration series. Safe to run multiple times (idempotent).

Usage:
    python migrate_db_text.py
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
    """Run database migration for ACIM Text series support."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))

    try:
        migrations_run = 0

        # Create text_sections table
        if not table_exists(conn, "text_sections"):
            log.info("Creating text_sections table...")
            conn.execute("""
                CREATE TABLE text_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_num INTEGER NOT NULL,           -- 0 for Preface, 1-31 for chapters
                    chapter_title TEXT NOT NULL,            -- "Introduction to Miracles"
                    section_num INTEGER NOT NULL,           -- Order within chapter (1, 2, 3...)
                    section_title TEXT NOT NULL,            -- "Principles of Miracles"
                    text TEXT NOT NULL,                     -- Full section content
                    word_count INTEGER,
                    character_count INTEGER,
                    estimated_duration_minutes REAL,        -- word_count / 150
                    used INTEGER DEFAULT 0,
                    used_date TEXT,
                    youtube_id TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            migrations_run += 1
        else:
            log.info("text_sections table already exists, skipping")

        # Create text_upload_log table
        if not table_exists(conn, "text_upload_log"):
            log.info("Creating text_upload_log table...")
            conn.execute("""
                CREATE TABLE text_upload_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    section_id INTEGER REFERENCES text_sections(id),
                    upload_date TEXT NOT NULL,
                    youtube_id TEXT,
                    youtube_url TEXT,
                    tiktok_id TEXT,                         -- Future TikTok support
                    audio_file TEXT,
                    video_file TEXT,
                    success INTEGER DEFAULT 0,
                    tiktok_success INTEGER DEFAULT 0,       -- Future TikTok support
                    error_msg TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            migrations_run += 1
        else:
            log.info("text_upload_log table already exists, skipping")

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
    print("\n=== ACIM Text Series — Database Migration ===\n")
    success = migrate()
    if success:
        print("\nMigration successful!")
        print("Next step: python import_text_sections.py")
    else:
        print("\nMigration failed. Check the logs above.")
