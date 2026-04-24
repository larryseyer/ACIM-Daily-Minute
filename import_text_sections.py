#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_text_sections.py - Parse ACIM Text and populate text_sections table.

Extracts all sections from the corrected Text files (Parts A and B) and
stores them in the database for sequential posting.

Usage:
    python3 import_text_sections.py             # Import sections (skips if already done)
    python3 import_text_sections.py --dry-run   # Preview without writing to database
    python3 import_text_sections.py --reset     # Clear and re-import all sections
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
TEXT_PART_A = BASE_DIR / "corrected_text" / "ACIM_Text_Part_A.txt"
TEXT_PART_B = BASE_DIR / "corrected_text" / "ACIM_Text_Part_B.txt"

# Mapping of spelled-out chapter numbers to integers
CHAPTER_WORD_TO_NUM = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
    'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
    'nineteen': 19, 'twenty': 20, 'twentyone': 21, 'twentytwo': 22,
    'twentythree': 23, 'twentyfour': 24, 'twentyfive': 25,
    'twentysix': 26, 'twentyseven': 27, 'twentyeight': 28,
    'twentynine': 29, 'thirty': 30, 'thirtyone': 31,
}


def word_to_chapter_num(word):
    """Convert a chapter word like 'one', 'twenty one', 'TWENTY-THREE' to number.

    Also handles spaced-out words like 'Th r e e', 'tw e lv e', 'thirte e n', 'fourte e n'.
    """
    # Normalize: lowercase, remove hyphens and ALL spaces
    normalized = word.lower().replace('-', '').replace(' ', '')
    return CHAPTER_WORD_TO_NUM.get(normalized)


def parse_toc_from_file(content):
    """
    Parse the Table of Contents to get expected section titles per chapter.
    Returns dict: {chapter_num: {'title': str, 'sections': [str, ...]}}
    """
    toc = {}

    # Find TOC region - between "Contents" and the first actual chapter
    # The TOC ends when we hit "one" (lowercase) which starts Chapter 1
    toc_start = content.find('Contents')
    if toc_start == -1:
        log.warning("Could not find 'Contents' in file")
        return toc

    # Find end of TOC (start of chapter one)
    toc_end_match = re.search(r'^\s*one\s*$', content[toc_start:], re.MULTILINE | re.IGNORECASE)
    if not toc_end_match:
        log.warning("Could not find chapter 'one' marker")
        return toc

    toc_text = content[toc_start:toc_start + toc_end_match.start()]
    lines = toc_text.split('\n')

    current_chapter = None
    pending_twenty_thirty = None  # For handling split lines like "TWENTY\nONE"

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Check for standalone "TWENTY" or "THIRTY" (compound number first part)
        if re.match(r'^(TWENTY|THIRTY)$', stripped, re.IGNORECASE):
            pending_twenty_thirty = stripped.lower()
            continue

        # Check for compound number second part: "ONE   CHAPTER TITLE . . . 123"
        if pending_twenty_thirty:
            compound_match = re.match(
                r'^(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE)\s+(.+?)\s*(?:\.\s*)+\d+',
                stripped, re.IGNORECASE
            )
            if compound_match:
                chapter_word = pending_twenty_thirty + compound_match.group(1).lower()
                chapter_num = word_to_chapter_num(chapter_word)
                if chapter_num:
                    chapter_title = compound_match.group(2).strip()
                    toc[chapter_num] = {'title': chapter_title, 'sections': []}
                    current_chapter = chapter_num
                pending_twenty_thirty = None
                continue
            else:
                pending_twenty_thirty = None

        # Check for simple chapter line: "ONE   INTRODUCTION TO MIRACLES . . . 1"
        chapter_match = re.match(
            r'^(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|'
            r'ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|'
            r'EIGHTEEN|NINETEEN|TWENTY|THIRTY)\s+(.+?)\s*(?:\.\s*)+\d+',
            stripped, re.IGNORECASE
        )
        if chapter_match:
            chapter_word = chapter_match.group(1).lower()
            chapter_num = word_to_chapter_num(chapter_word)
            if chapter_num:
                chapter_title = chapter_match.group(2).strip()
                toc[chapter_num] = {'title': chapter_title, 'sections': []}
                current_chapter = chapter_num
            continue

        # Check for section line (indented, has dots and page number)
        # Skip nested subsections (Roman numerals like "I.The Desire...")
        if current_chapter and re.match(r'^\s{3,}', line):
            # Skip if it starts with Roman numeral pattern
            if re.match(r'^\s+(I{1,4}V?|VI{0,3})\s*\.', stripped):
                continue

            section_match = re.match(r'^(.+?)\s*(?:\.\s*)+\d+$', stripped)
            if section_match:
                section_title = section_match.group(1).strip()
                # Clean up extra whitespace
                section_title = re.sub(r'\s+', ' ', section_title)
                if section_title and not section_title.startswith('I.') and not section_title.startswith('II.'):
                    toc[current_chapter]['sections'].append(section_title)

    return toc


def find_chapter_boundaries(content):
    """
    Find chapter boundaries in the text content.
    Returns list of (chapter_num, chapter_title, start_pos, end_pos)
    """
    boundaries = []
    seen_chapters = set()

    # First, find where the TOC ends (look for the actual chapter "one" marker)
    # The TOC contains "ONE" in uppercase as part of chapter listings,
    # but the actual chapter marker is lowercase "one" on its own line
    # after the TOC ends (around line 779 in the file)

    # Find "Contents" to locate TOC start
    toc_start = content.find('Contents')
    if toc_start == -1:
        toc_start = 0

    # The actual chapters start after a page number like "xxiv" followed by "one"
    # Look for the pattern: Roman numeral page, then "one" chapter marker
    content_start_match = re.search(
        r'xxiv\s*\n\s*(one)\s*\n',
        content[toc_start:],
        re.IGNORECASE
    )

    if content_start_match:
        content_start = toc_start + content_start_match.start()
    else:
        # Fallback: find first lowercase "one" on its own line after position 10000
        # (to skip the TOC which is in the first ~10000 chars)
        fallback_match = re.search(r'^\s*one\s*$', content[10000:], re.MULTILINE | re.IGNORECASE)
        if fallback_match:
            content_start = 10000 + fallback_match.start()
        else:
            content_start = 0

    # Now search for chapter markers only in the content area (after TOC)
    search_content = content[content_start:]

    # Pattern for chapter headers - handles:
    # "one", "twenty", "twenty one", "thirty one" etc.
    # Also handles spaced-out variants like "Th r e e", "tw e lv e", "thirte e n", "fourte e n"
    # Must be on its own line (possibly with whitespace)
    chapter_pattern = re.compile(
        r'^\s*(one|two|th\s*r\s*e\s*e|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|tw\s*e\s*lv\s*e|twelve|thirt\s*e\s*e\s*n|thirteen|'
        r'fourt\s*e\s*e\s*n|fourteen|fifteen|sixteen|seventeen|'
        r'eighteen|nineteen|'
        r'twenty(?:\s+(?:one|two|three|four|five|six|seven|eight|nine))?|'
        r'thirty(?:\s+one)?)\s*$',
        re.MULTILINE | re.IGNORECASE
    )

    matches = list(chapter_pattern.finditer(search_content))

    for i, match in enumerate(matches):
        chapter_word = match.group(1).strip()
        chapter_num = word_to_chapter_num(chapter_word)

        if chapter_num is None:
            continue

        # Skip if we've already seen this chapter (avoid duplicates from TOC remnants)
        if chapter_num in seen_chapters:
            continue
        seen_chapters.add(chapter_num)

        # Get the chapter title (next non-empty, non-page-number lines)
        title_search_start = match.end()
        title_lines = []
        for line in search_content[title_search_start:title_search_start + 500].split('\n'):
            line = line.strip()
            if not line:
                continue
            # Skip page numbers
            if re.match(r'^\d+$', line):
                continue
            # Skip Roman numerals (page numbers)
            if re.match(r'^[ivxlc]+$', line, re.IGNORECASE):
                continue
            # Skip if it looks like section content (starts lowercase, long)
            if line and line[0].islower() and len(line) > 50:
                break
            # Skip if it's another chapter word (malformed)
            if re.match(r'^(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty)$', line, re.IGNORECASE):
                continue
            title_lines.append(line)
            if len(title_lines) >= 3:
                break

        chapter_title = ' '.join(title_lines) if title_lines else f"Chapter {chapter_num}"

        # Adjust positions to account for content_start offset
        start_pos = content_start + match.start()

        boundaries.append((chapter_num, chapter_title, start_pos))

    # Sort by chapter number to ensure correct order
    boundaries.sort(key=lambda x: x[0])

    # Now calculate end positions based on sorted order
    final_boundaries = []
    for i, (chapter_num, chapter_title, start_pos) in enumerate(boundaries):
        if i + 1 < len(boundaries):
            end_pos = boundaries[i + 1][2]  # Start of next chapter
        else:
            end_pos = len(content)
        final_boundaries.append((chapter_num, chapter_title, start_pos, end_pos))

    return final_boundaries


def extract_sections_from_chapter(chapter_content, chapter_num, chapter_title, expected_sections):
    """
    Extract sections from a chapter's content.
    Returns list of section dicts.
    """
    sections = []

    if not expected_sections:
        log.warning(f"No expected sections for chapter {chapter_num}")
        return sections

    # Find each section by looking for ALL CAPS headers matching expected titles
    section_positions = []

    for section_title in expected_sections:
        # Create pattern to find this section header in ALL CAPS
        title_upper = section_title.upper()
        # Escape special regex chars
        escaped = re.escape(title_upper)
        # Allow flexible whitespace
        pattern_str = re.sub(r'\\ ', r'\\s+', escaped)
        # Allow optional space after commas (TOC may have "Peace,Teach" but text has "Peace, Teach")
        pattern_str = re.sub(r',', r',\\s*', pattern_str)
        # Allow hyphen to be space (TOC may have "Self-Concept" but text has "SELF CONCEPT")
        pattern_str = re.sub(r'\\-', r'[\\s-]', pattern_str)
        # Allow optional "THE " in patterns like "AND THE " (TOC has "and the" but text may omit "the")
        pattern_str = re.sub(r'AND\\s\+THE\\s\+', r'AND\\s+(?:THE\\s+)?', pattern_str)

        # Look for the title on its own line, with optional prefixes:
        # - Roman numerals: I. "To Have, Give All to All"
        # - "THE " prefix: Some sections add "THE" (e.g., "THE CONDITIONS OF FORGIVENESS")
        roman_prefix = r'(?:(?:I{1,3}V?|VI{0,3}|I?X)\.\s*)?'
        the_prefix = r'(?:THE\s+)?'
        pattern = re.compile(r'^' + roman_prefix + the_prefix + pattern_str + r'\s*$', re.MULTILINE | re.IGNORECASE)
        match = pattern.search(chapter_content)

        if match:
            section_positions.append((match.start(), match.end(), section_title))
        else:
            # Try more lenient matching - just first few words, with optional prefixes
            words = title_upper.split()
            if len(words) >= 2:
                partial = re.escape(' '.join(words[:3]))
                partial = re.sub(r'\\ ', r'\\s+', partial)
                partial = re.sub(r',', r',\\s*', partial)  # Handle comma spacing
                partial = re.sub(r'\\-', r'[\\s-]', partial)  # Hyphen can be space
                partial = re.sub(r'AND\\s\+THE\\s\+', r'AND\\s+(?:THE\\s+)?', partial)  # Optional "the"
                pattern = re.compile(r'^' + roman_prefix + the_prefix + partial + r'.*$', re.MULTILINE | re.IGNORECASE)
                match = pattern.search(chapter_content)
                if match:
                    section_positions.append((match.start(), match.end(), section_title))
                else:
                    log.debug(f"Ch.{chapter_num}: Section '{section_title}' not found")

    # Sort by position in chapter
    section_positions.sort(key=lambda x: x[0])

    # Check for chapter introduction (content before first section)
    if section_positions:
        first_section_start = section_positions[0][0]
        # Find where the chapter title ends (look for the title in uppercase)
        title_upper = chapter_title.upper()
        title_match = re.search(re.escape(title_upper), chapter_content, re.IGNORECASE)
        if title_match:
            intro_start = title_match.end()
        else:
            # Fallback: skip first few lines (chapter number, title)
            intro_start = 0
            lines = chapter_content.split('\n')
            char_count = 0
            for i, line in enumerate(lines[:5]):
                char_count += len(line) + 1
                # Skip chapter number line and title line
                if line.strip() and not re.match(r'^\d+$', line.strip()):
                    intro_start = char_count
                    break

        intro_text = chapter_content[intro_start:first_section_start].strip()
        intro_text = clean_section_text(intro_text)

        # Only add if there's substantial intro content (not just whitespace/page numbers)
        if len(intro_text) > 100:
            word_count = len(intro_text.split())
            char_count = len(intro_text)
            duration_minutes = word_count / 150.0

            sections.append({
                'chapter_num': chapter_num,
                'chapter_title': chapter_title,
                'section_num': 1,
                'section_title': 'Introduction',
                'text': intro_text,
                'word_count': word_count,
                'character_count': char_count,
                'estimated_duration_minutes': round(duration_minutes, 2),
            })
            log.info(f"Ch.{chapter_num}: Found introduction ({word_count} words)")

    # Extract content between section headers
    for i, (start_pos, header_end, section_title) in enumerate(section_positions):
        # Content starts after the header line
        content_start = header_end

        # Content ends at next section or end of chapter
        if i + 1 < len(section_positions):
            content_end = section_positions[i + 1][0]
        else:
            content_end = len(chapter_content)

        section_text = chapter_content[content_start:content_end].strip()
        section_text = clean_section_text(section_text)

        if len(section_text) < 100:
            log.debug(f"Ch.{chapter_num} Sec.{i+1}: Very short section ({len(section_text)} chars)")
            continue

        word_count = len(section_text.split())
        char_count = len(section_text)
        duration_minutes = word_count / 150.0

        sections.append({
            'chapter_num': chapter_num,
            'chapter_title': chapter_title,
            'section_num': len(sections) + 1,
            'section_title': section_title,
            'text': section_text,
            'word_count': word_count,
            'character_count': char_count,
            'estimated_duration_minutes': round(duration_minutes, 2),
        })

    return sections


def clean_section_text(text):
    """Clean up extracted section text."""
    # Remove page numbers (standalone numbers)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)

    # Remove chapter headers like "15 THE PURPOSE OF TIME"
    text = re.sub(r'^\d+\s+[A-Z][A-Z\s]+$', '', text, flags=re.MULTILINE)

    # Remove "TEXT" headers
    text = re.sub(r'^TEXT\s*$', '', text, flags=re.MULTILINE)

    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_preface_sections(content):
    """
    Extract preface sections (Chapter 0).
    """
    sections = []

    # Find "the use of terms" section title (standalone line, not embedded in publisher's note)
    use_of_terms_match = re.search(r'^\s*the use of terms\s*$', content, re.MULTILINE | re.IGNORECASE)
    if not use_of_terms_match:
        log.warning("Could not find 'the use of terms' section")
        return sections

    # Find where Chapter 1 starts
    chapter_one_match = re.search(r'^\s*one\s*$', content, re.MULTILINE | re.IGNORECASE)
    if not chapter_one_match:
        log.warning("Could not find Chapter 1")
        return sections

    # The preface content is between "the use of terms" and the TOC
    # Find the TOC start
    toc_match = re.search(r'Contents', content[use_of_terms_match.start():])
    if toc_match:
        section_end = use_of_terms_match.start() + toc_match.start()
    else:
        section_end = chapter_one_match.start()

    section_text = content[use_of_terms_match.end():section_end].strip()
    section_text = clean_section_text(section_text)

    if len(section_text) > 100:
        word_count = len(section_text.split())
        char_count = len(section_text)
        duration_minutes = word_count / 150.0

        sections.append({
            'chapter_num': 0,
            'chapter_title': 'Preface',
            'section_num': 1,
            'section_title': 'The Use of Terms',
            'text': section_text,
            'word_count': word_count,
            'character_count': char_count,
            'estimated_duration_minutes': round(duration_minutes, 2),
        })

    return sections


def parse_text_files():
    """
    Parse both Text Part A and Part B files and extract all sections.
    Returns list of section dicts.
    """
    all_sections = []

    if not TEXT_PART_A.exists():
        log.error(f"Text Part A not found: {TEXT_PART_A}")
        return []

    content_a = TEXT_PART_A.read_text(encoding='utf-8')

    if TEXT_PART_B.exists():
        content_b = TEXT_PART_B.read_text(encoding='utf-8')
        full_content = content_a + "\n\n" + content_b
    else:
        log.warning(f"Text Part B not found: {TEXT_PART_B}")
        full_content = content_a

    log.info(f"Total content length: {len(full_content):,} characters")

    # Parse TOC from Part A
    toc = parse_toc_from_file(content_a)
    log.info(f"Found {len(toc)} chapters in TOC")

    if len(toc) < 20:
        log.warning("TOC parsing may have failed - expected ~31 chapters")
        # Debug: show what we found
        for ch_num in sorted(toc.keys())[:5]:
            log.info(f"  TOC Ch.{ch_num}: {toc[ch_num]['title'][:40]}... ({len(toc[ch_num]['sections'])} sections)")

    # Extract preface sections
    log.info("Extracting preface sections...")
    preface_sections = extract_preface_sections(content_a)
    all_sections.extend(preface_sections)
    log.info(f"Extracted {len(preface_sections)} preface section(s)")

    # Find chapter boundaries in full content
    chapters = find_chapter_boundaries(full_content)
    log.info(f"Found {len(chapters)} chapter boundaries")

    # Extract sections from each chapter
    for chapter_num, chapter_title, start_pos, end_pos in chapters:
        chapter_content = full_content[start_pos:end_pos]

        if chapter_num in toc:
            toc_info = toc[chapter_num]
            expected_sections = toc_info['sections']
            # Use TOC title if cleaner
            if toc_info['title']:
                chapter_title = toc_info['title']

            sections = extract_sections_from_chapter(
                chapter_content, chapter_num, chapter_title, expected_sections
            )
            all_sections.extend(sections)
            log.info(f"Chapter {chapter_num}: {len(sections)} sections extracted (expected {len(expected_sections)})")
        else:
            log.warning(f"Chapter {chapter_num} not found in TOC")

    return all_sections


def import_sections(dry_run=False, reset=False):
    """Import parsed sections into the database."""

    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        log.error("Run migrate_db_text.py first!")
        return False

    sections = parse_text_files()

    if not sections:
        log.error("No sections parsed from text files!")
        return False

    if dry_run:
        log.info("\n=== DRY RUN - Preview ===")
        log.info(f"Total sections: {len(sections)}")

        # Group by chapter
        chapters = {}
        for s in sections:
            ch = s['chapter_num']
            if ch not in chapters:
                chapters[ch] = []
            chapters[ch].append(s)

        for ch_num in sorted(chapters.keys()):
            ch_sections = chapters[ch_num]
            ch_title = ch_sections[0]['chapter_title']
            total_words = sum(s['word_count'] for s in ch_sections)
            log.info(f"\nChapter {ch_num}: {ch_title}")
            log.info(f"  Sections: {len(ch_sections)}, Total words: {total_words:,}")
            for s in ch_sections[:3]:
                log.info(f"    {s['section_num']}. {s['section_title']} ({s['word_count']} words, ~{s['estimated_duration_minutes']:.1f} min)")
            if len(ch_sections) > 3:
                log.info(f"    ... and {len(ch_sections) - 3} more sections")

        total_words = sum(s['word_count'] for s in sections)
        total_duration = sum(s['estimated_duration_minutes'] for s in sections)
        log.info(f"\n=== Summary ===")
        log.info(f"Total sections: {len(sections)}")
        log.info(f"Total words: {total_words:,}")
        log.info(f"Total estimated duration: {total_duration:.0f} minutes ({total_duration/60:.1f} hours)")
        log.info(f"Average section: {total_words//len(sections)} words, {total_duration/len(sections):.1f} min")

        return True

    conn = sqlite3.connect(str(DB_PATH))

    try:
        existing = conn.execute("SELECT COUNT(*) FROM text_sections").fetchone()[0]

        if existing > 0 and not reset:
            log.info(f"Sections already imported ({existing} sections). Use --reset to re-import.")
            return True

        if reset and existing > 0:
            log.info(f"Resetting {existing} existing sections...")
            conn.execute("DELETE FROM text_sections")

        log.info(f"Importing {len(sections)} sections...")

        for section in sections:
            conn.execute(
                """INSERT INTO text_sections
                   (chapter_num, chapter_title, section_num, section_title,
                    text, word_count, character_count, estimated_duration_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (section['chapter_num'], section['chapter_title'],
                 section['section_num'], section['section_title'],
                 section['text'], section['word_count'],
                 section['character_count'], section['estimated_duration_minutes'])
            )

        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM text_sections").fetchone()[0]
        log.info(f"Successfully imported {count} sections")

        total_words = conn.execute("SELECT SUM(word_count) FROM text_sections").fetchone()[0]
        total_duration = conn.execute("SELECT SUM(estimated_duration_minutes) FROM text_sections").fetchone()[0]
        log.info(f"Total words: {total_words:,}")
        log.info(f"Total estimated duration: {total_duration:.0f} minutes ({total_duration/60:.1f} hours)")

        return True

    except sqlite3.Error as e:
        log.error(f"Database error: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import ACIM Text sections")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--reset", action="store_true", help="Clear and re-import all sections")
    args = parser.parse_args()

    print("\n=== ACIM Text Series - Import Sections ===\n")

    success = import_sections(dry_run=args.dry_run, reset=args.reset)

    if success:
        if args.dry_run:
            print("\nDry run complete. Use without --dry-run to import.")
        else:
            print("\nImport successful!")
            print("Next step: python3 text_chapters.py --status")
    else:
        print("\nImport failed. Check the logs above.")


if __name__ == "__main__":
    main()
