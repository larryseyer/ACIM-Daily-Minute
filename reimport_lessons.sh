#!/bin/bash
# Re-import lessons with fixed title extraction
cd "$(dirname "$0")"

echo "=== Re-importing lessons with fixed titles ==="
python3 import_lessons.py --reset

echo ""
echo "=== Verifying fix ==="
python3 -c "
import sqlite3
conn = sqlite3.connect('data/acim.db')
row = conn.execute('SELECT id, title, substr(text, 1, 150) as preview FROM lessons WHERE id = 1').fetchone()
print('Lesson 1:')
print(f'  Title: {row[1]}')
print(f'  Text preview: {row[2][:80]}...')
"
