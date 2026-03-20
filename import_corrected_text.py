#!/usr/bin/env python3
"""
import_corrected_text.py — Import corrected text files into the segments database.

Reads from corrected_text/*.txt and creates segments for the ACIM Daily Minute pipeline.

Usage:
    python import_corrected_text.py              # Preview (dry run)
    python import_corrected_text.py --apply      # Import to database
    python import_corrected_text.py --clear      # Clear and reimport
"""

import argparse
import re
import sqlite3
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent
CORRECTED_DIR = BASE_DIR / "corrected_text"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "acim.db"

# Target segment size (words) - aim for ~1 minute of audio at 150-180 wpm
MIN_WORDS = 140
TARGET_WORDS = 180
MAX_WORDS = 250

# Map corrected filenames to source identifiers and content start markers
# The marker is text that signals where actual content begins (skipping TOC)
SOURCE_MAP = {
    "ACIM_Text_Part_A.txt": {
        "name": "Text Part A",
        "start_marker": "As preface to this edition",  # Preface begins
    },
    "ACIM_Text_Part_B.txt": {
        "name": "Text Part B",
        "start_marker": "fifteen",  # Chapter 15 begins
    },
    "ACIM_Workbook.txt": {
        "name": "Workbook",
        "start_marker": "The training period is one year",  # Introduction begins
    },
    "ACIM_Manual.txt": {
        "name": "Manual",
        "start_marker": "This is a manual for",  # Introduction begins
    },
}


def init_db():
    """Initialize database with segments table if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pdf  TEXT NOT NULL,
            page_start  INTEGER,
            word_count  INTEGER,
            text        TEXT NOT NULL,
            used        INTEGER DEFAULT 0,
            used_date   TEXT,
            youtube_id  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving sentence boundaries."""
    # Split on sentence-ending punctuation followed by space or newline
    # Keep the punctuation with the sentence
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def create_segments(text: str, source: str) -> list[dict]:
    """Create segments from text, respecting sentence boundaries."""
    sentences = split_into_sentences(text)
    segments = []
    current_segment = []
    current_word_count = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        # If adding this sentence exceeds max and we have enough words, start new segment
        if current_word_count + sentence_words > MAX_WORDS and current_word_count >= MIN_WORDS:
            segment_text = ' '.join(current_segment)
            segments.append({
                'source': source,
                'text': segment_text,
                'word_count': current_word_count,
            })
            current_segment = [sentence]
            current_word_count = sentence_words
        else:
            current_segment.append(sentence)
            current_word_count += sentence_words

            # If we've reached target size and sentence ends cleanly, consider breaking
            if current_word_count >= TARGET_WORDS:
                # Continue to include more if next sentence is short
                pass

    # Add remaining text as final segment
    if current_segment:
        segment_text = ' '.join(current_segment)
        if current_word_count >= MIN_WORDS or not segments:
            segments.append({
                'source': source,
                'text': segment_text,
                'word_count': current_word_count,
            })
        else:
            # Merge with previous segment if too short
            if segments:
                prev = segments[-1]
                prev['text'] += ' ' + segment_text
                prev['word_count'] += current_word_count
            else:
                segments.append({
                    'source': source,
                    'text': segment_text,
                    'word_count': current_word_count,
                })

    return segments


def clean_text(text: str) -> str:
    """Clean text for segmentation - removes TOC, headers, titles."""
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip TOC lines (contain ". . ." patterns)
        if re.search(r'\.{2,}\s*\.{2,}', line) or re.search(r'\. \. \.', line):
            continue

        # Skip TOC lines that end with .NUMBER (page reference)
        if re.search(r'\.\d+$', line):
            continue

        # Skip lines that start with a number and contain quotes (TOC entries)
        if re.match(r'^\d+\s+"', line):
            continue

        # Skip lines that are just page numbers
        if re.match(r'^\d+$', line):
            continue

        # Skip Roman numeral page numbers (i, ii, iii, iv, etc.)
        if re.match(r'^[ivxlc]+$', line.lower()):
            continue

        # Skip header lines (ALL CAPS titles)
        if line.isupper() and len(line.split()) <= 10:
            continue

        # Skip "Contents" headers and part markers
        if line.lower() in ('contents', 'content', 'part 1', 'part 2', 'part i', 'part ii', 'workbook', 'manual', 'text'):
            continue

        # Skip lesson/chapter headers like "lesson 1" or "Chapter ONE"
        if re.match(r'^(lesson|chapter|review|introduction|preface)\s*\d*\s*$', line.lower()):
            continue

        # Skip "Review I", "Review II" etc.
        if re.match(r'^review\s+[ivx]+$', line.lower()):
            continue

        # Skip lines that are mostly numbers and dots (TOC structure)
        non_dot_chars = re.sub(r'[\d\s\.]', '', line)
        if len(non_dot_chars) < len(line) * 0.3:
            continue

        # Skip short lines that look like section headers (< 5 words, no sentence punctuation)
        if len(line.split()) < 5 and not re.search(r'[.!?]$', line):
            # But keep if it has lowercase (likely a sentence fragment)
            if not any(c.islower() for c in line):
                continue

        cleaned_lines.append(line)

    # Join and normalize whitespace
    text = ' '.join(cleaned_lines)
    text = re.sub(r'\s+', ' ', text)

    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")

    return text.strip()


def process_files(apply: bool = False, clear: bool = False):
    """Process all corrected text files."""
    txt_files = sorted(CORRECTED_DIR.glob("*.txt"))

    if not txt_files:
        print(f"No .txt files found in {CORRECTED_DIR}")
        return

    conn = init_db()

    if clear and apply:
        print("Clearing existing segments...")
        conn.execute("DELETE FROM segments")
        conn.commit()

    all_segments = []

    for txt_file in txt_files:
        if txt_file.name not in SOURCE_MAP:
            print(f"Skipping unknown file: {txt_file.name}")
            continue

        config = SOURCE_MAP[txt_file.name]
        source = config["name"]
        start_marker = config.get("start_marker", "")
        print(f"\nProcessing: {txt_file.name} → {source}")

        text = txt_file.read_text(encoding='utf-8')

        # Skip TOC by finding content start marker
        if start_marker:
            marker_pos = text.find(start_marker)
            if marker_pos > 0:
                skipped_chars = marker_pos
                text = text[marker_pos:]
                print(f"  Skipped {skipped_chars:,} chars of TOC (found '{start_marker[:30]}...')")

        text = clean_text(text)

        segments = create_segments(text, source)
        all_segments.extend(segments)

        word_counts = [s['word_count'] for s in segments]
        print(f"  Segments: {len(segments)}")
        print(f"  Words: {sum(word_counts):,} total")
        print(f"  Avg segment: {sum(word_counts) // len(segments)} words")

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total segments: {len(all_segments)}")
    print(f"Total words: {sum(s['word_count'] for s in all_segments):,}")

    if apply:
        print("\nImporting to database...")
        for seg in all_segments:
            conn.execute(
                "INSERT INTO segments (source_pdf, word_count, text) VALUES (?, ?, ?)",
                (seg['source'], seg['word_count'], seg['text'])
            )
        conn.commit()
        print(f"Imported {len(all_segments)} segments to {DB_PATH}")

        # Verify
        count = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        print(f"Database now has {count} segments")
    else:
        print("\nThis was a preview. Use --apply to import.")
        print("Use --clear --apply to clear existing and reimport.")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Import corrected text into segments database"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Import segments to database"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear existing segments before importing"
    )
    args = parser.parse_args()

    process_files(apply=args.apply, clear=args.clear)


if __name__ == "__main__":
    main()
