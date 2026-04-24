#!/usr/bin/env python3
"""
tts_generator.py — ElevenLabs TTS wrapper for ACIM Daily Minute.

Sends text to ElevenLabs using a cloned ACIM voice and saves the resulting MP3.
Automatically chunks long text (>10,000 chars) and concatenates audio.
"""

import logging
import os
import re
import subprocess
import tempfile
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
MAX_CHARS = 9500  # ElevenLabs limit is 10,000; use 9500 for safety margin


def split_text_into_chunks(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """
    Split text into chunks under max_chars, breaking at sentence boundaries.

    Prioritizes breaking at paragraph boundaries, then sentences, then as last
    resort at word boundaries.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find a good break point within max_chars
        chunk = remaining[:max_chars]

        # Try to break at paragraph boundary (double newline)
        para_break = chunk.rfind('\n\n')
        if para_break > max_chars // 2:
            break_point = para_break + 2
        else:
            # Try to break at sentence boundary
            # Look for . ! or ? followed by space or newline
            sentence_matches = list(re.finditer(r'[.!?][\s\n]', chunk))
            if sentence_matches and sentence_matches[-1].end() > max_chars // 2:
                break_point = sentence_matches[-1].end()
            else:
                # Last resort: break at last space
                space_break = chunk.rfind(' ')
                if space_break > max_chars // 2:
                    break_point = space_break + 1
                else:
                    # Absolute last resort: hard break at max_chars
                    break_point = max_chars

        chunks.append(remaining[:break_point].strip())
        remaining = remaining[break_point:].strip()

    return chunks


def concatenate_audio_files(input_files: list[str], output_path: str) -> bool:
    """
    Concatenate multiple MP3 files using ffmpeg.
    """
    if len(input_files) == 1:
        # Just copy the single file
        import shutil
        shutil.copy(input_files[0], output_path)
        return True

    # Create a temporary file list for ffmpeg
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        list_file = f.name
        for audio_file in input_files:
            f.write(f"file '{audio_file}'\n")

    try:
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            log.error(f"ffmpeg concat failed: {result.stderr}")
            return False

        return True
    finally:
        # Clean up list file
        Path(list_file).unlink(missing_ok=True)


def _generate_single_chunk(client: ElevenLabs, text: str, output_path: Path) -> bool:
    """Generate audio for a single chunk of text (must be under MAX_CHARS)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(
                f"Generating TTS (attempt {attempt}/{MAX_RETRIES}, "
                f"{len(text.split())} words, {len(text)} chars, voice={VOICE_ID})"
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
            with open(output_path, "wb") as f:
                for chunk in audio_iterator:
                    f.write(chunk)

            file_size = output_path.stat().st_size
            if file_size == 0:
                log.warning("Generated audio file is empty")
                output_path.unlink(missing_ok=True)
                continue

            log.info(f"Chunk audio saved: {output_path.name} ({file_size / 1024:.1f} KB)")

            # Log API cost
            try:
                from cost_tracker import log_api_usage
                log_api_usage("elevenlabs", {"characters": len(text)})
            except Exception:
                pass  # Cost tracking should never break TTS

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


def generate_audio(text: str, output_path: str) -> bool:
    """
    Generate TTS audio for text using ElevenLabs cloned voice.

    Automatically chunks long text (>10,000 chars) and concatenates audio.

    Args:
        text: The ACIM segment text (any length)
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

    # Split into chunks if needed
    chunks = split_text_into_chunks(text)
    total_chars = len(text)

    if len(chunks) == 1:
        # Simple case: single chunk
        log.info(f"Generating TTS for {len(text.split())} words ({total_chars} chars)")
        return _generate_single_chunk(client, text, output)

    # Multiple chunks needed
    log.info(
        f"Text too long ({total_chars} chars), splitting into {len(chunks)} chunks"
    )

    temp_files = []
    try:
        # Generate audio for each chunk
        for i, chunk in enumerate(chunks, 1):
            log.info(f"Processing chunk {i}/{len(chunks)} ({len(chunk)} chars)")

            temp_path = output.parent / f"{output.stem}_chunk{i:03d}.mp3"
            temp_files.append(str(temp_path))

            if not _generate_single_chunk(client, chunk, temp_path):
                log.error(f"Failed to generate chunk {i}")
                return False

            # Brief pause between API calls to avoid rate limiting
            if i < len(chunks):
                time.sleep(1)

        # Concatenate all chunks
        log.info(f"Concatenating {len(temp_files)} audio chunks...")
        if not concatenate_audio_files(temp_files, str(output)):
            log.error("Failed to concatenate audio chunks")
            return False

        file_size = output.stat().st_size
        log.info(
            f"TTS audio saved: {output} ({file_size / 1024:.1f} KB, "
            f"{total_chars} chars in {len(chunks)} chunks)"
        )
        return True

    finally:
        # Clean up temporary chunk files
        for temp_file in temp_files:
            Path(temp_file).unlink(missing_ok=True)
