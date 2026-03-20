#!/usr/bin/env python3
"""
pdf_extractor.py — One-time script to extract ACIM PDFs into SQLite segments.

Reads all 4 PDFs in order, extracts clean text, chunks into ~130-150 word
segments at natural sentence boundaries, and stores them in SQLite.

Usage:
    python pdf_extractor.py              # Extract and import
    python pdf_extractor.py --reset      # Clear DB and re-import
    python pdf_extractor.py --status     # Show segment counts
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

import nltk
from PyPDF2 import PdfReader
from dotenv import load_dotenv

load_dotenv()

# Ensure NLTK punkt tokenizer is available
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)

# --- Configuration ---
BASE_DIR = Path(__file__).parent
PDF_DIR = BASE_DIR / os.getenv("PDF_DIR", "pdfs")
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
DB_PATH = DATA_DIR / "acim.db"

TARGET_WORDS = 160
MIN_WORDS = 140
MAX_WORDS = 200

# Expected PDF order
PDF_FILES = [
    "1_ACIM_Text_A.pdf",
    "2_ACIM_Text_B.pdf",
    "3_ACIM_Workbook.pdf",
    "4_ACIM_Manual.pdf",
]

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def init_db() -> sqlite3.Connection:
    """Create database and tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS upload_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id   INTEGER REFERENCES segments(id),
            upload_date  TEXT NOT NULL,
            youtube_id   TEXT,
            youtube_url  TEXT,
            audio_file   TEXT,
            video_file   TEXT,
            success      INTEGER DEFAULT 0,
            error_msg    TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def clean_text(raw: str) -> str:
    """Clean extracted PDF text for chunking."""
    text = raw

    # --- Ligature Replacements ---
    # PDFs often contain typographic ligatures that cause TTS mispronunciation
    ligatures = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
    for lig, repl in ligatures.items():
        text = text.replace(lig, repl)

    # --- Capital+Space Pattern Fixes ---
    # PDF extraction sometimes adds errant spaces after capital letters
    capital_space_fixes = {
        "T ext": "Text", "T erms": "Terms", "T eacher": "Teacher",
        "T eaching": "Teaching", "T he": "The", "T o": "To", "T ime": "Time",
        "T ruth": "Truth", "T hink": "Think", "T hought": "Thought",
        "T houghts": "Thoughts", "T his": "This", "T hat": "That",
        "T here": "There", "T hey": "They", "T hen": "Then", "T hose": "Those",
        "T hus": "Thus", "Y ou": "You", "Y our": "Your", "Y et": "Yet",
        "Y es": "Yes", "W orld": "World", "W ords": "Words", "W ith": "With",
        "W hat": "What", "W hen": "When", "W here": "Where", "W hich": "Which",
        "W ho": "Who", "W hy": "Why", "W ill": "Will", "W ay": "Way", "W e": "We",
        "H oly": "Holy", "H is": "His", "H im": "Him", "H ere": "Here",
        "H ow": "How", "H eaven": "Heaven", "S pirit": "Spirit", "S on": "Son",
        "S oul": "Soul", "S elf": "Self", "F ather": "Father", "G od": "God",
        "L ove": "Love", "L ight": "Light", "M ind": "Mind", "C hrist": "Christ",
        "A tonement": "Atonement", "A nd": "And", "B ut": "But", "I f": "If",
        "I n": "In", "I t": "It", "I s": "Is", "O f": "Of", "O n": "On",
        "O r": "Or", "O ne": "One", "A ll": "All", "A re": "Are", "A s": "As",
        "A t": "At", "B e": "Be", "B y": "By", "N ot": "Not", "N o": "No", "S o": "So",
    }
    for pattern, replacement in capital_space_fixes.items():
        text = text.replace(pattern, replacement)

    # --- Spurious Space Fixes ---
    spurious_fixes = {
        "cour se": "course", "for give": "forgive",
        "for giveness": "forgiveness", "per ception": "perception",
        "mir acle": "miracle", "mir acles": "miracles",
        "infinitelyabundant": "infinitely abundant",
        "eternallyvital": "eternally vital",
    }
    for pattern, replacement in spurious_fixes.items():
        text = text.replace(pattern, replacement)

    # --- Remove Artifacts ---
    text = re.sub(r"PREFACE\s+[ivxIVX]+", "", text)  # PREFACE iii, etc.
    text = re.sub(r"P\s+R\s+E\s+F\s+A\s+C\s+E", "PREFACE", text)  # P R E F A C E
    text = re.sub(r"❉", "", text)  # Decorative symbol

    # Fix hyphenated line breaks
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Collapse multiple whitespace/newlines into single space
    text = re.sub(r"\s+", " ", text)
    # Strip footnote markers (lone numbers or asterisks mid-sentence)
    text = re.sub(r"\s*[\*†‡]\s*", " ", text)
    # Remove stray page numbers that appear alone
    text = re.sub(r"\s+\d{1,3}\s+", " ", text)

    # --- Fix Missing Spaces After Punctuation ---
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)  # .This -> . This
    text = re.sub(r',([a-z])', r', \1', text)  # ,if -> , if

    # Final whitespace normalization
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def extract_pdf_text(pdf_path: Path) -> list:
    """Extract text from PDF, returning list of (text, page_number) tuples."""
    pages = []
    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text()
        if raw:
            cleaned = clean_text(raw)
            if cleaned:
                pages.append((cleaned, i))
    return pages


def chunk_text(full_text: str) -> list[str]:
    """Split text into ~130-150 word segments at sentence boundaries."""
    sentences = nltk.sent_tokenize(full_text)
    chunks = []
    current = []
    count = 0
    for sent in sentences:
        words = len(sent.split())
        if count + words > MAX_WORDS and count >= MIN_WORDS:
            chunks.append(" ".join(current))
            current = [sent]
            count = words
        else:
            current.append(sent)
            count += words
    if current:
        chunk = " ".join(current)
        # If the last chunk is too short, merge with previous
        if count < MIN_WORDS and chunks:
            chunks[-1] = chunks[-1] + " " + chunk
        else:
            chunks.append(chunk)
    return chunks


def extract_and_store(conn: sqlite3.Connection) -> int:
    """Extract all PDFs and store segments in database."""
    total = 0
    for pdf_name in PDF_FILES:
        pdf_path = PDF_DIR / pdf_name
        if not pdf_path.exists():
            log.warning(f"PDF not found: {pdf_path}")
            continue

        log.info(f"Extracting: {pdf_name} ...")
        pages = extract_pdf_text(pdf_path)
        if not pages:
            log.warning(f"No text extracted from {pdf_name}")
            continue

        # Combine all page text, tracking approximate page starts
        full_text = " ".join(text for text, _ in pages)
        chunks = chunk_text(full_text)

        # Estimate page start for each chunk
        page_boundaries = []
        char_offset = 0
        for text, page_num in pages:
            page_boundaries.append((char_offset, page_num))
            char_offset += len(text) + 1  # +1 for the joining space

        chunk_offset = 0
        for chunk in chunks:
            # Find approximate page for this chunk
            page_start = 1
            for boundary_offset, page_num in page_boundaries:
                if chunk_offset >= boundary_offset:
                    page_start = page_num
                else:
                    break

            word_count = len(chunk.split())
            conn.execute(
                "INSERT INTO segments (source_pdf, page_start, word_count, text) VALUES (?, ?, ?, ?)",
                (pdf_name, page_start, word_count, chunk),
            )
            chunk_offset += len(chunk) + 1

        conn.commit()
        count = len(chunks)
        total += count
        log.info(f"  {pdf_name} ... {count} segments")

    return total


def show_status(conn: sqlite3.Connection):
    """Display current segment status."""
    total = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    used = conn.execute("SELECT COUNT(*) FROM segments WHERE used = 1").fetchone()[0]
    remaining = total - used

    print(f"\n=== ACIM Daily Minute — PDF Extractor Status ===")
    print(f"Segments total:     {total}")
    print(f"Segments used:      {used}")
    print(f"Segments remaining: {remaining}")

    if total > 0:
        years = remaining / 365.25
        print(f"Corpus exhaustion:  ~{years:.1f} years from now")

    # Per-PDF breakdown
    print(f"\nPer-PDF breakdown:")
    for pdf_name in PDF_FILES:
        count = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE source_pdf = ?", (pdf_name,)
        ).fetchone()[0]
        print(f"  {pdf_name}: {count} segments")

    # Upload stats
    uploads = conn.execute(
        "SELECT COUNT(*) FROM upload_log WHERE success = 1"
    ).fetchone()[0]
    if uploads > 0:
        last = conn.execute(
            "SELECT upload_date FROM upload_log WHERE success = 1 ORDER BY upload_date DESC LIMIT 1"
        ).fetchone()
        print(f"\nSuccessful uploads: {uploads}")
        if last:
            print(f"Last upload:        {last[0]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="ACIM PDF → SQLite segment extractor")
    parser.add_argument(
        "--reset", action="store_true", help="Clear all segments and re-import"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show segment counts and exit"
    )
    args = parser.parse_args()

    conn = init_db()

    if args.status:
        show_status(conn)
        conn.close()
        return

    if args.reset:
        log.info("Resetting database — clearing all segments...")
        conn.execute("DELETE FROM segments")
        conn.commit()

    # Check if segments already exist
    existing = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    if existing > 0 and not args.reset:
        log.info(
            f"Database already has {existing} segments. Use --reset to re-import."
        )
        show_status(conn)
        conn.close()
        return

    total = extract_and_store(conn)
    years = total / 365.25
    log.info(f"Total: {total} segments (~{years:.1f} years of daily content)")
    log.info(f"Saved to {DB_PATH}")

    show_status(conn)
    conn.close()


if __name__ == "__main__":
    main()
