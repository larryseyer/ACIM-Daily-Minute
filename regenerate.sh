#!/bin/bash
# Regenerate a specific day's Daily Minute
# Usage: ./regenerate.sh 3        # Regenerate day 3
#        ./regenerate.sh 3 --dry-run  # Test without uploading

set -e

DAY=${1:-}
DRY_RUN=${2:-}

if [[ -z "$DAY" ]] || [[ ! "$DAY" =~ ^[0-9]+$ ]]; then
    echo "Usage: ./regenerate.sh DAY_NUMBER [--dry-run]"
    echo "Example: ./regenerate.sh 3"
    echo "         ./regenerate.sh 3 --dry-run"
    exit 1
fi

echo "=== Regenerating ACIM Daily Minute Day $DAY ==="

cd "$(dirname "$0")"

# Activate venv if it exists
if [[ -d "venv" ]]; then
    source venv/bin/activate
fi

python3 -c "
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DAY = $DAY
DRY_RUN = '$DRY_RUN' == '--dry-run'

DB_PATH = Path('data/acim.db')
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

# Count current successful uploads
current_count = conn.execute('SELECT COUNT(*) FROM upload_log WHERE success = 1').fetchone()[0]
print(f'Current successful uploads: {current_count}')

if DAY > current_count + 1:
    print(f'Error: Cannot regenerate day {DAY}. Next day would be {current_count + 1}')
    exit(1)

# Find and remove upload_log entries for the target day
# Calculate the date for this day (assuming day 1 was the first upload)
first_upload = conn.execute('SELECT upload_date FROM upload_log WHERE success = 1 ORDER BY upload_date LIMIT 1').fetchone()
if first_upload:
    first_date = datetime.strptime(first_upload['upload_date'], '%Y-%m-%d')
    target_date = first_date + timedelta(days=DAY - 1)
    target_date_str = target_date.strftime('%Y-%m-%d')
    print(f'Target date for day {DAY}: {target_date_str}')

    # Find the upload entry for this day
    entry = conn.execute('SELECT * FROM upload_log WHERE upload_date = ?', (target_date_str,)).fetchone()
    if entry:
        print(f'Found upload entry: segment {entry[\"segment_id\"]}, youtube_id {entry[\"youtube_id\"]}')

        if not DRY_RUN:
            # Delete the upload_log entry
            conn.execute('DELETE FROM upload_log WHERE upload_date = ?', (target_date_str,))

            # Mark the segment as unused so it won't be picked again
            conn.execute('UPDATE segments SET used = 0, used_date = NULL WHERE id = ?', (entry['segment_id'],))

            conn.commit()
            print(f'Deleted upload_log entry and reset segment {entry[\"segment_id\"]}')
        else:
            print('[DRY-RUN] Would delete upload entry and reset segment')
    else:
        print(f'No upload entry found for {target_date_str}')
else:
    print('No uploads found in database')

conn.close()

if not DRY_RUN:
    print('\\nNow running daily pipeline to regenerate...')
"

if [[ "$DRY_RUN" != "--dry-run" ]]; then
    # Run the daily pipeline
    python3 main.py --run
fi

echo "=== Done ==="
