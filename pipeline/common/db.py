"""SQLite access for the pipeline. The app has its own read-only helper."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "corpus.db"
SCHEMA_PATH = ROOT / "pipeline" / "schema.sql"


def connect(path: Path | str = DB_PATH, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Apply schema.sql. Idempotent -- safe to call on an existing DB."""
    con = connect(path)
    con.executescript(SCHEMA_PATH.read_text())
    con.commit()
    return con


if __name__ == "__main__":
    con = init()
    n = len(list(con.execute("SELECT name FROM sqlite_master WHERE type='table'")))
    print(f"{DB_PATH.relative_to(ROOT)} ready -- {n} tables")
