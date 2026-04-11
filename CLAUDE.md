# ACIM Daily Minute — Website

## Overview

Static website for [acimdailyminute.org](https://acimdailyminute.org), served via GitHub Pages from the `docs/` folder. Free daily readings from A Course in Miracles.

**Repo:** https://github.com/larryseyer/ACIM-Daily-Minute

## Architecture

- **No build step** — plain HTML, CSS, and JavaScript
- **GitHub Pages** — served from `docs/` on `main` branch
- **Custom domain** — acimdailyminute.org (CNAME in docs/)
- **Design system** — `docs/style.css` with CSS custom properties
- **Dark mode default** — light mode via `data-theme="light"` on `<html>`, toggled by `docs/theme.js`
- **Nav/footer** — inline in every HTML file (no templating, same pattern as JTFNews)

## Development Environment

- **Files live on:** 2012 Intel MacBook Pro (network-mounted)
- **M4 path:** `/Volumes/MacLive/Users/larryseyer/ACIMDailyMinute`
- **Intel path:** `/Users/larryseyer/ACIMDailyMinute`
- File editing from M4 is fine; Python execution must happen on the Intel machine
- **Serena MCP does NOT work** on this network mount — use Claude Code native tools only

## Related Projects

| Project | Intel Path | Purpose |
|---------|-----------|---------|
| Backend | `/Users/larryseyer/acim-daily-minute` | Python pipeline: TTS, video, YouTube/TikTok uploads |
| Website | `/Users/larryseyer/ACIMDailyMinute` | This project — GitHub Pages site |
| iOS App | (M4 local) `/Users/larryseyer/ACIMDailyMinuteApp` | Future SwiftUI app |

The backend pushes data to this website's repo via GitHub API (not git push).

## Content Streams

1. **Daily Minute** — random ACIM text segment, 7 days/week (active)
2. **Daily Lessons** — sequential Workbook 1-365, weekdays only (active)
3. **Text Series** — complete Text read aloud (coming after Lessons complete, ~1.5 years)
4. **Manual for Teachers** — future, after Text Series

## Conventions

- CSS uses numbered section headers: `/* === N. SECTION NAME === */`
- Color tokens: `--color-gold` (Daily Minute), `--color-blue` (Lessons), `--color-text-muted` (Text Series)
- Typography: Georgia serif for headings/passages, system sans-serif for UI
- Buttons: pill-shaped with `--radius-pill`
- Mobile breakpoint: 768px
- When adding new pages: copy nav/footer from an existing page, update `aria-current="page"`

## Master Plan

See `/Users/larryseyer/.claude/plans/structured-floating-hickey.md` for the full implementation plan across all phases.
