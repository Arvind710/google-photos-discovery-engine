"""Clean stage: language tag → length floor → dedupe. Every removal is a MARK
in `exclusions` (A.1); the record stays in `records`.

PII is not here: it is scrubbed in `collect.base.make_record`, before the
first write (EC-OPS-8).

    python -m pipeline.clean.run_clean
"""

from __future__ import annotations

import re

from pipeline.clean import dedupe, language
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

MIN_CHARS = 20        # EC-COL-5: emoji-only or ≤ 20 characters carries no signal
_ALNUM = re.compile(r"[A-Za-z0-9ऀ-ॿ]")


def too_short(text: str) -> bool:
    return len(_ALNUM.findall(text)) < MIN_CHARS


def main() -> int:
    con = dbm.init()
    with rmod.Run(con, "clean", model=None, estimate_usd=0) as run:
        n = con.execute("SELECT count(*) FROM records").fetchone()[0]
        langs = language.run(con)
        short = 0
        for r in con.execute("SELECT record_id, source, text_clean FROM records").fetchall():
            if too_short(r["text_clean"]):
                con.execute("INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason,"
                            " detail, run_id) VALUES (?,?,?,?,?,?)",
                            (r["record_id"], r["source"], "clean", "too_short",
                             f"< {MIN_CHARS} letters or digits", run.run_id))
                short += 1
        con.commit()
        d = dedupe.run(con, run.run_id)
        excluded = con.execute("SELECT count(DISTINCT record_id) FROM exclusions"
                               " WHERE story_id IS NULL").fetchone()[0]
        run.n_input, run.n_output = n, n - excluded
    print(f"records {n} · language {langs} · too short {short} · exact dupes {d['exact']}"
          f" · same-author near dupes {d['near_same_author']}"
          f" · cross-author echo pairs (kept, reported) {d['cross_author_echo_pairs']}"
          f" · kept {n - excluded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
