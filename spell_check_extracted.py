#!/usr/bin/env python3
"""
spell_check_extracted.py — Check spelling in extracted text files.

Identifies actual spelling errors in the original PDF text (not extraction artifacts).

Usage:
    python spell_check_extracted.py                    # Check all extracted files
    python spell_check_extracted.py -o errors.txt     # Output to file
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

from spellchecker import SpellChecker

# --- Configuration ---
BASE_DIR = Path(__file__).parent
EXTRACTED_DIR = BASE_DIR / "extracted_text"

# --- ACIM-Specific Whitelist ---
ACIM_WHITELIST = {
    # Theological/Spiritual terms
    "atonement", "atonements", "christ", "christlike", "christly",
    "crucifixion", "crucify", "crucified", "ego", "egos", "egoic",
    "godlike", "godly", "godhead", "holiness", "redeemer", "redemption",
    "messiah", "messianic", "savior", "saviors", "sonship",

    # Hyphenated compounds (as single words when hyphen stripped)
    "rightmindedness", "wrongmindedness", "openmindedness", "onemindedness",
    "miraclemindedness", "miracleminded", "miracleworker", "miracleworkers",
    "selffullness", "selfimage", "selfimages", "selfconcept", "selfconcepts",
    "thoughtsystem", "thoughtsystems", "thoughtform", "thoughtforms",
    "cocreator", "cocreators", "cocreate", "cocreating", "cocreation",

    # Psychological/philosophical terms
    "superconscious", "perceiver", "perceivers", "unseparated",
    "intrapersonal", "causelessness", "overlearned", "selfdeception",
    "unforgiveness", "brotherless", "uncondemned",

    # ACIM-specific terms
    "guiltlessness", "guiltless", "sinlessness", "sinless",
    "changelessness", "changeless", "formlessness", "formless",
    "timelessness", "timeless", "spacelessness", "spaceless",
    "defenselessness", "defenseless", "invulnerability", "invulnerable",
    "unreality", "unreal", "undoing", "undo", "undone", "undoes",
    "unhealed", "unhealing", "unheal", "uncreated", "uncreate",
    "unlearning", "unlearn", "unlearned", "relearn", "relearning",
    "misperception", "misperceptions", "misperceive", "misperceived",
    "miscreation", "miscreations", "miscreate", "miscreated",
    "misthought", "misthink", "misuse", "misused",
    "overcame", "overlearn", "overlearning",
    "reestablish", "reestablished", "reestablishing",
    "reinterpret", "reinterpretation", "reinterpreted",
    "reawaken", "reawakening", "reawakened",

    # Common ACIM phrases/words
    "workbook", "workbooks", "textbook", "textbooks",
    "miracles", "miracle", "miraculous", "miraculously",
    "mindedness", "mindful", "mindfulness",
    "oneness", "wholeness", "allness", "sameness", "littleness",
    "grandiosity", "grandeur",

    # Proper nouns and names
    "helen", "schucman", "thetford", "bill", "jesus",

    # Archaic/formal words used in ACIM
    "thee", "thou", "thy", "thine", "thyself",
    "hast", "hath", "doth", "dost", "shalt", "wilt", "wouldst",
    "wherefore", "wherein", "whereof", "whereby", "herein", "thereof",
    "unto", "amongst", "whilst", "betwixt", "sayeth", "abideth",

    # British spellings
    "defences", "defence",

    # Other valid words that may flag
    "cannot", "whatsoever", "whosoever", "whomsoever", "wheresoever",
    "nonetheless", "notwithstanding", "inasmuch", "insofar",
    "beforehand", "afterward", "afterwards",
    "acknowledgement", "acknowledgment", "fulfillment", "fulfilment",
    "enrollment", "enrolment", "center", "centre",

    # Contractions fragments
    "ll", "ve", "re", "nt", "em",

    # Roman numerals
    "ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii",
    "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
    "xxi", "xxii", "xxiii", "xxiv", "xxv",

    # Single letters
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
}

# Patterns to ignore
IGNORE_PATTERNS = [
    r'^_+$',           # Blanks like _____
    r'^\d+$',          # Pure numbers
    r'^[ivxlcdm]+$',   # Roman numerals
]


def extract_words(text: str) -> list[str]:
    """Extract words from text."""
    text = re.sub(r"[^\w\s'-]", " ", text)
    words = text.lower().split()
    cleaned = []
    for word in words:
        word = word.strip("-'")
        if len(word) < 2 or word.isdigit():
            continue
        cleaned.append(word)
    return cleaned


def should_ignore(word: str) -> bool:
    """Check if word matches ignore patterns."""
    for pattern in IGNORE_PATTERNS:
        if re.match(pattern, word):
            return True
    return False


def check_file(file_path: Path, spell: SpellChecker) -> dict:
    """Check spelling in a file."""
    text = file_path.read_text(encoding='utf-8')
    words = extract_words(text)

    misspelled = defaultdict(lambda: {"count": 0, "context": ""})

    # Find unique words and their counts
    word_counts = defaultdict(int)
    for word in words:
        word_counts[word] += 1

    for word, count in word_counts.items():
        # Skip whitelist
        if word in ACIM_WHITELIST:
            continue

        # Skip ignore patterns
        if should_ignore(word):
            continue

        # Skip if it's a known word
        if word in spell:
            continue

        # It's misspelled
        misspelled[word]["count"] = count

        # Find context (first occurrence)
        if not misspelled[word]["context"]:
            # Find line containing word
            for line in text.split('\n'):
                if word in line.lower():
                    misspelled[word]["context"] = line.strip()[:80]
                    break

    return dict(misspelled)


def main():
    parser = argparse.ArgumentParser(
        description="Spell check extracted text files"
    )
    parser.add_argument(
        "-o", "--output", type=str,
        help="Output file for results"
    )
    args = parser.parse_args()

    print("Initializing spell checker...")
    spell = SpellChecker()

    # Find all text files
    txt_files = sorted(EXTRACTED_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {EXTRACTED_DIR}")
        return

    all_misspelled = defaultdict(lambda: {"count": 0, "files": [], "context": ""})

    for txt_file in txt_files:
        print(f"Checking: {txt_file.name}")
        misspelled = check_file(txt_file, spell)

        for word, data in misspelled.items():
            all_misspelled[word]["count"] += data["count"]
            all_misspelled[word]["files"].append(txt_file.name)
            if not all_misspelled[word]["context"]:
                all_misspelled[word]["context"] = data["context"]

    # Sort by count
    sorted_words = sorted(
        all_misspelled.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )

    # Output
    output_lines = []
    output_lines.append("=" * 70)
    output_lines.append("SPELLING ERRORS IN ORIGINAL PDFs")
    output_lines.append("=" * 70)
    output_lines.append(f"\nTotal unique misspellings: {len(sorted_words)}")
    output_lines.append(f"Total occurrences: {sum(d['count'] for _, d in sorted_words)}")
    output_lines.append("\n" + "-" * 70)
    output_lines.append("MISSPELLINGS (sorted by frequency)")
    output_lines.append("-" * 70 + "\n")

    for word, data in sorted_words:
        files_str = ", ".join(data["files"][:2])
        if len(data["files"]) > 2:
            files_str += f" +{len(data['files'])-2} more"
        output_lines.append(f"{word} ({data['count']}) — {files_str}")
        if data["context"]:
            output_lines.append(f"    Context: {data['context']}")

    result = "\n".join(output_lines)

    if args.output:
        Path(args.output).write_text(result, encoding='utf-8')
        print(f"\nResults saved to: {args.output}")
    else:
        print("\n" + result)

    print(f"\nTotal: {len(sorted_words)} unique misspellings")


if __name__ == "__main__":
    main()
