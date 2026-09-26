"""Run the Ask AI golden set (evals.md §10) and write
data/artifacts/golden_<run>.json, which evals/test_p5_ask.py reads.

Paid: every call is inside two `runs.Run`s, one per model (4.md gotcha 9).
Follow-up questions ask their history question first, for real, so the
reference they resolve is an answer the engine actually gave.

    python evals/golden_sweep.py                 # all 24
    python evals/golden_sweep.py --only S1 O3    # a subset while iterating
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from lib import analyst as A  # noqa: E402
from pipeline.common import db as dbm  # noqa: E402
from pipeline.common import env as envm  # noqa: E402
from pipeline.common import runs as rmod  # noqa: E402

GOLDEN = ROOT / "evals" / "fixtures" / "golden_questions.yaml"
INJECT = ROOT / "evals" / "fixtures" / "injection_stories.jsonl"
ART = ROOT / "data" / "artifacts"


def injected(pid: str) -> list[dict]:
    for line in INJECT.read_text().splitlines():
        r = json.loads(line)
        if r["id"] == pid:
            return [{"story_id": f"probe-{pid}", "text": r["text"], "source": "reddit",
                     "primary_stage": "5", "photo_class": "unclear", "population": "core"}]
    raise KeyError(pid)


def one(client, q: dict) -> dict:
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'corpus.db'}?mode=ro", uri=True,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    history, pre = None, None
    if q.get("history"):
        pre = A.ask(client, con, q["history"])
        history = [{"question": q["history"], "answer": pre.text}]
    kw = dict(history=history, inject_stories=injected(q["inject"]) if q.get("inject") else None)
    a = A.ask(client, con, q["q"], **kw)
    if a.error:                  # an API failure is not an answer: retry it once
        a = A.ask(client, con, q["q"], **kw)
    text = a.text or ""
    fails = []
    if a.route not in q["expect"]:
        fails.append(f"route {a.route}, expected {q['expect']}")
    for n in q.get("must_contain") or []:
        if not re.search(rf"(?<![\d.]){n}(?![\d])", A.V.CITATION.sub(" ", text)):
            fails.append(f"missing the number {n}")
    for pat in q.get("must_not") or []:
        if re.search(pat, text):
            fails.append(f"matched forbidden /{pat}/")
    usage = {}
    for x in ([pre] if pre else []) + [a]:
        for m, t in x.usage.items():
            u = usage.setdefault(m, [0, 0, 0])
            for i in range(3):
                u[i] += t[i]
    return {"id": q["id"], "category": q["category"], "question": q["q"],
            "restated": a.restated, "route": a.route, "expect": q["expect"],
            "route_ok": a.route in q["expect"], "verified": a.verified,
            "problems": a.report.problems() if a.report else [a.error or "no report"],
            "repaired": a.repaired, "withheld": a.withheld, "fails": fails, "gap": a.verdict.gap if a.verdict else "",
            "text": text, "seconds": round(a.seconds, 1),
            "cost_usd": round(a.cost_usd + (pre.cost_usd if pre else 0), 5), "usage": usage,
            "error": a.error}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    qs = yaml.safe_load(GOLDEN.read_text())["questions"]
    if args.only:
        qs = [q for q in qs if q["id"] in set(args.only)]
    from openai import OpenAI
    # A stuck call must not hold the sweep (the default timeout is 600 s).
    client = OpenAI(api_key=envm.require("OPENAI_API_KEY"), timeout=A.TIMEOUT_S, max_retries=1)
    con = dbm.init()
    est = 0.035 * len(qs)
    with rmod.Run(con, "ask-golden-plan", model=A.PLANNER_MODEL, estimate_usd=max(est / 10, .02),
                  prompt_version=A.PROMPT_VERSION, n=len(qs)) as rp, \
         rmod.Run(con, "ask-golden-synth", model=A.SYNTHESIS_MODEL, estimate_usd=max(est, .05),
                  prompt_version=A.PROMPT_VERSION, n=len(qs)) as rs:
        with ThreadPoolExecutor(args.workers) as ex:
            rows = list(ex.map(lambda q: one(client, q), qs))
        for r in rows:
            for m, run in ((A.PLANNER_MODEL, rp), (A.SYNTHESIS_MODEL, rs)):
                u = r["usage"].get(m, [0, 0, 0])
                run.add_usage(input_tokens=u[0], cached_tokens=u[1], output_tokens=u[2])
        summary = {
            "n": len(rows),
            "T13_route": sum(r["route_ok"] for r in rows) / len(rows),
            "verified": sum(r["verified"] for r in rows),
            "repaired": sum(r["repaired"] for r in rows),
            "withheld": sum(bool(r["withheld"]) for r in rows),
            "assertion_fails": sum(bool(r["fails"]) for r in rows),
            "problems_by_type": {k: sum(1 for r in rows for p in r["problems"]
                                        if p.startswith(k)) for k in
                                 ("unsupported number", "percentage without its count",
                                  "unverifiable quote", "citation not retrieved",
                                  "uncited claim", "share stated as", "label-and-colon",
                                  "closing", "refusal", "evidence", "length",
                                  "code name", "directional share", "comparison between")},
            "cost_usd": round(rp.cost_usd() + rs.cost_usd(), 4),
            "mean_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 1)}
        out = {"run_id": rs.run_id, "plan_run": rp.run_id, "prompt_version": A.PROMPT_VERSION,
               "subset": bool(args.only), "summary": summary, "rows": rows}
    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"golden_{rs.run_id}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    for r in rows:
        flag = "ok " if r["route_ok"] and r["verified"] and not r["fails"] else "BAD"
        print(f"{flag} {r['id']:<3} {r['route']:<8} verified={r['verified']} "
              f"repaired={r['repaired']} ${r['cost_usd']:.3f} {r['seconds']}s "
              f"{'; '.join(r['fails'] + r['problems'])[:220]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
