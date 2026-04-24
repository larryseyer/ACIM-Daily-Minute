#!/bin/bash
# Delete old lesson and text videos (they don't have titles read)
cd "$(dirname "$0")"

echo "=== Cleaning up old videos without titles ==="

# Count before
LESSON_COUNT=$(find video/daily-lessons -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
TEXT_COUNT=$(find video/text-series -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')

echo "Found $LESSON_COUNT lesson videos"
echo "Found $TEXT_COUNT text videos"

# Delete lesson videos
if [ -d "video/daily-lessons" ]; then
    rm -f video/daily-lessons/*.mp4
    echo "Deleted lesson videos"
fi

# Delete text videos
if [ -d "video/text-series" ]; then
    rm -f video/text-series/*.mp4
    echo "Deleted text videos"
fi

# PRESERVE audio files to save ElevenLabs credits!
# Audio files are expensive (TTS credits) - only delete videos
echo "Audio files PRESERVED (saving ElevenLabs credits)"

echo "=== Cleanup complete - videos deleted, audio preserved ==="
