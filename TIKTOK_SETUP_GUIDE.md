# TikTok Setup Guide for ACIM Daily Minute

This guide walks you through setting up TikTok integration for automated daily posting.

**Total time:** ~30 minutes of work + 5-10 business days waiting for API audit

---

## Phase 1: Create TikTok Account

**Time:** ~5 minutes

### Step 1.1: Create a New TikTok Account

1. Open an **incognito/private browser window** (to avoid using your personal account)
2. Go to [tiktok.com](https://www.tiktok.com)
3. Click **Sign up**
4. Choose **Use phone or email** → **Sign up with email**
5. Use a dedicated email (e.g., `acimdailyminute@gmail.com` or your existing email with a + alias like `larryseyer+acim@gmail.com`)
6. Create a strong password
7. Complete the CAPTCHA and verify your email

### Step 1.2: Set Up Your Profile

1. Click your profile icon → **Edit profile**
2. **Username:** `acimdailyminute` (or similar, must be unique)
3. **Name:** `ACIM Daily Minute`
4. **Bio:** `Daily one-minute readings from A Course in Miracles. A spiritual thought system scribed by Helen Schucman.`
5. **Profile photo:** Use your channel branding (optional for now)

### Step 1.3: Switch to Business Account (Recommended)

1. Go to **Settings** → **Manage account** → **Switch to Business Account**
2. Select category: **Education** or **Personal Blog**
3. This gives you access to analytics and looks more professional

---

## Phase 2: Register as TikTok Developer

**Time:** ~10 minutes

### Step 2.1: Access Developer Portal

1. Go to [developers.tiktok.com](https://developers.tiktok.com)
2. Click **Log in** (top right)
3. Sign in with your **ACIM Daily Minute TikTok account** (not your personal account)

### Step 2.2: Accept Developer Terms

1. You'll be prompted to accept the TikTok Developer Terms of Service
2. Read and accept the terms
3. You may need to verify your email again

### Step 2.3: Complete Developer Profile

1. Fill out required information:
   - **Company/Individual name:** Your name or "ACIM Daily Minute"
   - **Contact email:** Your email
   - **Country/Region:** United States
2. Save your profile

---

## Phase 3: Create TikTok App

**Time:** ~15 minutes

### Step 3.1: Create New App

1. In the developer portal, click **Manage apps** (top navigation)
2. Click **Create app** or **Connect an app**
3. Select **Content Posting API** as your use case

### Step 3.2: Fill Out App Information

| Field | Value |
|-------|-------|
| **App name** | `ACIM Daily Minute` |
| **App description** | `Automated daily posting of one-minute spiritual readings from A Course in Miracles. Videos feature scrolling text synchronized to narrated audio.` |
| **App icon** | Upload your channel logo (optional) |
| **Category** | Education / Lifestyle |
| **Platform** | Web |

### Step 3.3: Configure API Scopes

1. Go to **Products** or **Add products**
2. Find **Content Posting API** and click **Add** or **Configure**
3. Enable these scopes:
   - ✅ `video.upload` — Upload video files
   - ✅ `video.publish` — Publish videos to TikTok

### Step 3.4: Set Redirect URI

1. Go to **Configuration** or **Settings**
2. Find **Redirect URI** or **OAuth settings**
3. Add exactly this URI:
   ```
   http://localhost:8080/callback
   ```
4. Save changes

### Step 3.5: Note Your Credentials

After creating the app, you'll see:
- **Client Key** (also called App ID)
- **Client Secret** (click to reveal)

**Save these somewhere secure** — you'll need them in Phase 5.

---

## Phase 4: Submit for API Audit

**Time:** ~10 minutes to submit, then 5-10 business days waiting

### Step 4.1: Prepare Audit Submission

TikTok requires an audit before you can post publicly. Go to **Submit for review** or **API Audit**.

### Step 4.2: Fill Out Audit Form

**Use case description example:**
```
ACIM Daily Minute is an automated content posting system that publishes
daily one-minute spiritual readings from A Course in Miracles.

- Each video features scrolling text synchronized to AI-narrated audio
- Videos are 60-90 seconds in length
- Content is educational/spiritual in nature
- One video is posted per day at a scheduled time
- The same content is posted to YouTube (already operational)
- No user data is collected; this is a one-way posting system
```

**Explain why you need the API:**
```
We need the Content Posting API to automate daily video uploads.
Manual posting is not feasible for a daily content schedule.
The API allows our pipeline to upload and publish videos automatically.
```

### Step 4.3: Submit and Wait

1. Submit your audit request
2. TikTok will review (typically 5-10 business days)
3. You may receive follow-up questions via email — respond promptly
4. You'll get an email when approved

### Step 4.4: Check Audit Status

1. Return to [developers.tiktok.com](https://developers.tiktok.com)
2. Go to **Manage apps** → your app
3. Check the status:
   - **Pending** — Still under review
   - **Approved** — Ready to use!
   - **Rejected** — Read feedback and resubmit

---

## Phase 5: Configure Your Environment

**Time:** ~2 minutes (after audit approval)

### Step 5.1: Get Your Credentials

1. Go to [developers.tiktok.com](https://developers.tiktok.com) → **Manage apps**
2. Click on your ACIM Daily Minute app
3. Copy your **Client Key** and **Client Secret**

### Step 5.2: Add to .env File

On your Intel Mac, edit the `.env` file:

```bash
cd /Users/larryseyer/acim-daily-minute
nano .env
```

Add these lines (replace with your actual values):

```env
# TikTok
TIKTOK_CLIENT_KEY=your_actual_client_key_here
TIKTOK_CLIENT_SECRET=your_actual_client_secret_here
TIKTOK_REDIRECT_URI=http://localhost:8080/callback
```

Save and exit (Ctrl+X, then Y, then Enter).

---

## Phase 6: Run Authorization Setup

**Time:** ~2 minutes

### Step 6.1: Run the Database Migration

First, add the TikTok columns to your database:

```bash
cd /Users/larryseyer/acim-daily-minute
source venv/bin/activate
python migrate_db_tiktok.py
```

You should see:
```
=== ACIM Daily Minute — Database Migration ===

Adding tiktok_id column to segments table...
Adding tiktok_id column to upload_log table...
Adding tiktok_success column to upload_log table...
Migration complete: 3 column(s) added

Migration successful!
```

### Step 6.2: Run TikTok Setup

```bash
python setup_tiktok.py
```

This will:
1. Open your web browser to TikTok's authorization page
2. Ask you to log in to your ACIM Daily Minute TikTok account
3. Ask you to authorize the app
4. Capture the authorization and save tokens

You should see:
```
=== ACIM Daily Minute — TikTok Setup ===

Starting OAuth flow — a browser window will open...
Redirect URI: http://localhost:8080/callback

Waiting for authorization...
Authorization code received. Exchanging for tokens...

Credentials saved to: data/tiktok_tokens.json

=== Setup complete! ===
```

---

## Phase 7: Test the Integration

**Time:** ~5 minutes

### Step 7.1: Check Status

```bash
python main.py --status
```

You should see TikTok listed as "Configured":
```
=== ACIM Daily Minute Status ===
Segments total:     1847
Segments used:      5
Segments remaining: 1842

--- Platforms ---
YouTube:            Configured
  Uploads:          5
TikTok:             Configured
```

### Step 7.2: Dry Run Test

Test the full pipeline without actually uploading:

```bash
python main.py --dry-run
```

This will:
- Pick a segment
- Generate audio
- Build BOTH video formats (horizontal + vertical)
- Show what would be uploaded
- Clean up temp files

Look for:
```
Building horizontal video (1920x1080)
...
Building vertical video (1080x1920)
...
DRY RUN — would upload: ACIM Daily Minute for 2024-03-22 — Day 6
YouTube Video: video/acim-day-0006-2024-03-22.mp4
TikTok Video: video/acim-day-0006-2024-03-22-tiktok.mp4
```

### Step 7.3: Live Test (Optional)

When ready, do a real upload:

```bash
python main.py --run
```

Or test TikTok only (without affecting YouTube):

```bash
python main.py --run --tiktok-only
```

---

## Troubleshooting

### "TikTok credentials not found in .env"

Make sure your `.env` file contains:
```env
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
```

### "Authorization failed" during setup

1. Make sure you're logging into the **ACIM Daily Minute** TikTok account, not your personal account
2. Check that the redirect URI in developer portal matches exactly: `http://localhost:8080/callback`
3. Ensure your app has been approved (audit complete)

### "Token refresh failed"

Your tokens may have expired. Run setup again:
```bash
python setup_tiktok.py
```

### TikTok upload fails but YouTube works

Check the logs:
```bash
cat logs/acim.log | grep -i tiktok
```

Common issues:
- Token expired (run `setup_tiktok.py` again)
- Video rejected by TikTok (check TikTok creator inbox for details)
- API quota exceeded (wait and retry)

### Videos not appearing on TikTok

TikTok processes videos asynchronously. It may take a few minutes for the video to appear. Check your TikTok creator inbox for any content moderation notices.

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `python main.py --status` | Check configuration status |
| `python main.py --dry-run` | Test without uploading |
| `python main.py --run` | Upload to both platforms |
| `python main.py --run --skip-tiktok` | YouTube only |
| `python main.py --run --tiktok-only` | TikTok only |
| `python setup_tiktok.py` | Re-authorize TikTok |
| `python migrate_db_tiktok.py` | Add TikTok columns to database |

---

## Timeline Summary

| Phase | Action | Time |
|-------|--------|------|
| 1 | Create TikTok account | 5 min |
| 2 | Register as developer | 10 min |
| 3 | Create app | 15 min |
| 4 | Submit for audit | 10 min + **5-10 days wait** |
| 5 | Add credentials to .env | 2 min |
| 6 | Run setup_tiktok.py | 2 min |
| 7 | Test | 5 min |

**Total active work:** ~45 minutes
**Total elapsed time:** 5-10 business days (audit wait)
