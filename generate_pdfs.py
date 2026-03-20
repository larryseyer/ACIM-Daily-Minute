#!/usr/bin/env python3
"""
generate_pdfs.py — Generate corrected PDFs from golden Markdown files.

Creates professionally formatted PDFs from the corrected text in golden/*.md

Usage:
    python generate_pdfs.py              # Generate all PDFs
    python generate_pdfs.py --verify     # Verify PDFs were created
"""

import argparse
import re
import textwrap
from pathlib import Path

from fpdf import FPDF

# --- Unicode character replacements (for PDF compatibility) ---
UNICODE_REPLACEMENTS = {
    "\u201c": '"',  # Left double quote "
    "\u201d": '"',  # Right double quote "
    "\u2018": "'",  # Left single quote '
    "\u2019": "'",  # Right single quote '
    "\u2026": "...",  # Ellipsis …
    "\u2013": "-",  # En dash –
    "\u2014": "--",  # Em dash —
    "\u2757": "*",  # Decorative symbol ❉
}


def normalize_text(text: str) -> str:
    """Replace Unicode characters with ASCII equivalents for PDF compatibility."""
    for unicode_char, ascii_char in UNICODE_REPLACEMENTS.items():
        text = text.replace(unicode_char, ascii_char)
    return text


# --- Configuration ---
BASE_DIR = Path(__file__).parent
GOLDEN_DIR = BASE_DIR / "golden"
PDF_OUTPUT_DIR = BASE_DIR / "pdfs_corrected"

# Source files in order
GOLDEN_FILES = [
    "1_ACIM_Text_A.md",
    "2_ACIM_Text_B.md",
    "3_ACIM_Workbook.md",
    "4_ACIM_Manual.md",
]

# PDF formatting
PAGE_WIDTH = 210  # A4 width in mm
PAGE_HEIGHT = 297  # A4 height in mm
MARGIN_LEFT = 25
MARGIN_RIGHT = 25
MARGIN_TOP = 25
MARGIN_BOTTOM = 25
LINE_HEIGHT = 6
FONT_SIZE_BODY = 11
FONT_SIZE_TITLE = 24
FONT_SIZE_HEADER = 9


class ACIMPdf(FPDF):
    """Custom PDF class for ACIM books."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.set_auto_page_break(auto=True, margin=MARGIN_BOTTOM)

    def header(self):
        """Add header to each page."""
        if self.page_no() > 1:  # Skip header on first page
            self.set_font("Helvetica", "I", FONT_SIZE_HEADER)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, self.title, align="C")
            self.ln(15)
            self.set_text_color(0, 0, 0)

    def footer(self):
        """Add page number to footer."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", FONT_SIZE_HEADER)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def add_title_page(self, title: str, subtitle: str = ""):
        """Add a title page."""
        # Normalize any Unicode characters
        title = normalize_text(title)
        subtitle = normalize_text(subtitle)

        self.add_page()
        self.set_font("Helvetica", "B", FONT_SIZE_TITLE)

        # Center title vertically
        self.set_y(PAGE_HEIGHT / 3)
        self.cell(0, 20, title, align="C")
        self.ln(15)

        if subtitle:
            self.set_font("Helvetica", "I", 14)
            self.cell(0, 10, subtitle, align="C")
            self.ln(10)

        # Add "Corrected Edition" note
        self.set_y(PAGE_HEIGHT * 2 / 3)
        self.set_font("Helvetica", "I", 12)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, "Text-Corrected Edition", align="C")
        self.ln(8)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 8, "Spacing and typography errors corrected", align="C")
        self.set_text_color(0, 0, 0)

    def add_content(self, text: str):
        """Add body content with proper formatting."""
        # Normalize any Unicode characters
        text = normalize_text(text)

        self.set_font("Helvetica", "", FONT_SIZE_BODY)

        # Split into paragraphs (segments are separated by blank lines)
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Skip metadata lines (Source:, Segments:, etc.)
            if para.startswith("Source:") or para.startswith("Segments:") or para.startswith("Total words:"):
                continue

            # Skip horizontal rules
            if para == "---":
                self.ln(5)
                continue

            # Handle headers (lines starting with #)
            if para.startswith("# "):
                # This is the main title, skip as we have title page
                continue

            # Check if this looks like a section header (all caps, short)
            if len(para) < 100 and para.isupper():
                self.ln(5)
                self.set_font("Helvetica", "B", FONT_SIZE_BODY + 1)
                self.multi_cell(0, LINE_HEIGHT, para)
                self.set_font("Helvetica", "", FONT_SIZE_BODY)
                self.ln(3)
                continue

            # Regular paragraph
            # Clean up the text
            para = para.replace("\n", " ")  # Join wrapped lines
            para = re.sub(r" {2,}", " ", para)  # Normalize spaces

            # Add paragraph
            self.multi_cell(0, LINE_HEIGHT, para)
            self.ln(3)  # Space between paragraphs


def parse_golden_file(filepath: Path) -> tuple[str, str]:
    """Parse a golden .md file and return (title, content)."""
    content = filepath.read_text(encoding="utf-8")

    # Normalize Unicode characters for PDF compatibility
    content = normalize_text(content)

    # Extract title from first line (# Title)
    lines = content.split("\n")
    title = lines[0].replace("# ", "").strip() if lines else filepath.stem

    # Get content after the --- separator
    parts = content.split("---", 1)
    body = parts[1] if len(parts) > 1 else content

    return title, body


def generate_pdf(golden_file: Path, output_path: Path) -> bool:
    """Generate a PDF from a golden .md file."""
    try:
        title, content = parse_golden_file(golden_file)

        # Create PDF
        pdf = ACIMPdf(title)
        pdf.set_margins(MARGIN_LEFT, MARGIN_TOP, MARGIN_RIGHT)

        # Add title page
        pdf.add_title_page(
            title,
            "A Course In Miracles"
        )

        # Add content pages
        pdf.add_page()
        pdf.add_content(content)

        # Save PDF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))

        return True

    except Exception as e:
        print(f"Error generating {output_path.name}: {e}")
        return False


def generate_all_pdfs() -> dict:
    """Generate PDFs from all golden .md files."""
    PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    for md_name in GOLDEN_FILES:
        golden_path = GOLDEN_DIR / md_name
        if not golden_path.exists():
            print(f"Not found: {golden_path}")
            continue

        pdf_name = md_name.replace(".md", "_corrected.pdf")
        pdf_path = PDF_OUTPUT_DIR / pdf_name

        print(f"Generating: {pdf_name}...")
        success = generate_pdf(golden_path, pdf_path)

        if success:
            size_kb = pdf_path.stat().st_size / 1024
            results[pdf_name] = {
                "success": True,
                "path": str(pdf_path),
                "size_kb": round(size_kb, 1),
            }
            print(f"  Created: {pdf_name} ({size_kb:.1f} KB)")
        else:
            results[pdf_name] = {"success": False}

    return results


def verify_pdfs() -> bool:
    """Verify that all PDFs were created."""
    all_exist = True

    for md_name in GOLDEN_FILES:
        pdf_name = md_name.replace(".md", "_corrected.pdf")
        pdf_path = PDF_OUTPUT_DIR / pdf_name

        if pdf_path.exists():
            size_kb = pdf_path.stat().st_size / 1024
            print(f"VERIFIED: {pdf_name} ({size_kb:.1f} KB)")
        else:
            print(f"MISSING: {pdf_name}")
            all_exist = False

    return all_exist


def main():
    parser = argparse.ArgumentParser(
        description="Generate corrected PDFs from golden Markdown files"
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify PDFs were created"
    )

    args = parser.parse_args()

    if args.verify:
        print("Verifying PDF files...\n")
        success = verify_pdfs()
        if success:
            print("\nAll PDFs verified!")
        else:
            print("\nSome PDFs are missing!")
    else:
        print("Generating corrected PDFs...\n")
        results = generate_all_pdfs()

        print("\n" + "=" * 50)
        print("PDF GENERATION SUMMARY")
        print("=" * 50)

        successful = sum(1 for r in results.values() if r.get("success"))
        total_size = sum(r.get("size_kb", 0) for r in results.values())

        print(f"PDFs created: {successful}/{len(results)}")
        print(f"Total size: {total_size:.1f} KB")
        print(f"Output directory: {PDF_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
