#!/usr/bin/env python3
"""
setup_youtube.py — One-time YouTube OAuth setup for ACIM Daily Minute.

Creates OAuth credentials and optionally creates the ACIM Daily Minute playlist.

Usage:
    python setup_youtube.py
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
TOKENS_PATH = DATA_DIR / "youtube_tokens.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

PROJECT_NAME = "ACIM Daily Minute"
PLAYLIST_TITLE = "ACIM Daily Minute"
PLAYLIST_DESCRIPTION = "Daily one-minute readings from A Course in Miracles."


def main():
    print(f"\n{'='*50}")
    print(f"  {PROJECT_NAME} — YouTube Setup")
    print(f"{'='*50}\n")

    # Check for client secrets
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
    secrets_path = BASE_DIR / secrets_file

    if not secrets_path.exists():
        print(f"ERROR: Client secrets file not found: {secrets_path}")
        print()
        print("To set up YouTube API access:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (or select existing)")
        print("3. Enable the YouTube Data API v3")
        print("4. Create OAuth 2.0 credentials (Desktop application)")
        print("5. Download the JSON and save it as:")
        print(f"   {secrets_path}")
        print()
        sys.exit(1)

    # Authenticate
    print("Starting OAuth flow — a browser window will open...")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save tokens
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Credentials saved to: {TOKENS_PATH}")

    # Build YouTube service
    youtube = build("youtube", "v3", credentials=creds)

    # Get channel info
    try:
        channels = youtube.channels().list(part="snippet", mine=True).execute()
        if channels.get("items"):
            channel = channels["items"][0]
            print(f"\nAuthenticated as: {channel['snippet']['title']}")
            print(f"Channel ID: {channel['id']}")
        else:
            print("\nWarning: No YouTube channel found for this account.")
    except Exception as e:
        log.warning(f"Could not fetch channel info: {e}")

    # Offer to create playlist
    print()
    create = input(f"Create playlist '{PLAYLIST_TITLE}'? (y/n): ").strip().lower()
    if create == "y":
        try:
            playlist = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": PLAYLIST_TITLE,
                        "description": PLAYLIST_DESCRIPTION,
                    },
                    "status": {
                        "privacyStatus": "public",
                    },
                },
            ).execute()
            playlist_id = playlist["id"]
            print(f"\nPlaylist created: {PLAYLIST_TITLE}")
            print(f"Playlist ID: {playlist_id}")
            print(f"\nUpdate your .env file:")
            print(f"  YOUTUBE_PLAYLIST_ID={playlist_id}")
        except Exception as e:
            log.error(f"Failed to create playlist: {e}")
    else:
        print("Skipped playlist creation.")

    print(f"\n{'='*50}")
    print(f"  Setup complete!")
    print(f"{'='*50}")
    print()
    print("Next steps:")
    print("1. Update YOUTUBE_PLAYLIST_ID in your .env file (if you created a playlist)")
    print("2. Run: python pdf_extractor.py")
    print("3. Run: python main.py --dry-run")
    print()


if __name__ == "__main__":
    main()
