#!/usr/bin/env python3
from __future__ import annotations
"""
text_chapters.py — ACIM Text Series pipeline orchestrator.

Posts the complete ACIM Text sequentially, one section per day (7 days/week),
to a dedicated YouTube playlist with a custom background graphic.

Usage:
    python text_chapters.py              # Normal daily run (called by launchd)
    python text_chapters.py --run        # Manual run
    python text_chapters.py --status     # Show status
    python text_chapters.py --dry-run    # Test pipeline without uploading
    python text_chapters.py --section N  # Run specific section ID (for testing)
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

# Text series configuration
TEXT_PLAYLIST_ID = os.getenv("YOUTUBE_TEXT_PLAYLIST_ID")
BACKGROUND_PREFIX = "background-text"  # Uses background-text.png and background-text_tiktok.png

YOUTUBE_TAGS = [
    "ACIM", "A Course in Miracles", "Text", "Complete Narration",
    "spiritual", "Helen Schucman", "audiobook",
]

TIKTOK_HASHTAGS = "#ACIM #ACourseInMiracles #Text #Spirituality #Audiobook"


def setup_logging():
    """Configure logging with rotating file handler and console output."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "text_chapters.log"

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


def get_next_section() -> Optional[dict]:
    """
    Get the next section to post (sequential order by chapter then section).

    Returns the next section after the highest successfully posted section,
    or the first section if none have been posted yet.
    """
    conn = get_db()

    # Find highest successfully posted section
    row = conn.execute(
        """SELECT MAX(section_id) as max_section
           FROM text_upload_log WHERE success = 1"""
    ).fetchone()

    last_section_id = row['max_section'] if row['max_section'] else 0

    # Get the next section by ID (sections are stored in order)
    section = conn.execute(
        """SELECT * FROM text_sections
           WHERE id > ?
           ORDER BY id
           LIMIT 1""",
        (last_section_id,)
    ).fetchone()

    # If no more sections, we've completed the series
    if not section:
        total = conn.execute("SELECT COUNT(*) FROM text_sections").fetchone()[0]
        if last_section_id >= total:
            log.info("All text sections completed!")
        conn.close()
        return None

    conn.close()
    return dict(section)


def get_section_by_id(section_id: int) -> Optional[dict]:
    """Get a specific section by ID."""
    conn = get_db()
    section = conn.execute(
        "SELECT * FROM text_sections WHERE id = ?", (section_id,)
    ).fetchone()
    conn.close()
    return dict(section) if section else None


def log_section_upload(
    section_id: int,
    date_str: str,
    youtube_id: Optional[str],
    tiktok_id: Optional[str],
    youtube_success: bool,
    tiktok_success: bool,
    audio_file: Optional[str] = None,
    video_file: Optional[str] = None,
    error_msg: Optional[str] = None,
):
    """Log a section upload attempt to the database."""
    conn = get_db()
    youtube_url = f"https://youtu.be/{youtube_id}" if youtube_id else None

    conn.execute(
        """INSERT INTO text_upload_log
           (section_id, upload_date, youtube_id, youtube_url,
            tiktok_id, audio_file, video_file, success, tiktok_success, error_msg)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (section_id, date_str, youtube_id, youtube_url, tiktok_id,
         audio_file, video_file,
         1 if youtube_success else 0, 1 if tiktok_success else 0, error_msg),
    )
    conn.commit()
    conn.close()


def build_title(section: dict) -> str:
    """Build YouTube video title for a section."""
    ch_num = section['chapter_num']
    section_num = section['section_num']
    section_title = section['section_title']

    if ch_num == 0:
        # Preface
        title = f"ACIM Text — Preface: {section_title}"
    else:
        # Use Roman numerals for section numbers within chapter
        roman_numerals = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
        section_roman = roman_numerals[section_num - 1] if section_num <= len(roman_numerals) else str(section_num)
        title = f"ACIM Text Ch.{ch_num} — {section_roman}. {section_title}"

    # Truncate if too long for YouTube (100 char limit)
    if len(title) > 100:
        title = title[:97] + "..."

    return title


def build_description(section: dict) -> str:
    """Build YouTube video description for a section."""
    ch_num = section['chapter_num']
    ch_title = section['chapter_title']
    section_title = section['section_title']
    word_count = section['word_count']
    duration = section['estimated_duration_minutes']

    if ch_num == 0:
        chapter_info = "Preface"
    else:
        chapter_info = f"Chapter {ch_num}: {ch_title}"

    return (
        f"A Course in Miracles — Text\n"
        f"{chapter_info}\n"
        f'Section: "{section_title}"\n\n'
        f"Duration: ~{duration:.0f} minutes ({word_count:,} words)\n\n"
        f"---\n\n"
        f"Read from the public domain edition of A Course in Miracles, "
        f"as scribed by Helen Schucman.\n\n"
        f"This is part of the complete ACIM Text narration series.\n\n"
        f"#ACIM #ACourseInMiracles #Text #Chapter{ch_num}"
    )


def show_status():
    """Display current text series pipeline status."""
    if not DB_PATH.exists():
        print("Database not found. Run: python migrate_db_text.py")
        return

    conn = get_db()

    # Check if text_sections table exists and has data
    try:
        total_sections = conn.execute("SELECT COUNT(*) FROM text_sections").fetchone()[0]
    except sqlite3.OperationalError:
        print("Text sections table not found. Run: python migrate_db_text.py")
        conn.close()
        return

    if total_sections == 0:
        print("No sections imported. Run: python import_text_sections.py")
        conn.close()
        return

    # Get stats
    try:
        completed = conn.execute(
            "SELECT COUNT(DISTINCT section_id) FROM text_upload_log WHERE success = 1"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        completed = 0

    remaining = total_sections - completed

    # Check TikTok configuration
    try:
        from tiktok_uploader import is_tiktok_configured
        tiktok_configured = is_tiktok_configured()
    except ImportError:
        tiktok_configured = False

    # Get TikTok stats
    try:
        tiktok_uploads = conn.execute(
            "SELECT COUNT(DISTINCT section_id) FROM text_upload_log WHERE tiktok_success = 1"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        tiktok_uploads = 0

    # Get total stats
    total_words = conn.execute("SELECT SUM(word_count) FROM text_sections").fetchone()[0] or 0
    total_duration = conn.execute("SELECT SUM(estimated_duration_minutes) FROM text_sections").fetchone()[0] or 0

    print(f"\n=== ACIM Text Series Status ===")
    print(f"Total sections:     {total_sections}")
    print(f"Sections completed: {completed}")
    print(f"Sections remaining: {remaining}")
    print(f"Progress:           {completed/total_sections*100:.1f}%")
    print(f"\nTotal words:        {total_words:,}")
    print(f"Total duration:     {total_duration:.0f} min ({total_duration/60:.1f} hours)")

    # Next section info
    next_section = get_next_section()
    if next_section:
        print(f"\nNext section:       ID {next_section['id']}")
        print(f"  Chapter:          {next_section['chapter_num']} - {next_section['chapter_title'][:40]}")
        print(f"  Section:          {next_section['section_title'][:50]}")
        print(f"  Word count:       {next_section['word_count']}")
        print(f"  Duration:         ~{next_section['estimated_duration_minutes']:.1f} min")

    # Last upload info
    try:
        last = conn.execute(
            """SELECT section_id, upload_date FROM text_upload_log
               WHERE success = 1 ORDER BY upload_date DESC LIMIT 1"""
        ).fetchone()

        if last:
            print(f"\nLast uploaded:      Section {last['section_id']} on {last['upload_date']}")
        else:
            print(f"\nLast uploaded:      None yet")
    except sqlite3.OperationalError:
        print(f"\nLast uploaded:      None yet")

    # Time estimate (7 days/week)
    if remaining > 0:
        weeks = remaining / 7
        months = weeks / 4.33
        print(f"\nEst. completion:    ~{weeks:.0f} weeks ({months:.1f} months) @ 7/week")

    # Platform info
    print(f"\n--- Platforms ---")
    print(f"YouTube playlist:   {TEXT_PLAYLIST_ID or 'Not configured'}")
    print(f"YouTube uploads:    {completed}")
    print(f"TikTok:             {'Configured' if tiktok_configured else 'Not configured'}")
    if tiktok_configured and tiktok_uploads > 0:
        print(f"TikTok uploads:     {tiktok_uploads}")

    # Check for required assets
    print(f"\n--- Assets ---")
    bg_path = ASSETS_DIR / f"{BACKGROUND_PREFIX}.png"
    bg_tiktok_path = ASSETS_DIR / f"{BACKGROUND_PREFIX}_tiktok.png"
    thumb_path = ASSETS_DIR / "thumbnail-text.jpg"

    print(f"Background:         {'OK' if bg_path.exists() else 'MISSING: ' + str(bg_path)}")
    print(f"TikTok background:  {'OK' if bg_tiktok_path.exists() else 'MISSING: ' + str(bg_tiktok_path)}")
    print(f"Thumbnail:          {'OK' if thumb_path.exists() else 'MISSING: ' + str(thumb_path)}")

    print()

    conn.close()


def run_text_pipeline(
    dry_run: bool = False,
    specific_section: Optional[int] = None,
    skip_tiktok: bool = False,
):
    """Full pipeline for one text section upload."""
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

    log.info("=== ACIM Text Series pipeline starting ===")

    if not DB_PATH.exists():
        log.error("Database not found. Run: python migrate_db_text.py")
        return

    # Use a single date for the entire run
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Get the section to post
    if specific_section:
        section = get_section_by_id(specific_section)
        if not section:
            log.error(f"Section {specific_section} not found!")
            return
        log.info(f"Using specific section: {specific_section}")
    else:
        section = get_next_section()
        if not section:
            log.info("No more sections to post. Text series complete!")
            return

    # Check if we already uploaded today (prevent duplicates)
    if not dry_run and not specific_section:
        conn = get_db()
        already_done = conn.execute(
            "SELECT COUNT(*) FROM text_upload_log WHERE upload_date = ? AND success = 1",
            (date_str,),
        ).fetchone()[0]
        conn.close()
        if already_done > 0:
            log.info(f"Already uploaded a section for {date_str} — skipping")
            return

    log.info(
        f"Selected Section {section['id']}: Ch.{section['chapter_num']} "
        f"\"{section['section_title'][:40]}...\" "
        f"({section['word_count']} words, ~{section['estimated_duration_minutes']:.1f} min)"
    )

    # Ensure output dirs exist
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    text_video_dir = VIDEO_DIR / "text-series"
    text_video_dir.mkdir(parents=True, exist_ok=True)

    # Define paths
    audio_path = AUDIO_DIR / f"text_section_{section['id']}.mp3"
    youtube_video_path = text_video_dir / f"text-{section['id']:03d}-{date_str}.mp4"
    tiktok_video_path = text_video_dir / f"text-{section['id']:03d}-{date_str}-tiktok.mp4" if do_tiktok else None

    # Check if video already exists (reuse from previous dry-run)
    existing_videos = list(text_video_dir.glob(f"text-{section['id']:03d}-*.mp4"))
    existing_videos = [v for v in existing_videos if "tiktok" not in v.name]
    if existing_videos:
        existing_videos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        youtube_video_path = existing_videos[0]
        log.info(f"Reusing existing video: {youtube_video_path}")
    else:
        # Prepend title so TTS reads "Chapter N: Section Title." before the section text
        if section['chapter_num'] == 0:
            # Preface sections
            tts_text = f"{section['section_title']}.\n\n{section['text']}"
        else:
            tts_text = f"Chapter {section['chapter_num']}: {section['section_title']}.\n\n{section['text']}"

        # 1. Generate audio via ElevenLabs (reuse if exists to save credits!)
        if audio_path.exists():
            log.info(f"Reusing existing audio: {audio_path} (saving ElevenLabs credits)")
        elif not generate_audio(tts_text, str(audio_path)):
            log.error("TTS generation failed")
            return

        # 2. Build YouTube video (horizontal 1920x1080) with text background
        if not build_video(
            tts_text,
            str(audio_path),
            str(youtube_video_path),
            format="horizontal",
            background_prefix=BACKGROUND_PREFIX,
        ):
            log.error("YouTube video build failed")
            audio_path.unlink(missing_ok=True)
            return

    # 3. Build TikTok video (vertical 1080x1920) with text background
    if do_tiktok:
        if tiktok_video_path.exists():
            log.info(f"Reusing existing TikTok video: {tiktok_video_path}")
        else:
            # Prepare tts_text if not already defined (video was reused)
            if 'tts_text' not in locals():
                if section['chapter_num'] == 0:
                    tts_text = f"{section['section_title']}.\n\n{section['text']}"
                else:
                    tts_text = f"Chapter {section['chapter_num']}: {section['section_title']}.\n\n{section['text']}"

            # Need audio for TikTok video
            if not audio_path.exists():
                if not generate_audio(tts_text, str(audio_path)):
                    log.error("TTS generation failed for TikTok")
                    do_tiktok = False

            if do_tiktok and not build_video(
                tts_text,
                str(audio_path),
                str(tiktok_video_path),
                format="vertical",
                background_prefix=BACKGROUND_PREFIX,
            ):
                log.error("TikTok video build failed")
                do_tiktok = False

    # Build titles and descriptions
    title = build_title(section)
    description = build_description(section)
    tags = YOUTUBE_TAGS + [f"Chapter {section['chapter_num']}"]
    tiktok_title = f"ACIM Text Ch.{section['chapter_num']} {TIKTOK_HASHTAGS}"

    if dry_run:
        log.info(f"DRY RUN — would upload: {title}")
        log.info(f"YouTube Video: {youtube_video_path}")
        if tiktok_video_path:
            log.info(f"TikTok Video: {tiktok_video_path}")
        log.info(f"Audio: {audio_path}")
        log.info(f"Playlist: {TEXT_PLAYLIST_ID}")
        log.info(f"Section text preview: {section['text'][:200]}...")
        log.info("=== DRY RUN complete — video files kept for preview ===")
        return

    # 4. Upload to YouTube (with text playlist)
    youtube_id = None
    youtube_success = False

    # Use existing thumbnail if available
    thumbnail_path = ASSETS_DIR / "thumbnail-text.jpg"
    thumb_str = str(thumbnail_path) if thumbnail_path.exists() else None

    youtube_id = upload_youtube(
        str(youtube_video_path),
        title,
        description,
        tags,
        thumb_str,
        playlist_id=TEXT_PLAYLIST_ID,
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
        log_section_upload(
            section["id"],
            date_str,
            youtube_id,
            tiktok_id,
            youtube_success,
            tiktok_success,
            str(audio_path),
            str(youtube_video_path),
        )

    # 7. Cleanup temp files
    # KEEP audio files to save ElevenLabs credits for future runs!
    # audio_path.unlink(missing_ok=True)  # Preserved for credit savings
    if tiktok_video_path:
        tiktok_video_path.unlink(missing_ok=True)

    # Summary
    results = []
    if youtube_success:
        results.append(f"YouTube: {youtube_id}")
    if tiktok_success:
        results.append(f"TikTok: {tiktok_id}")
    if results:
        log.info(f"=== Done. Section {section['id']} uploaded: {', '.join(results)} ===")
    else:
        log.error("=== Pipeline complete but all uploads failed ===")


def main():
    parser = argparse.ArgumentParser(description="ACIM Text Series — Pipeline")
    parser.add_argument("--run", action="store_true", help="Run pipeline once now")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Test pipeline without uploading",
    )
    parser.add_argument(
        "--section", type=int, metavar="N",
        help="Run specific section ID (for testing)",
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

    if args.run or args.dry_run or args.section:
        run_text_pipeline(
            dry_run=args.dry_run,
            specific_section=args.section,
            skip_tiktok=args.skip_tiktok,
        )
        return

    # Default: show usage
    parser.print_help()


if __name__ == "__main__":
    main()
