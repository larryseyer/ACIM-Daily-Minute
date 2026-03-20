# ACIM Daily Minute

Automated daily 1-minute YouTube videos of A Course in Miracles readings using a cloned ElevenLabs voice, scrolling text video, and YouTube upload.

## How It Works

Each day the pipeline:
1. Picks a random unused ACIM text segment (~130-150 words)
2. Sends it to ElevenLabs TTS using a cloned voice
3. Renders a 1080p scrolling-text MP4 video with ffmpeg
4. Uploads it to the "ACIM Daily Minute" YouTube channel
5. Marks the segment as used; reshuffles when all are exhausted

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
brew install ffmpeg
```

### 2. Prepare Content

- Copy 4 ACIM PDFs to `pdfs/`:
  - `1_ACIM_Text_A.pdf`
  - `2_ACIM_Text_B.pdf`
  - `3_ACIM_Workbook.pdf`
  - `4_ACIM_Manual.pdf`
- Add a 1920x1080 background image to `assets/background.jpg`

### 3. Configure Environment

```bash
cp .env.template .env
# Edit .env and fill in your ELEVENLABS_API_KEY
```

### 4. Import ACIM Text

```bash
python pdf_extractor.py              # Imports ~2000+ segments
python pdf_extractor.py --status     # Verify count
```

### 5. Set Up YouTube

1. Create a YouTube channel named "ACIM Daily Minute"
2. Set up YouTube Data API v3 credentials at https://console.cloud.google.com/
3. Download OAuth client secrets as `client_secrets.json` in the project root
4. Run the setup wizard:

```bash
python setup_youtube.py
```

5. Update `YOUTUBE_PLAYLIST_ID` in `.env` with the playlist ID

### 6. Test

```bash
python main.py --dry-run    # Full pipeline test, no YouTube upload
python main.py --status     # Check status
```

### 7. First Real Upload

```bash
python main.py --run
```

### 8. Install Daily Automation

```bash
cp com.acim.dailyminute.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.acim.dailyminute.plist
launchctl list | grep acim   # Verify loaded
```

## Usage

```bash
python main.py              # Normal daily run (called by launchd)
python main.py --run        # Manual run
python main.py --status     # Show status
python main.py --dry-run    # Test without uploading
python main.py --reimport   # Re-extract PDFs
```

## Project Structure

```
acim-daily-minute/
├── pdfs/                    # ACIM PDF source files
├── data/acim.db             # SQLite database
├── audio/                   # Temp TTS audio (cleaned up after use)
├── video/                   # Final MP4 archive
├── assets/background.jpg    # Video background image
├── logs/acim.log            # Rotating log file
├── pdf_extractor.py         # PDF -> SQLite chunker
├── tts_generator.py         # ElevenLabs TTS
├── video_builder.py         # Pillow + ffmpeg video renderer
├── uploader.py              # YouTube upload
├── setup_youtube.py         # One-time OAuth setup
├── main.py                  # Pipeline orchestrator
└── com.acim.dailyminute.plist  # macOS launchd agent
```
