# ACIM Daily Minute - Claude Code Project Notes

## Development Environment

**Project files on**: 2012 Intel Mac running macOS Catalina (the "live"
machine — runs the daily 2 AM cron, owns credentials, owns the Python venv).
Editing may also happen from an M4 MacBook Pro via a network/Thunderbolt mount.

### Path Mapping

| Context | Path |
|---------|------|
| Local (Intel Mac — scripts run here) | `/Users/larryseyer/acim-daily-minute` |
| M4 MacBook Pro (edit-only view of Intel disk) | `/Volumes/MacLive/Users/larryseyer/acim-daily-minute` |

The two paths refer to the **same physical files** on the Intel Mac. File
edits made through the M4 mount land on the Intel Mac's disk. Do **not**
hardcode `/Volumes/MacLive/...` anywhere in Python code — scripts run on the
Intel Mac where that path doesn't exist. Use relative paths (e.g.,
`"data/acim.db"`) or `/Users/larryseyer/...`.

### Critical Rules

1. **Serena MCP**: Does NOT work on this remote setup — use Claude Code native tools only.
2. **Never touch the Python environment from the M4.** No `pip install`, no venv creation, no running `./venv/bin/python` for anything that writes files. The venv is Intel-native Python 3.9 and its binaries are architecture-specific. All package management happens on the Intel Mac.
3. **Never commit/push from Claude unless asked.** User reviews diffs before commits.

### Python Environment

- Intel Mac (Catalina): Python 3.8 or 3.9 (currently 3.9.13 in `venv/`).
- M4: do not run project Python from here. Claude can read/edit files, but all
  Python execution and verification happens on the Intel Mac.

### Daily Cron

- Runs once a day at **2 AM local time** on the Intel Mac.
- Entry point: `main.py` (Daily Minute) → `lessons.py` (Daily Lesson on weekdays).
- Website publish: `push_website.sh` / `github_push.py` push to GitHub Pages
  repo `larryseyer/ACIM-Daily-Minute` under `docs/`.

## Audio Hosting (Important — partially built)

**Current state:**
- YouTube uploads work end-to-end (`uploader.py`).
- TikTok uploads work.
- Audio files live on disk as `audio/acim_<segment_id>.mp3` (Daily Minute) and
  `audio/lesson_<N>.mp3` (Daily Lesson; `lesson_0.mp3` = Introduction).
- The RSS feeds (`podcast-minute.xml`, `podcast-lessons.xml`) emit
  `<enclosure>` URLs pointing to `audio/daily-minute/YYYY-MM-DD.mp3` and
  `audio/daily-lessons/lesson-NNN.mp3`, but those URLs are **not hosted** —
  they likely 404 when played directly. This is expected pre-existing
  behavior until the archive.org integration ships.

**Planned:**
- **archive.org** will host the audio files so the `<enclosure>` URLs in the
  RSS feeds resolve to playable MP3s. Existing on-disk files will need to be
  uploaded to archive.org with renaming to match the feed's URL scheme.
- When this work happens: upload existing MP3s with date/lesson renaming, and
  wire archive.org URL generation into `github_push.py` so new daily uploads
  push audio there automatically.

## Known Data Gaps

### 2 ghost Daily Minute episodes: 2026-03-18 and 2026-03-19

The Daily Minute launched 2026-03-18. YouTube has videos for all launch days,
but the Intel Mac's `upload_log` only has rows from 2026-03-20 onward — the
first 2 days were uploaded while the logging code was still being written, so
no `upload_log` rows exist for them, and no on-disk audio files either.

**Impact:**
- RSS feeds exclude those 2 days (feed shows 25 items as of 2026-04-15,
  missing Mar 18–19). This is accepted — unblocks iOS app ACIM-206 anyway.
- When archive.org integration ships, the 2 ghost episodes will need audio
  sourced somehow: either extract audio from the YouTube uploads (cheaper,
  preserves original narration) or regenerate via TTS from the original ACIM
  text (requires knowing which `segments.id` they used, which isn't recorded
  anywhere).
- When reconstructing, also insert 2 missing `upload_log` rows so the DB
  reflects full history.

## Financial Directives

- **Do NOT bulk-generate audio.** The ACIM project has 7 years of potential
  Daily Minute content and 1.5 years of potential Daily Lessons. Never
  generate audio for dates after today — the daily cron is the only thing
  allowed to advance the publish frontier.
- Any backfill of missing past episodes must be explicitly scoped with the
  user and capped at ≤13 TTS generations per category per session.
- The hard in-code guard: `WHERE upload_date <= :today` in every DB query
  that drives feed/output generation.
- "Today" = the calendar date the script runs on, NOT a lesson number.

## Backend Fix History

### 2026-04-24: Recreated lost `github_push.py`

The `github_push.py` source file vanished sometime between Apr 11 and Apr 16
(only `__pycache__/github_push.cpython-39.pyc` remained, and CPython 3.9
bytecode is not supported by `uncompyle6` / `decompyle3`). Result: every cron
run from Apr 16 → Apr 24 logged `Website push failed (non-fatal): No module
named 'github_push'` after each successful YouTube upload, so the GitHub
Pages feeds froze 9 days behind YouTube (last published item was lesson 11 /
segment 13575 on 2026-04-15).

The module was rebuilt from scratch using the call sites in `main.py` /
`lessons.py` / `push_website.sh`, the live feed format on
`acimdailyminute.org`, and `push_to_ghpages` in `~/JTFNews/main.py` as a
reference for the GitHub Contents API pattern. After running
`bash push_website.sh`, the feeds are caught up: podcast-minute.xml = 34
items (DB has 36; the 2 ghost episodes Mar 18–19 remain missing as
documented), podcast-lessons.xml = 19 items.

The file is **not** in git — it sits alongside other untracked locals
(`push_website.sh`, `cost_tracker.py`, `verify_import.py`, etc.). Consider
adding it to a future commit so this can't happen again. The
`verify_and_push_feeds.sh` script referenced below also doesn't exist —
`push_website.sh` is the actual manual-push entry point.

### 2026-04-15: Feed history backfill (`github_push.py`)

Fixed three iOS-blocking issues from `fixbackend.md`:
- `podcast-minute.xml` — was emitting only today's `<item>`; now emits every
  successful upload from `upload_log` JOIN `segments`, newest-first.
- `podcast-lessons.xml` — same fix using `lessons_log` JOIN `lessons`. The
  Introduction (lesson_id=0) is emitted with plain `<title>Introduction</title>`
  (no "Lesson 0:" prefix) — iOS parser special-cases this.
- `daily-lesson.json` / `daily-minute.json` — archive was capped at 7 entries
  via `[:7]` slices; now unbounded and rebuilt from the DB on every push
  (self-healing — no drift from missed runs).

Verify by running `bash verify_and_push_feeds.sh` from the repo root.

Plan document: `~/.claude/plans/parsed-zooming-shore.md` (on whichever machine
Claude Code was running when the plan was approved; also see `fixbackend.md`
in the repo for the original spec).
