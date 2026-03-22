#!/usr/bin/env python3
"""
tiktok_uploader.py — TikTok upload module for ACIM Daily Minute.

Authenticates with TikTok Content Posting API and uploads videos.
Follows similar pattern to uploader.py (YouTube).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
TOKENS_PATH = DATA_DIR / "tiktok_tokens.json"

# TikTok API endpoints
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_UPLOAD_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Chunk size for video upload (10MB)
CHUNK_SIZE = 10 * 1024 * 1024


def _load_tokens() -> dict | None:
    """Load tokens from file."""
    if not TOKENS_PATH.exists():
        log.error(f"TikTok tokens not found: {TOKENS_PATH}")
        log.error("Run setup_tiktok.py first to configure TikTok OAuth.")
        return None

    with open(TOKENS_PATH) as f:
        return json.load(f)


def _save_tokens(tokens: dict):
    """Save tokens to file."""
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def _refresh_tokens(tokens: dict) -> dict | None:
    """Refresh access token using refresh token."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")

    if not client_key or not client_secret:
        log.error("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in .env")
        return None

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        log.error("No refresh token available. Run setup_tiktok.py again.")
        return None

    try:
        response = requests.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        new_tokens = response.json()

        if "error" in new_tokens:
            log.error(f"Token refresh failed: {new_tokens.get('error_description', new_tokens['error'])}")
            return None

        # Merge with existing tokens (preserve open_id, etc.)
        tokens.update(new_tokens)
        _save_tokens(tokens)
        log.info("TikTok tokens refreshed successfully")
        return tokens

    except requests.RequestException as e:
        log.error(f"Token refresh failed: {e}")
        return None


def get_valid_access_token() -> tuple[str, str] | None:
    """
    Get a valid access token, refreshing if needed.

    Returns:
        Tuple of (access_token, open_id) or None on failure
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    open_id = tokens.get("open_id")

    if not access_token or not open_id:
        log.error("Invalid token file. Run setup_tiktok.py again.")
        return None

    # Check if token might be expired (TikTok tokens typically last 24 hours)
    # We'll refresh proactively if we have a refresh token
    # In practice, we could track expiry time, but simpler to try and refresh on 401

    return access_token, open_id


def upload_video(
    video_path: str,
    title: str,
    privacy_level: str = "PUBLIC_TO_EVERYONE",
) -> str | None:
    """
    Upload video to TikTok using Content Posting API.

    Args:
        video_path: Path to the MP4 file
        title: Video title/caption (will include hashtags)
        privacy_level: One of PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS,
                      FOLLOWER_OF_CREATOR, SELF_ONLY

    Returns:
        TikTok publish_id on success, None on failure
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        log.error("No access token. Run setup_tiktok.py first.")
        return None

    video_file = Path(video_path)
    if not video_file.exists():
        log.error(f"Video file not found: {video_path}")
        return None

    file_size = video_file.stat().st_size
    log.info(f"Uploading to TikTok: {video_file.name} ({file_size / 1024 / 1024:.1f} MB)")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # Step 1: Initialize upload
    # Using "PULL_FROM_URL" would require hosting the video somewhere
    # Using "FILE_UPLOAD" for direct upload
    init_payload = {
        "post_info": {
            "title": title[:150],  # TikTok title limit
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,  # Use frame at 1 second for cover
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": min(CHUNK_SIZE, file_size),
            "total_chunk_count": (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE,
        },
    }

    try:
        init_response = requests.post(
            TIKTOK_UPLOAD_INIT_URL,
            headers=headers,
            json=init_payload,
        )

        # Check for auth errors and refresh if needed
        if init_response.status_code == 401:
            log.info("Access token expired, refreshing...")
            tokens = _refresh_tokens(tokens)
            if not tokens:
                return None
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
            init_response = requests.post(
                TIKTOK_UPLOAD_INIT_URL,
                headers=headers,
                json=init_payload,
            )

        init_response.raise_for_status()
        init_data = init_response.json()

        if init_data.get("error", {}).get("code") != "ok":
            error = init_data.get("error", {})
            log.error(f"TikTok upload init failed: {error.get('message', error)}")
            return None

        publish_id = init_data["data"]["publish_id"]
        upload_url = init_data["data"]["upload_url"]

        log.info(f"Upload initialized, publish_id: {publish_id}")

        # Step 2: Upload video chunks
        with open(video_path, "rb") as f:
            chunk_num = 0
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                chunk_start = chunk_num * CHUNK_SIZE
                chunk_end = chunk_start + len(chunk) - 1

                upload_headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {chunk_start}-{chunk_end}/{file_size}",
                }

                upload_response = requests.put(
                    upload_url,
                    headers=upload_headers,
                    data=chunk,
                )

                if upload_response.status_code not in (200, 201, 206):
                    log.error(f"Chunk upload failed: {upload_response.status_code}")
                    return None

                chunk_num += 1
                progress = min(100, (chunk_end + 1) / file_size * 100)
                log.info(f"Upload progress: {progress:.0f}%")

        log.info("Video uploaded successfully")

        # Step 3: Check publish status (video goes through processing)
        # We'll just return the publish_id; the video will be processed async
        log.info(f"TikTok publish_id: {publish_id}")
        log.info("Note: Video will be processed by TikTok before becoming visible")

        return publish_id

    except requests.RequestException as e:
        log.error(f"TikTok upload failed: {e}")
        return None


def check_publish_status(publish_id: str) -> dict | None:
    """
    Check the status of a video publish operation.

    Args:
        publish_id: The publish_id returned from upload_video

    Returns:
        Status dict with 'status' key (PROCESSING_UPLOAD, PROCESSING_DOWNLOAD,
        SEND_TO_USER_INBOX, PUBLISH_COMPLETE, FAILED) or None on error
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    if not access_token:
        return None

    try:
        response = requests.post(
            TIKTOK_UPLOAD_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        response.raise_for_status()
        data = response.json()

        if data.get("error", {}).get("code") != "ok":
            log.error(f"Status check failed: {data.get('error', {}).get('message')}")
            return None

        return data.get("data", {})

    except requests.RequestException as e:
        log.error(f"Status check failed: {e}")
        return None


def is_tiktok_configured() -> bool:
    """Check if TikTok is configured and ready to use."""
    if not TOKENS_PATH.exists():
        return False

    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")

    return bool(client_key and client_secret)
