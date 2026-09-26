"""The final lexicon with hit counts — a required reproducibility output
([CTX] §6.2). Fills `hits` in `codebook/lexicon_v1.yaml` and writes the
per-source breakdown to `data/artifacts/lexicon_hits.json`.

A term's `hits` is the number of records it surfaced FIRST: a record found by
two terms is stored once, with the term that found it first as its
`collect_query`. Beside it the artifact gives how many of those records were
kept for segmentation and how many live core stories came from them — which
terms found stories, not just text.

The YAML is edited line by line, not re-dumped, so its comments survive. It is
not part of the codebook freeze (codebook.FROZEN_FILES).

    python -m pipeline.analyse.lexicon_hits
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.collect import config
from pipeline.common import db as dbm

ROOT = Path(__file__).resolve().parents[2]
LEXICON = ROOT / "codebook" / "lexicon_v1.yaml"
OUT = ROOT / "data" / "artifacts" / "lexicon_hits.json"

LIVE = ("s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)")
EXCLUDED = "SELECT record_id FROM exclusions WHERE story_id IS NULL AND stage <> 'segment'"


def counts(con) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for term in config.lexicon_terms():
        rows = con.execute(
            "SELECT r.source, count(*) AS n,"
            f" sum(r.record_id NOT IN ({EXCLUDED})) AS kept,"
            " (SELECT count(*) FROM stories s JOIN records r2 USING (record_id)"
            f"  WHERE r2.collect_query = ? AND r2.source = r.source AND s.bucket = 'core'"
            f"  AND {LIVE}) AS core"
            " FROM records r WHERE r.collect_query = ? GROUP BY r.source ORDER BY r.source",
            (term, term)).fetchall()
        by = {r["source"]: {"records": r["n"], "kept": r["kept"], "core_stories": r["core"]}
              for r in rows}
        out[term] = {"hits": sum(v["records"] for v in by.values()),
                     "kept": sum(v["kept"] for v in by.values()),
                     "core_stories": sum(v["core_stories"] for v in by.values()),
                     "by_source": by}
    return out


def write_yaml(hits: dict[str, int]) -> int:
    text = LEXICON.read_text()
    n = 0
    for term, h in hits.items():
        pat = re.compile(r'(\{term: "' + re.escape(term) + r'", hits: )(?:null|\d+)(\})')
        text, k = pat.subn(rf"\g<1>{h}\g<2>", text)
        n += k
    LEXICON.write_text(text)
    return n


def main() -> int:
    con = dbm.connect(read_only=True)
    c = counts(con)
    n = write_yaml({t: v["hits"] for t, v in c.items()})
    assert n == len(c), f"updated {n} of {len(c)} lexicon lines"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"note": "records first surfaced by each lexicon term; source"
                                       " terms other than the lexicon (store feeds, the GP Help"
                                       " listing screen) are not lexicon hits",
                               "terms": c}, indent=1))
    for t, v in sorted(c.items(), key=lambda kv: -kv[1]["hits"]):
        print(f"{v['hits']:>6} records · {v['kept']:>5} kept · {v['core_stories']:>3} core  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
