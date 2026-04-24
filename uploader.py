#!/usr/bin/env python3
from __future__ import annotations
"""
uploader.py — YouTube upload module for ACIM Daily Minute.

Authenticates with YouTube and uploads videos with metadata and thumbnails.
Adapted from JTF News upload pattern.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

log = logging.getLogger(__name__)

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
TOKENS_PATH = DATA_DIR / "youtube_tokens.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "27")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "ACIM Daily Minute")

TAGS = [
    "ACIM", "A Course in Miracles", "Helen Schucman",
    "spiritual", "daily reading", "meditation", "miracle",
]

# Fallback background color
FALLBACK_BG_COLOR = (26, 10, 46)


def get_youtube_credentials() -> tuple:
    """Returns (client_secrets_path, playlist_id) from .env"""
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
    secrets_path = BASE_DIR / secrets_file
    playlist_id = os.getenv("YOUTUBE_PLAYLIST_ID")
    return str(secrets_path), playlist_id


def get_authenticated_youtube_service():
    """Load/refresh OAuth tokens, return YouTube service object."""
    creds = None

    if TOKENS_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKENS_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        log.info("Refreshing expired YouTube credentials...")
        creds.refresh(Request())
        with open(TOKENS_PATH, "w") as f:
            f.write(creds.to_json())
    elif not creds or not creds.valid:
        secrets_path, _ = get_youtube_credentials()
        if not Path(secrets_path).exists():
            log.error(f"Client secrets file not found: {secrets_path}")
            log.error("Run setup_youtube.py first to configure YouTube OAuth.")
            return None

        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        creds = flow.run_local_server(port=0)
        TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKENS_PATH, "w") as f:
            f.write(creds.to_json())
        log.info("YouTube credentials saved.")

    return build("youtube", "v3", credentials=creds)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try font fallback chain."""
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
    return ImageFont.load_default()


def generate_thumbnail(day_number: int, output_path: str) -> bool:
    """
    Generate a 1280x720 PNG thumbnail.

    Args:
        day_number: The day number for subtitle text
        output_path: Path to save the thumbnail PNG

    Returns:
        True on success
    """
    thumb_w, thumb_h = 1280, 720
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Load background or use fallback
    img = None
    for ext in ("jpg", "jpeg", "png"):
        bg_path = ASSETS_DIR / f"background.{ext}"
        if bg_path.exists():
            try:
                img = Image.open(str(bg_path)).convert("RGB")
                img = img.resize((thumb_w, thumb_h), Image.LANCZOS)
                break
            except Exception:
                pass
    if img is None:
        img = Image.new("RGB", (thumb_w, thumb_h), FALLBACK_BG_COLOR)
    else:
        img = Image.new("RGB", (thumb_w, thumb_h), FALLBACK_BG_COLOR)

    # Apply dark overlay
    overlay = Image.new("RGBA", (thumb_w, thumb_h), (0, 0, 0, 140))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    draw = ImageDraw.Draw(img)

    # Title text
    title_font = _get_font(72)
    title = CHANNEL_NAME
    title_bbox = title_font.getbbox(title)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = (thumb_w - title_w) // 2
    draw.text((title_x, thumb_h // 2 - 80), title, font=title_font, fill="white")

    # Day subtitle
    subtitle_font = _get_font(48)
    subtitle = f"Day {day_number}"
    sub_bbox = subtitle_font.getbbox(subtitle)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_x = (thumb_w - sub_w) // 2
    draw.text((sub_x, thumb_h // 2 + 20), subtitle, font=subtitle_font, fill=(200, 200, 255))

    img.save(str(output), "PNG")
    log.info(f"Thumbnail saved: {output}")
    return True


def upload_video(video_path: str, title: str, description: str,
                 tags: list, thumbnail_path: str,
                 playlist_id: Optional[str] = None) -> Optional[str]:
    """
    Upload video to YouTube, set thumbnail, add to playlist.

    Args:
        video_path: Path to the MP4 file
        title: Video title
        description: Video description
        tags: List of tags
        thumbnail_path: Path to thumbnail PNG
        playlist_id: Optional playlist ID to add video to (overrides .env default)

    Returns:
        YouTube video ID on success, None on failure
    """
    from datetime import datetime

    youtube = get_authenticated_youtube_service()
    if not youtube:
        log.error("Failed to authenticate with YouTube")
        return None

    try:
        # Upload video
        today_iso = datetime.now().strftime("%Y-%m-%dT00:00:00.000Z")
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": CATEGORY_ID,
                "defaultLanguage": "en-US",
                "defaultAudioLanguage": "en-US",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "license": "creativeCommon",
                "embeddable": True,
                "publicStatsViewable": True,
            },
            "recordingDetails": {
                "recordingDate": today_iso,
            },
        }

        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=1024*1024)
        request = youtube.videos().insert(
            part="snippet,status,recordingDetails",
            body=body,
            media_body=media,
            notifySubscribers=True,
        )

        log.info(f"Uploading video: {title}")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log.info(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]
        log.info(f"Video uploaded: https://youtu.be/{video_id}")

        # Set thumbnail (compress to JPEG under 2MB if needed)
        if Path(thumbnail_path).exists():
            try:
                thumb_upload_path = thumbnail_path
                thumb_size = Path(thumbnail_path).stat().st_size
                if thumb_size > 2 * 1024 * 1024:
                    log.info(f"Thumbnail too large ({thumb_size/1024:.0f}KB), compressing...")
                    thumb_img = Image.open(thumbnail_path).convert("RGB")
                    thumb_img = thumb_img.resize((1280, 720), Image.LANCZOS)
                    compressed_path = str(Path(thumbnail_path).parent / "thumbnail_upload.jpg")
                    thumb_img.save(compressed_path, "JPEG", quality=85)
                    thumb_upload_path = compressed_path
                    log.info(f"Compressed to {Path(compressed_path).stat().st_size/1024:.0f}KB")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumb_upload_path, mimetype="image/jpeg"),
                ).execute()
                log.info("Thumbnail set successfully")
            except Exception as e:
                log.warning(f"Failed to set thumbnail: {e}")

        # Add to playlist (use provided playlist_id or fall back to .env default)
        if playlist_id is None:
            _, playlist_id = get_youtube_credentials()
        if playlist_id and playlist_id != "your_playlist_id_here":
            try:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        },
                    },
                ).execute()
                log.info(f"Added to playlist: {playlist_id}")
            except Exception as e:
                log.warning(f"Failed to add to playlist: {e}")

        return video_id

    except Exception as e:
        log.error(f"YouTube upload failed: {e}")
        return None
