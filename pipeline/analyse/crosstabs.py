"""The cross-tabs every Analysis view reads (architecture.md §4, [CTX] §8.4,
implementationplan.md task 4.1). Free: no model call.

One generic table, `analysis_crosstab`. A row is: among the stories of
population P that fall in segment `val_b` of `dim_b`, how many carry `val_a`
of `dim_a`, and from how many different people.

    dim_a  "<population>.<field>"   e.g. "core.primary_stage", "core.q:5.6"
    dim_b  "photo_class" | "source" | "outcome" | "_all"
    n      stories with val_a in that segment
    denom  stories in that segment that could carry val_a: every story for a
           spine field; for a question, the stories that were ASKED it
    n_authors  distinct authors among the n (EC-COL-6)

Every view splits on photo_class ([CTX] §15.4), so photo_class is the default
`dim_b`, always with a pooled `_all` segment beside it. Only live, coded
stories count. Core is the headline population; adjacent is reported
separately and never pooled with it.

A share is never formatted here: views pass (n, denom) to `share()`.

    python -m pipeline.analyse.crosstabs
"""

from __future__ import annotations

from collections import defaultdict

from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

LIVE = "s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)"
POPULATIONS = ("core", "adjacent")
SPINE_A = ("primary_stage", "failure_owner", "metric_node", "outcome", "media_type", "source",
           "photo_class")
# (dim_a, dim_b) pairs beyond "everything × photo_class".
EXTRA = (("primary_stage", "source"), ("q:3.2", "outcome"), ("q:9.4", "outcome"))


def load(con) -> tuple[dict[str, dict], dict[str, dict[str, set[str]]]]:
    """(spine per story, question → value → {story ids}) for live coded stories."""
    spine = {r["story_id"]: dict(r) for r in con.execute(
        "SELECT p.story_id, s.bucket AS population, s.author_key, r.source, p.primary_stage,"
        " p.failure_owner, p.metric_node, p.outcome, p.media_type, p.photo_class"
        " FROM story_spine p JOIN stories s USING (story_id) JOIN records r USING (record_id)"
        f" WHERE {LIVE}")}
    codes: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in con.execute("SELECT story_id, question, value FROM story_codes"):
        if r["story_id"] in spine:
            codes[r["question"]][r["value"]].add(r["story_id"])
    return spine, codes


def values_of(field: str, spine: dict, codes: dict) -> tuple[dict[str, set[str]], set[str]]:
    """(value → stories, stories that could carry a value)."""
    if field.startswith("q:"):
        by = codes.get(field[2:], {})
        asked = set().union(*by.values()) if by else set()
        return {v: ids for v, ids in by.items() if v != "not_stated"}, asked
    by: dict[str, set[str]] = defaultdict(set)
    for sid, s in spine.items():
        by[str(s[field])].add(sid)
    return by, set(spine)


def rows(spine: dict, codes: dict, cb: cbm.Codebook) -> list[tuple]:
    out = []
    questions = [f"q:{q}" for q in cb.questions]
    pairs = [(a, "photo_class") for a in SPINE_A + tuple(questions) if a != "photo_class"]
    pairs += [("photo_class", "_all"), *EXTRA]
    for pop in POPULATIONS:
        members = {sid for sid, s in spine.items() if s["population"] == pop}
        for a, b in pairs:
            va, asked = values_of(a, spine, codes)
            asked &= members
            if b == "_all":
                segs = {"_all": members}
            else:
                vb, _ = values_of(b, spine, codes)
                segs = {"_all": members, **{k: ids & members for k, ids in vb.items()}}
            for seg, seg_ids in segs.items():
                denom_ids = asked & seg_ids
                if not denom_ids:
                    continue
                for val, ids in va.items():
                    hit = ids & denom_ids
                    if hit:
                        out.append((f"{pop}.{a}", val, b if b != "_all" else "_all", seg,
                                    len(hit), len(denom_ids),
                                    len({spine[x]["author_key"] for x in hit} - {None})))
    return out


def main() -> int:
    con = dbm.init()
    cb = cbm.load()
    with rmod.Run(con, "analyse-crosstabs", model=None, estimate_usd=0,
                  codebook_version=cb.version_string) as run:
        spine, codes = load(con)
        rs = rows(spine, codes, cb)
        con.execute("DELETE FROM analysis_crosstab")
        con.executemany("INSERT INTO analysis_crosstab (dim_a, val_a, dim_b, val_b, n, denom,"
                        " n_authors, run_id) VALUES (?,?,?,?,?,?,?,?)",
                        [(*r, run.run_id) for r in rs])
        con.commit()
        run.n_input, run.n_output = len(spine), len(rs)
    print(f"{len(spine)} live coded stories · {len(rs)} cross-tab rows · run {run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
