"""Evidence-span verification — T-2 (100%, absolute) and T-3 (≥ 15 characters).

The deterministic check that carries the most weight in the system
(architecture.md §5.6): a quote the model offers as evidence is kept only if it
is found, exactly, in `records.text_clean` — the canonical text, never `text_en`
(EC-CLEAN-4, EC-CODE-4). What is stored is the SLICE of `text_clean` that
matched, so a stored span is verbatim by construction.

Matching tolerates only what cannot change a word — runs of whitespace, and
straight vs curly quotes — exactly as Pass 1 does (`segment.stories._pattern`).
The search is confined to the regions the coder was shown: the story's own span
and the same author's later posts in the thread. Another person's words in the
same thread never verify a code (EC-SEG-9).
"""

from __future__ import annotations

from pipeline.segment import stories as seg

MIN_SPAN = 15                                   # T-3 (EC-VAL-5)


def find(text: str, quote: str, regions: list[tuple[int, int]]) -> str | None:
    """The exact slice of `text` that `quote` matches inside one of `regions`,
    or None. Too short a match counts as not found (T-3)."""
    q = " ".join((quote or "").split()).strip(" .…\"'“”")
    if len(q) < MIN_SPAN:
        return None
    pat = seg._pattern(q)
    if pat is None:
        return None
    for a, b in regions:
        m = pat.search(text, a, b)
        if m and m.end() - m.start() >= MIN_SPAN:
            return text[m.start():m.end()]
    return None


def regions(text_clean: str, posts: list[dict], char_start: int, char_end: int,
            author: str | None) -> list[tuple[int, int]]:
    """The story's span, then the same author's later posts (what the coder saw)."""
    out = [(char_start, char_end)]
    if author and len(posts) > 1:
        k = next((i for i, p in enumerate(posts) if p["start"] <= char_start < p["end"]), None)
        if k is not None:
            out += [(p["start"], p["end"]) for p in posts[k + 1:] if p["author_key"] == author]
    return out
