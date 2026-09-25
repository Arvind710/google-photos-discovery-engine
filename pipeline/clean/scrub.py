"""PII scrubbing — typed placeholders, never deletion (EC-CLEAN-3, EC-OPS-8).

Called by `collect.base.make_record` on every post BEFORE the first write, so
no unscrubbed text ever reaches `corpus.db`, which is committed to a public
repo. Typed placeholders keep the sentence parseable: "I emailed [EMAIL] and
they never replied" still reads as a story; a deletion would not.

P1-INV-4 checks the committed corpus with `leaks()`: zero email, phone or
handle patterns may survive.
"""

from __future__ import annotations

import re

_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# @handle and u/handle — the user-name forms across Reddit, X, YouTube, Quora.
_HANDLE = re.compile(r"(?<![\w@/])(?:/?u/[A-Za-z0-9_-]{3,}|@[A-Za-z0-9_.]{2,})")
# A phone is 10–15 digits with optional +, spaces, dots, dashes, brackets. The
# candidate is checked by digit count, so "2019 or 2020" never matches.
_PHONE_CAND = re.compile(r"(?<![\w+])\+?\d[\d\s().-]{7,20}\d(?!\w)")
_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _phone(m: re.Match) -> str:
    digits = sum(c.isdigit() for c in m.group(0))
    return "[PHONE]" if 10 <= digits <= 15 else m.group(0)


def scrub(text: str) -> tuple[str, list[str]]:
    """(scrubbed text, kinds found). Order matters: URLs and emails first, so
    their parts are not re-read as handles or numbers."""
    found: list[str] = []
    out = text
    for pat, repl, kind in ((_URL, "[URL]", "URL"), (_EMAIL, "[EMAIL]", "EMAIL"),
                            (_HANDLE, "[HANDLE]", "HANDLE"), (_PAN, "[ID_NUMBER]", "PAN"),
                            (_AADHAAR, "[ID_NUMBER]", "AADHAAR"), (_CARD, "[LONG_NUMBER]", "CARD")):
        out, n = pat.subn(repl, out)
        if n:
            found.append(kind)
    out2 = _PHONE_CAND.sub(_phone, out)
    if out2 != out:
        found.append("PHONE")
    return out2, found


def leaks(text: str) -> list[str]:
    """What P1-INV-4 asserts is absent from every stored text."""
    hits = []
    if _EMAIL.search(text):
        hits.append("email")
    if _HANDLE.search(text):
        hits.append("handle")
    if any(10 <= sum(c.isdigit() for c in m.group(0)) <= 15 for m in _PHONE_CAND.finditer(text)):
        hits.append("phone")
    return hits
