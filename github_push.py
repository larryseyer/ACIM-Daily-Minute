"""github_push — Publish ACIM Daily Minute / Daily Lessons feeds to GitHub Pages.

Recreated 2026-04-24 after the original source was lost while the .pyc cache
remained. The cache could not be decompiled (no decompiler supports CPython
3.9). Behaviour is reconstructed from:

  * Call sites in main.py / lessons.py / push_website.sh (function signatures).
  * The live feeds at https://www.acimdailyminute.org/* (output format).
  * The fix-history note in CLAUDE.md (unbounded archives, lesson_0 = plain
    "Introduction", history rebuilt from DB every push).
  * The push_to_ghpages helper in /Users/larryseyer/JTFNews/main.py (GitHub
    Contents API pattern, malformed-XML guard).

All feeds are rebuilt from the SQLite DB on every push; nothing depends on
prior on-disk state, so the catch-up after the 9-day outage is automatic.

Hard guard: every DB query restricts to upload_date <= today (CLAUDE.md
financial directive — never publish content for future calendar dates).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "acim.db"

SITE_URL = "https://www.acimdailyminute.org"
TOTAL_LESSONS = 365


# ---------------------------------------------------------------------------
# GitHub Contents API helpers
# ---------------------------------------------------------------------------

def _gh_config() -> Optional[tuple[str, str, str, str]]:
    token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER", "larryseyer")
    repo = os.getenv("GITHUB_REPO", "ACIM-Daily-Minute")
    branch = os.getenv("GITHUB_BRANCH", "main")
    if not token:
        log.warning("GITHUB_TOKEN not set — skipping GitHub push")
        return None
    return token, owner, repo, branch


def _put_file(gh_path: str, content_bytes: bytes, message: str) -> bool:
    """Create or update a single file in the GitHub repo via the Contents API."""
    cfg = _gh_config()
    if cfg is None:
        return False
    token, owner, repo, branch = cfg

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{gh_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    sha: Optional[str] = None
    try:
        r = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=30)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except requests.RequestException as e:
        log.warning(f"GitHub GET failed for {gh_path}: {e}")

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        log.warning(f"GitHub PUT failed for {gh_path}: {e}")
        return False

    if r.status_code in (200, 201):
        return True
    log.warning(f"GitHub PUT {gh_path} -> {r.status_code}: {r.text[:200]}")
    return False


def _validate_xml(content_bytes: bytes, label: str) -> bool:
    """Refuse to publish malformed XML (mirrors the JTFNews safety guard)."""
    try:
        ET.fromstring(content_bytes)
        return True
    except ET.ParseError as e:
        log.error(f"REFUSING to publish malformed XML ({label}): {e}")
        return False


# ---------------------------------------------------------------------------
# DB queries (today-bounded)
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_minute_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ul.segment_id, ul.upload_date, ul.youtube_id,
               s.text, s.source_pdf, s.word_count
        FROM upload_log ul
        JOIN segments s ON ul.segment_id = s.id
        WHERE ul.success = 1
          AND ul.upload_date <= :today
        ORDER BY ul.upload_date DESC, ul.id DESC
        """,
        {"today": _today()},
    ).fetchall()


def _fetch_lesson_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ll.lesson_id, ll.upload_date, ll.youtube_id,
               l.title, l.text, l.word_count
        FROM lessons_log ll
        JOIN lessons l ON ll.lesson_id = l.id
        WHERE ll.success = 1
          AND ll.upload_date <= :today
        ORDER BY ll.upload_date DESC, ll.id DESC
        """,
        {"today": _today()},
    ).fetchall()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pubdate(date_str: str) -> str:
    """Render YYYY-MM-DD as RFC-822 publish time at 07:00:00 GMT."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=7, minute=0, second=0, tzinfo=timezone.utc
    )
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _pretty_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Cross-platform "no leading zero" day-of-month.
    return dt.strftime("%B ") + str(dt.day) + dt.strftime(", %Y")


def _minute_audio_url(date_str: str) -> str:
    return f"audio/daily-minute/{date_str}.mp3"


def _lesson_audio_url(lesson_id: int) -> str:
    return f"audio/daily-lessons/lesson-{lesson_id:03d}.mp3"


def _lesson_title_for_feed(lesson_id: int, db_title: str) -> str:
    """Per CLAUDE.md: lesson_id=0 emits the bare word 'Introduction'."""
    if lesson_id == 0:
        return "Introduction"
    return f"Lesson {lesson_id}: {db_title}"


def _estimate_lesson_duration(word_count: int) -> str:
    """Estimate audio length from word count. ElevenLabs narration runs at
    roughly 150 wpm in this project (observed 156 words → 64s, 295 → 120s).
    Round up to the nearest second so we never under-report."""
    seconds = max(60, int(round(word_count * 60 / 150)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------------------
# Feed builders
# ---------------------------------------------------------------------------

_MINUTE_CHANNEL_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>ACIM Daily Minute</title>
    <link>{site}</link>
    <language>en-us</language>
    <copyright>Public domain text; audio CC BY-SA 4.0</copyright>
    <itunes:author>ACIM Daily Minute</itunes:author>
    <itunes:owner>
      <itunes:name>ACIM Daily Minute</itunes:name>
      <itunes:email>podcast@acimdailyminute.org</itunes:email>
    </itunes:owner>
    <description>A one-minute reading from A Course in Miracles, every day. Short, reflective passages from the Text, Workbook, and Manual for Teachers.</description>
    <itunes:image href="{site}/assets/podcast-minute-artwork.png"/>
    <itunes:category text="Religion &amp; Spirituality"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <atom:link href="{site}/podcast-minute.xml" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{built}</lastBuildDate>
"""

_LESSON_CHANNEL_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>ACIM Daily Lessons</title>
    <link>{site}</link>
    <language>en-us</language>
    <copyright>Public domain text; audio CC BY-SA 4.0</copyright>
    <itunes:author>ACIM Daily Minute</itunes:author>
    <itunes:owner>
      <itunes:name>ACIM Daily Minute</itunes:name>
      <itunes:email>podcast@acimdailyminute.org</itunes:email>
    </itunes:owner>
    <description>The 365 Workbook Lessons from A Course in Miracles, one per weekday. Follow the Course's own practice sequence at your own pace.</description>
    <itunes:image href="{site}/assets/podcast-lessons-artwork.png"/>
    <itunes:category text="Religion &amp; Spirituality"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <atom:link href="{site}/podcast-lessons.xml" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{built}</lastBuildDate>
"""


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_minute_feed(rows: list[sqlite3.Row]) -> bytes:
    parts = [
        _MINUTE_CHANNEL_HEADER.format(
            site=SITE_URL,
            built=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        )
    ]
    for r in rows:
        date_str = r["upload_date"]
        text = r["text"] or ""
        source = r["source_pdf"] or ""
        seg_id = r["segment_id"]
        item = (
            "    <item>\n"
            f"      <title>Daily Minute — {_pretty_date(date_str)}</title>\n"
            f"      <description>{_xml_escape(text)}</description>\n"
            "      <content:encoded><![CDATA["
            f"<p>\u201c{text}\u201d</p><p><em>\u2014 {source}</em></p>"
            "]]></content:encoded>\n"
            f'      <enclosure url="{SITE_URL}/{_minute_audio_url(date_str)}" type="audio/mpeg" length="0"/>\n'
            f"      <guid isPermaLink=\"false\">acim-minute-{date_str}</guid>\n"
            f"      <pubDate>{_pubdate(date_str)}</pubDate>\n"
            "      <itunes:duration>01:00</itunes:duration>\n"
            f"      <itunes:episode>{seg_id}</itunes:episode>\n"
            "      <itunes:explicit>false</itunes:explicit>\n"
            "    </item>\n"
        )
        parts.append(item)
    parts.append("  </channel>\n</rss>\n")
    return "".join(parts).encode("utf-8")


def _build_lesson_feed(rows: list[sqlite3.Row]) -> bytes:
    parts = [
        _LESSON_CHANNEL_HEADER.format(
            site=SITE_URL,
            built=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        )
    ]
    for r in rows:
        lesson_id = r["lesson_id"]
        date_str = r["upload_date"]
        text = r["text"] or ""
        title = _lesson_title_for_feed(lesson_id, r["title"] or "")
        body_lead = (
            f"<p><strong>{_xml_escape(title)}</strong></p>"
            if lesson_id != 0
            else "<p><strong>Introduction</strong></p>"
        )
        item = (
            "    <item>\n"
            f"      <title>{_xml_escape(title)}</title>\n"
            f"      <description>{_xml_escape(text[:500])}</description>\n"
            "      <content:encoded><![CDATA["
            f"{body_lead}<p>{_xml_escape(text)}</p>"
            "]]></content:encoded>\n"
            f'      <enclosure url="{SITE_URL}/{_lesson_audio_url(lesson_id)}" type="audio/mpeg" length="0"/>\n'
            f"      <guid isPermaLink=\"false\">acim-lesson-{lesson_id:03d}</guid>\n"
            f"      <pubDate>{_pubdate(date_str)}</pubDate>\n"
            f"      <itunes:duration>{_estimate_lesson_duration(r['word_count'] or 0)}</itunes:duration>\n"
            f"      <itunes:episode>{lesson_id}</itunes:episode>\n"
            "      <itunes:explicit>false</itunes:explicit>\n"
            "    </item>\n"
        )
        parts.append(item)
    parts.append("  </channel>\n</rss>\n")
    return "".join(parts).encode("utf-8")


def _build_minute_json(rows: list[sqlite3.Row], current_youtube_id: str = "") -> bytes:
    if not rows:
        return b"{}\n"
    head = rows[0]
    archive = [
        {
            "date": r["upload_date"],
            "text": r["text"] or "",
            "source_reference": r["source_pdf"] or "",
            "audio_url": _minute_audio_url(r["upload_date"]),
        }
        for r in rows[1:]
    ]
    youtube_id = current_youtube_id or head["youtube_id"] or ""
    payload = {
        "segment_id": head["segment_id"],
        "date": head["upload_date"],
        "text": head["text"] or "",
        "source_pdf": head["source_pdf"] or "",
        "source_reference": head["source_pdf"] or "",
        "word_count": head["word_count"] or 0,
        "audio_url": _minute_audio_url(head["upload_date"]),
        "youtube_url": f"https://youtube.com/watch?v={youtube_id}" if youtube_id else "",
        "youtube_id": youtube_id,
        "tiktok_url": "",
        "archive": archive,
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _build_lesson_json(rows: list[sqlite3.Row], current_youtube_id: str = "") -> bytes:
    if not rows:
        return b"{}\n"
    head = rows[0]
    archive = [
        {
            "lesson_id": r["lesson_id"],
            "title": _lesson_title_for_feed(r["lesson_id"], r["title"] or ""),
            "date": r["upload_date"],
            "audio_url": _lesson_audio_url(r["lesson_id"]),
        }
        for r in rows[1:]
    ]
    youtube_id = current_youtube_id or head["youtube_id"] or ""
    payload = {
        "lesson_id": head["lesson_id"],
        "date": head["upload_date"],
        "title": _lesson_title_for_feed(head["lesson_id"], head["title"] or ""),
        "text": head["text"] or "",
        "word_count": head["word_count"] or 0,
        "audio_url": _lesson_audio_url(head["lesson_id"]),
        "youtube_url": f"https://youtube.com/watch?v={youtube_id}" if youtube_id else "",
        "youtube_id": youtube_id,
        "total_lessons": TOTAL_LESSONS,
        "archive": archive,
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _build_alexa_json(minute_rows: list[sqlite3.Row]) -> bytes:
    if not minute_rows:
        return b"[]\n"
    head = minute_rows[0]
    iso = datetime.strptime(head["upload_date"], "%Y-%m-%d").strftime(
        "%Y-%m-%dT06:00:00.0Z"
    )
    item = {
        "uid": f"acim-minute-{head['upload_date']}",
        "updateDate": iso,
        "titleText": "ACIM Daily Minute",
        "mainText": head["text"] or "",
        "redirectionUrl": f"{SITE_URL}/daily-minute.html",
    }
    return (json.dumps([item], indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _build_unified_feed(
    minute_rows: list[sqlite3.Row], lesson_rows: list[sqlite3.Row]
) -> bytes:
    """A single 'latest entry' feed mirroring docs/feed.xml on the live site."""
    built = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items: list[tuple[str, str]] = []  # (date_str, item_xml)

    if minute_rows:
        r = minute_rows[0]
        date_str = r["upload_date"]
        text = (r["text"] or "")[:400]
        items.append(
            (
                date_str,
                "    <item>\n"
                f"      <title>Daily Minute — {_pretty_date(date_str)}</title>\n"
                f"      <description>{_xml_escape(text)}</description>\n"
                "      <acim:stream>minute</acim:stream>\n"
                f"      <link>{SITE_URL}/daily-minute.html</link>\n"
                f"      <pubDate>{_pubdate(date_str)}</pubDate>\n"
                f"      <guid isPermaLink=\"false\">acim-minute-{date_str}</guid>\n"
                "    </item>\n",
            )
        )

    if lesson_rows:
        r = lesson_rows[0]
        lesson_id = r["lesson_id"]
        date_str = r["upload_date"]
        title = _lesson_title_for_feed(lesson_id, r["title"] or "")
        text = (r["text"] or "")[:400]
        items.append(
            (
                date_str,
                "    <item>\n"
                f"      <title>{_xml_escape(title)}</title>\n"
                f"      <description>{_xml_escape(text)}</description>\n"
                "      <acim:stream>lesson</acim:stream>\n"
                f"      <link>{SITE_URL}/lessons.html</link>\n"
                f"      <pubDate>{_pubdate(date_str)}</pubDate>\n"
                f"      <guid isPermaLink=\"false\">acim-lesson-{lesson_id:03d}</guid>\n"
                "    </item>\n",
            )
        )

    items.sort(key=lambda x: x[0], reverse=True)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss xmlns:atom="http://www.w3.org/2005/Atom"\n'
        '     xmlns:acim="https://acimdailyminute.org/rss"\n'
        '     version="2.0">\n'
        "  <channel>\n"
        "    <title>ACIM Daily Minute</title>\n"
        f"    <link>{SITE_URL}/</link>\n"
        "    <description>Daily readings from A Course in Miracles. One-minute text passages and the 365 Workbook Lessons.</description>\n"
        "    <language>en-us</language>\n"
        f"    <lastBuildDate>{built}</lastBuildDate>\n"
        f'    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "".join(x[1] for x in items)
        + "  </channel>\n</rss>\n"
    )
    return body.encode("utf-8")


# ---------------------------------------------------------------------------
# Public API: called by main.py / lessons.py / push_website.sh
# ---------------------------------------------------------------------------

def push_all_daily_minute(
    *,
    segment_id: int,
    text: str,
    source_pdf: str,
    source_reference: str,
    word_count: int,
    date_str: str,
    youtube_id: str,
) -> bool:
    """Rebuild and push every Daily Minute feed from the DB.

    The keyword arguments describe the *just-uploaded* item, but the feeds are
    rebuilt unbounded from upload_log so a missed run on Monday is healed by
    Tuesday's run automatically (per CLAUDE.md fix history, 2026-04-15).
    """
    conn = _open_db()
    try:
        minute_rows = _fetch_minute_rows(conn)
        lesson_rows = _fetch_lesson_rows(conn)
    finally:
        conn.close()

    feed_xml = _build_minute_feed(minute_rows)
    json_blob = _build_minute_json(minute_rows, current_youtube_id=youtube_id)
    alexa_blob = _build_alexa_json(minute_rows)
    unified = _build_unified_feed(minute_rows, lesson_rows)

    if not _validate_xml(feed_xml, "podcast-minute.xml"):
        return False
    if not _validate_xml(unified, "feed.xml"):
        return False

    msg = f"Daily Minute: segment {segment_id} ({date_str})"
    ok = True
    ok &= _put_file("docs/podcast-minute.xml", feed_xml, msg)
    ok &= _put_file("docs/daily-minute.json", json_blob, msg)
    ok &= _put_file("docs/alexa.json", alexa_blob, msg)
    ok &= _put_file("docs/feed.xml", unified, msg)
    if ok:
        log.info(f"Pushed Daily Minute feeds: {msg}")
    return ok


def push_all_daily_lesson(
    *,
    lesson_id: int,
    title: str,
    text: str,
    word_count: int,
    date_str: str,
    youtube_id: str,
) -> bool:
    """Rebuild and push every Daily Lesson feed from the DB."""
    conn = _open_db()
    try:
        minute_rows = _fetch_minute_rows(conn)
        lesson_rows = _fetch_lesson_rows(conn)
    finally:
        conn.close()

    feed_xml = _build_lesson_feed(lesson_rows)
    json_blob = _build_lesson_json(lesson_rows, current_youtube_id=youtube_id)
    unified = _build_unified_feed(minute_rows, lesson_rows)

    if not _validate_xml(feed_xml, "podcast-lessons.xml"):
        return False
    if not _validate_xml(unified, "feed.xml"):
        return False

    display_title = _lesson_title_for_feed(lesson_id, title)
    msg = f"Daily Lesson: {display_title} ({date_str})"
    ok = True
    ok &= _put_file("docs/podcast-lessons.xml", feed_xml, msg)
    ok &= _put_file("docs/daily-lesson.json", json_blob, msg)
    ok &= _put_file("docs/feed.xml", unified, msg)
    if ok:
        log.info(f"Pushed Daily Lesson feeds: {msg}")
    return ok


def push_monitor(
    *,
    state: str,
    stream_health: str,
    api_costs: dict,
    streams: dict,
) -> bool:
    """Push monitor.json. Caller passes only the streams it touched; we merge
    with whatever exists in the live monitor.json so a Daily Minute push
    doesn't blow away the Daily Lesson stream block (or vice versa)."""
    cfg = _gh_config()
    base = {
        "streams": {
            "daily_minute": {"status": "unknown", "last_updated": "--"},
            "daily_lessons": {"status": "unknown", "last_updated": "--"},
            "text_series": {"status": "coming_soon", "estimated_start": "Late 2027"},
        }
    }
    if cfg is not None:
        _, owner, repo, branch = cfg
        try:
            r = requests.get(
                f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/docs/monitor.json",
                timeout=15,
            )
            if r.status_code == 200:
                base = r.json()
        except (requests.RequestException, ValueError):
            pass

    merged_streams = dict(base.get("streams", {}))
    for k, v in (streams or {}).items():
        merged_streams[k] = v

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_start": base.get("uptime_start"),
        "uptime_seconds": base.get("uptime_seconds", 0),
        "streams": merged_streams,
        "api_costs": api_costs,
        "status": {
            "state": state,
            "stream_health": stream_health,
            "next_cycle_minutes": None,
            "degraded_services": [],
        },
        "feeds": {
            "feed_xml": f"{SITE_URL}/feed.xml",
            "podcast_minute": f"{SITE_URL}/podcast-minute.xml",
            "podcast_lessons": f"{SITE_URL}/podcast-lessons.xml",
            "alexa": f"{SITE_URL}/alexa.json",
        },
    }
    blob = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if _put_file("docs/monitor.json", blob, f"Monitor: {state}/{stream_health}"):
        log.info("Pushed monitor.json")
        return True
    return False


# ---------------------------------------------------------------------------
# CLI: ./venv/bin/python github_push.py [--dry-run] [--out DIR]
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Rebuild and push ACIM Daily Minute feeds")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build feeds locally and write to --out instead of pushing",
    )
    p.add_argument(
        "--out",
        default="/tmp/acim-feeds",
        help="Output directory for --dry-run (default: /tmp/acim-feeds)",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    conn = _open_db()
    try:
        minute_rows = _fetch_minute_rows(conn)
        lesson_rows = _fetch_lesson_rows(conn)
    finally:
        conn.close()

    print(f"Daily Minute rows: {len(minute_rows)}")
    if minute_rows:
        print(f"  latest: segment {minute_rows[0]['segment_id']} on {minute_rows[0]['upload_date']}")
    print(f"Daily Lesson rows: {len(lesson_rows)}")
    if lesson_rows:
        print(f"  latest: lesson {lesson_rows[0]['lesson_id']} on {lesson_rows[0]['upload_date']}")

    artifacts = {
        "podcast-minute.xml": _build_minute_feed(minute_rows),
        "podcast-lessons.xml": _build_lesson_feed(lesson_rows),
        "daily-minute.json": _build_minute_json(minute_rows),
        "daily-lesson.json": _build_lesson_json(lesson_rows),
        "alexa.json": _build_alexa_json(minute_rows),
        "feed.xml": _build_unified_feed(minute_rows, lesson_rows),
    }
    for name in ("podcast-minute.xml", "podcast-lessons.xml", "feed.xml"):
        if not _validate_xml(artifacts[name], name):
            raise SystemExit(f"XML validation failed for {name}")

    if args.dry_run:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for name, blob in artifacts.items():
            (out / name).write_bytes(blob)
            print(f"  wrote {out / name} ({len(blob)} bytes)")
        return

    if not minute_rows or not lesson_rows:
        raise SystemExit("Refusing to push: at least one feed has no rows")

    head_min = minute_rows[0]
    head_les = lesson_rows[0]
    ok = True
    ok &= push_all_daily_minute(
        segment_id=head_min["segment_id"],
        text=head_min["text"] or "",
        source_pdf=head_min["source_pdf"] or "",
        source_reference=head_min["source_pdf"] or "",
        word_count=head_min["word_count"] or 0,
        date_str=head_min["upload_date"],
        youtube_id=head_min["youtube_id"] or "",
    )
    ok &= push_all_daily_lesson(
        lesson_id=head_les["lesson_id"],
        title=head_les["title"] or "",
        text=head_les["text"] or "",
        word_count=head_les["word_count"] or 0,
        date_str=head_les["upload_date"],
        youtube_id=head_les["youtube_id"] or "",
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    _cli()
