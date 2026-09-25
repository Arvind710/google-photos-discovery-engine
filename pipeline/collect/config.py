"""What every collector searches for. One place, so the collection bias is one
auditable list (EC-COL-12 / [CTX] §6.2).

Search terms come from `codebook/lexicon_v1.yaml` — the [CTX] §6.2 seed, which
P1-MET-3 expands. The term that surfaced a record is stored on it as
`collect_query`. Subreddits come from [CTX] §6.1; `architecture.md` §5.1 never
listed them, so this is where the choice is recorded.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def lexicon_terms() -> list[str]:
    lex = yaml.safe_load((ROOT / "codebook" / "lexicon_v1.yaml").read_text())
    return [t["term"] for group in lex["terms"].values() for t in group]


# [CTX] §6.1, plus the two tech-help subs it gestures at ("tech-help subs").
SUBREDDITS = ["googlephotos", "GooglePixel", "Android", "iphone", "india", "DataHoarder",
              "applephotos", "techsupport", "AndroidQuestions"]

# The lexicon's phrases are written for full-text search inside a community
# about photos. On platform-wide search (X, Quora, YouTube, Stack Exchange,
# HN) a bare phrase like "that photo of" returns everything, so those
# collectors anchor each term to Google Photos.
def anchored(term: str) -> str:
    t = term.lower()
    return term if ("google photos" in t or "ask photos" in t) else f"google photos {term}"


# Pilot = a stratified slice of the lexicon, so the ~600-record pilot spans
# the four groups rather than the first eight terms of one.
PILOT_TERMS = ["can't find photo", "search not working", "ask photos",
               "find photo without date", "photo from years ago", "screenshot I took",
               "had to scroll", "photo nahi mil rahi"]
