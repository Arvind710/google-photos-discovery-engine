"""T-5 and T-6 — the dual-model check on segmentation (implementationplan.md
task 2.5, evals.md §7). A second, different model (gpt-5) segments a stratified
sample of already-segmented records with the SAME prompt; the two are compared.

T-5  story-count agreement: share of records where both return the same number
     of stories (≥ 80%).
T-6  `reaches_stage` agreement on matched stories (≥ 75%). What `reaches_stage`
     decides is which coding blocks run (C at ≥ 5, D at ≥ 7), so T-6 is
     agreement on that GATING BAND (<5 · 5–6 · ≥7); exact and within-one
     agreement are reported beside it (Docs/decisions.md D-7).

Disagreements on `reaches_stage` RESOLVE UPWARD (EC-SEG-5): where the second
model's value is higher, the stored story takes it. Over-gating costs a few
`not_stated`; under-gating deletes data silently. Every change is listed.

Stories are matched by span overlap: two spans match when their overlap is at
least half of the shorter one.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

from pipeline.common import runs as rmod
from pipeline.segment import stories as seg

ESTIMATE_USD = 0.40


def band(stage: int) -> str:
    return "D" if stage >= 7 else "C" if stage >= 5 else "AB"


def sample(con, n: int, seed: int = 27, *, with_stories: bool = False) -> list[str]:
    """Equal allocation per source (EC-VAL-4), from records Pass 1 has read.
    `with_stories` draws only from records the primary found stories in: three
    in four records hold none, so a mixed sample leaves T-6 with a handful of
    matched stories (8 of 60 records, 2026-09-26)."""
    pool = ("SELECT record_id FROM stories" if with_stories else
            "SELECT record_id FROM stories UNION SELECT record_id FROM exclusions"
            " WHERE stage='segment' AND story_id IS NULL")
    rows = con.execute(f"SELECT r.record_id, r.source FROM records r WHERE r.record_id IN"
                       f" ({pool}) ORDER BY r.record_id").fetchall()
    by: dict[str, list[str]] = defaultdict(list)
    for rid, src in rows:
        by[src].append(rid)
    rng = random.Random(seed)
    per = max(1, n // len(by))
    picked = []
    for _src, ids in sorted(by.items()):
        picked += rng.sample(ids, min(per, len(ids)))
    rest = [i for ids in by.values() for i in ids if i not in set(picked)]
    picked += rng.sample(rest, max(0, n - len(picked)))
    return picked[:n]


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    inter = min(a[1], b[1]) - max(a[0], b[0])
    return inter > 0 and inter >= 0.5 * min(a[1] - a[0], b[1] - b[0])


def main(con, client, *, n: int = 60, with_stories: bool = False) -> int:
    ids = sample(con, n, with_stories=with_stories)
    recs = {r.record_id: r for r in seg.corpus_records(con, ids)}
    # corpus_records excludes records marked at stage `segment`; add those back.
    missing = [i for i in ids if i not in recs]
    if missing:
        q = ",".join("?" * len(missing))
        for r in con.execute("SELECT record_id, source, text_clean, posts_json, author_key,"
                             f" thread_context FROM records WHERE record_id IN ({q})", missing):
            recs[r["record_id"]] = seg.record_from_row(r)
    primary: dict[str, list] = defaultdict(list)
    for s in con.execute("SELECT story_id, record_id, char_start, char_end, reaches_stage, bucket"
                         f" FROM stories WHERE record_id IN ({','.join('?' * len(ids))})", ids):
        primary[s["record_id"]].append(dict(s))

    with rmod.Run(con, "segment-dual", model=seg.SECOND_MODEL, estimate_usd=ESTIMATE_USD,
                  prompt_version=seg.PROMPT_VERSION, effort=seg.EFFORT, n=len(ids),
                  with_stories=with_stories) as run:
        second = seg.run_sync(client, [recs[i] for i in ids], run, model=seg.SECOND_MODEL,
                              effort=seg.EFFORT)
        count_ok, pairs, raised, rows = 0, [], [], []
        for rid in ids:
            p, s2 = primary[rid], second[rid].stories
            count_ok += len(p) == len(s2)
            used = set()
            for ps in p:
                m = next((k for k, t in enumerate(s2) if k not in used and
                          _overlap((ps["char_start"], ps["char_end"]), (t.char_start, t.char_end))),
                         None)
                if m is None:
                    continue
                used.add(m)
                a, b = ps["reaches_stage"], s2[m].reaches_stage
                pairs.append((a, b, ps["bucket"], s2[m].bucket))
                if b > a:                                        # resolve UPWARD
                    con.execute("UPDATE stories SET reaches_stage=? WHERE story_id=?",
                                (b, ps["story_id"]))
                    raised.append({"story_id": ps["story_id"], "from": a, "to": b})
            rows.append({"record_id": rid, "source": recs[rid].source, "primary": len(p),
                         "second": len(s2)})
        con.commit()
        k = len(pairs)
        result = {
            "run_id": run.run_id, "n_records": len(ids), "with_stories": with_stories,
            "T5_count_agreement": count_ok / len(ids),
            "matched_stories": k,
            "T6_band_agreement": sum(band(a) == band(b) for a, b, *_ in pairs) / k if k else None,
            "reaches_exact": sum(a == b for a, b, *_ in pairs) / k if k else None,
            "reaches_within_one": sum(abs(a - b) <= 1 for a, b, *_ in pairs) / k if k else None,
            "bucket_agreement": sum(x == y for *_, x, y in pairs) / k if k else None,
            "raised_upward": raised, "records": rows,
            "usage": {"input": run.input_tokens, "output": run.output_tokens, "usd": run.cost_usd()},
        }
        con.execute("UPDATE runs SET params_json=json_set(params_json,'$.result',json(?))"
                    " WHERE run_id=?", (json.dumps({k2: v for k2, v in result.items()
                                                    if k2 not in ("records", "raised_upward")}
                                                   | {"n_raised": len(raised)}), run.run_id))
        con.commit()
    seg.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (seg.ARTIFACTS / f"segment_dual_{run.run_id}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k2: v for k2, v in result.items() if k2 not in ("records", "raised_upward")},
                     indent=1), f"raised upward: {len(raised)}")
    return 0
