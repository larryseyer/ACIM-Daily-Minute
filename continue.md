# Session Continuation - Daily Lessons Postponed

## CURRENT STATUS (March 27, 2026)

| Pipeline | Status | Notes |
|----------|--------|-------|
| **Daily Minute** (`main.py`) | ✅ Running normally | Continues posting daily |
| **Daily Lessons** (`lessons.py`) | ⏸️ Postponed | Wait until April 11th |

**Reason**: ElevenLabs quota exhausted (51 credits remaining). Conserving remaining credits for Daily Minute series which is already live and building audience.

**Credits renew**: April 11, 2026

---

## APRIL 11th: TEST DAILY LESSONS BEFORE LAUNCH

### Step 1: Test the Introduction Video
```bash
cd /Users/larryseyer/acim-daily-minute
./test_introduction.sh
```

**What to verify in the output video:**
- [ ] No "PART I" text appearing in video
- [ ] No mid-sentence gaps (spaces where there shouldn't be)
- [ ] 2-second pause at start before text appears
- [ ] Audio starts when text starts scrolling (not before)
- [ ] Text stays on screen until audio finishes (or slightly after)

### Step 2: If Introduction passes, test Lesson 1
```bash
./test_lessons.sh
```

**What to verify:**
- [ ] Lesson number spoken: "Lesson 1"
- [ ] Title in quotes visible and spoken
- [ ] No duplicate title reading

### Step 3: If both pass, you're ready to go live
```bash
python3 lessons.py --status           # Check current state
python3 lessons.py --run --force      # Upload Part 1 Introduction
```

---

## ALL CODE FIXES COMPLETED (March 27)

These fixes are already in place and waiting to be tested:

| Problem | Solution | File |
|---------|----------|------|
| Curly quotes not matching titles | Regex matches both `"..."` and `"..."` | `import_lessons.py` |
| Missing Part 1 & 2 Introductions | Added extraction with IDs 0 and 500 | `import_lessons.py` |
| "PART I" appearing in video text | Regex removes Roman numerals too | `import_lessons.py` |
| Title duplicated in audio | TTS now says "Lesson N" then text only | `lessons.py` |
| Mid-sentence gaps in video | Whitespace normalized to single spaces | `video_builder.py` |
| Audio starts before text visible | 2-second title hold + audio delay | `video_builder.py` |
| Text leaves screen too early | 85% scroll speed factor | `video_builder.py` |

### Credit-Saving Improvements (CRITICAL - prevents future waste)

| File | Change |
|------|--------|
| `cleanup_old_videos.sh` | No longer deletes audio files |
| `lessons.py` | Checks for existing audio before TTS call |
| `lessons.py` | Keeps audio after successful upload |
| `text_chapters.py` | Same credit-saving logic |
| `main.py` | Same credit-saving logic |

---

## DATABASE STATUS

**367 entries imported and ready:**
- ID 0: Part 1 Introduction (475 words)
- IDs 1-220: Part 1 Lessons
- ID 500: Part 2 Introduction (829 words)
- IDs 221-365: Part 2 Lessons

**Posting sequence will be:**
1. Part 1 Introduction (ID 0)
2. Lessons 1-220
3. Part 2 Introduction (ID 500)
4. Lessons 221-365
5. Repeat from beginning

---

## AFTER DAILY LESSONS ARE WORKING

### Still TODO:

1. **Add source attribution to Daily Minute**
   - Modify `main.py` description to say which part of ACIM the reading is from
   - This doesn't require TTS credits (description only)

2. **Create Manual for Teachers pipeline**
   - `import_manual.py` - Parse ACIM_Manual.txt
   - `migrate_db_manual.py` - Create database tables
   - `manual.py` - Pipeline orchestrator
   - This is for ~2 years from now (after Text series)

---

## QUICK REFERENCE

### Test Scripts (use these first)
```bash
./test_introduction.sh      # Part 1 Introduction (ID 0)
./test_lessons.sh           # Lesson 1
./test_text.sh              # Text Section 509
```

### Production Scripts
```bash
python3 lessons.py --run --force    # Upload next lesson
python3 lessons.py --status         # Check progress
```

### Reset Scripts (if needed)
```bash
./reset_lessons_log.sh      # Clear upload history
./cleanup_old_videos.sh     # Delete videos (keeps audio!)
```

---

## ENVIRONMENT NOTES

- **Python runs on**: Intel Mac (local) at `/Users/larryseyer/acim-daily-minute`
- **Claude sees files at**: `/Volumes/MacLive/Users/larryseyer/acim-daily-minute`
- **Always give user paths as**: `/Users/larryseyer/...`

---

*Last updated: March 27, 2026 - Daily Minute continues; Daily Lessons postponed to April 11th*
