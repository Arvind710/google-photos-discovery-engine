"""Read-only DB access for the Streamlit app.

The app COMPUTES NOTHING. Every figure it renders is a SELECT from a
materialised `analysis_*` table written by the offline pipeline. That is
what guarantees the charts and the chatbot cannot disagree with each other,
and it is what keeps the deck's numbers matching the link ([CTX] §15.6).

Streamlit re-executes the whole script on every widget interaction, so
uncached reads would re-hit disk constantly (architecture.md §2).

WHY THE CACHE IS KEYED ON A FILE FINGERPRINT
--------------------------------------------
This module previously cached the connection with a bare `@st.cache_resource`
and returned `None` when the file was missing. Two failures followed from
that, and both were live:

1. `st.cache_resource` caches whatever it returns, INCLUDING `None`. Streamlit
   Cloud hot-reloads code without restarting the process, so a single moment
   with no readable database — mid-deploy, while a 20 MB file is being
   replaced — cached a `None` that survived every subsequent rerun. The app
   then reported an empty corpus indefinitely, and only a container reboot
   cleared it.

2. The failure was silent AND mislabelled. `corpus_is_populated()` returning
   False was rendered as "the corpus has not been collected yet", which is an
   assertion about the pipeline made on evidence that only concerned the file.
   An evaluator would have read it as a project that had not run.

Both are fixed by keying the cache on (path, size, mtime): when the file
changes the key changes, so a new connection is opened rather than a stale or
null one reused. `db_status()` reports which of the genuinely distinct
conditions holds, so callers can say something true.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "corpus.db"


def _fingerprint() -> tuple[str, int, int] | None:
    """(path, size, mtime_ns), or None if there is no readable file.

    Computed on every call — it is two stat() syscalls, far cheaper than the
    class of bug it prevents, and it is what makes the cache key follow the
    file rather than the process lifetime.
    """
    try:
        s = DB_PATH.stat()
    except OSError:
        return None
    if s.st_size == 0:
        return None
    return (str(DB_PATH), s.st_size, s.st_mtime_ns)


@st.cache_resource
def _connect(fp: tuple[str, int, int]) -> sqlite3.Connection:
    """Keyed on the fingerprint, so a changed file yields a new connection.
    Never called when the file is absent, so it cannot cache a null result."""
    path = fp[0]
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def connection() -> sqlite3.Connection | None:
    fp = _fingerprint()
    return None if fp is None else _connect(fp)


@st.cache_data(ttl=None)
def _query(fp: tuple[str, int, int] | None, sql: str, params: tuple) -> pd.DataFrame:
    """`fp` is part of the cache key on purpose: results must not outlive the
    file they were read from."""
    con = connection()
    if con is None:
        return pd.DataFrame()
    return pd.read_sql_query(sql, con, params=params)


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _query(_fingerprint(), sql, params)


def db_status() -> tuple[str, str]:
    """(status, human-readable detail). Distinguishes conditions that a single
    boolean conflated — 'no file' and 'no records' have different causes and
    different fixes, and saying the wrong one misleads whoever reads it.
    """
    fp = _fingerprint()
    if fp is None:
        # relative_to() raises when DB_PATH sits outside ROOT, which happens
        # under test and would turn a diagnostic into a crash.
        try:
            shown = DB_PATH.relative_to(ROOT)
        except ValueError:
            shown = DB_PATH
        return ("missing", (
            f"No readable database at `{shown}`. On a "
            "deployment this means the file is absent from the repository or "
            "was mid-replacement when the app last started — not that the "
            "pipeline has not run."))
    try:
        n = int(query("SELECT count(*) AS n FROM records").iloc[0]["n"])
    except Exception as exc:                                  # noqa: BLE001
        return ("unreadable", f"Database present ({fp[1]:,} bytes) but unreadable: {exc}")
    if n == 0:
        return ("empty", "Database present but holds no records. Run the "
                         "collectors in `pipeline/collect/`.")
    return ("ok", f"{n:,} records")


def corpus_is_populated() -> bool:
    return db_status()[0] == "ok"


def published_run_id() -> str | None:
    """EC-OPS-11 / X-3: the app reads a PINNED run, never 'latest'. A pipeline
    re-run mid-demo must not change what an evaluator is looking at."""
    row = published()
    return None if row is None else row["run_id"]


def published() -> dict | None:
    """The pinned run and its corpus stamp, or None before P6 publishes one."""
    try:
        df = query("SELECT run_id, corpus_version, published_at FROM published"
                   " WHERE singleton = 1")
    except Exception:                                         # noqa: BLE001
        return None
    return None if df.empty else df.iloc[0].to_dict()
