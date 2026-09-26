"""Opportunity candidates, two gates, five weights, and the sensitivity check
([CTX] §9, §15.2; architecture.md §6; implementationplan.md tasks 4.3–4.4).
Free: no model call. Rebuilds `analysis_opportunity` and
`analysis_weight_sensitivity` whole.

CANDIDATES (Docs/decisions.md D-11). [CTX] §9.1 defines an opportunity as
stage × failure mode × segment. With 115 core stories every failure-mode cell
inside a stage holds fewer than ten stories, so a candidate is one PRIMARY
STAGE where something went wrong; its failure modes and photo-class split are
reported inside it as counts. Stage 1 (context) and 9–10 (nothing went wrong)
are listed as `not_a_failure`, never scored.

SCORES, 1–5, each with a one-line reason:
    frequency          core stories at this stage ÷ live core stories, banded
    metric_leverage    the stage's metric node (the fixed rule) → node_leverage
    evidence_strength  distinct sources, less one if mean coding_conf < 0.6
    reach              judgement (opportunity_inputs_v1.yaml)
    severity           mean story severity — `low_reliability` (κ 0.33), so it
                       is OUT of the headline and in a sensitivity row (D-11)
GATES (≥ 3 to pass): addressable_by_gp, ai_necessity — judgement, same file.

STATUS: `gated_out` (a gate failed, shown with the gate named — P4-INV-5),
`below_floor` (passes the gates but n_core < 30: [CTX] §15.5 draws no
comparison below 30, so it is not ranked — P4-INV-2), or `ranked`.

SENSITIVITY: 1,000 draws, each weight moved uniformly within ±10 absolute
(floored at 0) and renormalised; the share of draws each candidate comes
first. Computed for the ranked pool, and for every gate-passing candidate as
an ILLUSTRATIVE pool that ignores the floor.

    python -m pipeline.analyse.opportunity
"""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from pipeline.classify import blocks as B
from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

ROOT = Path(__file__).resolve().parents[2]
SCORING = ROOT / "codebook" / "scoring_v1.yaml"
INPUTS = ROOT / "codebook" / "opportunity_inputs_v1.yaml"
FLOOR = 30                                  # [CTX] §15.5 — the same floor as app/lib/evidence.share()
FAILURE_STAGES = ("0", "2", "3", "4", "5", "6", "7", "8")
HEADLINE = ("metric_leverage", "frequency", "evidence_strength", "reach")   # D-11: no severity
# What each criterion is computed from — P4-INV-3 checks none is low_reliability.
# metric_leverage is scored from the candidate's STAGE through the fixed node rule
# (classify.blocks.metric_node), not from story-level metric_node, whose κ fell to
# 0.58 after the D-11 re-code; the story-level nodes are shown, never scored.
CRITERION_FIELDS = {"frequency": ["primary_stage"], "metric_leverage": ["primary_stage"],
                    "evidence_strength": ["source"], "reach": [], "severity": ["severity"]}
# Reliable questions that say HOW a stage went wrong (display only, never scored).
FAILURE_MODE_QS = {"0": ("0.1", "0.2"), "2": ("2.4",), "3": ("3.2", "3.4"), "4": ("4.3",),
                   "5": ("5.6", "5.1", "5.2", "5.3", "5.4"), "6": ("6.4", "3.2"),
                   "7": ("7.2",), "8": ("8.2",)}
LIVE = "s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)"
DRAWS, SEED = 1000, 31


def frequency_score(n: int, denom: int) -> tuple[int, str]:
    share = n / denom
    s = 1 if share < .05 else 2 if share < .10 else 3 if share < .15 else 4 if share < .25 else 5
    return s, f"{n} of {denom} core stories (bands <5% · 5–10 · 10–15 · 15–25 · ≥25%)"


def evidence_score(n_sources: int, conf: float) -> tuple[int, str]:
    base = (1 if n_sources <= 1 else 2 if n_sources == 2 else 3 if n_sources <= 4
            else 4 if n_sources <= 6 else 5)
    s = max(1, base - (1 if conf < 0.6 else 0))
    return s, (f"{n_sources} sources" + (f"; mean coding confidence {conf:.2f} < 0.6, less one"
                                         if conf < 0.6 else f"; mean coding confidence {conf:.2f}"))


def weighted(scores: dict[str, int], weights: dict[str, float], keys) -> float:
    tot = sum(weights[k] for k in keys)
    return sum(weights[k] * scores[k] for k in keys) / tot


def sensitivity(cands: list[dict], weights: dict[str, float], keys, *, draws: int = DRAWS,
                spread: float = 10, seed: int = SEED) -> dict[str, float]:
    """Share of draws in which each candidate scores highest (ties split)."""
    if not cands:
        return {}
    rng = random.Random(seed)
    wins: Counter = Counter()
    for _ in range(draws):
        w = {k: max(0.0, weights[k] + rng.uniform(-spread, spread)) for k in keys}
        if sum(w.values()) == 0:
            continue
        sc = {c["candidate_id"]: weighted(c["scores"], w, keys) for c in cands}
        best = max(sc.values())
        top = [k for k, v in sc.items() if abs(v - best) < 1e-9]
        for k in top:
            wins[k] += 1 / len(top)
    return {c["candidate_id"]: round(wins[c["candidate_id"]] / draws, 4) for c in cands}


def build(con, scoring: dict, inputs: dict, rel: dict[str, str]) -> list[dict]:
    # P4-INV-3: no low_reliability field feeds a gate or the headline score.
    bad = [f for k in HEADLINE for f in CRITERION_FIELDS[k] if rel.get(f) == "low_reliability"]
    assert not bad, f"low_reliability fields in the headline score: {bad} (P4-INV-3)"
    rows = [dict(r) for r in con.execute(
        "SELECT p.story_id, s.bucket, s.author_key, r.source, p.primary_stage, p.metric_node,"
        " p.photo_class, p.severity, p.coding_conf, p.workaround FROM story_spine p"
        f" JOIN stories s USING (story_id) JOIN records r USING (record_id) WHERE {LIVE}")]
    core = [r for r in rows if r["bucket"] == "core"]
    denom = len(core)
    codes: dict[str, dict[str, list[str]]] = {}
    for r in con.execute("SELECT story_id, question, value FROM story_codes"
                         " WHERE value <> 'not_stated'"):
        codes.setdefault(r[0], {}).setdefault(r[1], []).append(r[2])
    spans = {r[0]: r[1] for r in con.execute(
        "SELECT story_id, span FROM evidence WHERE field='primary_stage'")}
    node_lev = inputs["node_leverage"]
    out = []
    for stage in sorted({r["primary_stage"] for r in core}, key=int):
        rs = [r for r in core if r["primary_stage"] == stage]
        cid = f"stage{stage}"
        adj = sum(r["bucket"] == "adjacent" and r["primary_stage"] == stage for r in rows)
        modes: Counter = Counter()
        for r in rs:
            for q in FAILURE_MODE_QS.get(stage, ()):
                for v in codes.get(r["story_id"], {}).get(q, []):
                    modes[f"{q} {v}"] += 1
        best = sorted(rs, key=lambda r: (-r["coding_conf"], r["story_id"]))
        quotes, seen = [], set()
        for r in best:                                      # spread across sources
            if r["story_id"] in spans and r["source"] not in seen and len(quotes) < 5:
                quotes.append({"story_id": r["story_id"], "source": r["source"],
                               "span": spans[r["story_id"]]})
                seen.add(r["source"])
        detail = {"sources": dict(Counter(r["source"] for r in rs).most_common()),
                  "photo_class": dict(Counter(r["photo_class"] for r in rs).most_common()),
                  "metric_nodes": dict(Counter(r["metric_node"] for r in rs).most_common()),
                  "failure_modes": dict(modes.most_common(12)),
                  "workaround_stories": sum(bool(r["workaround"]) for r in rs),
                  "mean_coding_conf": round(sum(r["coding_conf"] for r in rs) / len(rs), 3),
                  "quotes": quotes}
        c = {"candidate_id": cid, "primary_stage": stage, "n_core": len(rs), "denom": denom,
             "n_authors": len({r["author_key"] for r in rs} - {None}), "n_adjacent": adj,
             "detail": detail, "scores": {}, "why": {}, "gates": {}}
        if stage not in FAILURE_STAGES:
            c.update(label=("Why they went looking — context, not a failure" if stage == "1"
                            else "Nothing went wrong — found, or found by accident"),
                     status="not_a_failure",
                     status_reason="Not a point where retrieval failed; reported, not scored")
            out.append(c)
            continue
        spec = inputs["candidates"][cid]                    # KeyError = an unscored candidate
        c["label"] = spec["label"]
        f, fw = frequency_score(len(rs), denom)
        node = B.metric_node(stage, {}, "not_stated")        # the stage's node (D-11)
        e, ew = evidence_score(len(detail["sources"]), detail["mean_coding_conf"])
        sev = round(sum(r["severity"] for r in rs) / len(rs))
        c["scores"] = {"frequency": f, "metric_leverage": node_lev[node]["score"],
                       "evidence_strength": e, "reach": spec["reach"]["score"], "severity": sev}
        c["why"] = {"frequency": fw,
                    "metric_leverage": f"{node}: {node_lev[node]['why']}",
                    "evidence_strength": ew, "reach": spec["reach"]["why"],
                    "severity": f"mean story severity {sum(r['severity'] for r in rs) / len(rs):.2f}"
                                " — low_reliability (κ 0.33): sensitivity row only"}
        for g, rule in scoring["gates"].items():
            c["gates"][g] = {"score": spec[g]["score"], "why": spec[g]["why"],
                             "passed": spec[g]["score"] >= rule["min"]}
        w = scoring["weights"]
        c["score_headline"] = round(weighted(c["scores"], w, HEADLINE), 3)
        c["score_with_severity"] = round(weighted(c["scores"], w, tuple(w)), 3)
        failed = [g for g, v in c["gates"].items() if not v["passed"]]
        if failed:
            c["status"] = "gated_out"
            c["status_reason"] = "; ".join(f"{g} {c['gates'][g]['score']} < 3: "
                                           f"{c['gates'][g]['why']}" for g in failed)
        elif len(rs) < FLOOR:
            c["status"] = "below_floor"
            c["status_reason"] = (f"{len(rs)} core stories, under the {FLOOR} below which no "
                                  "comparison is drawn ([CTX] §15.5) — shown, not ranked")
        else:
            c["status"], c["status_reason"] = "ranked", "passes both gates, at or above the floor"
        out.append(c)
    ranked = sorted((c for c in out if c["status"] == "ranked"),
                    key=lambda c: (-c["score_headline"], c["candidate_id"]))
    for k, c in enumerate(ranked, 1):
        c["rank_headline"] = k
    return out


def main() -> int:
    con = dbm.init()
    cb = cbm.load()
    scoring = yaml.safe_load(SCORING.read_text())
    inputs = yaml.safe_load(INPUTS.read_text())
    started = datetime.now(UTC)
    # P4-INV-4: the weights were registered before this ranking run.
    assert datetime.fromisoformat(scoring["pre_registered_at"]) < started, "P4-INV-4"
    rel = {r[0]: r[1] for r in con.execute("SELECT field, verdict FROM analysis_reliability")}
    with rmod.Run(con, "analyse-opportunity", model=None, estimate_usd=0,
                  codebook_version=cb.version_string, inputs_status=inputs["status"],
                  pre_registered_at=scoring["pre_registered_at"]) as run:
        cands = build(con, scoring, inputs, rel)
        w = scoring["weights"]
        sens = []
        for variant, keys in (("headline", HEADLINE), ("with_severity", tuple(w))):
            for pool, members in (("ranked", [c for c in cands if c["status"] == "ranked"]),
                                  ("gates_passed", [c for c in cands if c["status"]
                                                    in ("ranked", "below_floor")])):
                for cid, share in sensitivity(members, w, keys).items():
                    sens.append((variant, cid, share, DRAWS, pool, run.run_id))
        con.execute("DELETE FROM analysis_opportunity")
        con.execute("DELETE FROM analysis_weight_sensitivity")
        for c in cands:
            con.execute(
                "INSERT INTO analysis_opportunity (candidate_id, primary_stage, label, n_core,"
                " denom, n_authors, n_adjacent, detail_json, scores_json, gates_json,"
                " inputs_status, status, status_reason, score_headline, score_with_severity,"
                " rank_headline, run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["candidate_id"], c["primary_stage"], c["label"], c["n_core"], c["denom"],
                 c["n_authors"], c["n_adjacent"], json.dumps(c["detail"]),
                 json.dumps({k: {"score": v, "why": c["why"][k]} for k, v in c["scores"].items()}),
                 json.dumps(c["gates"]), inputs["status"], c["status"], c["status_reason"],
                 c.get("score_headline"), c.get("score_with_severity"), c.get("rank_headline"),
                 run.run_id))
        con.executemany("INSERT INTO analysis_weight_sensitivity (variant, candidate_id,"
                        " top_share, draws, pool, run_id) VALUES (?,?,?,?,?,?)", sens)
        con.commit()
        run.n_output = len(cands)
    for c in cands:
        s = c.get("scores") or {}
        print(f"{c['candidate_id']:<7} {c['status']:<13} n={c['n_core']:<3} "
              f"head={c.get('score_headline')} sev={c.get('score_with_severity')} {s}")
    for r in sens:
        print(f"  sensitivity {r[0]:<13} {r[4]:<12} {r[1]:<7} {r[2]:.3f}")
    print(f"inputs: {inputs['status']} · run {run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
