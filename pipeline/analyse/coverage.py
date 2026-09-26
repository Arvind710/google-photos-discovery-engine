"""The coverage register — all 60 questions, pooled and per source
(architecture.md §3.4, T-11, P3-MET-10/11, EC-COV-1…5).

For each question: of the stories that were ASKED it (their blocks covered
it), how many answered with anything other than `not_stated`. A question whose
not_stated share is above 85% goes to the interview register — public text
cannot answer it — and becomes a Part 3 interview question. Anything below is
`coded`, including questions that started in block R (a disposition is data,
not judgement: EC-COV-1).

Beside the rate, the top value's share among answered stories is kept in the
run params: 95% coverage with one value everywhere carries no information
(EC-COV-2).

10.3 is structural (every story is a public post) and is always `coded`.

    python -m pipeline.analyse.coverage
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

REGISTER_ABOVE = 0.85
LIVE = ("s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)")


def measure(con, cb: cbm.Codebook) -> tuple[list[tuple], dict]:
    """Rows for analysis_coverage (without run_id) and the concentration detail."""
    per: dict[tuple[str, str], dict[str, set]] = defaultdict(lambda: defaultdict(set))
    values: dict[str, Counter] = defaultdict(Counter)
    for r in con.execute("SELECT c.story_id, c.question, c.value, r.source FROM story_codes c"
                         " JOIN stories s USING (story_id) JOIN records r USING (record_id)"
                         f" WHERE {LIVE}"):
        for src in (r["source"], "_all"):
            d = per[(r["question"], src)]
            d["asked"].add(r["story_id"])
            if r["value"] != "not_stated":
                d["answered"].add(r["story_id"])
        if r["value"] != "not_stated":
            values[r["question"]][r["value"]] += 1
    rows, detail = [], {}
    sources = sorted({src for _, src in per} - {"_all"})
    for qid, q in cb.questions.items():
        for src in ["_all", *sources]:
            d = per.get((qid, src))
            if not d:
                if src == "_all":                      # T-11: every question has a pooled row
                    rows.append((qid, src, q["stage"], q["block"], 0, 0, None, "register"))
                continue
            asked, ans = len(d["asked"]), len(d["answered"])
            ns = asked - ans
            disp = "coded" if q["block"] == "S" or ns / asked <= REGISTER_ABOVE else "register"
            rows.append((qid, src, q["stage"], q["block"], ans, ns, ans / asked, disp))
        tot = sum(values[qid].values())
        top = values[qid].most_common(1)
        detail[qid] = {"top_value": top[0][0] if top else None,
                       "top_share": round(top[0][1] / tot, 3) if top else None,
                       "degenerate": bool(top and top[0][1] / tot > REGISTER_ABOVE)}
    return rows, detail


def main() -> int:
    con = dbm.init()
    cb = cbm.load()
    with rmod.Run(con, "analyse-coverage", model=None, estimate_usd=0,
                  codebook_version=cb.version_string, register_above=REGISTER_ABOVE) as run:
        rows, detail = measure(con, cb)
        con.execute("DELETE FROM analysis_coverage")
        con.executemany("INSERT INTO analysis_coverage (question, source, stage, block, n_coded,"
                        " n_not_stated, coverage, disposition, run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        [(*r, run.run_id) for r in rows])
        con.execute("UPDATE runs SET params_json=json_set(params_json,'$.concentration',json(?))"
                    " WHERE run_id=?", (json.dumps(detail), run.run_id))
        con.commit()
        run.n_output = len(rows)
    pooled = [r for r in rows if r[1] == "_all"]
    print(f"{len(pooled)} questions · coded {sum(r[7] == 'coded' for r in pooled)} · "
          f"register {sum(r[7] == 'register' for r in pooled)}")
    for r in pooled:
        cov = "—" if r[6] is None else f"{r[6]:.0%}"
        print(f"  {r[0]:>5} {r[3]}  {cov:>4} of {r[4] + r[5]:>3}  {r[7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
