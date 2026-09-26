"""The facts pack — the ONLY evidence the recommendation and the Part 3 handoff
may cite (architecture.md §6: "generated from the analysis tables, never from
raw stories"; P4-INV-6: every claim cites an analysis_* row that exists).

Each fact is built deterministically from one materialised row and carries
where it came from:

    {"id": "F07", "text": "…", "table": "analysis_crosstab",
     "where": {"dim_a": "core.primary_stage", "dim_b": "photo_class", …}}

so a test can re-select the row. Numbers the model writes must appear in the
text of a fact it cites (recommendation.check_numbers). Low-reliability fields
are named as such inside the fact text.
"""

from __future__ import annotations

import json
from collections import Counter

import yaml

from pipeline.common import codebook as cbm

STAGE_NAME = {"0": "library state (the photo was never there or was gone)",
              "1": "trigger and intent", "2": "memory — could not remember enough",
              "3": "strategy — where and how they looked", "4": "articulation — could not put it"
              " into words", "5": "search did not understand or match the cue",
              "6": "recognition — hard to spot in the results", "7": "recovery after a miss",
              "8": "persistence", "9": "outcome — nothing went wrong", "10": "aftermath"}


class Pack:
    def __init__(self) -> None:
        self.facts: list[dict] = []

    def add(self, text: str, table: str, where: dict) -> str:
        fid = f"F{len(self.facts) + 1:02d}"
        self.facts.append({"id": fid, "text": text, "table": table, "where": where})
        return fid


def share_words(n: int, d: int) -> str:
    """Counts first; a percentage only at or above the floor of 30 ([CTX] §15.5)."""
    return f"{n} of {d}" + (f" ({round(100 * n / d)}%)" if d >= 30 else "")


def build(con, cb: cbm.Codebook) -> Pack:
    p = Pack()
    f = {r["step"]: r for r in con.execute(
        "SELECT step, n, n_authors FROM analysis_funnel WHERE source='_all'")}
    p.add(f"{f['collected']['n']} public records were read; {f['stories']['n']} are retrieval "
          f"stories from {f['stories']['n_authors']} people; {f['stories:core']['n']} are core "
          f"(a known photo, vaguely remembered) from {f['stories:core']['n_authors']} people, and "
          f"{f['stories:adjacent']['n']} adjacent. The engine was designed for at least 300 core "
          "stories; every share is of coded public stories, never a retrieval success rate, a share"
          " of users or a share of searches.", "analysis_funnel",
          {"step": "stories:core", "source": "_all"})
    # --- where it breaks, and for whom
    for r in con.execute("SELECT val_a, n, denom, n_authors FROM analysis_crosstab WHERE"
                         " dim_a='core.primary_stage' AND dim_b='photo_class' AND val_b='_all'"
                         " ORDER BY n DESC"):
        seg = {x["val_b"]: x["n"] for x in con.execute(
            "SELECT val_b, n FROM analysis_crosstab WHERE dim_a='core.primary_stage' AND"
            " dim_b='photo_class' AND val_a=? AND val_b<>'_all'", (r["val_a"],))}
        p.add(f"Core stories whose FIRST failure is Stage {r['val_a']} ({STAGE_NAME[r['val_a']]}):"
              f" {share_words(r['n'], r['denom'])}, from {r['n_authors']} people. By photo type: "
              + ", ".join(f"{k} {v}" for k, v in sorted(seg.items(), key=lambda kv: -kv[1]))
              + ".", "analysis_crosstab", {"dim_a": "core.primary_stage", "val_a": r["val_a"],
                                            "dim_b": "photo_class", "val_b": "_all"})
    pc = {r["val_a"]: r for r in con.execute(
        "SELECT val_a, n, denom FROM analysis_crosstab WHERE dim_a='core.photo_class'"
        " AND val_b='_all'")}
    p.add("Core stories by photo type: " + ", ".join(
        f"{k} {share_words(v['n'], v['denom'])}" for k, v in
        sorted(pc.items(), key=lambda kv: -kv[1]["n"])) + ". 'unclear' means the story does not"
          " say why the photo was kept.", "analysis_crosstab",
          {"dim_a": "core.photo_class", "val_b": "_all"})
    adj0 = con.execute("SELECT n, denom FROM analysis_crosstab WHERE dim_a='adjacent.primary_stage'"
                       " AND val_a='0' AND dim_b='photo_class' AND val_b='_all'").fetchone()
    p.add(f"Among adjacent stories, {share_words(adj0['n'], adj0['denom'])} first fail at Stage 0:"
          " the photo was deleted, never backed up or elsewhere. Most public talk about not "
          "finding a photo is about photos that are gone, not vaguely remembered.",
          "analysis_crosstab", {"dim_a": "adjacent.primary_stage", "val_a": "0",
                                "dim_b": "photo_class", "val_b": "_all"})
    for q, label in (("5.6", "what search showed them"), ("3.2", "how they looked inside Google"
                                                          " Photos"), ("4.1", "first query shape")):
        rows = con.execute("SELECT val_a, n, denom FROM analysis_crosstab WHERE dim_a=? AND"
                           " dim_b='photo_class' AND val_b='_all' ORDER BY n DESC LIMIT 5",
                           (f"core.q:{q}",)).fetchall()
        if rows:
            p.add(f"Question {q} ({label}), core stories that answered it, of {rows[0]['denom']}"
                  " asked: " + ", ".join(f"{r['val_a']} {r['n']}" for r in rows) + ".",
                  "analysis_crosstab", {"dim_a": f"core.q:{q}", "dim_b": "photo_class",
                                        "val_b": "_all"})
    # --- memory and the solution's hypotheses
    d = {(r["metric"], r["key"]): r for r in con.execute(
        "SELECT * FROM analysis_derived WHERE population='core'")}
    for (m, k), words in ((("cue_remembered", "what"), "remember WHAT was in the photo"),
                          (("cue_remembered", "when"), "remember WHEN it was taken"),
                          (("cue_forgotten", "when"), "say they forgot the date or year"),
                          (("certain_wrong", "_all"), "reveal a cue they were certain of and "
                                                      "later found WRONG (2.2)"),
                          (("results_as_cues", "_all"), "say the results reminded them of "
                                                        "something new (6.5)"),
                          (("anchor_and_pivot", "_all"), "used a near-hit to reach the target"
                                                         " (anchor and pivot)"),
                          (("workaround", "_all"), "used a workaround outside search")):
        r = d[(m, k)]
        note = f" [{r['note']}]" if r["note"] else ""
        p.add(f"Core stories that {words}: {share_words(r['n'], r['denom'])}.{note}",
              "analysis_derived", {"metric": m, "key": k, "population": "core"})
    # --- reliability and coverage
    rel = {r["field"]: r for r in con.execute("SELECT * FROM analysis_reliability")}
    ps = rel["primary_stage"]
    p.add(f"A second model re-coded {ps['n']} stories: on the primary stage the two agree in "
          f"{share_words(round(ps['raw_agreement'] * ps['n']), ps['n'])} stories, kappa "
          f"{ps['value']:.2f} (ok). Low-reliability "
          "fields, barred from headlines and scores: " + ", ".join(sorted(
              f for f, r in rel.items() if r["verdict"] == "low_reliability")) + ". Agreement is "
          "consistency, not correctness.", "analysis_reliability", {"field": "primary_stage"})
    reg = [r["question"] for r in con.execute(
        "SELECT question FROM analysis_coverage WHERE source='_all' AND disposition='register'")]
    p.add(f"{len(reg)} of 60 codebook questions are answered by too few public stories (over 85% "
          "not stated) and go to the interviews: " + ", ".join(sorted(
              reg, key=lambda q: tuple(map(int, q.split("."))))) + ".", "analysis_coverage",
          {"source": "_all", "disposition": "register"})
    # --- the metric decomposition each candidate maps to ([SOL-METRIC])
    from pipeline.classify import blocks as B
    nodes = cb.metric_nodes
    formula = " ".join(yaml.safe_load((cbm.CODEBOOK_DIR / "metric_nodes_v1.yaml").read_text())
                       ["formula"].split())
    p.add(f"The goal metric decomposes as: {formula} Each candidate is a stage, and each stage "
          "drags down one factor: " + "; ".join(
              f"Stage {st} → {B.metric_node(st, {}, 'not_stated')} ({nodes[B.metric_node(st, {}, 'not_stated')]['label']})"
              for st in ("0", "2", "3", "5", "6")) + ". Improving a factor raises retrieval "
          "success for users; it does not change any share of public stories, which only "
          "describes what people wrote.", "analysis_opportunity", {})
    # --- the opportunities
    for r in con.execute("SELECT * FROM analysis_opportunity ORDER BY n_core DESC"):
        det = json.loads(r["detail_json"])
        if r["status"] == "not_a_failure":
            continue
        sc = json.loads(r["scores_json"])
        gates = json.loads(r["gates_json"])
        p.add(f"Opportunity candidate {r['candidate_id']} — {r['label']}: {r['n_core']} core "
              f"stories from {r['n_authors']} people ({r['n_adjacent']} adjacent at the same "
              f"stage); status {r['status']} ({r['status_reason']}). Gates: " + "; ".join(
                  f"{g} {v['score']}" for g, v in gates.items()) + ". Scores: " + "; ".join(
                  f"{k} {v['score']}" for k, v in sc.items()) + f". Headline score "
              f"{r['score_headline']}" + (f", rank {r['rank_headline']}" if r["rank_headline"]
                                         else "") + ". Photo types: " + ", ".join(
                  f"{k} {v}" for k, v in det["photo_class"].items()) + ". Stated failure modes: "
              + (", ".join(f"{k} ({v})" for k, v in det["failure_modes"].items()) or "none")
              + ". Sources: " + ", ".join(f"{k} {v}" for k, v in det["sources"].items()) + ".",
              "analysis_opportunity", {"candidate_id": r["candidate_id"]})
        for q in det["quotes"][:3]:
            p.add(f"Quote from a {r['candidate_id']} story ({q['source']}, {q['story_id']}): "
                  f"\"{q['span']}\"", "analysis_opportunity", {"candidate_id": r["candidate_id"]})
    for r in con.execute("SELECT * FROM analysis_weight_sensitivity WHERE variant='headline'"
                         " AND pool='gates_passed' ORDER BY top_share DESC LIMIT 1"):
        p.add(f"Weight sensitivity: over {r['draws']} draws moving each pre-registered weight by up"
              f" to 10 points, {r['candidate_id']} ranks first in {share_words(round(r['top_share'] * r['draws']), r['draws'])} "
              "of draws, even counting candidates below the evidence floor; with severity "
              "(low reliability) added back it is unchanged.", "analysis_weight_sensitivity",
              {"variant": "headline", "candidate_id": r["candidate_id"], "pool": "gates_passed"})
    # --- emergent themes (counts only, never ranked, D-10)
    themes = yaml.safe_load((cbm.CODEBOOK_DIR / "emergent_themes_v1.yaml").read_text())["themes"]
    got = Counter(r[0] for r in con.execute("SELECT theme FROM story_themes"))
    p.add("Emerging themes found after the codebook (counts only, not ranked): " + "; ".join(
        f"{v['label']} {got.get(k, 0)}" for k, v in themes.items()) + ".", "story_themes", {})
    return p


def row_exists(con, fact: dict) -> bool:
    w = fact["where"]
    sql = f"SELECT count(*) FROM {fact['table']}" + (
        " WHERE " + " AND ".join(f"{k} = ?" for k in w) if w else "")
    return con.execute(sql, tuple(w.values())).fetchone()[0] > 0
