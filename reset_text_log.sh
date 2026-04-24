#!/bin/bash
# Reset the Text Series upload log (run after deleting from YouTube)
cd "$(dirname "$0")"
python3 -c "
import sqlite3
conn = sqlite3.connect('data/acim.db')
conn.execute('DELETE FROM text_upload_log')
conn.commit()
print('Text upload log cleared - ready to start fresh')
"
