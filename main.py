#!/usr/bin/env python3
from __future__ import annotations
"""
main.py — ACIM Daily Minute pipeline orchestrator.

Orchestrates the full daily pipeline: pick segment, generate TTS audio,
build scrolling text video, upload to YouTube.

Usage:
    python main.py              # Normal daily run (called by launchd)
    python main.py --run        # Manual run
    python main.py --status     # Show status
    python main.py --dry-run    # Test pipeline without uploading
    python main.py --reimport   # Re-extract PDFs
"""

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
BASE_DIR = Path(__file__).parent
PDF_DIR = BASE_DIR / os.getenv("PDF_DIR", "pdfs")
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
AUDIO_DIR = BASE_DIR / os.getenv("AUDIO_DIR", "audio")
VIDEO_DIR = BASE_DIR / os.getenv("VIDEO_DIR", "video")
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
LOG_DIR = BASE_DIR / os.getenv("LOG_DIR", "logs")
DB_PATH = DATA_DIR / "acim.db"

TAGS = [
    "ACIM", "A Course in Miracles", "Helen Schucman",
    "spiritual", "daily reading", "meditation", "miracle",
]


def setup_logging():
    """Configure logging with rotating file handler and console output."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "acim.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Rotating file handler (10MB max, 5 backups)
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    root.addHandler(console_handler)


log = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def pick_random_segment() -> dict | None:
    """
    Pick a random unused segment.
    If all segments are used, reset all to unused and reshuffle.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM segments WHERE used = 0 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()

    if not row:
        # All used — reset and start over
        conn.execute("UPDATE segments SET used = 0, used_date = NULL, youtube_id = NULL")
        conn.commit()
        log.info("All segments used — reshuffled corpus")
        row = conn.execute(
            "SELECT * FROM segments WHERE used = 0 ORDER BY RANDOM() LIMIT 1"
        ).fetchone()

    conn.close()
    return dict(row) if row else None


def get_next_day_number() -> int:
    """Get the next day number based on successful uploads."""
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM upload_log WHERE success = 1"
    ).fetchone()[0]
    conn.close()
    return count + 1


def mark_segment_used(segment_id: int, date_str: str):
    """Mark a segment as used in the database."""
    conn = get_db()
    conn.execute(
        "UPDATE segments SET used = 1, used_date = ? WHERE id = ?",
        (date_str, segment_id),
    )
    conn.commit()
    conn.close()


def log_upload(segment_id: int, date_str: str, video_id: str | None,
               audio_file: str, video_file: str, success: bool,
               error_msg: str | None = None):
    """Log an upload attempt to the database."""
    conn = get_db()
    youtube_url = f"https://youtu.be/{video_id}" if video_id else None
    conn.execute(
        """INSERT INTO upload_log
           (segment_id, upload_date, youtube_id, youtube_url,
            audio_file, video_file, success, error_msg)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (segment_id, date_str, video_id, youtube_url,
         audio_file, video_file, 1 if success else 0, error_msg),
    )
    conn.commit()
    conn.close()


def build_description(day_number: int, segment: dict) -> str:
    """Build YouTube video description."""
    return (
        f"A one-minute reading from A Course in Miracles.\n\n"
        f"Today's reading:\n\n"
        f"{segment['text']}\n\n"
        f"---\n\n"
        f"Read from the public domain edition of A Course in Miracles, "
        f"as scribed by Helen Schucman.\n\n"
        f"A Course in Miracles is a self-study spiritual thought system.\n\n"
        f"#ACIM #ACourseInMiracles #SpiritualDaily #Meditation"
    )


def show_status():
    """Display current pipeline status."""
    if not DB_PATH.exists():
        print("Database not found. Run: python pdf_extractor.py")
        return

    conn = get_db()

    total = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    used = conn.execute("SELECT COUNT(*) FROM segments WHERE used = 1").fetchone()[0]
    remaining = total - used

    uploads = conn.execute(
        "SELECT COUNT(*) FROM upload_log WHERE success = 1"
    ).fetchone()[0]

    print(f"\n=== ACIM Daily Minute Status ===")
    print(f"Segments total:     {total}")
    print(f"Segments used:      {used}")
    print(f"Segments remaining: {remaining}")

    if uploads > 0:
        last = conn.execute(
            "SELECT upload_date FROM upload_log WHERE success = 1 "
            "ORDER BY upload_date DESC LIMIT 1"
        ).fetchone()
        print(f"Last upload:        {last[0]}  (Day {uploads})")
        print(f"Next upload:        Today  (Day {uploads + 1})")
    else:
        print(f"Last upload:        None")
        print(f"Next upload:        Day 1")

    if remaining > 0:
        years = remaining / 365.25
        print(f"Corpus exhaustion:  ~{years:.1f} years from now")

    print(f"YouTube channel:    {os.getenv('CHANNEL_NAME', 'ACIM Daily Minute')}")
    print()

    conn.close()


def run_daily_pipeline(dry_run: bool = False):
    """Full pipeline for one day's upload."""
    # Import here to avoid circular imports and allow --status without deps
    from tts_generator import generate_audio
    from uploader import generate_thumbnail, upload_video
    from video_builder import build_video

    log.info("=== ACIM Daily Minute pipeline starting ===")

    if not DB_PATH.exists():
        log.error("Database not found. Run: python pdf_extractor.py")
        return

    # Use a single date for the entire run
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Check if we already uploaded today (prevent duplicates)
    if not dry_run:
        conn = get_db()
        already_done = conn.execute(
            "SELECT COUNT(*) FROM upload_log WHERE upload_date = ? AND success = 1",
            (date_str,),
        ).fetchone()[0]
        conn.close()
        if already_done > 0:
            log.info(f"Already uploaded for {date_str} — skipping")
            return

    # Ensure output dirs exist
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Pick a random unused segment
    segment = pick_random_segment()
    if not segment:
        log.error("No segments available")
        return

    log.info(
        f"Selected segment {segment['id']} from {segment['source_pdf']} "
        f"({segment['word_count']} words)"
    )

    # 2. Generate audio via ElevenLabs
    audio_path = AUDIO_DIR / f"acim_{segment['id']}.mp3"
    if not generate_audio(segment["text"], str(audio_path)):
        log.error("TTS generation failed")
        return

    # 3. Thumbnail — use custom one if it exists, otherwise generate
    day_number = get_next_day_number()
    thumbnail_path = ASSETS_DIR / "thumbnail.png"
    if thumbnail_path.exists():
        log.info(f"Using existing thumbnail: {thumbnail_path}")
    else:
        generate_thumbnail(day_number, str(thumbnail_path))

    # 4. Build video
    video_path = VIDEO_DIR / f"acim-day-{day_number:04d}-{date_str}.mp4"
    if not build_video(segment["text"], str(audio_path), str(video_path)):
        log.error("Video build failed")
        audio_path.unlink(missing_ok=True)
        return

    # 5. Upload to YouTube (skip in dry-run mode)
    title = f"ACIM Daily Minute for {date_str} \u2014 Day {day_number}"
    description = build_description(day_number, segment)

    if dry_run:
        log.info(f"DRY RUN — would upload: {title}")
        log.info(f"Video: {video_path}")
        log.info(f"Audio: {audio_path}")
        log.info(f"Segment text: {segment['text'][:100]}...")
        # Cleanup temp audio
        audio_path.unlink(missing_ok=True)
        log.info("=== DRY RUN complete ===")
        return

    video_id = upload_video(
        str(video_path), title, description, TAGS, str(thumbnail_path)
    )

    # 6. Mark segment used, log upload
    mark_segment_used(segment["id"], date_str)
    log_upload(
        segment["id"], date_str, video_id,
        str(audio_path), str(video_path),
        success=bool(video_id),
    )

    # 7. Cleanup temp audio
    audio_path.unlink(missing_ok=True)

    log.info(f"=== Done. Day {day_number} uploaded: {video_id} ===")


def get_next_run_time() -> datetime:
    """Calculate next 2:00 AM Central (local) run time."""
    upload_hour = int(os.getenv("UPLOAD_HOUR", "2"))
    upload_minute = int(os.getenv("UPLOAD_MINUTE", "0"))

    now = datetime.now()
    today_run = now.replace(hour=upload_hour, minute=upload_minute, second=0, microsecond=0)

    if now >= today_run:
        # Already past today's run time, schedule for tomorrow
        return today_run + timedelta(days=1)
    return today_run


def run_scheduler():
    """Run 24/7, executing the pipeline daily at the scheduled time."""
    log.info("=== ACIM Daily Minute scheduler started ===")
    log.info(f"Schedule: daily at {os.getenv('UPLOAD_HOUR', '2')}:{os.getenv('UPLOAD_MINUTE', '0'):>02}")
    log.info("Press Ctrl+C to stop")

    while True:
        try:
            next_run = get_next_run_time()
            sleep_seconds = (next_run - datetime.now()).total_seconds()
            hours = int(sleep_seconds // 3600)
            minutes = int((sleep_seconds % 3600) // 60)
            log.info(f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')} ({hours}h {minutes}m from now)")

            # Sleep until next run, checking every 60 seconds
            while datetime.now() < next_run:
                time.sleep(60)

            # Run the pipeline
            log.info("Scheduled run triggered")
            run_daily_pipeline(dry_run=False)

        except KeyboardInterrupt:
            log.info("Shutting down...")
            break
        except Exception as e:
            log.error(f"Pipeline error: {e}")
            log.info("Will retry at next scheduled time")
            time.sleep(300)  # Wait 5 minutes on error


def main():
    parser = argparse.ArgumentParser(description="ACIM Daily Minute — Pipeline")
    parser.add_argument("--run", action="store_true", help="Run pipeline once now")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Test pipeline without uploading to YouTube",
    )
    parser.add_argument(
        "--reimport", action="store_true",
        help="Re-extract PDFs (calls pdf_extractor.py --reset)",
    )
    args = parser.parse_args()

    setup_logging()

    if args.status:
        show_status()
        return

    if args.reimport:
        log.info("Re-importing PDFs...")
        subprocess.run(
            [sys.executable, str(BASE_DIR / "pdf_extractor.py"), "--reset"],
            check=True,
        )
        return

    if args.run:
        # One-time manual run
        run_daily_pipeline(dry_run=False)
        return

    if args.dry_run:
        # One-time dry run
        run_daily_pipeline(dry_run=True)
        return

    # Default: run the 24/7 scheduler
    run_scheduler()


if __name__ == "__main__":
    main()
