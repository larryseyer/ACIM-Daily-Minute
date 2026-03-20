#!/usr/bin/env python3
"""
fix_text_spacing.py — Fix spacing errors in ACIM database segments.

Fixes ligature characters, capital+space patterns, and other spacing issues
introduced during PDF extraction.

Usage:
    python fix_text_spacing.py --analyze          # Report error statistics
    python fix_text_spacing.py --preview          # Show before/after without changing
    python fix_text_spacing.py --fix              # Apply corrections (auto-backup)
    python fix_text_spacing.py --rollback <file>  # Restore from backup
"""

import argparse
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "acim.db"
BACKUP_DIR = DATA_DIR / "backups"


# --- Ligature Replacements ---
LIGATURES = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

# --- Capital+Space Patterns ---
# Common words that appear with errant spaces after capitals
CAPITAL_SPACE_FIXES = {
    "T ext": "Text",
    "T erms": "Terms",
    "T eacher": "Teacher",
    "T eaching": "Teaching",
    "T he": "The",
    "T o": "To",
    "T ime": "Time",
    "T ruth": "Truth",
    "T hink": "Think",
    "T hought": "Thought",
    "T houghts": "Thoughts",
    "T his": "This",
    "T hat": "That",
    "T here": "There",
    "T hey": "They",
    "T hen": "Then",
    "T hose": "Those",
    "T hus": "Thus",
    "Y ou": "You",
    "Y our": "Your",
    "Y et": "Yet",
    "Y es": "Yes",
    "W orld": "World",
    "W ords": "Words",
    "W ith": "With",
    "W hat": "What",
    "W hen": "When",
    "W here": "Where",
    "W hich": "Which",
    "W ho": "Who",
    "W hy": "Why",
    "W ill": "Will",
    "W ay": "Way",
    "W e": "We",
    "H oly": "Holy",
    "H is": "His",
    "H im": "Him",
    "H ere": "Here",
    "H ow": "How",
    "H eaven": "Heaven",
    "S pirit": "Spirit",
    "S on": "Son",
    "S oul": "Soul",
    "S elf": "Self",
    "F ather": "Father",
    "G od": "God",
    "L ove": "Love",
    "L ight": "Light",
    "M ind": "Mind",
    "C hrist": "Christ",
    "A tonement": "Atonement",
    "A nd": "And",
    "B ut": "But",
    "I f": "If",
    "I n": "In",
    "I t": "It",
    "I s": "Is",
    "O f": "Of",
    "O n": "On",
    "O r": "Or",
    "O ne": "One",
    "A ll": "All",
    "A re": "Are",
    "A s": "As",
    "A t": "At",
    "B e": "Be",
    "B y": "By",
    "N ot": "Not",
    "N o": "No",
    "S o": "So",
}

# --- Known Spurious Spaces ---
SPURIOUS_SPACE_FIXES = {
    "cour se": "course",
    "for give": "forgive",
    "for giveness": "forgiveness",
    "per ception": "perception",
    "mir acle": "miracle",
    "mir acles": "miracles",
}

# --- Artifacts to Remove ---
ARTIFACT_PATTERNS = [
    (r"PREFACE\s+[ivxIVX]+", ""),  # PREFACE iii, PREFACE iv, PREFACE v, etc.
    (r"P\s+R\s+E\s+F\s+A\s+C\s+E", "PREFACE"),  # P R E F A C E
    (r"❉", ""),  # Decorative symbol
    (r"\s*\.\s*\.\s*\.\s*", " "),  # Multiple spaced periods
]

# --- Missing Spaces (compound words that got stuck together) ---
MISSING_SPACE_FIXES = {
    "infinitelyabundant": "infinitely abundant",
    "eternallyvital": "eternally vital",
}


def connect_db() -> sqlite3.Connection:
    """Connect to the database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def create_backup() -> Path:
    """Create a timestamped backup of the database."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"acim_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def rollback(backup_file: str) -> bool:
    """Restore database from a backup file."""
    backup_path = Path(backup_file)
    if not backup_path.exists():
        # Try in backup directory
        backup_path = BACKUP_DIR / backup_file

    if not backup_path.exists():
        print(f"Error: Backup file not found: {backup_file}")
        return False

    shutil.copy2(backup_path, DB_PATH)
    print(f"Restored database from: {backup_path}")
    return True


def fix_text(text: str) -> tuple[str, dict]:
    """
    Apply all text fixes and return (fixed_text, changes_made).

    changes_made is a dict with counts of each type of fix applied.
    """
    changes = {
        "ligatures": 0,
        "capital_space": 0,
        "spurious_space": 0,
        "missing_space": 0,
        "artifacts": 0,
        "missing_space_after_punct": 0,
        "whitespace": 0,
    }

    original = text

    # 1. Replace ligatures
    for lig, replacement in LIGATURES.items():
        if lig in text:
            count = text.count(lig)
            changes["ligatures"] += count
            text = text.replace(lig, replacement)

    # 2. Fix capital+space patterns
    for pattern, replacement in CAPITAL_SPACE_FIXES.items():
        if pattern in text:
            count = text.count(pattern)
            changes["capital_space"] += count
            text = text.replace(pattern, replacement)

    # 3. Fix known spurious spaces
    for pattern, replacement in SPURIOUS_SPACE_FIXES.items():
        if pattern in text:
            count = text.count(pattern)
            changes["spurious_space"] += count
            text = text.replace(pattern, replacement)

    # 3b. Fix known missing spaces (compound words stuck together)
    for pattern, replacement in MISSING_SPACE_FIXES.items():
        if pattern in text:
            count = text.count(pattern)
            changes["missing_space"] += count
            text = text.replace(pattern, replacement)

    # 4. Remove/fix artifacts
    for pattern, replacement in ARTIFACT_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            changes["artifacts"] += len(matches)
            text = re.sub(pattern, replacement, text)

    # 5. Fix missing space after punctuation (when followed by uppercase)
    # e.g., ".This" -> ". This"
    punct_pattern = r'([.!?])([A-Z])'
    punct_matches = re.findall(punct_pattern, text)
    if punct_matches:
        changes["missing_space_after_punct"] += len(punct_matches)
        text = re.sub(punct_pattern, r'\1 \2', text)

    # 5b. Fix missing space after comma before lowercase letter
    # e.g., ",if" -> ", if"
    comma_pattern = r',([a-z])'
    comma_matches = re.findall(comma_pattern, text)
    if comma_matches:
        changes["missing_space_after_punct"] += len(comma_matches)
        text = re.sub(comma_pattern, r', \1', text)

    # 6. Normalize whitespace (multiple spaces to single)
    if "  " in text:
        changes["whitespace"] += 1
        text = re.sub(r' {2,}', ' ', text)

    # 7. Trim leading/trailing whitespace
    text = text.strip()

    return text, changes


def analyze(conn: sqlite3.Connection, verbose: bool = False) -> dict:
    """Analyze all segments for errors and return statistics."""
    cursor = conn.execute("SELECT id, text FROM segments")

    stats = {
        "total_segments": 0,
        "segments_with_errors": 0,
        "ligatures": {"count": 0, "segments": 0, "examples": []},
        "capital_space": {"count": 0, "segments": 0, "examples": []},
        "spurious_space": {"count": 0, "segments": 0, "examples": []},
        "missing_space": {"count": 0, "segments": 0, "examples": []},
        "artifacts": {"count": 0, "segments": 0, "examples": []},
        "missing_space_after_punct": {"count": 0, "segments": 0, "examples": []},
        "whitespace": {"count": 0, "segments": 0, "examples": []},
    }

    for row in cursor:
        stats["total_segments"] += 1
        seg_id = row["id"]
        text = row["text"]

        _, changes = fix_text(text)

        has_error = False
        for error_type, count in changes.items():
            if count > 0:
                has_error = True
                stats[error_type]["count"] += count
                stats[error_type]["segments"] += 1

                # Capture examples
                if len(stats[error_type]["examples"]) < 3:
                    stats[error_type]["examples"].append({
                        "id": seg_id,
                        "snippet": text[:100] + "..." if len(text) > 100 else text
                    })

        if has_error:
            stats["segments_with_errors"] += 1

    return stats


def print_analysis(stats: dict):
    """Print analysis results in a formatted way."""
    print("\n" + "=" * 60)
    print("ACIM DATABASE TEXT ANALYSIS")
    print("=" * 60)

    print(f"\nTotal segments: {stats['total_segments']}")
    print(f"Segments with errors: {stats['segments_with_errors']} "
          f"({100*stats['segments_with_errors']/stats['total_segments']:.1f}%)")

    print("\n--- Error Breakdown ---\n")

    error_types = [
        ("ligatures", "Ligature characters (ﬁ, ﬂ, etc.)"),
        ("capital_space", "Capital+space patterns (T ext, Y our, etc.)"),
        ("spurious_space", "Spurious spaces (cour se, etc.)"),
        ("missing_space", "Missing spaces (compound words)"),
        ("artifacts", "Formatting artifacts (PREFACE iii, etc.)"),
        ("missing_space_after_punct", "Missing space after punctuation"),
        ("whitespace", "Multiple/excess whitespace"),
    ]

    for key, description in error_types:
        data = stats[key]
        if data["count"] > 0:
            print(f"{description}:")
            print(f"  Occurrences: {data['count']}")
            print(f"  Affected segments: {data['segments']}")
            if data["examples"]:
                print(f"  Example (ID {data['examples'][0]['id']}): {data['examples'][0]['snippet']}")
            print()


def preview(conn: sqlite3.Connection, limit: int = 10):
    """Preview fixes without applying them."""
    cursor = conn.execute("SELECT id, text FROM segments")

    shown = 0
    for row in cursor:
        if shown >= limit:
            break

        seg_id = row["id"]
        original = row["text"]
        fixed, changes = fix_text(original)

        total_changes = sum(changes.values())
        if total_changes > 0:
            shown += 1
            print(f"\n{'='*60}")
            print(f"Segment ID: {seg_id}")
            print(f"Changes: {changes}")
            print(f"\n--- BEFORE ---")
            print(original[:300] + "..." if len(original) > 300 else original)
            print(f"\n--- AFTER ---")
            print(fixed[:300] + "..." if len(fixed) > 300 else fixed)

    print(f"\n{'='*60}")
    print(f"Previewed {shown} segments with changes (limit: {limit})")


def apply_fixes(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Apply fixes to all segments in the database."""
    cursor = conn.execute("SELECT id, text FROM segments")

    total_fixes = {
        "segments_updated": 0,
        "ligatures": 0,
        "capital_space": 0,
        "spurious_space": 0,
        "missing_space": 0,
        "artifacts": 0,
        "missing_space_after_punct": 0,
        "whitespace": 0,
    }

    updates = []

    for row in cursor:
        seg_id = row["id"]
        original = row["text"]
        fixed, changes = fix_text(original)

        total_changes = sum(changes.values())
        if total_changes > 0:
            updates.append((fixed, seg_id))
            total_fixes["segments_updated"] += 1
            for key, count in changes.items():
                total_fixes[key] += count

    if not dry_run and updates:
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE segments SET text = ? WHERE id = ?",
            updates
        )
        conn.commit()

    return total_fixes


def main():
    parser = argparse.ArgumentParser(
        description="Fix spacing errors in ACIM database segments"
    )
    parser.add_argument(
        "--analyze", action="store_true",
        help="Analyze and report error statistics"
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Preview fixes without applying them"
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Apply fixes (creates automatic backup)"
    )
    parser.add_argument(
        "--rollback", type=str, metavar="BACKUP_FILE",
        help="Restore database from backup file"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Limit number of previews (default: 10)"
    )

    args = parser.parse_args()

    # Handle rollback separately
    if args.rollback:
        rollback(args.rollback)
        return

    # Need at least one action
    if not (args.analyze or args.preview or args.fix):
        parser.print_help()
        return

    conn = connect_db()

    try:
        if args.analyze:
            stats = analyze(conn, verbose=args.verbose)
            print_analysis(stats)

        if args.preview:
            preview(conn, limit=args.limit)

        if args.fix:
            # Create backup first
            backup_path = create_backup()
            print(f"Created backup: {backup_path}")

            # Apply fixes
            results = apply_fixes(conn)

            print("\n" + "=" * 60)
            print("FIX RESULTS")
            print("=" * 60)
            print(f"Segments updated: {results['segments_updated']}")
            print(f"Ligatures fixed: {results['ligatures']}")
            print(f"Capital+space fixed: {results['capital_space']}")
            print(f"Spurious spaces fixed: {results['spurious_space']}")
            print(f"Missing spaces fixed: {results['missing_space']}")
            print(f"Artifacts removed: {results['artifacts']}")
            print(f"Punctuation spacing fixed: {results['missing_space_after_punct']}")
            print(f"Whitespace normalized: {results['whitespace']}")
            print(f"\nTo rollback: python fix_text_spacing.py --rollback {backup_path.name}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
