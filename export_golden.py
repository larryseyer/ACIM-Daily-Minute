#!/usr/bin/env python3
"""
export_golden.py — Export corrected ACIM text to golden Markdown files.

Creates a 'golden/' directory with one .md file per source PDF,
containing all corrected text segments in order.

Usage:
    python export_golden.py              # Export to golden/ directory
    python export_golden.py --verify     # Verify export matches database
"""

import argparse
import sqlite3
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "acim.db"
GOLDEN_DIR = BASE_DIR / "golden"

# Source PDFs in order
PDF_FILES = [
    "1_ACIM_Text_A.pdf",
    "2_ACIM_Text_B.pdf",
    "3_ACIM_Workbook.pdf",
    "4_ACIM_Manual.pdf",
]


def connect_db() -> sqlite3.Connection:
    """Connect to the database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def export_golden(conn: sqlite3.Connection) -> dict:
    """Export all segments to golden .md files, organized by source PDF."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    stats = {}

    for pdf_name in PDF_FILES:
        # Get all segments for this PDF in order
        cursor = conn.execute(
            """
            SELECT id, page_start, word_count, text
            FROM segments
            WHERE source_pdf = ?
            ORDER BY id
            """,
            (pdf_name,)
        )
        segments = cursor.fetchall()

        if not segments:
            print(f"No segments found for {pdf_name}")
            continue

        # Create markdown filename
        md_name = pdf_name.replace(".pdf", ".md")
        md_path = GOLDEN_DIR / md_name

        # Build markdown content
        lines = []
        lines.append(f"# {pdf_name.replace('.pdf', '').replace('_', ' ')}")
        lines.append("")
        lines.append(f"Source: `{pdf_name}`")
        lines.append(f"Segments: {len(segments)}")
        lines.append(f"Total words: {sum(s['word_count'] for s in segments)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for seg in segments:
            # Add segment text (no extra formatting to preserve original structure)
            lines.append(seg["text"])
            lines.append("")  # Blank line between segments

        # Write to file
        content = "\n".join(lines)
        md_path.write_text(content, encoding="utf-8")

        stats[pdf_name] = {
            "segments": len(segments),
            "words": sum(s["word_count"] for s in segments),
            "file": str(md_path),
        }

        print(f"Exported: {md_path.name} ({len(segments)} segments)")

    return stats


def verify_export(conn: sqlite3.Connection) -> bool:
    """Verify that exported files match database content."""
    all_match = True

    for pdf_name in PDF_FILES:
        md_name = pdf_name.replace(".pdf", ".md")
        md_path = GOLDEN_DIR / md_name

        if not md_path.exists():
            print(f"MISSING: {md_path}")
            all_match = False
            continue

        # Read file content
        content = md_path.read_text(encoding="utf-8")

        # Get segments from database
        cursor = conn.execute(
            "SELECT text FROM segments WHERE source_pdf = ? ORDER BY id",
            (pdf_name,)
        )
        segments = cursor.fetchall()

        # Verify each segment is in the file
        missing = 0
        for seg in segments:
            if seg["text"] not in content:
                missing += 1

        if missing > 0:
            print(f"MISMATCH: {md_name} - {missing} segments not found in file")
            all_match = False
        else:
            print(f"VERIFIED: {md_name} - all {len(segments)} segments present")

    return all_match


def main():
    parser = argparse.ArgumentParser(
        description="Export corrected ACIM text to golden Markdown files"
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify export matches database content"
    )

    args = parser.parse_args()

    conn = connect_db()

    try:
        if args.verify:
            print("Verifying golden master files...\n")
            success = verify_export(conn)
            if success:
                print("\nAll files verified successfully!")
            else:
                print("\nVerification FAILED - some files need re-export")
        else:
            print("Exporting to golden master files...\n")
            stats = export_golden(conn)

            print("\n" + "=" * 50)
            print("EXPORT SUMMARY")
            print("=" * 50)
            total_segments = sum(s["segments"] for s in stats.values())
            total_words = sum(s["words"] for s in stats.values())
            print(f"Files created: {len(stats)}")
            print(f"Total segments: {total_segments}")
            print(f"Total words: {total_words}")
            print(f"Output directory: {GOLDEN_DIR}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
