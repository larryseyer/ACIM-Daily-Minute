#!/usr/bin/env python3
from __future__ import annotations
"""
lessons.py — ACIM Daily Lessons pipeline orchestrator.

Posts the 365 ACIM Workbook lessons sequentially, one per weekday (Mon-Fri),
to a separate YouTube playlist with a custom background graphic.

Usage:
    python lessons.py              # Normal daily run (called by launchd)
    python lessons.py --run        # Manual run (respects weekday check)
    python lessons.py --status     # Show status
    python lessons.py --dry-run    # Test pipeline without uploading
    python lessons.py --force      # Run even on weekends
    python lessons.py --lesson N   # Run specific lesson (for testing)
"""

import argparse
import logging
import os
import sqlite3
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
AUDIO_DIR = BASE_DIR / os.getenv("AUDIO_DIR", "audio")
VIDEO_DIR = BASE_DIR / os.getenv("VIDEO_DIR", "video")
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
LOG_DIR = BASE_DIR / os.getenv("LOG_DIR", "logs")
DB_PATH = DATA_DIR / "acim.db"

# Lessons-specific configuration
LESSONS_PLAYLIST_ID = os.getenv("YOUTUBE_LESSONS_PLAYLIST_ID")
BACKGROUND_PREFIX = "background-lessons"  # Uses background-lessons.jpg and background-lessons_tiktok.jpg

YOUTUBE_TAGS = [
    "ACIM", "A Course in Miracles", "Workbook", "Daily Lesson",
    "meditation", "spiritual", "Helen Schucman",
]

TIKTOK_HASHTAGS = "#ACIM #ACourseInMiracles #WorkbookLesson #Spirituality #DailyLesson"


def setup_logging():
    """Configure logging with rotating file handler and console output."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "lessons.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Clear existing handlers
    root.handlers.clear()

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


def is_weekday() -> bool:
    """Check if today is a weekday (Monday=0 through Friday=4)."""
    return datetime.now().weekday() < 5


def get_next_lesson() -> Optional[dict]:
    """
    Get the next lesson to post (sequential order).

    Returns the next lesson after the highest successfully posted lesson,
    or lesson 1 if none have been posted yet.
    """
    conn = get_db()

    # Find highest successfully posted lesson
    row = conn.execute(
        """SELECT MAX(lesson_id) as max_lesson
           FROM lessons_log WHERE success = 1"""
    ).fetchone()

    last_lesson = row['max_lesson'] if row['max_lesson'] else 0
    next_lesson_id = last_lesson + 1

    # Wrap around if we've completed all 365
    if next_lesson_id > 365:
        log.info("All 365 lessons completed! Starting over from lesson 1.")
        next_lesson_id = 1

    # Get the lesson
    lesson = conn.execute(
        "SELECT * FROM lessons WHERE id = ?", (next_lesson_id,)
    ).fetchone()

    conn.close()

    if lesson:
        return dict(lesson)
    return None


def get_lesson_by_id(lesson_id: int) -> Optional[dict]:
    """Get a specific lesson by ID."""
    conn = get_db()
    lesson = conn.execute(
        "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
    ).fetchone()
    conn.close()
    return dict(lesson) if lesson else None


def log_lesson_upload(
    lesson_id: int,
    date_str: str,
    youtube_id: Optional[str],
    tiktok_id: Optional[str],
    youtube_success: bool,
    tiktok_success: bool,
    error_msg: Optional[str] = None,
):
    """Log a lesson upload attempt to the database."""
    conn = get_db()
    youtube_url = f"https://youtu.be/{youtube_id}" if youtube_id else None

    conn.execute(
        """INSERT INTO lessons_log
           (lesson_id, upload_date, youtube_id, youtube_url,
            tiktok_id, success, tiktok_success, error_msg)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (lesson_id, date_str, youtube_id, youtube_url, tiktok_id,
         1 if youtube_success else 0, 1 if tiktok_success else 0, error_msg),
    )
    conn.commit()
    conn.close()


def build_description(lesson: dict) -> str:
    """Build YouTube video description for a lesson."""
    return (
        f"ACIM Workbook Lesson {lesson['id']}\n\n"
        f'"{lesson["title"]}"\n\n'
        f"Today's lesson:\n\n"
        f"{lesson['text']}\n\n"
        f"---\n\n"
        f"Read from the public domain edition of A Course in Miracles, "
        f"as scribed by Helen Schucman.\n\n"
        f"The Workbook contains 365 lessons — one for each day of the year.\n\n"
        f"#ACIM #ACourseInMiracles #WorkbookLesson #Lesson{lesson['id']}"
    )


def show_status():
    """Display current lessons pipeline status."""
    if not DB_PATH.exists():
        print("Database not found. Run: python migrate_db_lessons.py")
        return

    conn = get_db()

    # Check if lessons table exists and has data
    try:
        total_lessons = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
    except sqlite3.OperationalError:
        print("Lessons table not found. Run: python migrate_db_lessons.py")
        conn.close()
        return

    if total_lessons == 0:
        print("No lessons imported. Run: python import_lessons.py")
        conn.close()
        return

    # Get stats
    completed = conn.execute(
        "SELECT COUNT(DISTINCT lesson_id) FROM lessons_log WHERE success = 1"
    ).fetchone()[0]

    remaining = total_lessons - completed

    # Check TikTok configuration
    try:
        from tiktok_uploader import is_tiktok_configured
        tiktok_configured = is_tiktok_configured()
    except ImportError:
        tiktok_configured = False

    # Get TikTok stats
    try:
        tiktok_uploads = conn.execute(
            "SELECT COUNT(DISTINCT lesson_id) FROM lessons_log WHERE tiktok_success = 1"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        tiktok_uploads = 0

    print(f"\n=== ACIM Daily Lessons Status ===")
    print(f"Total lessons:      {total_lessons}")
    print(f"Lessons completed:  {completed}")
    print(f"Lessons remaining:  {remaining}")
    print(f"Progress:           {completed/total_lessons*100:.1f}%")

    # Next lesson info
    next_lesson = get_next_lesson()
    if next_lesson:
        print(f"\nNext lesson:        Lesson {next_lesson['id']}")
        print(f'  Title:            "{next_lesson["title"][:50]}..."' if len(next_lesson["title"]) > 50 else f'  Title:            "{next_lesson["title"]}"')
        print(f"  Word count:       {next_lesson['word_count']}")

    # Last upload info
    last = conn.execute(
        """SELECT lesson_id, upload_date FROM lessons_log
           WHERE success = 1 ORDER BY upload_date DESC LIMIT 1"""
    ).fetchone()

    if last:
        print(f"\nLast uploaded:      Lesson {last['lesson_id']} on {last['upload_date']}")
    else:
        print(f"\nLast uploaded:      None yet")

    # Time estimate (weekdays only)
    if remaining > 0:
        weeks = remaining / 5
        months = weeks / 4.33
        print(f"\nEst. completion:    ~{weeks:.0f} weeks ({months:.1f} months) @ 5/week")

    # Platform info
    print(f"\n--- Platforms ---")
    print(f"YouTube playlist:   {LESSONS_PLAYLIST_ID or 'Not configured'}")
    print(f"YouTube uploads:    {completed}")
    print(f"TikTok:             {'Configured' if tiktok_configured else 'Not configured'}")
    if tiktok_configured and tiktok_uploads > 0:
        print(f"TikTok uploads:     {tiktok_uploads}")

    print(f"\nToday is:           {'Weekday' if is_weekday() else 'Weekend'}")
    print()

    conn.close()


def run_lessons_pipeline(
    dry_run: bool = False,
    force: bool = False,
    specific_lesson: Optional[int] = None,
    skip_tiktok: bool = False,
):
    """Full pipeline for one lesson upload."""
    # Import here to avoid circular imports and allow --status without deps
    from tts_generator import generate_audio
    from uploader import upload_video as upload_youtube
    from video_builder import build_video

    # Check if TikTok is configured
    try:
        from tiktok_uploader import is_tiktok_configured, upload_video as upload_tiktok
        tiktok_available = is_tiktok_configured()
    except ImportError:
        tiktok_available = False
        upload_tiktok = None

    do_tiktok = tiktok_available and not skip_tiktok

    log.info("=== ACIM Daily Lessons pipeline starting ===")

    # Check weekday (unless forced)
    if not is_weekday() and not force:
        log.info("Today is a weekend. Use --force to run anyway.")
        return

    if not DB_PATH.exists():
        log.error("Database not found. Run: python migrate_db_lessons.py")
        return

    # Use a single date for the entire run
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Get the lesson to post
    if specific_lesson:
        lesson = get_lesson_by_id(specific_lesson)
        if not lesson:
            log.error(f"Lesson {specific_lesson} not found!")
            return
        log.info(f"Using specific lesson: {specific_lesson}")
    else:
        lesson = get_next_lesson()
        if not lesson:
            log.error("No lesson available. Run: python import_lessons.py")
            return

    # Check if we already uploaded today (prevent duplicates)
    if not dry_run and not specific_lesson:
        conn = get_db()
        already_done = conn.execute(
            "SELECT COUNT(*) FROM lessons_log WHERE upload_date = ? AND success = 1",
            (date_str,),
        ).fetchone()[0]
        conn.close()
        if already_done > 0:
            log.info(f"Already uploaded a lesson for {date_str} — skipping")
            return

    log.info(
        f"Selected Lesson {lesson['id']}: \"{lesson['title'][:50]}...\" "
        f"({lesson['word_count']} words)"
    )

    # Ensure output dirs exist
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    daily_lessons_video_dir = VIDEO_DIR / "daily-lessons"
    daily_lessons_video_dir.mkdir(parents=True, exist_ok=True)

    # Define paths
    audio_path = AUDIO_DIR / f"lesson_{lesson['id']}.mp3"
    youtube_video_path = daily_lessons_video_dir / f"lesson-{lesson['id']:03d}-{date_str}.mp4"
    tiktok_video_path = daily_lessons_video_dir / f"lesson-{lesson['id']:03d}-{date_str}-tiktok.mp4" if do_tiktok else None

    # Check if video already exists (reuse from previous dry-run, any date)
    existing_videos = list(daily_lessons_video_dir.glob(f"lesson-{lesson['id']:03d}-*.mp4"))
    existing_videos = [v for v in existing_videos if "tiktok" not in v.name]  # Exclude TikTok versions
    if existing_videos:
        # Use the most recent one
        existing_videos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        youtube_video_path = existing_videos[0]
        log.info(f"Reusing existing video: {youtube_video_path}")
    else:
        # 1. Generate audio via ElevenLabs
        if not generate_audio(lesson["text"], str(audio_path)):
            log.error("TTS generation failed")
            return

        # 2. Build YouTube video (horizontal 1920x1080) with lessons background
        if not build_video(
            lesson["text"],
            str(audio_path),
            str(youtube_video_path),
            format="horizontal",
            background_prefix=BACKGROUND_PREFIX,
        ):
            log.error("YouTube video build failed")
            audio_path.unlink(missing_ok=True)
            return

    # 3. Build TikTok video (vertical 1080x1920) with lessons background
    if do_tiktok:
        if tiktok_video_path.exists():
            log.info(f"Reusing existing TikTok video: {tiktok_video_path}")
        else:
            # Need audio for TikTok video
            if not audio_path.exists():
                if not generate_audio(lesson["text"], str(audio_path)):
                    log.error("TTS generation failed for TikTok")
                    do_tiktok = False

            if do_tiktok and not build_video(
                lesson["text"],
                str(audio_path),
                str(tiktok_video_path),
                format="vertical",
                background_prefix=BACKGROUND_PREFIX,
            ):
                log.error("TikTok video build failed")
                do_tiktok = False

    # Build titles and descriptions
    title = f'ACIM Lesson {lesson["id"]}: "{lesson["title"]}"'
    # Truncate title if too long for YouTube (100 char limit)
    if len(title) > 100:
        title = f'ACIM Lesson {lesson["id"]}: "{lesson["title"][:60]}..."'

    description = build_description(lesson)
    tags = YOUTUBE_TAGS + [f"Lesson {lesson['id']}"]
    tiktok_title = f'ACIM Lesson {lesson["id"]} {TIKTOK_HASHTAGS}'

    if dry_run:
        log.info(f"DRY RUN — would upload: {title}")
        log.info(f"YouTube Video: {youtube_video_path}")
        if tiktok_video_path:
            log.info(f"TikTok Video: {tiktok_video_path}")
        log.info(f"Audio: {audio_path}")
        log.info(f"Playlist: {LESSONS_PLAYLIST_ID}")
        log.info(f"Lesson text preview: {lesson['text'][:200]}...")
        # Keep files for preview (don't delete)
        log.info("=== DRY RUN complete — video files kept for preview ===")
        return

    # 4. Upload to YouTube (with lessons playlist)
    youtube_id = None
    youtube_success = False

    # Use existing thumbnail if available, otherwise None
    thumbnail_path = ASSETS_DIR / "thumbnail-lessons.jpg"
    thumb_str = str(thumbnail_path) if thumbnail_path.exists() else None

    youtube_id = upload_youtube(
        str(youtube_video_path),
        title,
        description,
        tags,
        thumb_str,
        playlist_id=LESSONS_PLAYLIST_ID,
    )
    youtube_success = bool(youtube_id)
    if youtube_success:
        log.info(f"YouTube upload successful: https://youtu.be/{youtube_id}")
    else:
        log.error("YouTube upload failed")

    # 5. Upload to TikTok
    tiktok_id = None
    tiktok_success = False
    if do_tiktok and upload_tiktok and tiktok_video_path:
        tiktok_id = upload_tiktok(str(tiktok_video_path), tiktok_title)
        tiktok_success = bool(tiktok_id)
        if tiktok_success:
            log.info(f"TikTok upload successful: publish_id={tiktok_id}")
        else:
            log.error("TikTok upload failed")

    # 6. Log the upload
    if youtube_success or tiktok_success:
        log_lesson_upload(
            lesson["id"],
            date_str,
            youtube_id,
            tiktok_id,
            youtube_success,
            tiktok_success,
        )

    # 7. Cleanup temp files
    audio_path.unlink(missing_ok=True)
    if tiktok_video_path:
        tiktok_video_path.unlink(missing_ok=True)
    # Keep YouTube video for potential re-upload? Or delete:
    # youtube_video_path.unlink(missing_ok=True)

    # Summary
    results = []
    if youtube_success:
        results.append(f"YouTube: {youtube_id}")
    if tiktok_success:
        results.append(f"TikTok: {tiktok_id}")
    if results:
        log.info(f"=== Done. Lesson {lesson['id']} uploaded: {', '.join(results)} ===")
    else:
        log.error("=== Pipeline complete but all uploads failed ===")


def main():
    parser = argparse.ArgumentParser(description="ACIM Daily Lessons — Pipeline")
    parser.add_argument("--run", action="store_true", help="Run pipeline once now")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Test pipeline without uploading",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Run even on weekends",
    )
    parser.add_argument(
        "--lesson", type=int, metavar="N",
        help="Run specific lesson number (1-365)",
    )
    parser.add_argument(
        "--skip-tiktok", action="store_true",
        help="Skip TikTok upload (YouTube only)",
    )
    args = parser.parse_args()

    setup_logging()

    if args.status:
        show_status()
        return

    if args.run or args.dry_run or args.lesson:
        run_lessons_pipeline(
            dry_run=args.dry_run,
            force=args.force,
            specific_lesson=args.lesson,
            skip_tiktok=args.skip_tiktok,
        )
        return

    # Default: show usage
    parser.print_help()


if __name__ == "__main__":
    main()
