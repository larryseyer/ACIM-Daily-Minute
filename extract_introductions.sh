#!/bin/bash
# Extract and preview the Workbook Introductions
cd "$(dirname "$0")"

echo "=== Part 1 Introduction Preview (lines 478-550) ==="
sed -n '478,550p' corrected_text/ACIM_Workbook.txt

echo ""
echo "=== Part 2 Introduction Preview (lines 13018-13100) ==="
sed -n '13018,13100p' corrected_text/ACIM_Workbook.txt
