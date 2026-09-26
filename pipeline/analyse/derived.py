"""The derived analyses that answer [CTX]'s own questions (architecture.md §5.7,
implementationplan.md task 4.2). Free: no model call. Rebuilds
`analysis_derived` whole.

    cue_remembered / cue_forgotten / cue_wrong   the cue matrix ([CTX] §8.4 view 4):
        per cue family (who, what, where, when, …), the stories that recalled
        it (2.1), forgot it (2.4, mapped to a family) or were certain and
        WRONG about it (2.2 accuracy = certain_wrong). 2.1 is
        `low_reliability` (κ/Jaccard 0.56): every row says so in `note`, and
        the cue matrix is never a headline claim or a score input (P4-INV-3).
    certain_wrong          any cue certain-but-wrong — the direct evidence for 5.3
    results_as_cues        6.5 answered with something other than `nothing`
    anchor_and_pivot       6.7 any action on a near-hit, or 7.2 / 9.1 anchor_and_pivot
    workaround             spine `workaround` = 1; 9.4 fallback:*; 10.2 any habit
    js_divergence          Jensen–Shannon divergence of each source's primary-stage
                           distribution from the pooled one (sources with ≥ 10
                           stories) — does a pattern hold across sources, or is it
                           one community's artefact ([CTX] §8.4 view 13)

Denominators are the stories ASKED the question (core: every core story is
asked every question). Rates are stored as value = n / denom for convenience;
views still render them through `share()`.

    python -m pipeline.analyse.derived
"""

from __future__ import annotations

import math
from collections import Counter

from pipeline.analyse import crosstabs as xt
from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

FAMILIES = ("who", "what", "where", "when", "event", "perceptual", "meaning", "capture",
            "source", "library_position")
# 2.4 "what is missing" values → the 2.1 cue family they are the absence of.
FORGOTTEN_FAMILY = {"date_or_year": "when", "exact_place_or_venue_name": "where",
                    "album": "library_position", "whose_phone_took_it": "who",
                    "word_for_the_thing": "what", "what_else_in_frame": "what",
                    "photo_video_or_screenshot": "what", "which_app_or_account": "source"}
MIN_JS = 10


def _authors(ids: set[str], spine: dict) -> int:
    return len({spine[x]["author_key"] for x in ids} - {None})


def _row(metric, key, pop, ids, denom_ids, spine, note=None):
    ids = ids & denom_ids
    return (metric, key, pop, (len(ids) / len(denom_ids)) if denom_ids else None, len(ids),
            len(denom_ids), _authors(ids, spine), note)


def js_divergence(p: Counter, q: Counter) -> float:
    """Jensen–Shannon divergence, base 2, in [0, 1]."""
    keys = set(p) | set(q)
    sp, sq = sum(p.values()), sum(q.values())
    P = {k: p[k] / sp for k in keys}
    Q = {k: q[k] / sq for k in keys}
    M = {k: (P[k] + Q[k]) / 2 for k in keys}

    def kl(a):
        return sum(a[k] * math.log2(a[k] / M[k]) for k in keys if a[k] > 0)
    return (kl(P) + kl(Q)) / 2


def rows(spine: dict, codes: dict, rel: dict[str, str]) -> list[tuple]:
    out = []
    low = {f for f, v in rel.items() if v == "low_reliability"}
    for pop in xt.POPULATIONS:
        members = {sid for sid, s in spine.items() if s["population"] == pop}

        def asked(q, members=members):
            return set().union(*codes.get(q, {}).values()) & members if codes.get(q) else set()

        def with_values(q, pred, members=members):
            return {sid for v, ids in codes.get(q, {}).items() if pred(v) for sid in ids} & members

        # ---- cue matrix
        a21, a24 = asked("2.1"), asked("2.4")
        note21 = "rests on 2.1, low_reliability" if "q:2.1" in low else None
        for fam in FAMILIES:
            out.append(_row("cue_remembered", fam, pop,
                            with_values("2.1", lambda v, f=fam: v.split(":")[0] == f), a21, spine,
                            note21))
            out.append(_row("cue_forgotten", fam, pop,
                            with_values("2.4", lambda v, f=fam: FORGOTTEN_FAMILY.get(v) == f), a24,
                            spine))
        # ---- 6.5 / 6.7 / 7.2 / 9.1
        out.append(_row("results_as_cues", "_all", pop,
                        with_values("6.5", lambda v: v not in ("not_stated", "nothing")),
                        asked("6.5"), spine))
        pivot = (with_values("6.7", lambda v: v not in ("not_stated", "ignore_it"))
                 | with_values("7.2", lambda v: v == "anchor_and_pivot")
                 | with_values("9.1", lambda v: v == "path:anchor_and_pivot"))
        out.append(_row("anchor_and_pivot", "_all", pop, pivot, members, spine))
        # ---- workarounds
        wk = {sid for sid in members if spine[sid].get("workaround")}
        out.append(_row("workaround", "_all", pop, wk, members, spine))
        for v in sorted({v for v in codes.get("9.4", {}) if v.startswith("fallback:")}):
            out.append(_row("fallback", v.split(":", 1)[1], pop,
                            with_values("9.4", lambda x, v=v: x == v), asked("9.4"), spine))
        out.append(_row("preventive_habit", "_all", pop,
                        with_values("10.2", lambda v: v != "not_stated"), asked("10.2"), spine))
        # ---- source divergence on primary_stage
        pooled = Counter(spine[s]["primary_stage"] for s in members)
        for src in sorted({spine[s]["source"] for s in members}):
            ids = {s for s in members if spine[s]["source"] == src}
            if len(ids) >= MIN_JS:
                d = js_divergence(Counter(spine[s]["primary_stage"] for s in ids), pooled)
                out.append(("js_divergence", src, pop, round(d, 4), len(ids), len(members),
                            _authors(ids, spine), "primary_stage vs pooled, base 2"))
    return out


def certain_wrong_rows(con, spine: dict) -> list[tuple]:
    """2.2 is stored as cue (value) + judgement (accuracy), D-9."""
    out = []
    for pop in xt.POPULATIONS:
        members = {sid for sid, s in spine.items() if s["population"] == pop}
        asked, wrong, fam_wrong = set(), set(), {f: set() for f in FAMILIES}
        for r in con.execute("SELECT story_id, value, accuracy FROM story_codes"
                             " WHERE question='2.2'"):
            if r["story_id"] not in members:
                continue
            asked.add(r["story_id"])
            if r["accuracy"] == "certain_wrong":
                wrong.add(r["story_id"])
                fam = r["value"].split(":")[0]
                if fam in fam_wrong:
                    fam_wrong[fam].add(r["story_id"])
        out.append(_row("certain_wrong", "_all", pop, wrong, asked, spine))
        out += [_row("cue_wrong", f, pop, ids, asked, spine) for f, ids in fam_wrong.items()]
    return out


def main() -> int:
    con = dbm.init()
    cb = cbm.load()
    with rmod.Run(con, "analyse-derived", model=None, estimate_usd=0,
                  codebook_version=cb.version_string) as run:
        spine, codes = xt.load(con)
        for sid, (wk,) in ((r[0], r[1:]) for r in con.execute(
                "SELECT story_id, workaround FROM story_spine")):
            if sid in spine:
                spine[sid]["workaround"] = wk
        rel = {r[0]: r[1] for r in con.execute("SELECT field, verdict FROM analysis_reliability")}
        rs = [r for r in rows(spine, codes, rel) + certain_wrong_rows(con, spine) if r[5]]
        con.execute("DELETE FROM analysis_derived")
        con.executemany("INSERT INTO analysis_derived (metric, key, population, value, n, denom,"
                        " n_authors, note, run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        [(*r, run.run_id) for r in rs])
        con.commit()
        run.n_output = len(rs)
    print(f"{len(rs)} derived rows · run {run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
