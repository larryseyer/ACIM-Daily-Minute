#!/bin/bash
# Test Daily Lessons pipeline (dry run - no upload)
cd "$(dirname "$0")"
python3 lessons.py --dry-run --lesson 1 --force
