#!/bin/bash
# Check lesson 1 data to see title vs text content
cd "$(dirname "$0")"
python3 -c "
import sqlite3
conn = sqlite3.connect('data/acim.db')
row = conn.execute('SELECT id, title, substr(text, 1, 300) as text_preview FROM lessons WHERE id = 1').fetchone()
print('=== Lesson 1 Data ===')
print(f'ID: {row[0]}')
print(f'Title: {row[1]}')
print(f'Text starts with:')
print(row[2])
print('...')
"
