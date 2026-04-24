#!/usr/bin/env python3
"""
import_lessons.py — Parse ACIM Workbook and populate lessons table.

Extracts all 365 workbook lessons from the corrected text file and
stores them in the database for sequential posting.

Usage:
    python import_lessons.py             # Import lessons (skips if already done)
    python import_lessons.py --dry-run   # Preview without writing to database
    python import_lessons.py --reset     # Clear and re-import all lessons
"""

import argparse
import logging
import os
import re
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
WORKBOOK_PATH = BASE_DIR / "corrected_text" / "ACIM_Workbook.txt"


def extract_title_from_content(content: str) -> str:
    """
    Extract the lesson title (quoted text at the beginning).

    Returns the text within the first set of quotes found.
    Handles both straight quotes ("...") and curly quotes ("...").
    """
    # Look for text in quotes, handling multi-line titles
    # The title is typically the first quoted text after the lesson header
    # Match both straight quotes and curly quotes
    match = re.search(r'["""]([^"""]+)["""]', content[:500], re.DOTALL)
    if match:
        # Clean up whitespace in the title
        title = match.group(1)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    # Fallback: use first line of content (without leading quotes)
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    if lines:
        first_line = lines[0][:100]
        # Remove leading curly/straight quotes if present
        first_line = re.sub(r'^["""]', '', first_line)
        return first_line
    return "Untitled"


def normalize_lesson_number(num_str: str) -> int:
    """
    Normalize a lesson number string that may have spaces.
    E.g., "10 0" -> 100, "2 61" -> 261, "15" -> 15
    """
    return int(num_str.replace(' ', ''))


def extract_introduction(content: str, part: int) -> str:
    """
    Extract the Introduction text for Part 1 or Part 2.

    Part 1 Introduction: Between "PART 1" + "INTRODUCTION" and "lesson 1"
    Part 2 Introduction: Between "PART 2" + "INTRODUCTION" and "lesson 221"
    """
    if part == 1:
        # Find Part 1 Introduction (after TOC, before lesson 1)
        # Look for standalone "INTRODUCTION" after "PART 1"
        intro_match = re.search(
            r'PART\s*1\s*\n+\s*INTRODUCTION\s*\n(.+?)(?=l\s*e\s*s\s*s\s*o\s*n\s+1\s*$)',
            content,
            re.DOTALL | re.IGNORECASE | re.MULTILINE
        )
    else:
        # Find Part 2 Introduction (before lesson 221)
        intro_match = re.search(
            r'PART\s*2\s*\n+\s*INTRODUCTION\s*\n(.+?)(?=l\s*e\s*s\s*s\s*o\s*n\s+2\s*2\s*1\s*$|Now is the need for practice almost done)',
            content,
            re.DOTALL | re.IGNORECASE | re.MULTILINE
        )

    if intro_match:
        intro_text = intro_match.group(1).strip()
        # Clean up page numbers and headers
        intro_text = re.sub(r'^\s*\d+\s*$', '', intro_text, flags=re.MULTILINE)
        intro_text = re.sub(r'^\s*WORKBOOK\s*$', '', intro_text, flags=re.MULTILINE)
        intro_text = re.sub(r'^\s*PART\s*[12I]+\s*$', '', intro_text, flags=re.MULTILINE | re.IGNORECASE)
        intro_text = re.sub(r'\n{3,}', '\n\n', intro_text)
        return intro_text.strip()

    return ""


def parse_workbook(file_path: Path) -> list[dict]:
    """
    Parse the ACIM Workbook text file and extract all 365 lessons plus Introductions.

    Returns a list of dicts with: id (lesson number), title, text, word_count
    Special IDs: 0 = Part 1 Introduction, 500 = Part 2 Introduction
    """
    log.info(f"Parsing workbook: {file_path}")

    content = file_path.read_text(encoding='utf-8')

    # Find where actual lessons start (skip TOC)
    # Look for "lesson 1" that's NOT in the TOC (TOC has page numbers after)
    # The actual lesson 1 starts with "lesson 1" followed by the title

    # Pattern to find lesson markers with various PDF extraction artifacts:
    # - "lesson N" (normal)
    # - "lesson N N" (spaced numbers like "10 0" = 100)
    # - "l e s s o n N" (spaced letters)
    # - "le s s on N" (partially spaced)
    # - "lesson N to M" (range for 361-365)
    # The pattern matches: l, optional spaces, e, optional spaces, s, etc.
    lesson_pattern = re.compile(
        r'^\s*l\s*e\s*s\s*s\s*o\s*n\s+(\d[\d ]*?)(?:\s+to\s+(\d[\d ]*?))?\s*$',
        re.IGNORECASE | re.MULTILINE
    )

    # Find all lesson markers
    markers = list(lesson_pattern.finditer(content))

    if not markers:
        log.error("No lesson markers found in workbook!")
        return []

    log.info(f"Found {len(markers)} lesson markers")

    lessons = []

    for i, match in enumerate(markers):
        start_lesson = normalize_lesson_number(match.group(1))
        end_lesson = normalize_lesson_number(match.group(2)) if match.group(2) else start_lesson

        # Get content start position (after the lesson header)
        content_start = match.end()

        # Get content end position (start of next lesson or end of file)
        if i + 1 < len(markers):
            content_end = markers[i + 1].start()
        else:
            content_end = len(content)

        # Extract lesson content
        lesson_content = content[content_start:content_end].strip()

        # Skip if this looks like TOC (has page numbers like ". . . . . 3")
        if re.search(r'\. \. \. \. \. \.\s*\d+', lesson_content[:200]):
            continue

        # Skip if too short (likely a TOC entry)
        if len(lesson_content) < 100:
            continue

        # Clean up the content
        # Remove page numbers (lines that are just numbers, with possible leading/trailing whitespace)
        lesson_content = re.sub(r'^\s*\d+\s*$', '', lesson_content, flags=re.MULTILINE)
        # Remove "WORKBOOK" headers
        lesson_content = re.sub(r'^\s*WORKBOOK\s*$', '', lesson_content, flags=re.MULTILINE)
        # Remove "PART 1" / "PART 2" / "PART I" / "PART II" headers
        lesson_content = re.sub(r'^\s*PART\s*[12I]+\s*$', '', lesson_content, flags=re.MULTILINE | re.IGNORECASE)
        # Clean up multiple blank lines
        lesson_content = re.sub(r'\n{3,}', '\n\n', lesson_content)
        lesson_content = lesson_content.strip()

        # Extract title
        title = extract_title_from_content(lesson_content)

        # Calculate word count
        word_count = len(lesson_content.split())

        # Handle ranges (lessons 361-365)
        for lesson_num in range(start_lesson, end_lesson + 1):
            lessons.append({
                'id': lesson_num,
                'title': title,
                'text': lesson_content,
                'word_count': word_count,
            })

    # Sort by lesson number and remove duplicates (keep first occurrence)
    seen = set()
    unique_lessons = []
    for lesson in sorted(lessons, key=lambda x: x['id']):
        if lesson['id'] not in seen and 1 <= lesson['id'] <= 365:
            seen.add(lesson['id'])
            unique_lessons.append(lesson)

    log.info(f"Extracted {len(unique_lessons)} unique lessons")

    # Verify we have all 365
    missing = set(range(1, 366)) - seen
    if missing:
        log.warning(f"Missing {len(missing)} lessons: {sorted(missing)[:20]}{'...' if len(missing) > 20 else ''}")

    # Extract and add Introductions
    part1_intro = extract_introduction(content, 1)
    if part1_intro:
        unique_lessons.insert(0, {
            'id': 0,
            'title': 'Part 1 Introduction',
            'text': part1_intro,
            'word_count': len(part1_intro.split()),
        })
        log.info(f"Added Part 1 Introduction ({len(part1_intro.split())} words)")
    else:
        log.warning("Could not extract Part 1 Introduction")

    part2_intro = extract_introduction(content, 2)
    if part2_intro:
        unique_lessons.append({
            'id': 500,
            'title': 'Part 2 Introduction',
            'text': part2_intro,
            'word_count': len(part2_intro.split()),
        })
        log.info(f"Added Part 2 Introduction ({len(part2_intro.split())} words)")
    else:
        log.warning("Could not extract Part 2 Introduction")

    return unique_lessons


def import_lessons(dry_run: bool = False, reset: bool = False):
    """Import parsed lessons into the database."""

    if not WORKBOOK_PATH.exists():
        log.error(f"Workbook not found: {WORKBOOK_PATH}")
        return False

    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        log.error("Run migrate_db_lessons.py first!")
        return False

    # Parse the workbook
    lessons = parse_workbook(WORKBOOK_PATH)

    if not lessons:
        log.error("No lessons parsed from workbook!")
        return False

    if dry_run:
        log.info("\n=== DRY RUN - Preview ===")
        log.info(f"Total lessons: {len(lessons)}")
        for lesson in lessons[:5]:
            log.info(f"\nLesson {lesson['id']}: \"{lesson['title']}\"")
            log.info(f"  Words: {lesson['word_count']}")
            log.info(f"  Preview: {lesson['text'][:150]}...")

        if len(lessons) > 5:
            log.info(f"\n... and {len(lessons) - 5} more lessons")

        # Show last lesson too
        if len(lessons) > 5:
            lesson = lessons[-1]
            log.info(f"\nLesson {lesson['id']}: \"{lesson['title']}\"")
            log.info(f"  Words: {lesson['word_count']}")
            log.info(f"  Preview: {lesson['text'][:150]}...")

        return True

    conn = sqlite3.connect(str(DB_PATH))

    try:
        # Check if lessons already imported
        existing = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]

        if existing > 0 and not reset:
            log.info(f"Lessons already imported ({existing} lessons). Use --reset to re-import.")
            return True

        if reset and existing > 0:
            log.info(f"Resetting {existing} existing lessons...")
            conn.execute("DELETE FROM lessons")

        # Import lessons
        log.info(f"Importing {len(lessons)} lessons...")

        for lesson in lessons:
            # Allow special IDs: 0 (Part 1 Intro), 500 (Part 2 Intro), and 1-365
            conn.execute(
                """INSERT OR REPLACE INTO lessons (id, title, text, word_count)
                   VALUES (?, ?, ?, ?)""",
                (lesson['id'], lesson['title'], lesson['text'], lesson['word_count'])
            )

        conn.commit()

        # Verify
        count = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
        log.info(f"Successfully imported {count} lessons")

        # Show summary
        total_words = conn.execute("SELECT SUM(word_count) FROM lessons").fetchone()[0]
        avg_words = total_words // count if count else 0
        log.info(f"Total words: {total_words:,} | Average per lesson: {avg_words}")

        return True

    except sqlite3.Error as e:
        log.error(f"Database error: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import ACIM Workbook lessons")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--reset", action="store_true", help="Clear and re-import all lessons")
    args = parser.parse_args()

    print("\n=== ACIM Daily Lessons — Import Workbook ===\n")

    success = import_lessons(dry_run=args.dry_run, reset=args.reset)

    if success:
        if args.dry_run:
            print("\nDry run complete. Use without --dry-run to import.")
        else:
            print("\nImport successful!")
            print("Next step: python lessons.py --status")
    else:
        print("\nImport failed. Check the logs above.")


if __name__ == "__main__":
    main()
