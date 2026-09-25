"""Deduplication — and the most consequential rule in the build (EC-CLEAN-1).

Forty people independently writing "I can never find old screenshots" IS the
finding. A near-duplicate pass that compares across authors reads that
consensus as duplication and deletes the strongest evidence in the corpus —
and the charts look normal afterwards. So:

    EXACT   the same words, ignoring case and punctuation. The earliest is
            kept, the rest are marked `exact_duplicate` — but only when the
            copies share an author, or the text is long enough (≥ 25 words)
            that identical wording means a quote or cross-post (EC-CLEAN-2).
            Two DIFFERENT people writing the same short line ("search can't
            find old photos") is consensus, and is kept. Myntra's rule removed
            those too; this is the EC-CLEAN-1 hole it left.
    NEAR    ONLY within (source, author_key): the same person posting the
            same thing again. Word-set Jaccard > 0.85, the definition
            `evals/fixtures/_build_fixtures.py` pins. Marked
            `near_duplicate_same_author`. NEVER across authors — not with a
            higher threshold, not "just to be safe".

Cross-author similarity is still MEASURED and reported as consensus, never
used to remove anything. P1-PROBE-1 pins both directions on
`dedupe_consensus.jsonl`: all 40 distinct authors kept, 4 of 5 same-author
repeats removed.

Exclusions MARK, they do not delete (A.1).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import defaultdict
from itertools import combinations

NEAR_DUPE = 0.85
_TOKEN = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def exact_key(text: str) -> str:
    return hashlib.sha1(" ".join(_TOKEN.findall(text.lower())).encode()).hexdigest()


def _order(r: dict) -> tuple:
    return (r.get("created_at") or "9999", r["record_id"])


EXACT_CROSS_AUTHOR_MIN_WORDS = 25


def find_exact(rows: list[dict]) -> list[tuple[str, str]]:
    """(loser, winner) pairs. Keeps the earliest. Across authors only for long
    text — see the module docstring."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[exact_key(r["text"])].append(r)
    out = []
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=_order)
        long_text = len(_TOKEN.findall(g[0]["text"].lower())) >= EXACT_CROSS_AUTHOR_MIN_WORDS
        kept: list[dict] = []
        for r in g:
            winner = next((k for k in kept if long_text or (
                r.get("author_key") and k.get("author_key") == r["author_key"])), None)
            if winner is None:
                kept.append(r)
            else:
                out.append((r["record_id"], winner["record_id"]))
    return out


def find_near_same_author(rows: list[dict]) -> list[tuple[str, str]]:
    """(loser, winner) pairs WITHIN (source, author_key) only. The scoping is
    the correctness property, not an optimisation (EC-CLEAN-1). Records with
    no author are never near-deduped: nothing says they are the same person."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("author_key"):
            groups[(r["source"], r["author_key"])].append(r)
    out = []
    for g in groups.values():
        g.sort(key=_order)
        kept: list[tuple[dict, set[str]]] = []
        for r in g:
            t = tokens(r["text"])
            winner = next((k for k, kt in kept if jaccard(t, kt) > NEAR_DUPE), None)
            if winner is None:
                kept.append((r, t))
            else:
                out.append((r["record_id"], winner["record_id"]))
    return out


def cross_author_echoes(rows: list[dict], threshold: float = NEAR_DUPE) -> int:
    """Pairs of DIFFERENT authors above the near-dupe threshold — consensus,
    reported and never removed. Pairwise within a source, which is fine at
    P1 scale; it only feeds a reported count."""
    by_source: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for r in rows:
        if r.get("author_key") and len(r["text"]) <= 2000:
            by_source[r["source"]].append((r["author_key"], tokens(r["text"])))
    n = 0
    for items in by_source.values():
        if len(items) > 3000:
            continue
        n += sum(1 for (a, ta), (b, tb) in combinations(items, 2)
                 if a != b and jaccard(ta, tb) > threshold)
    return n


def run(con: sqlite3.Connection, run_id: str) -> dict[str, int]:
    """Only records not already excluded are compared."""
    rows = [dict(r) for r in con.execute(
        "SELECT record_id, source, author_key, created_at, text_clean AS text FROM records"
        " WHERE record_id NOT IN (SELECT record_id FROM exclusions WHERE story_id IS NULL)")]
    stats = {"exact": 0, "near_same_author": 0}
    exact = find_exact(rows)
    losers = {loser for loser, _ in exact}
    for loser, winner in exact:
        con.execute("INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail,"
                    " run_id) SELECT record_id, source, 'clean', 'exact_duplicate', ?, ?"
                    " FROM records WHERE record_id=?", (f"duplicate of {winner}", run_id, loser))
        stats["exact"] += 1
    remaining = [r for r in rows if r["record_id"] not in losers]
    for loser, winner in find_near_same_author(remaining):
        con.execute("INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail,"
                    " run_id) SELECT record_id, source, 'clean', 'near_duplicate_same_author',"
                    " ?, ? FROM records WHERE record_id=?",
                    (f"same-author near-duplicate of {winner}", run_id, loser))
        stats["near_same_author"] += 1
    stats["cross_author_echo_pairs"] = cross_author_echoes(remaining)
    con.commit()
    return stats
