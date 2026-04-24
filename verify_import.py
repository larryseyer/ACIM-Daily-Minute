#!/usr/bin/env python3
"""Verify text sections import - shows first 5 sections with preview."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "acim.db"

if not DB_PATH.exists():
    print(f"Database not found: {DB_PATH}")
    exit(1)

conn = sqlite3.connect(str(DB_PATH))
rows = conn.execute(
    'SELECT id, chapter_num, section_title, substr(text, 1, 100) FROM text_sections ORDER BY id LIMIT 5'
).fetchall()

print("\n=== First 5 Text Sections ===\n")
for r in rows:
    print(f"{r[0]}. Chapter {r[1]} - {r[2]}")
    print(f"   {r[3]}...")
    print()

# Summary stats
total = conn.execute('SELECT COUNT(*) FROM text_sections').fetchone()[0]
with_intro = conn.execute("SELECT COUNT(*) FROM text_sections WHERE section_title = 'Introduction'").fetchone()[0]
print(f"=== Summary ===")
print(f"Total sections: {total}")
print(f"Chapter introductions: {with_intro}")
conn.close()
