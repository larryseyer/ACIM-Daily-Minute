#!/usr/bin/env python3
"""
setup_tiktok.py — One-time TikTok OAuth setup for ACIM Daily Minute.

Creates OAuth credentials for the TikTok Content Posting API.

Prerequisites:
1. Create TikTok account for "ACIM Daily Minute"
2. Register at https://developers.tiktok.com/
3. Create an app with video.publish scope
4. Submit for API audit (5-10 business days)
5. Add TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET to .env

Usage:
    python setup_tiktok.py
"""

import base64
import hashlib
import http.server
import json
import logging
import os
import secrets
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
TOKENS_PATH = DATA_DIR / "tiktok_tokens.json"

# TikTok OAuth endpoints
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

PROJECT_NAME = "ACIM Daily Minute"

# Authorization callback handler
auth_code = None
auth_error = None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback from TikTok."""

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

    def do_GET(self):
        global auth_code, auth_error

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: system-ui; text-align: center; padding: 50px;">
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        elif "error" in params:
            auth_error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html><body style="font-family: system-ui; text-align: center; padding: 50px;">
                <h1>Authorization Failed</h1>
                <p>Error: {auth_error}</p>
                <p>Please try again.</p>
                </body></html>
            """.encode())
        else:
            self.send_response(400)
            self.end_headers()


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge."""
    # Generate random code verifier (43-128 chars)
    code_verifier = secrets.token_urlsafe(32)

    # Create code challenge using S256 method
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return code_verifier, code_challenge


def main():
    global auth_code, auth_error

    print(f"\n{'='*50}")
    print(f"  {PROJECT_NAME} — TikTok Setup")
    print(f"{'='*50}\n")

    # Check for required environment variables
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")

    if not client_key or not client_secret:
        print("ERROR: TikTok credentials not found in .env")
        print()
        print("To set up TikTok API access:")
        print("1. Go to https://developers.tiktok.com/")
        print("2. Create a new app (or select existing)")
        print("3. Add the 'video.publish' scope")
        print("4. Submit for API audit (required for public posting)")
        print("5. Add to your .env file:")
        print("   TIKTOK_CLIENT_KEY=your_client_key")
        print("   TIKTOK_CLIENT_SECRET=your_client_secret")
        print("   TIKTOK_REDIRECT_URI=http://localhost:8080/callback")
        print()
        sys.exit(1)

    # Parse redirect URI to get port
    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    port = parsed_redirect.port or 8080

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    # Build authorization URL
    auth_params = {
        "client_key": client_key,
        "scope": "video.publish,video.upload",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{TIKTOK_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print("Starting OAuth flow — a browser window will open...")
    print(f"Redirect URI: {redirect_uri}")
    print()

    # Start local server for callback
    server = http.server.HTTPServer(("localhost", port), OAuthCallbackHandler)
    server.timeout = 300  # 5 minute timeout

    # Open browser
    webbrowser.open(auth_url)
    print("Waiting for authorization...")

    # Wait for callback
    while auth_code is None and auth_error is None:
        server.handle_request()

    server.server_close()

    if auth_error:
        print(f"\nERROR: Authorization failed: {auth_error}")
        sys.exit(1)

    print("\nAuthorization code received. Exchanging for tokens...")

    # Exchange code for tokens
    token_data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    try:
        response = requests.post(
            TIKTOK_TOKEN_URL,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        tokens = response.json()

        if "error" in tokens:
            print(f"\nERROR: Token exchange failed: {tokens.get('error_description', tokens['error'])}")
            sys.exit(1)

        # Save tokens
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKENS_PATH, "w") as f:
            json.dump(tokens, f, indent=2)

        print(f"\nCredentials saved to: {TOKENS_PATH}")

        # Show token info
        if "open_id" in tokens:
            print(f"TikTok Open ID: {tokens['open_id']}")
        if "expires_in" in tokens:
            hours = tokens["expires_in"] // 3600
            print(f"Access token expires in: {hours} hours")
        if "refresh_expires_in" in tokens:
            days = tokens["refresh_expires_in"] // 86400
            print(f"Refresh token expires in: {days} days")

    except requests.RequestException as e:
        print(f"\nERROR: Token exchange failed: {e}")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  Setup complete!")
    print(f"{'='*50}")
    print()
    print("Next steps:")
    print("1. Test with: python main.py --dry-run")
    print("2. Videos will now upload to both YouTube and TikTok")
    print()


if __name__ == "__main__":
    main()
