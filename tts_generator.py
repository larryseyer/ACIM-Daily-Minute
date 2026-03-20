#!/usr/bin/env python3
"""
tts_generator.py — ElevenLabs TTS wrapper for ACIM Daily Minute.

Sends text to ElevenLabs using a cloned ACIM voice and saves the resulting MP3.
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import ElevenLabs

load_dotenv()

log = logging.getLogger(__name__)

# --- Configuration ---
API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "yNH37Ooobr7UDkJSd3sa")
MODEL_ID = "eleven_multilingual_v2"

VOICE_SETTINGS = {
    "stability": 0.71,
    "similarity_boost": 0.85,
    "style": 0.20,
    "use_speaker_boost": True,
}

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def generate_audio(text: str, output_path: str) -> bool:
    """
    Generate TTS audio for text using ElevenLabs cloned voice.

    Args:
        text: The ACIM segment text (~130-150 words)
        output_path: Full path to save the MP3 file

    Returns:
        True on success, False on failure
    """
    if not API_KEY:
        log.error("ELEVENLABS_API_KEY not set in environment")
        return False

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    client = ElevenLabs(api_key=API_KEY)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(
                f"Generating TTS (attempt {attempt}/{MAX_RETRIES}, "
                f"{len(text.split())} words, voice={VOICE_ID})"
            )

            audio_iterator = client.text_to_speech.convert(
                voice_id=VOICE_ID,
                text=text,
                model_id=MODEL_ID,
                voice_settings={
                    "stability": VOICE_SETTINGS["stability"],
                    "similarity_boost": VOICE_SETTINGS["similarity_boost"],
                    "style": VOICE_SETTINGS["style"],
                    "use_speaker_boost": VOICE_SETTINGS["use_speaker_boost"],
                },
            )

            # Write audio chunks to file
            with open(output, "wb") as f:
                for chunk in audio_iterator:
                    f.write(chunk)

            file_size = output.stat().st_size
            if file_size == 0:
                log.warning("Generated audio file is empty")
                output.unlink(missing_ok=True)
                continue

            log.info(
                f"TTS audio saved: {output} ({file_size / 1024:.1f} KB, "
                f"~{len(text)} chars used)"
            )
            return True

        except Exception as e:
            log.warning(f"TTS attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                log.info(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                log.error(f"TTS generation failed after {MAX_RETRIES} attempts: {e}")
                return False

    return False
