#!/usr/bin/env python3
"""
video_builder.py — Pillow frame renderer + ffmpeg muxer for ACIM Daily Minute.

Creates MP4 videos with ACIM text scrolling vertically over a background image,
synced to the audio duration. Supports both horizontal (1920x1080 for YouTube)
and vertical (1080x1920 for TikTok) formats.
"""

import json
import logging
import os
import subprocess
import textwrap
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

log = logging.getLogger(__name__)

# --- Configuration from .env ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
FPS = int(os.getenv("VIDEO_FPS", "30"))
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "ACIM Daily Minute")

# Format-specific configurations
FORMAT_CONFIGS = {
    "horizontal": {
        "width": 1920,
        "height": 1080,
        "font_size": 52,
        "margin_x": 80,
        "box_pad_x": 40,
        "box_pad_y": 30,
        "background_file": "background-minute",
    },
    "vertical": {
        "width": 1080,
        "height": 1920,
        "font_size": 44,
        "margin_x": 60,
        "box_pad_x": 30,
        "box_pad_y": 25,
        "background_file": "background-minute_tiktok",
    },
}

VideoFormat = Literal["horizontal", "vertical"]

# Fallback background color if no image
FALLBACK_BG_COLOR = (26, 10, 46)  # dark purple #1a0a2e


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try font fallback chain: Helvetica -> Arial -> DejaVuSans -> default."""
    font_names = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for font_path in font_names:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except (OSError, IOError):
                continue
    log.warning("No system fonts found, using PIL default")
    return ImageFont.load_default()


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def _get_background(width: int, height: int, background_file: str = "background") -> Image.Image:
    """Load background image or create solid color fallback."""
    for ext in ("jpg", "jpeg", "png"):
        bg_path = ASSETS_DIR / f"{background_file}.{ext}"
        if bg_path.exists():
            try:
                bg = Image.open(str(bg_path)).convert("RGB")
                log.info(f"Loaded background: {bg_path}")
                return bg.resize((width, height), Image.LANCZOS)
            except Exception as e:
                log.warning(f"Failed to load background image: {e}")

    log.info("Using solid dark purple background (no background image found)")
    return Image.new("RGB", (width, height), FALLBACK_BG_COLOR)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, text_width: int) -> list[str]:
    """Wrap text to fit within text_width pixels."""
    # Estimate characters per line based on average char width
    test_text = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    bbox = font.getbbox(test_text)
    avg_char_width = (bbox[2] - bbox[0]) / len(test_text)
    chars_per_line = int(text_width / avg_char_width)

    lines = textwrap.wrap(text, width=chars_per_line)
    return lines


def _calculate_text_height(lines: list[str], font: ImageFont.FreeTypeFont, line_spacing: int) -> int:
    """Calculate total height of wrapped text block."""
    if not lines:
        return 0
    bbox = font.getbbox("Ay")
    line_height = (bbox[3] - bbox[1]) + line_spacing
    return len(lines) * line_height


def build_video(
    text: str,
    audio_path: str,
    output_path: str,
    format: VideoFormat = "horizontal",
    background_prefix: Optional[str] = None,
) -> bool:
    """
    Render scrolling text video synced to audio.

    Args:
        text: The ACIM segment text to display
        audio_path: Path to the MP3 from ElevenLabs
        output_path: Path to write the final MP4
        format: Video format - "horizontal" (1920x1080) or "vertical" (1080x1920)
        background_prefix: Optional prefix for background images. When set,
            uses "{prefix}.jpg" for horizontal and "{prefix}_tiktok.jpg" for vertical.
            Example: background_prefix="background-lessons" uses "background-lessons.jpg" and "background-lessons_tiktok.jpg"

    Returns:
        True on success, False on failure
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Get format-specific configuration
    config = FORMAT_CONFIGS[format]
    width = config["width"]
    height = config["height"]
    font_size = config["font_size"]
    margin_x = config["margin_x"]
    box_pad_x = config["box_pad_x"]
    box_pad_y = config["box_pad_y"]

    # Determine background file - use prefix if provided, else default
    if background_prefix:
        # Custom background: "prefix" for horizontal, "prefix_tiktok" for vertical
        background_file = background_prefix if format == "horizontal" else f"{background_prefix}_tiktok"
    else:
        background_file = config["background_file"]

    text_width = width - (2 * margin_x)

    log.info(f"Building {format} video ({width}x{height})")

    try:
        # Get audio duration
        duration = _get_audio_duration(audio_path)
        total_frames = int(duration * FPS)
        log.info(f"Audio duration: {duration:.1f}s, total frames: {total_frames}")

        # Prepare rendering resources
        font = _get_font(font_size)
        background = _get_background(width, height, background_file)
        lines = _wrap_text(text, font, text_width)

        # Calculate line height
        bbox = font.getbbox("Ay")
        line_height = (bbox[3] - bbox[1])
        line_spacing = 16
        total_line_height = line_height + line_spacing

        # Calculate scroll distance
        text_block_height = len(lines) * total_line_height
        # Text starts below screen, scrolls until it's above screen
        total_scroll = height + text_block_height
        pixels_per_frame = total_scroll / total_frames if total_frames > 0 else 1

        log.info(
            f"Text: {len(lines)} lines, block height: {text_block_height}px, "
            f"scroll speed: {pixels_per_frame:.2f} px/frame"
        )

        # Step 1: Render frames to a temporary raw video file
        raw_path = str(output) + ".raw"
        log.info("Rendering frames to temp file...")

        with open(raw_path, "wb") as raw_file:
            for frame_num in range(total_frames):
                # Start with background
                frame = background.copy().convert("RGBA")

                # Calculate Y offset — text starts below screen and scrolls up
                y_offset = height - (frame_num * pixels_per_frame)

                # Draw semi-transparent shaded box behind text that scrolls with it
                box_top = int(y_offset - box_pad_y)
                box_bottom = int(y_offset + text_block_height + box_pad_y)
                box_left = margin_x - box_pad_x
                box_right = width - margin_x + box_pad_x

                # Only draw box if it's at least partially visible
                if box_bottom > 0 and box_top < height:
                    box_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    box_draw = ImageDraw.Draw(box_overlay)
                    box_draw.rounded_rectangle(
                        [box_left, max(box_top, -20), box_right, min(box_bottom, height + 20)],
                        radius=20,
                        fill=(0, 0, 0, 150),
                    )
                    frame = Image.alpha_composite(frame, box_overlay)

                frame = frame.convert("RGB")
                draw = ImageDraw.Draw(frame)

                # Draw each line of text
                for i, line in enumerate(lines):
                    y = y_offset + (i * total_line_height)
                    # Only draw if line is visible
                    if -total_line_height < y < height + total_line_height:
                        # Center text horizontally
                        line_bbox = font.getbbox(line)
                        line_w = line_bbox[2] - line_bbox[0]
                        x = (width - line_w) // 2
                        # Draw dark outline around text
                        outline_color = (0, 0, 0)
                        for ox, oy in [(-2,-2),(-2,0),(-2,2),(0,-2),(0,2),(2,-2),(2,0),(2,2)]:
                            draw.text((x+ox, y+oy), line, font=font, fill=outline_color)
                        draw.text((x, y), line, font=font, fill="white")

                raw_file.write(frame.tobytes())

                # Progress logging every 10%
                if total_frames > 0 and frame_num % max(1, total_frames // 10) == 0:
                    pct = (frame_num / total_frames) * 100
                    log.info(f"Rendering: {pct:.0f}% ({frame_num}/{total_frames} frames)")

        log.info("Frames rendered. Encoding video with ffmpeg...")

        # Step 2: Use ffmpeg to encode the raw video file with audio
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgb24",
            "-r", str(FPS),
            "-i", raw_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=600)

        # Clean up raw file
        Path(raw_path).unlink(missing_ok=True)

        if result.returncode != 0:
            log.error(f"ffmpeg failed: {result.stderr[-500:]}")
            return False

        file_size = output.stat().st_size / (1024 * 1024)
        log.info(f"Video saved: {output} ({file_size:.1f} MB)")
        return True

    except Exception as e:
        # Clean up raw file on error
        raw_path = str(output) + ".raw"
        Path(raw_path).unlink(missing_ok=True)
        log.error(f"Video build failed: {e}")
        return False
