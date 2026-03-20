#!/usr/bin/env python3
"""
fix_extracted_text.py — Fix the few actual spacing errors in extracted text.

These are genuine errors found in the original PDFs (not extraction artifacts).

Usage:
    python fix_extracted_text.py                  # Preview fixes
    python fix_extracted_text.py --apply          # Apply fixes
"""

import argparse
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent
EXTRACTED_DIR = BASE_DIR / "extracted_text"
CORRECTED_DIR = BASE_DIR / "corrected_text"

# Split words from letter-spaced headers (pdftotext interprets tracking as spaces)
# These appear in stylized chapter/lesson headers
HEADER_SPLITS = {
    # Lesson headers in Workbook (138 occurrences)
    "le sson": "lesson",

    # Chapter numbers in Text Part B (chapters 20-29, lowercase)
    "twe nty": "twenty",
    "thre e": "three",
    "seve n": "seven",
    "eigh t": "eight",

    # Title and chapter headers in Text Part A (uppercase, fully letter-spaced)
    "M IRACLES": "MIRACLES",
    "P R E FA C E": "PREFACE",
    "T WO": "TWO",
    "T W E LV E": "TWELVE",
    "T H I RT E E N": "THIRTEEN",
    "F O U RT E E N": "FOURTEEN",
    "T H I RT Y": "THIRTY",
}

# Actual spacing errors found in original PDFs
# Format: "error": "correction"
SPACING_FIXES = {
    # Missing space between words
    "inbetween": "in between",
    "inspite": "in spite",

    # Missing space before "You" (prayer context)
    "inYou": "in You",
    "hearYour": "hear Your",
    "whomYou": "whom You",
    "andYou": "and You",

    # Table of contents number joins (these appear in TOC)
    "97and": "97 and",
    "and100": "and 100",
    "and110": "and 110",
}


def fix_text(text: str) -> tuple[str, dict]:
    """Apply fixes and return (fixed_text, changes_made)."""
    changes = {}

    # Remove form feed characters (page breaks from PDF)
    if '\f' in text:
        count = text.count('\f')
        changes['[form feed]'] = count
        text = text.replace('\f', '')

    # Apply header split fixes first (e.g., "le sson" → "lesson")
    for error, correction in HEADER_SPLITS.items():
        if error in text:
            count = text.count(error)
            changes[error] = count
            text = text.replace(error, correction)

    # Apply spacing fixes (joined words and original PDF errors)
    for error, correction in SPACING_FIXES.items():
        if error in text:
            count = text.count(error)
            changes[error] = count
            text = text.replace(error, correction)

    return text, changes


def process_files(apply: bool = False):
    """Process all text files."""
    txt_files = sorted(EXTRACTED_DIR.glob("*.txt"))

    if not txt_files:
        print(f"No .txt files found in {EXTRACTED_DIR}")
        return

    if apply:
        CORRECTED_DIR.mkdir(parents=True, exist_ok=True)

    total_changes = {}

    for txt_file in txt_files:
        print(f"\nProcessing: {txt_file.name}")

        text = txt_file.read_text(encoding='utf-8')
        fixed_text, changes = fix_text(text)

        if changes:
            for error, count in changes.items():
                # Look up correction in both dictionaries
                correction = HEADER_SPLITS.get(error) or SPACING_FIXES.get(error) or "(removed)"
                print(f"  {error} → {correction} ({count}x)")
                total_changes[error] = total_changes.get(error, 0) + count

            if apply:
                # Save to corrected directory
                output_path = CORRECTED_DIR / txt_file.name
                output_path.write_text(fixed_text, encoding='utf-8')
                print(f"  Saved: {output_path}")

                # Also create markdown version
                md_name = txt_file.stem + ".md"
                md_path = CORRECTED_DIR / md_name
                title = txt_file.stem.replace("_", " ")
                md_content = f"# {title}\n\n{fixed_text}"
                md_path.write_text(md_content, encoding='utf-8')
                print(f"  Saved: {md_path}")
        else:
            print("  No fixes needed")
            if apply:
                # Copy unchanged
                output_path = CORRECTED_DIR / txt_file.name
                output_path.write_text(text, encoding='utf-8')

                # Also create markdown version
                md_name = txt_file.stem + ".md"
                md_path = CORRECTED_DIR / md_name
                title = txt_file.stem.replace("_", " ")
                md_content = f"# {title}\n\n{text}"
                md_path.write_text(md_content, encoding='utf-8')

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    if total_changes:
        total = sum(total_changes.values())
        print(f"Total fixes: {total}")
        for error, count in sorted(total_changes.items(), key=lambda x: -x[1]):
            print(f"  {error}: {count}")
    else:
        print("No fixes needed - text is clean!")

    if apply:
        print(f"\nCorrected files saved to: {CORRECTED_DIR}")
    else:
        print("\nThis was a preview. Use --apply to save corrected files.")


def main():
    parser = argparse.ArgumentParser(
        description="Fix spacing errors in extracted text"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply fixes and save to corrected_text/"
    )
    args = parser.parse_args()

    process_files(apply=args.apply)


if __name__ == "__main__":
    main()
