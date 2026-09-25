"""Shared helpers for every collector — ported from the Myntra build, with two
changes this project needs.

Collectors are THIN: fetch, map to `records`, write. Language tagging, length
filtering and dedupe are the clean stage (`pipeline/clean/`), so what was
collected and what was kept stay separable.

1. A THREAD IS ONE RECORD (EC-COL-4, the segmentation fixtures). A Reddit post
   with its comments, a GP Help question with its replies, a Stack Exchange
   question with its answers: one `record_id`, the posts joined in order, and
   `posts_json` (A.11) holding each post's author and offsets into
   `text_clean`. Segmentation then looks a story's author up from its span
   (A.2, EC-COL-12) instead of asking a model.
2. PII IS SCRUBBED HERE, before the first write (EC-OPS-8). Scrubbing later
   would shift text and invalidate the post offsets, and would mean an
   unscrubbed copy existed in a file that is committed to a public repo.

Every record carries `collect_method` (A.10, Docs/decisions.md D-1).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pipeline.clean import scrub

# D-1: how each source is obtained. GP Help may fall back to Apify (EC-COL-11).
SOURCE_METHOD = {
    "reddit": "apify", "x": "apify", "quora": "apify",
    "gp_help": "headless_render",
    "play": "public_scraper_lib",
    "appstore": "public_feed",
    "youtube": "official_api", "stackexchange": "official_api", "hackernews": "official_api",
}
SOURCES = tuple(SOURCE_METHOD)

DELETED_MARKERS = {"[deleted]", "[removed]", "[deleted by user]", ""}
POST_SEPARATOR = "\n\n"

_salt: str = ""


def set_salt(salt: str) -> None:
    """Collectors call this once from the env. No salt → no writes (EC-OPS-7)."""
    global _salt
    _salt = salt or ""


def author_key(source: str, handle: str | None) -> str | None:
    """Salted, source-scoped pseudonym. Same person on the same platform → same
    key across runs, so within-author dedupe works; the handle never enters the
    database, and without the env-only salt the key cannot be reversed."""
    if not handle or handle.strip().lower() in DELETED_MARKERS:
        return None
    if not _salt:
        raise RuntimeError("AUTHOR_SALT is not set — refusing to write unsalted author keys "
                           "(EC-OPS-7)")
    return hashlib.sha256(f"{_salt}::{source}::{handle.strip().lower()}".encode()).hexdigest()[:32]


def record_id(source: str, native_id: str) -> str:
    """sha1(source ‖ native_id): re-ingest is idempotent by construction (EC-CLEAN-7)."""
    return hashlib.sha1(f"{source}‖{native_id}".encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def to_iso(value: Any) -> str | None:
    """NULL is valid (EC-COL-9): time analysis runs only over records that have it."""
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        v = float(value) / (1000 if value > 1e11 else 1)       # ms or s epoch
        try:
            return datetime.fromtimestamp(v, tz=UTC).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")   # X's created_at
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds")


_HSPACE = re.compile(r"[ \t\f\v ]+")
_MANY_NL = re.compile(r"\n{3,}")


def normalise(text: str) -> str:
    """Whitespace only. Case, punctuation, CAPS and '!!!' are kept — they carry
    intensity (EC-CLEAN-6). Line breaks are kept: they are structure."""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(_HSPACE.sub(" ", line).strip() for line in t.split("\n"))
    return _MANY_NL.sub("\n\n", t).strip()


@dataclass
class Post:
    author: str | None
    text: str
    created_at: Any = None


def is_deleted(text: str | None) -> bool:
    return text is None or str(text).strip().lower() in DELETED_MARKERS


def make_record(*, source: str, native_id: str, source_url: str, posts: list[Post],
                ingest_run_id: str, collect_query: str | None, created_at: Any = None,
                rating: int | None = None, engagement: int | None = None,
                thread_context: str | None = None, platform_hint: str | None = None,
                region_hint: str | None = None, method: str | None = None,
                ) -> tuple[dict[str, Any] | None, int]:
    """Map one item (a review, or a whole thread) onto `records`.

    Returns (record or None, n_deleted_posts). Deleted/removed posts are left
    out of the thread and COUNTED; a record whose every post is deleted is not
    written (a row needs text) and is counted by the caller (EC-COL-3).
    """
    if not source_url:
        raise ValueError(f"{source}/{native_id}: no source_url — no record without a permalink")
    if source not in SOURCE_METHOD:
        raise ValueError(f"unknown source {source!r}")

    kept = [p for p in posts if not is_deleted(p.text)]
    n_deleted = len(posts) - len(kept)
    raw_parts, clean_parts, bounds = [], [], []
    pos = 0
    for p in kept:
        scrubbed, _ = scrub.scrub(str(p.text))
        clean = normalise(scrubbed)
        if not clean:
            n_deleted += 1
            continue
        if clean_parts:
            pos += len(POST_SEPARATOR)
        bounds.append({"author_key": author_key(source, p.author), "start": pos,
                       "end": pos + len(clean)})
        pos += len(clean)
        raw_parts.append(scrubbed)
        clean_parts.append(clean)
    if not clean_parts:
        return None, n_deleted

    text_clean = POST_SEPARATOR.join(clean_parts)
    assert all(text_clean[b["start"]:b["end"]] == c for b, c in zip(bounds, clean_parts, strict=True))
    ctx = scrub.scrub(thread_context)[0] if thread_context else None
    return {
        "record_id": record_id(source, native_id),
        "source": source,
        "collect_method": method or SOURCE_METHOD[source],
        "source_url": source_url,
        "native_id": str(native_id),
        "author_key": bounds[0]["author_key"],
        "created_at": to_iso(created_at if created_at is not None else kept[0].created_at),
        "text_raw": POST_SEPARATOR.join(raw_parts),     # scrubbed, otherwise verbatim
        "text_clean": text_clean,                       # CANONICAL (EC-CLEAN-4)
        "text_en": None,
        "lang": None,                                   # set by clean/language.py
        "rating": rating,
        "engagement": engagement,
        "thread_context": ctx,
        "platform_hint": platform_hint,
        "region_hint": region_hint,
        "collect_query": collect_query,
        "collected_at": now_iso(),
        "ingest_run_id": ingest_run_id,
        "posts_json": json.dumps(bounds) if len(bounds) > 1 else None,
    }, n_deleted


COLUMNS = ("record_id", "source", "collect_method", "source_url", "native_id", "author_key",
           "created_at", "text_raw", "text_clean", "text_en", "lang", "rating", "engagement",
           "thread_context", "platform_hint", "region_hint", "collect_query", "collected_at",
           "ingest_run_id", "posts_json")


def write_records(con: sqlite3.Connection, rows: Iterable[dict]) -> tuple[int, int]:
    """Idempotent insert. Returns (new, already_present) — re-running a
    collector never duplicates, and never overwrites what was collected first."""
    rows = list(rows)
    if not rows:
        return 0, 0
    before = con.total_changes
    con.executemany(f"INSERT OR IGNORE INTO records ({','.join(COLUMNS)}) "
                    f"VALUES ({','.join('?' * len(COLUMNS))})",
                    [tuple(r[c] for c in COLUMNS) for r in rows])
    con.commit()
    new = con.total_changes - before
    return new, len(rows) - new


class Tally:
    """The per-run accounting identity (P1-INV-1):
        fetched == written_new + already_present + all_deleted + duplicate_in_batch
    Stored in the run's params, so the test can check every collect run."""

    def __init__(self) -> None:
        self.fetched = self.written_new = self.already_present = 0
        self.all_deleted = self.duplicate_in_batch = self.deleted_posts = 0
        self.by_query: dict[str, int] = {}
        self.failed_queries: list[str] = []
        self._seen: set[str] = set()

    def add(self, con: sqlite3.Connection, rec: dict | None, n_deleted: int,
            query: str | None) -> None:
        self.fetched += 1
        self.deleted_posts += n_deleted
        if rec is None:
            self.all_deleted += 1
            return
        if rec["record_id"] in self._seen:           # same thread surfaced by two queries
            self.duplicate_in_batch += 1
            return
        self._seen.add(rec["record_id"])
        new, old = write_records(con, [rec])
        self.written_new += new
        self.already_present += old
        if query is not None:
            self.by_query[query] = self.by_query.get(query, 0) + new

    def check(self) -> None:
        total = (self.written_new + self.already_present + self.all_deleted
                 + self.duplicate_in_batch)
        if total != self.fetched:
            raise AssertionError(f"accounting identity broken: {self.fetched} fetched, {total} "
                                 "accounted for (P1-INV-1)")

    def as_params(self) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if not k.startswith("_")}


def finish(con: sqlite3.Connection, run, tally: Tally, **extra: Any) -> None:
    """Merge the tally into the run's params and set n_output. Call inside the
    `with Run(...)` block, before it closes."""
    tally.check()
    row = con.execute("SELECT params_json FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
    params = json.loads(row[0] or "{}")
    params.update(tally=tally.as_params(), **extra)
    con.execute("UPDATE runs SET params_json=? WHERE run_id=?",
                (json.dumps(params, default=str), run.run_id))
    con.commit()
    run.n_input = tally.fetched
    run.n_output = tally.written_new
