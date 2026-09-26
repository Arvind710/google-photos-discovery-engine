"""Reliability without a human gold set (architecture.md §5.6, [CTX] §15.7).

1. `dual`: a stratified sample of coded stories (source × photo_class ×
   primary_stage, EC-VAL-4) is coded AGAIN by gpt-5-mini — a different model,
   the same prompt and blocks — through the Batch API. The sample doubles as the
   model-choice experiment of arch §5.4.
2. `reliability`: per field, raw agreement, Cohen's κ (single-select) or mean
   Jaccard (multi-select), the top value's share and the marginals — three
   numbers together, because κ alone bars correct but skewed fields (EC-VAL-2):
       κ ≥ 0.60                     ok
       κ < 0.60, top value > 85%    degenerate  (real but nearly constant)
       κ < 0.60 otherwise           low_reliability — barred from headlines
   Also the cross-coder not_stated gap per question (P3-MET-7, flag > 20pp).
3. `adjudicate`: gpt-5 sees the story and both codings of each disputed spine
   field and picks one, with a reason. A silver standard, not correctness
   (EC-VAL-3): the split of who was upheld is reported, and the primary coding
   is never overwritten.

Agreement measures consistency, not correctness — two models can agree and both
be wrong (EC-VAL-1). That sentence goes on the Methodology page unhedged.

    python -m pipeline.validate.agreement dual --n 100
    python -m pipeline.validate.agreement reliability
    python -m pipeline.validate.agreement adjudicate
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict

from pipeline.classify import blocks as B
from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod
from pipeline.segment import stories as seg

SECOND = "gpt-5-mini"
KAPPA_OK = 0.60
DEGENERATE = 0.85
SPINE = ("photo_class", "media_type", "primary_stage", "outcome", "failure_owner",
         "metric_node", "severity")
ADJUDICATE = ("primary_stage", "photo_class", "media_type", "outcome")


# ------------------------------------------------------------------- sample
def sample(con, n: int, seed: int = 28) -> list[str]:
    """Proportional over source × photo_class strata (≥ 1 each), and within a
    stratum spread across primary_stage before repeating one."""
    rows = con.execute("SELECT p.story_id, r.source, p.photo_class, p.primary_stage"
                       " FROM story_spine p JOIN stories s USING (story_id)"
                       " JOIN records r USING (record_id) ORDER BY p.story_id").fetchall()
    rng = random.Random(seed)
    strata: dict[tuple, list] = defaultdict(list)
    for r in rows:
        strata[(r["source"], r["photo_class"])].append(r)
    picked = []
    for _k, rs in sorted(strata.items()):
        k = max(1, round(n * len(rs) / len(rows)))
        rng.shuffle(rs)
        by_stage: dict[str, list] = defaultdict(list)
        for r in rs:
            by_stage[r["primary_stage"]].append(r)
        order = []
        while any(by_stage.values()):                      # round-robin over stages
            for st in sorted(by_stage):
                if by_stage[st]:
                    order.append(by_stage[st].pop())
        picked += [r["story_id"] for r in order[:k]]
    rng.shuffle(picked)
    return picked[:n]


# --------------------------------------------------------------- the codings
def primary(con, cb, sids: list[str]) -> dict[str, dict]:
    q = ",".join("?" * len(sids))
    out: dict[str, dict] = {}
    for r in con.execute(f"SELECT * FROM story_spine WHERE story_id IN ({q})", sids):
        out[r["story_id"]] = {f: str(r[f]) for f in SPINE}
    for r in con.execute(f"SELECT story_id, question, value, accuracy FROM story_codes"
                         f" WHERE story_id IN ({q}) AND question <> '10.3'", sids):
        v = f"{r['value']}={r['accuracy']}" if r["question"] == "2.2" and r["accuracy"] else r["value"]
        out[r["story_id"]].setdefault(f"q:{r['question']}", []).append(v)
    return out


def flatten(c: B.Coded) -> dict:
    d = {f: str(c.spine[f]) for f in SPINE}
    for q, v, acc, _ in c.rows:
        if q != "10.3":
            d.setdefault(f"q:{q}", []).append(f"{v}={acc}" if q == "2.2" and acc else v)
    return d


# ------------------------------------------------------------------- metrics
def kappa(pairs: list[tuple[str, str]]) -> tuple[float | None, float]:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb_ = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb_[k] for k in ca) / (n * n)
    k = 1.0 if pe == 1 and po == 1 else None if pe == 1 else (po - pe) / (1 - pe)
    return k, po


def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def verdict(value: float | None, top_share: float) -> str:
    if value is not None and value >= KAPPA_OK:
        return "ok"
    return "degenerate" if top_share > DEGENERATE else "low_reliability"


def reliability_rows(cb, p: dict[str, dict], s: dict[str, dict]) -> tuple[list[tuple], dict]:
    rows, gaps = [], {}
    fields = list(SPINE) + [f"q:{q}" for q in cb.questions if q != "10.3"]
    for f in fields:
        both = [sid for sid in p if sid in s and f in p[sid] and f in s[sid]]
        if not both:
            continue
        if f in SPINE or cb.questions[f[2:]]["select"] == "single":
            pairs = [(str(p[x][f][0] if isinstance(p[x][f], list) else p[x][f]),
                      str(s[x][f][0] if isinstance(s[x][f], list) else s[x][f])) for x in both]
            val, raw = kappa(pairs)
            marg = Counter(a for a, _ in pairs)
            metric = "kappa"
        else:
            sets = [(frozenset(p[x][f]), frozenset(s[x][f])) for x in both]
            val = sum(jaccard(a, b) for a, b in sets) / len(sets)
            raw = sum(a == b for a, b in sets) / len(sets)
            marg = Counter("|".join(sorted(a)) for a, _ in sets)
            metric = "jaccard"
        top = marg.most_common(1)[0][1] / len(both)
        rows.append((f, metric, None if val is None else round(val, 4), round(raw, 4),
                     round(top, 4), json.dumps(dict(marg.most_common(12))), len(both),
                     verdict(val, top)))
        if f.startswith("q:"):
            def ns(d, x, f=f):
                v = d[x][f]
                return (v if isinstance(v, list) else [v]) == ["not_stated"]
            gp = sum(ns(p, x) for x in both) / len(both)
            gs = sum(ns(s, x) for x in both) / len(both)
            gaps[f[2:]] = {"primary": round(gp, 3), "secondary": round(gs, 3),
                           "gap_pp": round(100 * abs(gp - gs), 1), "flag": abs(gp - gs) > 0.20}
    return rows, gaps


# ---------------------------------------------------------------- commands
def dual(con, client, cb, n: int) -> None:
    sids = sample(con, n)
    items = {i.story_id: i for i in B.live_items(con, skip_done=False) if i.story_id in set(sids)}
    system = B.system_prompt(cb)
    with rmod.Run(con, "code-dual", model=SECOND, batch=True, estimate_usd=0.60,
                  prompt_version=B.PROMPT_VERSION, codebook_version=cb.version_string,
                  n=len(sids), effort=B.EFFORT_BY_BUCKET) as run:
        out = B.batch_and_wait(client, run.run_id,
                               [(sid, B.request_body(cb, items[sid], system, model=SECOND))
                                for sid in sids])
        second, fatal = {}, Counter()
        for o in out:
            body = (o.get("response") or {}).get("body") or {}
            u = seg._usage(body)
            run.add_usage(input_tokens=u[0], output_tokens=u[1], cached_tokens=u[2])
            a = B.answer_of(body)
            c = (B.Coded(o["custom_id"], fatal=a) if isinstance(a, str)
                 else B.validate(cb, items[o["custom_id"]], a))
            if c.fatal:
                fatal[c.fatal] += 1
                continue
            second[o["custom_id"]] = flatten(c)
        prim = primary(con, cb, list(second))
        con.execute("DELETE FROM double_coding WHERE coder IN ('primary','secondary')")
        for coder, d in (("primary", prim), ("secondary", second)):
            con.executemany("INSERT INTO double_coding (story_id, field, coder, value, run_id)"
                            " VALUES (?,?,?,?,?)",
                            [(sid, f, coder, json.dumps(v), run.run_id)
                             for sid, fs in d.items() for f, v in fs.items()])
        strata = Counter((items[s].source, prim[s]["photo_class"], prim[s]["primary_stage"])
                         for s in second)
        con.execute("UPDATE runs SET n_input=?, n_output=?, params_json=json_set(params_json,"
                    "'$.fatal',json(?),'$.strata',json(?)) WHERE run_id=?",
                    (len(sids), len(second), json.dumps(fatal),
                     json.dumps({"|".join(k): v for k, v in strata.items()}), run.run_id))
        con.commit()
    print(f"dual-coded {len(second)} of {len(sids)} · fatal {dict(fatal)} · ${run.cost_usd():.3f}")
    reliability(con, cb)


def _load_double(con) -> tuple[dict, dict, str]:
    p, s, rid = defaultdict(dict), defaultdict(dict), None
    for r in con.execute("SELECT story_id, field, coder, value, run_id FROM double_coding"
                         " WHERE coder IN ('primary','secondary')"):
        (p if r["coder"] == "primary" else s)[r["story_id"]][r["field"]] = json.loads(r["value"])
        rid = r["run_id"]
    return p, s, rid


def reliability(con, cb) -> None:
    p, s, dual_run = _load_double(con)
    rows, gaps = reliability_rows(cb, p, s)
    con.execute("DELETE FROM analysis_reliability")
    con.executemany("INSERT INTO analysis_reliability (field, metric, value, raw_agreement,"
                    " top_share, marginals_json, n, verdict, run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    [(*r, dual_run) for r in rows])
    con.commit()
    strata = json.loads(con.execute("SELECT params_json FROM runs WHERE run_id=?",
                                    (dual_run,)).fetchone()[0]).get("strata")
    art = {"dual_run": dual_run, "n": len(p), "fields": [
        dict(zip(("field", "metric", "value", "raw_agreement", "top_share", "marginals", "n",
                  "verdict"), r, strict=True)) for r in rows],
        "not_stated_gap": gaps, "strata": strata}
    (seg.ARTIFACTS / f"reliability_{dual_run}.json").write_text(json.dumps(art, indent=1))
    for r in rows:
        if not r[0].startswith("q:"):
            print(f"  {r[0]:<14} {r[1]:<7} {r[2]}  raw {r[3]}  top {r[4]}  n {r[6]}  {r[7]}")
    v = Counter(r[7] for r in rows)
    print(f"all fields: {dict(v)} · not_stated gaps > 20pp: "
          f"{[q for q, g in gaps.items() if g['flag']]}")


ADJ_SCHEMA = B._obj({"fields": {"type": "array", "items": B._obj({
    "field": {"type": "string", "enum": list(ADJUDICATE)},
    "choice": {"type": "string", "enum": ["A", "B", "neither"]},
    "value": B.STR, "reason": B.STR})}})


def adjudicate(con, client, cb) -> None:
    p, s, dual_run = _load_double(con)
    items = {i.story_id: i for i in B.live_items(con, skip_done=False)}
    disputes = {sid: [f for f in ADJUDICATE if p[sid].get(f) != s[sid].get(f)]
                for sid in s if sid in p}
    disputes = {k: v for k, v in disputes.items() if v}
    rng = random.Random(29)
    system = (B.system_prompt(cb) + "\n\n## Your task now\nTwo coders disagreed on some spine"
              " fields of this story. For each field listed, say which coding is right: A, B,"
              " or neither (then give the right value). Judge only from the story and the"
              " codebook. One-clause reason, under 15 words.")
    bodies, order = [], {}
    for sid, fs in disputes.items():
        flip = rng.random() < 0.5                  # the adjudicator never knows which is primary
        a, b = (s, p) if flip else (p, s)
        order[sid] = flip
        listing = "\n".join(f"- {f}: A = {a[sid][f]} · B = {b[sid][f]}" for f in fs)
        bodies.append((sid, {"model": B.MODEL, "instructions": system,
                             "reasoning": {"effort": "low"},
                             "input": B.render(items[sid]) + f"\n\nDisputed fields:\n{listing}",
                             "text": {"format": {"type": "json_schema", "name": "adjudication",
                                                 "schema": ADJ_SCHEMA, "strict": True}}}))
    with rmod.Run(con, "code-adjudicate", model=B.MODEL, batch=True, estimate_usd=0.40,
                  prompt_version="adjudicate_v1", codebook_version=cb.version_string,
                  of_dual=dual_run, n=len(bodies)) as run:
        out = B.batch_and_wait(client, run.run_id, bodies)
        upheld, rows = Counter(), []
        for o in out:
            sid = o["custom_id"]
            body = (o.get("response") or {}).get("body") or {}
            u = seg._usage(body)
            run.add_usage(input_tokens=u[0], output_tokens=u[1], cached_tokens=u[2])
            a = B.answer_of(body)
            if isinstance(a, str):
                upheld["failed"] += 1
                continue
            for f in a["fields"]:
                if f["field"] not in disputes[sid]:
                    continue
                ch = f["choice"]
                who = ("neither" if ch == "neither" else
                       ("secondary" if (ch == "A") == order[sid] else "primary"))
                upheld[f"{f['field']}:{who}"] += 1
                upheld[who] += 1
                val = (p if who == "primary" else s)[sid][f["field"]] if who != "neither" \
                    else f["value"]
                rows.append((sid, f["field"], "adjudicator",
                             json.dumps({"value": val, "upheld": who, "reason": f["reason"]}),
                             run.run_id))
        con.execute("DELETE FROM double_coding WHERE coder='adjudicator'")
        con.executemany("INSERT INTO double_coding (story_id, field, coder, value, run_id)"
                        " VALUES (?,?,?,?,?)", rows)
        con.execute("UPDATE runs SET n_output=?, params_json=json_set(params_json,'$.upheld',"
                    "json(?)) WHERE run_id=?", (len(rows), json.dumps(upheld), run.run_id))
        con.commit()
    (seg.ARTIFACTS / f"adjudication_{run.run_id}.json").write_text(json.dumps(
        {"run_id": run.run_id, "dual_run": dual_run, "disputed_stories": len(disputes),
         "upheld": upheld, "rows": [json.loads(r[3]) | {"story_id": r[0], "field": r[1]}
                                    for r in rows]}, indent=1))
    print(f"{len(disputes)} disputed stories · upheld {dict(upheld)} · ${run.cost_usd():.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dual", "reliability", "adjudicate"])
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    cb = cbm.load()
    con = dbm.init()
    if args.cmd == "reliability":
        reliability(con, cb)
        return 0
    vals = envm.load()
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=vals["OPENAI_API_KEY"])
    (dual if args.cmd == "dual" else adjudicate)(con, client, cb, *(
        [args.n] if args.cmd == "dual" else []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
