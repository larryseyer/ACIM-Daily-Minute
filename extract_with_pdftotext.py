#!/usr/bin/env python3
"""
extract_with_pdftotext.py — Extract ACIM PDFs using pdftotext (Poppler).

Uses pdftotext for high-quality text extraction, then saves as:
- Plain text (.txt) for ElevenLabs TTS
- Markdown (.md) with basic formatting

Usage:
    python extract_with_pdftotext.py              # Extract all PDFs
    python extract_with_pdftotext.py --pdf 1      # Extract specific PDF (1-4)
    python extract_with_pdftotext.py --compare    # Compare with old extraction

Original PDFs in /pdfs/ are NEVER modified.
Output goes to /extracted_text/
"""

import argparse
import subprocess
import sys
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent
PDF_DIR = BASE_DIR / "pdfs"
OUTPUT_DIR = BASE_DIR / "extracted_text"

# PDF files in order
PDF_FILES = [
    ("1_ACIM_Text_A.pdf", "ACIM_Text_Part_A"),
    ("2_ACIM_Text_B.pdf", "ACIM_Text_Part_B"),
    ("3_ACIM_Workbook.pdf", "ACIM_Workbook"),
    ("4_ACIM_Manual.pdf", "ACIM_Manual"),
]


def check_pdftotext():
    """Verify pdftotext is installed."""
    try:
        result = subprocess.run(
            ["pdftotext", "-v"],
            capture_output=True,
            text=True
        )
        # pdftotext prints version to stderr
        version = result.stderr.strip().split('\n')[0] if result.stderr else "unknown"
        print(f"Using: {version}")
        return True
    except FileNotFoundError:
        print("ERROR: pdftotext not found. Install with: brew install poppler")
        return False


def extract_pdf(pdf_path: Path, use_layout: bool = True) -> str:
    """Extract text from PDF using pdftotext."""
    args = ["pdftotext"]
    if use_layout:
        args.append("-layout")  # Preserve layout/columns
    args.extend([str(pdf_path), "-"])  # Output to stdout

    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR extracting {pdf_path.name}: {result.stderr}")
        return ""

    return result.stdout


def clean_extracted_text(text: str) -> str:
    """
    Minimal cleaning of extracted text.

    pdftotext output is already clean - we only do essential fixes
    that won't introduce new errors.
    """
    # Replace common ligatures (these are real characters in PDFs)
    ligatures = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }
    for lig, repl in ligatures.items():
        text = text.replace(lig, repl)

    # Remove decorative symbols
    text = text.replace("❉", "")

    return text


def save_plain_text(text: str, output_path: Path):
    """Save as plain text for ElevenLabs."""
    # For TTS, we want clean flowing text
    # Remove excessive blank lines but keep paragraph breaks
    lines = text.split('\n')
    cleaned_lines = []
    prev_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False

    output_path.write_text('\n'.join(cleaned_lines), encoding='utf-8')
    print(f"  Saved: {output_path}")


def save_markdown(text: str, title: str, output_path: Path):
    """Save as markdown with basic formatting."""
    # Add title
    md_content = f"# {title}\n\n"
    md_content += text

    output_path.write_text(md_content, encoding='utf-8')
    print(f"  Saved: {output_path}")


def extract_all(pdf_indices: list = None):
    """Extract specified PDFs (or all if none specified)."""
    if not check_pdftotext():
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which PDFs to process
    if pdf_indices:
        to_process = [(i-1, PDF_FILES[i-1]) for i in pdf_indices if 1 <= i <= len(PDF_FILES)]
    else:
        to_process = list(enumerate(PDF_FILES))

    for idx, (pdf_name, output_base) in to_process:
        pdf_path = PDF_DIR / pdf_name

        if not pdf_path.exists():
            print(f"WARNING: PDF not found: {pdf_path}")
            continue

        print(f"\nExtracting: {pdf_name}")

        # Extract with pdftotext
        raw_text = extract_pdf(pdf_path, use_layout=True)
        if not raw_text:
            continue

        # Clean (minimal - just ligatures and symbols)
        cleaned_text = clean_extracted_text(raw_text)

        # Save plain text
        txt_path = OUTPUT_DIR / f"{output_base}.txt"
        save_plain_text(cleaned_text, txt_path)

        # Save markdown
        md_path = OUTPUT_DIR / f"{output_base}.md"
        title = output_base.replace("_", " ")
        save_markdown(cleaned_text, title, md_path)

        # Stats
        word_count = len(cleaned_text.split())
        line_count = len(cleaned_text.split('\n'))
        print(f"  Words: {word_count:,}, Lines: {line_count:,}")

    print(f"\nOutput directory: {OUTPUT_DIR}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract ACIM PDFs using pdftotext"
    )
    parser.add_argument(
        "--pdf", type=int, nargs="+",
        help="Specific PDF number(s) to extract (1-4)"
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare extraction with database content"
    )
    args = parser.parse_args()

    if args.compare:
        print("Compare mode not yet implemented")
        return

    extract_all(args.pdf)


if __name__ == "__main__":
    main()
