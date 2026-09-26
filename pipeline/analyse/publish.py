"""Publish the corpus: pin the run the app serves (EC-OPS-11, X-3, schema A.8)
and materialise the Methodology page's figures (schema A.15). Free.

The app COMPUTES NOTHING and reads no artifact file for a figure: what the
How it works page shows beyond the other analysis tables — the lexicon with its
hit counts ([CTX] §6.2), the blind read, the adjudication, the fixture scores,
the ten stories of the sanity strip ([CTX] §15.7), the stated limitations — is
written here into `analysis_methodology`.

The published row pins a `publish-…` run whose MANIFEST lists every analysis
table's run id(s) at this moment. A table rebuilt after publishing no longer
matches the manifest, and `evals/test_p6_release.py` fails until the corpus is
re-published — so the stamp in the footer can never describe a corpus the
pages are not showing.

    python -m pipeline.analyse.publish
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml

from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data" / "artifacts"
CORPUS_VERSION = "v1.0"
SANITY_N, SANITY_SEED = 10, 32
LIVE = "s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)"
# Every table the pages or Ask AI read. Each must carry run_id (P3-INV-10).
TABLES = ("analysis_funnel", "analysis_sources", "analysis_coverage", "analysis_reliability",
          "analysis_crosstab", "analysis_derived", "analysis_opportunity",
          "analysis_weight_sensitivity", "analysis_synthesis", "analysis_method_flags")


def _latest(prefix: str, **match) -> tuple[str, dict]:
    for p in sorted(ART.glob(f"{prefix}_*.json"), reverse=True):
        d = json.loads(p.read_text())
        if all(d.get(k) == v for k, v in match.items()):
            return p.name, d
    raise SystemExit(f"no {prefix} artifact matching {match}")


def manifest(con) -> dict[str, list[str]]:
    return {t: sorted(r[0] for r in con.execute(f"SELECT DISTINCT run_id FROM {t}"))
            for t in TABLES}


def methodology(con, cb) -> dict[str, object]:
    lex = yaml.safe_load((ROOT / "codebook" / "lexicon_v1.yaml").read_text())["terms"]
    hits = json.loads((ART / "lexicon_hits.json").read_text())["terms"]
    lexicon = [{"group": g, "term": t["term"], "hits": t["hits"],
                "kept": hits[t["term"]]["kept"], "core_stories": hits[t["term"]]["core_stories"]}
               for g, terms in lex.items() for t in terms]
    bn, b = _latest("blind_read")
    an, a = _latest("adjudication")
    from pipeline.classify import blocks as B
    fn, f = _latest("code_fixtures", prompt_version=B.PROMPT_VERSION)
    sn, sg = _latest("segment_fixtures", pipeline="find+confirm")
    ev = con.execute("SELECT count(*), min(length(span)) FROM evidence").fetchone()
    core = [r[0] for r in con.execute(
        "SELECT p.story_id FROM story_spine p JOIN stories s USING (story_id)"
        f" WHERE s.bucket='core' AND {LIVE} ORDER BY p.story_id")]
    lim = yaml.safe_load((ROOT / "evals" / "limitations.yaml").read_text())
    return {
        "lexicon": lexicon,
        "blind_read": {"n": b["n"], "stage_agreement": b["stage_agreement"], "artifact": bn},
        "adjudication": {"disputed": a["disputed_stories"],
                         **{k: a["upheld"].get(k, 0) for k in ("primary", "secondary",
                                                              "neither")}, "artifact": an},
        "spans": {"n": ev[0], "min_len": ev[1]},
        "coding_fixtures": {"n": f["summary"]["n"], "primary_stage": f["summary"]["T8_primary_stage"],
                            "triple": f["summary"]["P3_MET_2_triple_question"],
                            "stage2_vs_4": f["summary"]["P3_MET_3_stage2_vs_4"], "artifact": fn},
        "segment_fixtures": {"story_counts_exact": sg["summary"]["P2_MET_3_count_exact"],
                             "bucket_boundary": sg["summary"]["T9_bucket_boundary"],
                             "artifact": sn},
        # [CTX] §15.7: "10 randomly chosen coded stories" — seeded, so the page is stable.
        "sanity_strip": random.Random(SANITY_SEED).sample(core, SANITY_N),
        "limitations": [{"id": k, "threshold": v["threshold"], "measured": v["measured"],
                         "mitigation": " ".join(str(v["mitigation"]).split())}
                        for k, v in lim.items()],
        "codebook": {"version": cb.version_string, "frozen_at": cb.frozen["frozen_at"],
                     "questions": len(cb.questions)},
        "spend": {"openai_recorded_usd": round(rmod.committed_spend(con), 2),
                  "openai_budget_usd": rmod.CEILING_USD},
    }


def main() -> int:
    con = dbm.init()
    cb = cbm.load()
    f = {r["step"]: r for r in con.execute(
        "SELECT step, n, n_authors FROM analysis_funnel WHERE source='_all'")}
    lo, hi = con.execute("SELECT min(substr(collected_at,1,10)), max(substr(collected_at,1,10))"
                         " FROM records").fetchone()
    stamp = (f"Corpus {CORPUS_VERSION} — {f['stories:core']['n']} core stories from "
             f"{f['stories:core']['n_authors']} people, in {f['collected']['n']:,} public records "
             f"collected {lo} to {hi} · codebook {cb.version_string}")
    with rmod.Run(con, "publish", model=None, estimate_usd=0, corpus_version=CORPUS_VERSION,
                  codebook_version=cb.version_string) as run:
        rows = methodology(con, cb)
        rows["manifest"] = manifest(con)
        con.execute("DELETE FROM analysis_methodology")
        con.executemany("INSERT INTO analysis_methodology (key, value_json, run_id) VALUES (?,?,?)",
                        [(k, json.dumps(v, ensure_ascii=False), run.run_id) for k, v in rows.items()])
        con.execute("INSERT OR REPLACE INTO published (singleton, run_id, corpus_version,"
                    " published_at) VALUES (1, ?, ?, ?)", (run.run_id, stamp, rmod._now()))
        con.commit()
        run.n_output = len(rows)
    print(stamp)
    print(f"published {run.run_id} · {len(rows)} methodology keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
