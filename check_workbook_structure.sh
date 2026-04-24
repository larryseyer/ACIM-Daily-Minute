#!/bin/bash
# Check workbook file structure to see Introduction content
cd "$(dirname "$0")"

echo "=== Searching for INTRODUCTION and PART markers ==="
grep -n -i "introduction\|part 1\|part 2" corrected_text/ACIM_Workbook.txt | head -30

echo ""
echo "=== First 100 lines of workbook (to see structure) ==="
head -100 corrected_text/ACIM_Workbook.txt
