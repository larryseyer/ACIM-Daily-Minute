#!/bin/bash
# Reset the Daily Lessons upload log (run after deleting from YouTube)
cd "$(dirname "$0")"
python3 -c "
import sqlite3
conn = sqlite3.connect('data/acim.db')
conn.execute('DELETE FROM lessons_log')
conn.commit()
print('Lessons upload log cleared - ready to start fresh')
"
