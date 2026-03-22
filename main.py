#!/usr/bin/env python3
from __future__ import annotations
"""
main.py — ACIM Daily Minute pipeline orchestrator.

Orchestrates the full daily pipeline: pick segment, generate TTS audio,
build scrolling text videos (YouTube + TikTok), upload to both platforms.

Usage:
    python main.py              # Normal daily run (called by launchd)
    python main.py --run        # Manual run
    python main.py --status     # Show status
    python main.py --dry-run    # Test pipeline without uploading
    python main.py --reimport   # Re-extract PDFs
    python main.py --skip-tiktok  # Skip TikTok upload
    python main.py --tiktok-only  # Only upload to TikTok (skip YouTube)
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

YOUTUBE_TAGS = [
    "ACIM", "A Course in Miracles", "Helen Schucman",
    "spiritual", "daily reading", "meditation", "miracle",
]

TIKTOK_HASHTAGS = "#ACIM #ACourseInMiracles #Spirituality #DailyInspiration #Meditation"


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


def log_upload(
    segment_id: int,
    date_str: str,
    youtube_id: str | None,
    tiktok_id: str | None,
    audio_file: str,
    video_file: str,
    youtube_success: bool,
    tiktok_success: bool,
    error_msg: str | None = None,
):
    """Log an upload attempt to the database."""
    conn = get_db()
    youtube_url = f"https://youtu.be/{youtube_id}" if youtube_id else None

    # Check if tiktok columns exist; if not, use old schema
    cursor = conn.execute("PRAGMA table_info(upload_log)")
    columns = [row[1] for row in cursor.fetchall()]

    if "tiktok_id" in columns:
        conn.execute(
            """INSERT INTO upload_log
               (segment_id, upload_date, youtube_id, youtube_url,
                tiktok_id, audio_file, video_file, success, tiktok_success, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (segment_id, date_str, youtube_id, youtube_url, tiktok_id,
             audio_file, video_file, 1 if youtube_success else 0,
             1 if tiktok_success else 0, error_msg),
        )
    else:
        # Fallback to old schema (before migration)
        conn.execute(
            """INSERT INTO upload_log
               (segment_id, upload_date, youtube_id, youtube_url,
                audio_file, video_file, success, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (segment_id, date_str, youtube_id, youtube_url,
             audio_file, video_file, 1 if youtube_success else 0, error_msg),
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

    # Check TikTok configuration
    try:
        from tiktok_uploader import is_tiktok_configured
        tiktok_configured = is_tiktok_configured()
    except ImportError:
        tiktok_configured = False

    conn = get_db()

    total = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    used = conn.execute("SELECT COUNT(*) FROM segments WHERE used = 1").fetchone()[0]
    remaining = total - used

    uploads = conn.execute(
        "SELECT COUNT(*) FROM upload_log WHERE success = 1"
    ).fetchone()[0]

    # Check for TikTok uploads if column exists
    cursor = conn.execute("PRAGMA table_info(upload_log)")
    columns = [row[1] for row in cursor.fetchall()]
    tiktok_uploads = 0
    if "tiktok_success" in columns:
        tiktok_uploads = conn.execute(
            "SELECT COUNT(*) FROM upload_log WHERE tiktok_success = 1"
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

    print(f"\n--- Platforms ---")
    print(f"YouTube:            Configured")
    print(f"  Uploads:          {uploads}")
    print(f"TikTok:             {'Configured' if tiktok_configured else 'Not configured (run setup_tiktok.py)'}")
    if tiktok_configured and tiktok_uploads > 0:
        print(f"  Uploads:          {tiktok_uploads}")

    print(f"\nChannel name:       {os.getenv('CHANNEL_NAME', 'ACIM Daily Minute')}")
    print()

    conn.close()


def run_daily_pipeline(
    dry_run: bool = False,
    skip_tiktok: bool = False,
    tiktok_only: bool = False,
):
    """Full pipeline for one day's upload."""
    # Import here to avoid circular imports and allow --status without deps
    from tts_generator import generate_audio
    from uploader import generate_thumbnail, upload_video as upload_youtube
    from video_builder import build_video

    # Check if TikTok is configured
    try:
        from tiktok_uploader import is_tiktok_configured, upload_video as upload_tiktok
        tiktok_available = is_tiktok_configured()
    except ImportError:
        tiktok_available = False
        upload_tiktok = None

    do_youtube = not tiktok_only
    do_tiktok = tiktok_available and not skip_tiktok

    log.info("=== ACIM Daily Minute pipeline starting ===")
    log.info(f"Platforms: YouTube={'yes' if do_youtube else 'skip'}, TikTok={'yes' if do_tiktok else 'skip/not configured'}")

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

    # 2. Generate audio via ElevenLabs (shared between both platforms)
    audio_path = AUDIO_DIR / f"acim_{segment['id']}.mp3"
    if not generate_audio(segment["text"], str(audio_path)):
        log.error("TTS generation failed")
        return

    day_number = get_next_day_number()

    # 3. Build YouTube video (horizontal 1920x1080)
    youtube_video_path = None
    if do_youtube:
        youtube_video_path = VIDEO_DIR / f"acim-day-{day_number:04d}-{date_str}.mp4"
        if not build_video(segment["text"], str(audio_path), str(youtube_video_path), format="horizontal"):
            log.error("YouTube video build failed")
            audio_path.unlink(missing_ok=True)
            return

    # 4. Build TikTok video (vertical 1080x1920)
    tiktok_video_path = None
    if do_tiktok:
        tiktok_video_path = VIDEO_DIR / f"acim-day-{day_number:04d}-{date_str}-tiktok.mp4"
        if not build_video(segment["text"], str(audio_path), str(tiktok_video_path), format="vertical"):
            log.error("TikTok video build failed")
            # Continue with YouTube if that's enabled
            if not do_youtube:
                audio_path.unlink(missing_ok=True)
                return
            do_tiktok = False

    # 5. Thumbnail for YouTube
    thumbnail_path = ASSETS_DIR / "thumbnail.jpg"
    if do_youtube:
        if thumbnail_path.exists():
            log.info(f"Using existing thumbnail: {thumbnail_path}")
        else:
            generate_thumbnail(day_number, str(thumbnail_path))

    # Build titles and descriptions
    title = f"ACIM Daily Minute for {date_str} — Day {day_number}"
    description = build_description(day_number, segment)
    tiktok_title = f"ACIM Daily Minute Day {day_number} {TIKTOK_HASHTAGS}"

    if dry_run:
        log.info(f"DRY RUN — would upload: {title}")
        if youtube_video_path:
            log.info(f"YouTube Video: {youtube_video_path}")
        if tiktok_video_path:
            log.info(f"TikTok Video: {tiktok_video_path}")
        log.info(f"Audio: {audio_path}")
        log.info(f"Segment text: {segment['text'][:100]}...")
        # Cleanup temp files
        audio_path.unlink(missing_ok=True)
        if tiktok_video_path:
            tiktok_video_path.unlink(missing_ok=True)
        log.info("=== DRY RUN complete ===")
        return

    # 6. Upload to YouTube
    youtube_id = None
    youtube_success = False
    if do_youtube:
        youtube_id = upload_youtube(
            str(youtube_video_path), title, description, YOUTUBE_TAGS, str(thumbnail_path)
        )
        youtube_success = bool(youtube_id)
        if youtube_success:
            log.info(f"YouTube upload successful: https://youtu.be/{youtube_id}")
        else:
            log.error("YouTube upload failed")

    # 7. Upload to TikTok
    tiktok_id = None
    tiktok_success = False
    if do_tiktok and upload_tiktok:
        tiktok_id = upload_tiktok(str(tiktok_video_path), tiktok_title)
        tiktok_success = bool(tiktok_id)
        if tiktok_success:
            log.info(f"TikTok upload successful: publish_id={tiktok_id}")
        else:
            log.error("TikTok upload failed")

    # 8. Mark segment used, log upload
    # Only mark as used if at least one platform succeeded
    if youtube_success or tiktok_success:
        mark_segment_used(segment["id"], date_str)

    log_upload(
        segment["id"],
        date_str,
        youtube_id,
        tiktok_id,
        str(audio_path),
        str(youtube_video_path or tiktok_video_path),
        youtube_success,
        tiktok_success,
    )

    # 9. Cleanup temp files
    audio_path.unlink(missing_ok=True)
    if tiktok_video_path:
        tiktok_video_path.unlink(missing_ok=True)

    # Summary
    results = []
    if youtube_success:
        results.append(f"YouTube: {youtube_id}")
    if tiktok_success:
        results.append(f"TikTok: {tiktok_id}")
    if results:
        log.info(f"=== Done. Day {day_number} uploaded: {', '.join(results)} ===")
    else:
        log.error("=== Pipeline complete but all uploads failed ===")


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
        help="Test pipeline without uploading",
    )
    parser.add_argument(
        "--reimport", action="store_true",
        help="Re-extract PDFs (calls pdf_extractor.py --reset)",
    )
    parser.add_argument(
        "--skip-tiktok", action="store_true",
        help="Skip TikTok upload (YouTube only)",
    )
    parser.add_argument(
        "--tiktok-only", action="store_true",
        help="Only upload to TikTok (skip YouTube)",
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
        run_daily_pipeline(
            dry_run=False,
            skip_tiktok=args.skip_tiktok,
            tiktok_only=args.tiktok_only,
        )
        return

    if args.dry_run:
        # One-time dry run
        run_daily_pipeline(
            dry_run=True,
            skip_tiktok=args.skip_tiktok,
            tiktok_only=args.tiktok_only,
        )
        return

    # Default: run the 24/7 scheduler
    run_scheduler()


if __name__ == "__main__":
    main()
