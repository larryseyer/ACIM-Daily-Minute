# ACIM Daily Minute — Design & Implementation Plan
**Date:** 2026-03-17  
**Project:** `~/acim-daily-minute/`  
**Purpose:** Automated daily 1-minute YouTube video of A Course in Miracles readings using a cloned ElevenLabs voice, scrolling text video, and YouTube upload — running 24/7 on a Mac alongside JTF News.

---

## Overview

This system runs independently from JTF News on the same Mac. Each day it:
1. Picks a random unused ACIM text segment from SQLite (~130–150 words)
2. Sends it to ElevenLabs TTS using a cloned voice
3. Renders a 1080p scrolling-text MP4 video with `ffmpeg`
4. Uploads it to the "ACIM Daily Minute" YouTube channel
5. Marks the segment as used; reshuffles when all are exhausted

**No OBS. No news scraping. No Claude AI calls. Pure pipeline.**

---

## Project Structure

```
~/acim-daily-minute/
├── pdfs/
│   ├── 1_ACIM_Text_A.pdf
│   ├── 2_ACIM_Text_B.pdf
│   ├── 3_ACIM_Workbook.pdf
│   └── 4_ACIM_Manual.pdf
├── data/
│   ├── acim.db                  # SQLite — all segments + tracking
│   └── youtube_tokens.json      # OAuth tokens (auto-created by setup_youtube.py)
├── audio/                       # Temp ElevenLabs MP3 output (deleted after video)
├── video/                       # Final MP4 archive
├── assets/
│   └── background.jpg           # 1920x1080 spiritual background image
├── logs/
│   └── acim.log                 # Rotating daily log
├── pdf_extractor.py             # One-time PDF → SQLite chunker
├── tts_generator.py             # ElevenLabs TTS module
├── video_builder.py             # ffmpeg scrolling text video renderer
├── uploader.py                  # YouTube upload (adapted from JTF News pattern)
├── main.py                      # Daily pipeline orchestrator + scheduler
├── setup_youtube.py             # One-time OAuth setup (adapted from JTF News)
├── requirements.txt
├── .env                         # Secrets — never commit
├── .gitignore
└── com.acim.dailyminute.plist   # macOS launchd — runs main.py daily at 6:00 AM
```

---

## Environment Variables (`.env`)

```env
# ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=yNH37Ooobr7UDkJSd3sa

# YouTube
YOUTUBE_CLIENT_SECRETS_FILE=client_secrets.json
YOUTUBE_PLAYLIST_ID=your_playlist_id_here

# Schedule (24-hour format, local time)
UPLOAD_HOUR=6
UPLOAD_MINUTE=0

# Paths
PDF_DIR=pdfs
ASSETS_DIR=assets
AUDIO_DIR=audio
VIDEO_DIR=video
DATA_DIR=data
LOG_DIR=logs

# Video settings
VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080
VIDEO_FPS=30
FONT_SIZE=52
FONT_COLOR=white
BACKGROUND_COLOR=black
SCROLL_SPEED=60

# Channel branding
CHANNEL_NAME=ACIM Daily Minute
YOUTUBE_CATEGORY_ID=27
```

---

## SQLite Schema (`data/acim.db`)

### Table: `segments`

```sql
CREATE TABLE segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_pdf  TEXT NOT NULL,       -- e.g. "1_ACIM_Text_A.pdf"
    page_start  INTEGER,             -- approximate page number
    word_count  INTEGER,
    text        TEXT NOT NULL,       -- the ~130-150 word chunk
    used        INTEGER DEFAULT 0,   -- 0 = available, 1 = used
    used_date   TEXT,                -- ISO date when used e.g. "2026-03-17"
    youtube_id  TEXT,                -- YouTube video ID after upload
    created_at  TEXT DEFAULT (datetime('now'))
);
```

### Table: `upload_log`

```sql
CREATE TABLE upload_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id   INTEGER REFERENCES segments(id),
    upload_date  TEXT NOT NULL,      -- ISO date "2026-03-17"
    youtube_id   TEXT,
    youtube_url  TEXT,
    audio_file   TEXT,
    video_file   TEXT,
    success      INTEGER DEFAULT 0,
    error_msg    TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);
```

---

## Module: `pdf_extractor.py`

**Purpose:** One-time script. Reads all 4 PDFs in order, extracts clean text, chunks into ~130–150 word segments at natural sentence boundaries, stores in SQLite.

**Run once:** `python pdf_extractor.py`  
**Re-run:** `python pdf_extractor.py --reset` (clears and re-imports all)  
**Status:** `python pdf_extractor.py --status`

### Dependencies
```
pdfplumber
nltk
```

### Key Logic

```python
# Chunking algorithm (pseudocode)
TARGET_WORDS = 140          # aim for ~1 min at ~140wpm
MIN_WORDS    = 100
MAX_WORDS    = 180

def chunk_text(full_text: str) -> list[str]:
    sentences = nltk.sent_tokenize(full_text)
    chunks = []
    current = []
    count = 0
    for sent in sentences:
        words = len(sent.split())
        if count + words > MAX_WORDS and count >= MIN_WORDS:
            chunks.append(" ".join(current))
            current = [sent]
            count = words
        else:
            current.append(sent)
            count += words
    if current:
        chunks.append(" ".join(current))
    return chunks
```

### Text Cleaning

Before chunking, clean extracted PDF text:
- Remove page headers/footers (e.g. "A Course in Miracles", chapter headings that repeat)
- Collapse multiple whitespace/newlines
- Fix hyphenated line breaks (e.g. "some-\nthing" → "something")
- Strip footnote markers (numbers, asterisks mid-sentence)
- Keep paragraph breaks as a single space

### CLI Output Example
```
Extracting: 1_ACIM_Text_A.pdf ... 847 segments
Extracting: 2_ACIM_Text_B.pdf ... 612 segments
Extracting: 3_ACIM_Workbook.pdf ... 524 segments
Extracting: 4_ACIM_Manual.pdf  ... 189 segments
Total: 2172 segments (~5.9 years of daily content)
Saved to data/acim.db
```

---

## Module: `tts_generator.py`

**Purpose:** Sends text to ElevenLabs using the cloned ACIM voice. Returns path to saved MP3.

### Dependencies
```
elevenlabs
```

### Voice Settings

```python
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "yNH37Ooobr7UDkJSd3sa")

VOICE_SETTINGS = {
    "stability": 0.71,
    "similarity_boost": 0.85,
    "style": 0.20,
    "use_speaker_boost": True
}

MODEL_ID = "eleven_multilingual_v2"
```

### Function Signature

```python
def generate_audio(text: str, output_path: str) -> bool:
    """
    Generate TTS audio for text using ElevenLabs cloned voice.
    
    Args:
        text: The ACIM segment text (~130-150 words)
        output_path: Full path to save the MP3 file
        
    Returns:
        True on success, False on failure
    """
```

### Error Handling
- Retry up to 3 times with 5s backoff on API errors
- Log ElevenLabs character usage per call
- Raise on total failure so main.py can abort cleanly

---

## Module: `video_builder.py`

**Purpose:** Creates a 1920x1080 MP4 video with the ACIM text scrolling vertically over a background image, synced to the audio duration.

### Dependencies
```
Pillow
ffmpeg (system — called via subprocess)
```

### Video Spec

| Property | Value |
|---|---|
| Resolution | 1920 × 1080 |
| FPS | 30 |
| Format | MP4 (H.264 + AAC) |
| Duration | Matches audio length exactly |
| Background | `assets/background.jpg` (user-provided) |
| Text | White, centered, scrolling upward |
| Font | System font fallback: Helvetica → Arial → DejaVuSans |
| Font size | 52pt |
| Text area | 1520px wide (80px margin each side) |
| Scroll | Smooth vertical, text enters from bottom, exits at top |

### Approach: Frame-by-frame via Pillow → ffmpeg

```
1. Get audio duration via ffprobe
2. Calculate total scroll distance (text height + screen height)
3. Calculate pixels-per-frame based on duration and FPS
4. Render each frame as PIL Image:
   - Paste background.jpg
   - Draw semi-transparent dark overlay (rgba 0,0,0,120) for readability
   - Draw wrapped text at scroll offset Y position
   - Draw channel name watermark bottom-right: "ACIM Daily Minute"
4. Pipe frames to ffmpeg stdin as rawvideo → mux with audio → output MP4
```

### Function Signature

```python
def build_video(text: str, audio_path: str, output_path: str) -> bool:
    """
    Render scrolling text video synced to audio.
    
    Args:
        text: The ACIM segment text to display
        audio_path: Path to the MP3 from ElevenLabs
        output_path: Path to write the final MP4
        
    Returns:
        True on success, False on failure
    """
```

### ffmpeg Command Pattern

```bash
ffmpeg -y \
  -f rawvideo -vcodec rawvideo -s 1920x1080 -pix_fmt rgb24 -r 30 -i pipe:0 \
  -i audio.mp3 \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k \
  -shortest \
  output.mp4
```

---

## Module: `uploader.py`

**Purpose:** Authenticates with YouTube and uploads the video. Directly adapted from JTF News `main.py` functions `get_youtube_credentials()`, `get_authenticated_youtube_service()`, and `upload_to_youtube()`.

### YouTube Metadata

```python
title       = f"ACIM Daily Minute — Day {day_number}"
description = (
    f"A one-minute reading from A Course in Miracles.\n\n"
    f"Read in sequence from the original text by Helen Schucman.\n\n"
    f"A Course in Miracles is a self-study spiritual thought system.\n"
    f"Learn more: https://acim.org/\n\n"
    f"#ACIM #ACourseInMiracles #SpiritualDaily #Meditation"
)
tags        = ["ACIM", "A Course in Miracles", "Helen Schucman",
               "spiritual", "daily reading", "meditation", "miracle"]
category_id = "27"   # Education
privacy     = "public"
```

### Day Number Logic

`day_number` = total count of rows in `upload_log` where `success = 1` + 1  
(i.e. "Day 1", "Day 2", ... forever — resets never happen on YouTube titles)

### Thumbnail

- Generate a simple 1280×720 PNG thumbnail via Pillow:
  - Same background as video
  - Large centered text: "ACIM Daily Minute"
  - Subtitle: "Day {N}"
  - Save to `assets/thumbnail.png`, reuse each day (overwrite)

### Function Signatures (adapted from JTF News)

```python
def get_youtube_credentials() -> tuple[str | None, str | None]:
    """Returns (client_secrets_path, playlist_id) from .env"""

def get_authenticated_youtube_service():
    """Load/refresh OAuth tokens, return YouTube service object"""

def upload_video(video_path: str, title: str, description: str,
                 tags: list, thumbnail_path: str) -> str | None:
    """Upload video, set thumbnail, add to playlist. Returns video_id."""
```

---

## Module: `setup_youtube.py`

Directly adapted from JTF News `setup_youtube.py`. Changes:
- Project name: "ACIM Daily Minute"  
- Playlist name: "ACIM Daily Minute"  
- Playlist description: "Daily one-minute readings from A Course in Miracles."
- All other logic identical

Run once: `python setup_youtube.py`

---

## Module: `main.py`

**Purpose:** Orchestrates the full daily pipeline. Designed to be called by launchd once per day, but also runnable manually.

### Pipeline (called once per day)

```python
def run_daily_pipeline():
    """Full pipeline for one day's upload."""
    
    log.info("=== ACIM Daily Minute pipeline starting ===")
    
    # 1. Pick a random unused segment
    segment = pick_random_segment()    # reshuffles if all used
    if not segment:
        log.error("No segments available")
        return
    
    # 2. Generate audio via ElevenLabs
    audio_path = AUDIO_DIR / f"acim_{segment['id']}.mp3"
    if not generate_audio(segment['text'], str(audio_path)):
        log.error("TTS generation failed")
        return
    
    # 3. Generate thumbnail
    day_number = get_next_day_number()
    thumbnail_path = ASSETS_DIR / "thumbnail.png"
    generate_thumbnail(day_number, str(thumbnail_path))
    
    # 4. Build video
    date_str = datetime.now().strftime("%Y-%m-%d")
    video_path = VIDEO_DIR / f"acim-day-{day_number:04d}-{date_str}.mp4"
    if not build_video(segment['text'], str(audio_path), str(video_path)):
        log.error("Video build failed")
        audio_path.unlink(missing_ok=True)
        return
    
    # 5. Upload to YouTube
    title = f"ACIM Daily Minute — Day {day_number}"
    description = build_description(day_number, segment)
    video_id = upload_video(str(video_path), title, description,
                            TAGS, str(thumbnail_path))
    
    # 6. Mark segment used, log upload
    mark_segment_used(segment['id'], date_str)
    log_upload(segment['id'], date_str, video_id, str(audio_path), str(video_path),
               success=bool(video_id))
    
    # 7. Cleanup temp audio
    audio_path.unlink(missing_ok=True)
    
    log.info(f"=== Done. Day {day_number} uploaded: {video_id} ===")
```

### Segment Selection

```python
def pick_random_segment() -> dict | None:
    """
    Pick a random unused segment.
    If all segments are used, reset all to unused and reshuffle.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM segments WHERE used = 0 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    
    if not row:
        # All used — reset and start over
        conn.execute("UPDATE segments SET used = 0, used_date = NULL, youtube_id = NULL")
        conn.commit()
        log.info("All segments used — reshuffled corpus")
        row = conn.execute(
            "SELECT * FROM segments WHERE used = 0 ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    
    return dict(row) if row else None
```

### CLI

```bash
# Normal daily run (called by launchd)
python main.py

# Manual run for a specific day (for testing)
python main.py --run

# Show status
python main.py --status

# Test pipeline without uploading to YouTube
python main.py --dry-run

# Re-extract PDFs (calls pdf_extractor.py --reset)
python main.py --reimport
```

### Status Output Example
```
=== ACIM Daily Minute Status ===
Segments total:    2172
Segments used:     47
Segments remaining: 2125
Last upload:       2026-03-16  (Day 47)
Next upload:       2026-03-17  (Day 48)
Corpus exhaustion: ~5.8 years from now
YouTube channel:   ACIM Daily Minute
```

---

## Scheduling: `com.acim.dailyminute.plist`

macOS launchd plist — runs `python main.py` once daily at 6:00 AM local time.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.acim.dailyminute</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOUR_USERNAME/acim-daily-minute/main.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/acim-daily-minute</string>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/acim-daily-minute/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/acim-daily-minute/logs/launchd-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
```

### Install launchd

```bash
cp com.acim.dailyminute.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.acim.dailyminute.plist
launchctl list | grep acim   # verify loaded
```

---

## `requirements.txt`

```
pdfplumber>=0.10.0
nltk>=3.8
elevenlabs>=1.0.0
Pillow>=10.0.0
python-dotenv>=1.0.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1
requests>=2.31.0
```

System dependencies (install via Homebrew):
```bash
brew install ffmpeg
```

---

## `.gitignore`

```
.env
data/youtube_tokens.json
client_secrets.json
audio/
video/
logs/
__pycache__/
*.pyc
.DS_Store
```

---

## Build Order for Claude Code

Implement modules in this exact order — each depends on the previous:

1. **Project scaffold** — create all folders, `.env` template, `.gitignore`, `requirements.txt`
2. **`pdf_extractor.py`** — PDF parsing + chunking + SQLite schema creation
3. **`tts_generator.py`** — ElevenLabs TTS wrapper
4. **`video_builder.py`** — Pillow frame renderer + ffmpeg muxer
5. **`uploader.py`** — YouTube auth + upload (adapted from JTF News pattern)
6. **`setup_youtube.py`** — One-time OAuth setup wizard
7. **`main.py`** — Pipeline orchestrator + CLI + scheduling
8. **`com.acim.dailyminute.plist`** — launchd agent
9. **README.md** — Setup instructions: install deps → run pdf_extractor → run setup_youtube → test with --dry-run → install launchd

---

## First-Run Checklist (for README)

```
[ ] pip install -r requirements.txt
[ ] brew install ffmpeg
[ ] Copy 4 ACIM PDFs to ~/acim-daily-minute/pdfs/
[ ] Add a 1920x1080 background image to assets/background.jpg
[ ] Copy .env.template to .env and fill in ELEVENLABS_API_KEY
[ ] python pdf_extractor.py              # imports ~2000+ segments
[ ] python pdf_extractor.py --status     # verify count
[ ] Create YouTube channel "ACIM Daily Minute"
[ ] python setup_youtube.py              # OAuth + playlist setup
[ ] python main.py --dry-run             # test full pipeline, no upload
[ ] python main.py --run                 # first real upload
[ ] Install launchd plist for daily automation
```

---

## Notes for Claude Code

- **Do not share any code or imports with JTF News.** This is a fully self-contained project.
- **No OBS.** Video is built entirely with Pillow + ffmpeg subprocess — no screen recording.
- **No Claude AI API calls.** Text comes directly from the ACIM PDFs, no summarization or processing.
- **ElevenLabs Voice ID** is already cloned and ready: `yNH37Ooobr7UDkJSd3sa` — use this exactly.
- **YouTube OAuth** follows the identical pattern from JTF News `setup_youtube.py` — replicate that flow, just rebrand for ACIM.
- **Background image** — the user will provide `assets/background.jpg`. Code should check it exists and fall back to a solid dark purple (`#1a0a2e`) if missing.
- **Font fallback chain:** Try `Helvetica` → `Arial` → `DejaVuSans` → PIL default.
- **All paths** should use `pathlib.Path`, never string concatenation.
- **Logging** — use Python `logging` with a rotating file handler (10MB max, 5 backups) writing to `logs/acim.log`, plus console output.
- **The `.env` file** must never be created by the script — only a `.env.template` with placeholder values.
```
