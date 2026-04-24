#!/bin/bash
# push_website.sh — Manually push current data to the website (GitHub Pages)
#
# Usage:
#   cd /Users/larryseyer/acim-daily-minute
#   ./push_website.sh
#
# Pushes the latest Daily Minute and Daily Lesson data from the local
# database to the website repo via GitHub API. Also pushes monitor status,
# RSS feed, podcast feeds, and Alexa JSON.

set -e
cd "$(dirname "$0")"

echo "=== ACIM Daily Minute — Manual Website Push ==="
echo ""

# Verify github_push.py can be imported
echo "Checking github_push.py..."
python3 -c "import github_push; print('  OK — module loads cleanly')"

echo ""
echo "Pushing data to website..."
echo ""

python3 << 'PYEOF'
import sqlite3
from github_push import push_all_daily_minute, push_all_daily_lesson, push_monitor
from cost_tracker import get_api_costs_today, get_daily_budget, get_month_estimate, archive_yesterday_cost

conn = sqlite3.connect("data/acim.db")
conn.row_factory = sqlite3.Row

# --- Daily Minute ---
row = conn.execute("""
    SELECT ul.segment_id, ul.upload_date, ul.youtube_id,
           s.text, s.source_pdf, s.word_count
    FROM upload_log ul
    JOIN segments s ON ul.segment_id = s.id
    WHERE ul.success = 1
    ORDER BY ul.upload_date DESC LIMIT 1
""").fetchone()

if row:
    print(f"Daily Minute: segment {row['segment_id']} from {row['upload_date']} (YouTube: {row['youtube_id']})")
    push_all_daily_minute(
        segment_id=row["segment_id"],
        text=row["text"],
        source_pdf=row["source_pdf"],
        source_reference=row["source_pdf"],
        word_count=row["word_count"],
        date_str=row["upload_date"],
        youtube_id=row["youtube_id"] or "",
    )
else:
    print("No Daily Minute uploads found in database")

# --- Daily Lesson ---
row = conn.execute("""
    SELECT ll.lesson_id, ll.upload_date, ll.youtube_id,
           l.title, l.text, l.word_count
    FROM lessons_log ll
    JOIN lessons l ON ll.lesson_id = l.id
    WHERE ll.success = 1
    ORDER BY ll.upload_date DESC LIMIT 1
""").fetchone()

if row:
    print(f"Daily Lesson: lesson {row['lesson_id']} — {row['title'][:50]} (YouTube: {row['youtube_id']})")
    push_all_daily_lesson(
        lesson_id=row["lesson_id"],
        title=row["title"],
        text=row["text"],
        word_count=row["word_count"],
        date_str=row["upload_date"],
        youtube_id=row["youtube_id"] or "",
    )
else:
    print("No Daily Lesson uploads found in database")

# --- Archive yesterday's costs ---
archive_yesterday_cost()

# --- Monitor Status (with real data from database) ---
print("Pushing monitor status...")

# Count uploads
dm_count = conn.execute("SELECT COUNT(*) FROM upload_log WHERE success = 1").fetchone()[0]
dl_count = conn.execute("SELECT COUNT(*) FROM lessons_log WHERE success = 1").fetchone()[0]

# Latest daily minute
dm_latest = conn.execute("""
    SELECT ul.segment_id, ul.upload_date
    FROM upload_log ul WHERE ul.success = 1
    ORDER BY ul.upload_date DESC LIMIT 1
""").fetchone()

# Latest daily lesson
dl_latest = conn.execute("""
    SELECT ll.lesson_id, ll.upload_date
    FROM lessons_log ll WHERE ll.success = 1
    ORDER BY ll.upload_date DESC LIMIT 1
""").fetchone()

# Build cost data for monitor
today_costs = get_api_costs_today()
daily_budget = get_daily_budget()
month_est = get_month_estimate()
total_usd = today_costs.get("total_cost_usd", 0)
budget_pct = (total_usd / daily_budget * 100) if daily_budget > 0 else 0

push_monitor(
    state="idle",
    stream_health="online",
    api_costs={
        "today": today_costs.get("services", {}),
        "total_usd": round(total_usd, 4),
        "month_estimate_usd": round(month_est, 2),
        "daily_budget": round(daily_budget, 2),
        "budget_pct": round(budget_pct, 1),
    },
    streams={
        "daily_minute": {
            "status": "completed",
            "last_updated": dm_latest["upload_date"] if dm_latest else "--",
            "segment_id": dm_latest["segment_id"] if dm_latest else 0,
            "episodes_published": dm_count,
        },
        "daily_lessons": {
            "status": "completed",
            "last_updated": dl_latest["upload_date"] if dl_latest else "--",
            "lesson_id": dl_latest["lesson_id"] if dl_latest else 0,
            "episodes_published": dl_count,
        },
        "text_series": {
            "status": "coming_soon",
            "estimated_start": "Late 2027",
        },
    },
)

conn.close()
print(f"  Daily Minute: {dm_count} episodes, last {dm_latest['upload_date'] if dm_latest else 'none'}")
print(f"  Daily Lessons: {dl_count} episodes, last lesson {dl_latest['lesson_id'] if dl_latest else 'none'}")
print("")
print("=== Push complete ===")
PYEOF
