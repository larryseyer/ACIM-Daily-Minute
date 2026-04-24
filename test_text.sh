#!/bin/bash
# Test Text Series pipeline (dry run - no upload)
# Section 509 is the first text section
cd "$(dirname "$0")"
python3 text_chapters.py --dry-run --section 509
