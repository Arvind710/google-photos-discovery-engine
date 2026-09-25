"""Language tagging — METADATA ONLY, never a reason to drop (EC-CLEAN-5).

Ported from the Myntra build. Short Hinglish is exactly where automatic
language ID fails, and it is exactly the text [CTX] §15.3's India hypotheses
need, so `unknown` is a valid value and nothing is excluded on language.

`text_clean` stays the original, canonical text (EC-CLEAN-4). `text_en` is a
translation AID for the model, filled later only where it helps; a span is
never taken from it.
"""

from __future__ import annotations

import re
import sqlite3

# Hindi function words written in Latin script: common in speech, rare in English.
HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "kya", "aur", "bhi", "yaar", "acha", "accha", "bohot",
    "bahut", "kar", "karo", "karna", "kiya", "mera", "meri", "tera", "apna", "mujhe", "hoga",
    "hota", "gaya", "raha", "rahi", "rahe", "bas", "abhi", "phir", "pehle", "wala", "wali",
    "matlab", "kaise", "kyun", "kyu", "thoda", "zyada", "sahi", "galat", "kabhi", "lekin",
    "magar", "mil", "mili", "dhoondh", "dhoondhe", "purani", "yaad", "ki", "ka", "ke", "me",
    "mein", "toh", "koi", "kuch", "sab", "pata",
}
_STRONG = HINGLISH_MARKERS - {"me", "ki", "ka", "ke", "bas", "mil", "kar"}   # also English-ish

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
OTHER_SCRIPT = re.compile(r"[ঀ-෿฀-๿぀-ヿ一-鿿؀-ۿ"
                          r"Ѐ-ӿ가-힯]")
_WORD = re.compile(r"[a-z]+")


def detect(text: str) -> str:
    """en | hi | hi-Latn | mixed | other | unknown"""
    if not text or not text.strip():
        return "unknown"
    has_deva = bool(DEVANAGARI.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_deva:
        return "mixed" if has_latin and len(_WORD.findall(text.lower())) > 3 else "hi"
    if OTHER_SCRIPT.search(text):
        return "other"
    words = _WORD.findall(text.lower())
    if not words:
        return "unknown"
    strong = sum(w in _STRONG for w in words)
    weak = sum(w in HINGLISH_MARKERS for w in words)
    if strong >= 2 or (strong >= 1 and weak >= 2) or (strong == 1 and len(words) <= 8):
        return "hi-Latn"
    return "en"


def run(con: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in list(con.execute("SELECT record_id, text_clean FROM records WHERE lang IS NULL")):
        lang = detect(r["text_clean"])
        con.execute("UPDATE records SET lang=? WHERE record_id=?", (lang, r["record_id"]))
        counts[lang] = counts.get(lang, 0) + 1
    con.commit()
    return counts
