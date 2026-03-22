#!/usr/bin/env python3
"""
migrate_db_tiktok.py — Database migration for TikTok integration.

Adds TikTok-related columns to the existing database schema.
Safe to run multiple times (idempotent).

Usage:
    python migrate_db_tiktok.py
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


def get_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get existing column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def migrate():
    """Run database migration for TikTok support."""
    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        log.error("Run the main pipeline first to create the database.")
        return False

    log.info(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))

    try:
        # Check current schema
        segment_cols = get_column_names(conn, "segments")
        upload_cols = get_column_names(conn, "upload_log")

        migrations_run = 0

        # Add tiktok_id to segments table
        if "tiktok_id" not in segment_cols:
            log.info("Adding tiktok_id column to segments table...")
            conn.execute("ALTER TABLE segments ADD COLUMN tiktok_id TEXT")
            migrations_run += 1
        else:
            log.info("segments.tiktok_id already exists, skipping")

        # Add TikTok columns to upload_log table
        if "tiktok_id" not in upload_cols:
            log.info("Adding tiktok_id column to upload_log table...")
            conn.execute("ALTER TABLE upload_log ADD COLUMN tiktok_id TEXT")
            migrations_run += 1
        else:
            log.info("upload_log.tiktok_id already exists, skipping")

        if "tiktok_success" not in upload_cols:
            log.info("Adding tiktok_success column to upload_log table...")
            conn.execute("ALTER TABLE upload_log ADD COLUMN tiktok_success INTEGER DEFAULT 0")
            migrations_run += 1
        else:
            log.info("upload_log.tiktok_success already exists, skipping")

        conn.commit()

        if migrations_run > 0:
            log.info(f"Migration complete: {migrations_run} column(s) added")
        else:
            log.info("No migrations needed, database is up to date")

        # Show current schema
        log.info("\n--- Current upload_log schema ---")
        for col in get_column_names(conn, "upload_log"):
            log.info(f"  {col}")

        return True

    except sqlite3.Error as e:
        log.error(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("\n=== ACIM Daily Minute — Database Migration ===\n")
    success = migrate()
    if success:
        print("\nMigration successful!")
        print("You can now run: python main.py --status")
    else:
        print("\nMigration failed. Check the logs above.")
