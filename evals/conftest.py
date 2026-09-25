import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from pipeline.common import codebook as cb_mod  # noqa: E402
from pipeline.common import db as db_mod  # noqa: E402


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def codebook():
    return cb_mod.load()


@pytest.fixture()
def blank_db(tmp_path) -> sqlite3.Connection:
    """A fresh DB with the schema applied. No data."""
    return db_mod.init(tmp_path / "test.db")


@pytest.fixture(scope="session")
def corpus():
    """The real corpus. Skips cleanly until P1 has populated it — and the
    report counts a skip as NOT passed."""
    path = ROOT / "data" / "corpus.db"
    if not path.exists():
        pytest.skip("corpus.db does not exist yet")
    con = db_mod.connect(path, read_only=True)
    if con.execute("SELECT count(*) FROM records").fetchone()[0] == 0:
        pytest.skip("corpus.db is empty — P1 has not run")
    return con
