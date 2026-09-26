"""P1-MET-3 — the lexicon recall probe (evals.md §6, T-4 ≤ 5%).

A record the prefilter rejects never reaches a model and leaves no trace, so
its cost cannot be seen downstream (EC-PRE). With no gold set to measure recall
against, this samples the REJECTED records and asks `gpt-5-mini` how many were
relevant after all. `core` share among the rejected is T-4; core + adjacent is
reported beside it.

Stratified by source so one large source cannot hide another's losses. Runs
inside `runs.Run` with the §8-style estimate ($0.05), so T-19 halts it at 1.5×.
The verdicts are written to `data/artifacts/lexicon_probe_<run>.json` (committed:
record ids, buckets and reasons only — no text).

    python -m pipeline.validate.lexicon_probe --n 200
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "relevance_probe_v1.md"
OUT = ROOT / "data" / "artifacts"
MODEL = "gpt-5-mini"
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"bucket": {"type": "string", "enum": ["core", "adjacent", "irrelevant"]},
                         "reason": {"type": "string"}},
          "required": ["bucket", "reason"]}


def sample(con, n: int, seed: int = 26) -> list[dict]:
    rows = [dict(r) for r in con.execute(
        "SELECT r.record_id, r.source, r.text_clean FROM exclusions e JOIN records r"
        " USING (record_id) WHERE e.reason='lexicon_rejected' AND e.story_id IS NULL")]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["source"], []).append(r)
    rng = random.Random(seed)
    total = len(rows)
    picked: list[dict] = []
    for _src, rs in sorted(by.items()):
        k = max(1, round(n * len(rs) / total)) if total else 0     # proportional, ≥1 per source
        picked += rng.sample(rs, min(k, len(rs)))
    return picked[:n] if len(picked) > n else picked


def judge(client, system: str, text: str) -> tuple[dict, object]:
    resp = client.responses.create(
        model=MODEL, instructions=system, reasoning={"effort": "minimal"},
        input=f"<record>\n{text[:6000]}\n</record>",
        text={"format": {"type": "json_schema", "name": "bucket", "schema": SCHEMA,
                         "strict": True}})
    return json.loads(resp.output_text), resp.usage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()
    vals = envm.load()
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        return 2
    from openai import OpenAI

    client = OpenAI(api_key=vals["OPENAI_API_KEY"])
    con = dbm.init()
    rows = sample(con, args.n)
    if not rows:
        print("no lexicon_rejected records — run pipeline.clean.prefilter first", file=sys.stderr)
        return 2
    system = PROMPT.read_text()
    verdicts = []
    with rmod.Run(con, "probe-lexicon-recall", model=MODEL, estimate_usd=0.05,
                  prompt_version="relevance_probe_v1", n=len(rows)) as run:
        for r in rows:
            v, usage = judge(client, system, r["text_clean"])
            run.add_usage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                          cached_tokens=getattr(usage.input_tokens_details, "cached_tokens", 0))
            verdicts.append({"record_id": r["record_id"], "source": r["source"], **v})
        n = len(verdicts)
        core = sum(v["bucket"] == "core" for v in verdicts)
        adj = sum(v["bucket"] == "adjacent" for v in verdicts)
        result = {"run_id": run.run_id, "n": n, "core": core, "adjacent": adj,
                  "t4_core_share": core / n, "core_or_adjacent_share": (core + adj) / n,
                  "t4_threshold": 0.05, "passed": core / n <= 0.05,
                  "by_source": {}, "verdicts": verdicts}
        for v in verdicts:
            s = result["by_source"].setdefault(v["source"], {"n": 0, "core": 0, "adjacent": 0})
            s["n"] += 1
            s[v["bucket"]] = s.get(v["bucket"], 0) + 1
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"lexicon_probe_{run.run_id}.json").write_text(json.dumps(result, indent=1))
        run.n_input, run.n_output = n, core
        con.execute("UPDATE runs SET params_json=json_set(params_json,'$.result',json(?))"
                    " WHERE run_id=?", (json.dumps({k: v for k, v in result.items()
                                                    if k != "verdicts"}), run.run_id))
        con.commit()
    print(f"T-4: {core} of {n} rejected records were core ({core / n:.1%}; threshold 5%) · "
          f"core or adjacent {core + adj} ({(core + adj) / n:.1%}) · "
          f"{'PASS' if result['passed'] else 'FAIL'} · cost ${run.cost_usd():.4f}")
    for src, s in sorted(result["by_source"].items()):
        print(f"   {src:<14} {s['core']}/{s['n']} core, {s['adjacent']} adjacent")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
