"""P4 gate — Analysis and opportunities (evals.md §9). Built in order: the
cross-tabs, derived analyses and scoring first (this file's tests), then the
recommendation, handoff and pages (P4-INV-1, -6, -7, -8 and P4-MET-3 land with
them).

UNIT tests pin the scoring arithmetic and run in CI; CORPUS tests read the
materialised tables.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

import pytest
import yaml

from pipeline.analyse import derived, opportunity

pytestmark = pytest.mark.p4


# ======================================================================= UNIT
def test_frequency_bands():
    assert [opportunity.frequency_score(n, 100)[0] for n in (4, 5, 10, 15, 25, 60)] == \
        [1, 2, 3, 4, 5, 5]


def test_evidence_strength_rule():
    assert opportunity.evidence_score(7, 0.7)[0] == 5
    assert opportunity.evidence_score(7, 0.5)[0] == 4          # low confidence costs one
    assert opportunity.evidence_score(1, 0.5)[0] == 1          # never below 1


def _c(cid, **s):
    return {"candidate_id": cid, "scores": s}


def test_sensitivity_is_deterministic_and_a_dominant_candidate_always_wins():
    w = {"metric_leverage": 30, "frequency": 20, "evidence_strength": 15, "reach": 10}
    a = _c("a", metric_leverage=5, frequency=5, evidence_strength=3, reach=4)
    b = _c("b", metric_leverage=5, frequency=2, evidence_strength=2, reach=3)
    s = opportunity.sensitivity([a, b], w, tuple(w))
    assert s == opportunity.sensitivity([a, b], w, tuple(w)) and s["a"] == 1.0
    # Crossing candidates split the draws: neither dominates.
    c = _c("c", metric_leverage=2, frequency=5, evidence_strength=5, reach=5)
    d = _c("d", metric_leverage=5, frequency=4, evidence_strength=2, reach=2)
    s2 = opportunity.sensitivity([c, d], w, tuple(w))
    assert 0 < s2["c"] < 1 and abs(s2["c"] + s2["d"] - 1) < 1e-9


def test_headline_score_excludes_severity():
    w = yaml.safe_load(opportunity.SCORING.read_text())["weights"]
    sc = {"metric_leverage": 5, "frequency": 5, "evidence_strength": 5, "reach": 5, "severity": 1}
    assert opportunity.weighted(sc, w, opportunity.HEADLINE) == 5
    assert opportunity.weighted(sc, w, tuple(w)) < 5
    assert "severity" not in opportunity.HEADLINE


def test_P4_INV_3_build_refuses_a_low_reliability_headline_field(blank_db):
    with pytest.raises(AssertionError, match="P4-INV-3"):
        opportunity.build(blank_db, {}, {}, {"primary_stage": "low_reliability"})


def test_js_divergence_bounds():
    p = Counter({"5": 10, "0": 10})
    assert derived.js_divergence(p, p) == pytest.approx(0)
    assert derived.js_divergence(Counter({"5": 1}), Counter({"0": 1})) == pytest.approx(1)


def test_inputs_file_scores_every_failure_stage_candidate_with_reasons():
    inp = yaml.safe_load(opportunity.INPUTS.read_text())
    assert inp["status"] in ("proposed", "approved")
    for cid, spec in inp["candidates"].items():
        for k in ("addressable_by_gp", "ai_necessity", "reach"):
            assert 1 <= spec[k]["score"] <= 5 and spec[k]["why"], (cid, k)
    assert all(1 <= v["score"] <= 5 and v["why"] for v in inp["node_leverage"].values())


# ===================================================================== CORPUS
@pytest.fixture(scope="module")
def con(corpus):
    if corpus.execute("SELECT count(*) FROM analysis_opportunity").fetchone()[0] == 0:
        pytest.skip("no opportunity rows — python -m pipeline.analyse.opportunity")
    return corpus


@pytest.mark.needs_corpus
def test_crosstab_rows_carry_n_denom_authors_and_run_id(con):
    bad = con.execute("SELECT count(*) FROM analysis_crosstab WHERE n > denom OR n < 1 OR"
                      " run_id IS NULL OR n_authors IS NULL").fetchone()[0]
    assert bad == 0
    n = dict(con.execute("SELECT val_a, n FROM analysis_crosstab WHERE"
                         " dim_a='core.primary_stage' AND dim_b='photo_class' AND val_b='_all'"))
    live = dict(con.execute(
        "SELECT p.primary_stage, count(*) FROM story_spine p JOIN stories s USING (story_id)"
        " WHERE s.bucket='core' AND s.story_id NOT IN (SELECT story_id FROM exclusions WHERE"
        " story_id IS NOT NULL) GROUP BY 1"))
    assert n == live


@pytest.mark.needs_corpus
def test_derived_rows_are_counts_over_asked_stories(con):
    assert con.execute("SELECT count(*) FROM analysis_derived WHERE n > denom OR denom < 1"
                       " OR run_id IS NULL").fetchone()[0] == 0
    notes = [r[0] for r in con.execute("SELECT note FROM analysis_derived"
                                       " WHERE metric='cue_remembered'")]
    assert notes and all("low_reliability" in (x or "") for x in notes)   # 2.1 is flagged


@pytest.mark.needs_corpus
def test_P4_INV_2_nothing_ranked_below_the_floor(con):
    assert con.execute("SELECT count(*) FROM analysis_opportunity WHERE rank_headline IS NOT"
                       f" NULL AND n_core < {opportunity.FLOOR}").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM analysis_opportunity WHERE (status='ranked') <>"
                       " (rank_headline IS NOT NULL)").fetchone()[0] == 0


@pytest.mark.needs_corpus
def test_P4_INV_3_headline_score_is_the_reliable_criteria_only(con):
    w = yaml.safe_load(opportunity.SCORING.read_text())["weights"]
    for sc, head in con.execute("SELECT scores_json, score_headline FROM analysis_opportunity"
                                " WHERE score_headline IS NOT NULL"):
        s = {k: v["score"] for k, v in json.loads(sc).items()}
        assert opportunity.weighted(s, w, opportunity.HEADLINE) == pytest.approx(head, abs=1e-3)
    rel = dict(con.execute("SELECT field, verdict FROM analysis_reliability"))
    assert all(rel.get(f) != "low_reliability" for k in opportunity.HEADLINE
               for f in opportunity.CRITERION_FIELDS[k])


@pytest.mark.needs_corpus
def test_P4_INV_4_weights_registered_before_every_ranking_run(con):
    reg = datetime.fromisoformat(yaml.safe_load(opportunity.SCORING.read_text())
                                 ["pre_registered_at"])
    for (started,) in con.execute("SELECT started_at FROM runs WHERE stage='analyse-opportunity'"):
        assert datetime.fromisoformat(started) > reg


@pytest.mark.needs_corpus
def test_P4_INV_5_gated_out_candidates_are_present_with_the_gate_named(con):
    rows = con.execute("SELECT status_reason, gates_json FROM analysis_opportunity"
                       " WHERE status='gated_out'").fetchall()
    for reason, gates in rows:
        failed = [g for g, v in json.loads(gates).items() if not v["passed"]]
        assert failed and all(g in reason for g in failed)


@pytest.mark.needs_corpus
def test_P4_MET_1_sensitivity_reported_for_both_variants(con):
    got = {(v, p) for v, p in con.execute(
        "SELECT DISTINCT variant, pool FROM analysis_weight_sensitivity")}
    ranked = con.execute("SELECT count(*) FROM analysis_opportunity WHERE status='ranked'"
                         ).fetchone()[0]
    want = {("headline", "gates_passed"), ("with_severity", "gates_passed")}
    if ranked:
        want |= {("headline", "ranked"), ("with_severity", "ranked")}
    assert want <= got
    assert all(r[0] == 1000 for r in con.execute(
        "SELECT DISTINCT draws FROM analysis_weight_sensitivity"))


@pytest.mark.needs_corpus
def test_every_scored_candidate_carries_reasons_and_quotes_verified(con):
    ev = {r[0]: r[1] for r in con.execute(
        "SELECT e.span, r.text_clean FROM evidence e JOIN stories s USING (story_id)"
        " JOIN records r USING (record_id) WHERE e.field='primary_stage'")}
    for sc, detail in con.execute("SELECT scores_json, detail_json FROM analysis_opportunity"
                                  " WHERE status <> 'not_a_failure'"):
        assert all(v["why"] for v in json.loads(sc).values())
        for q in json.loads(detail)["quotes"]:
            assert q["span"] in ev and len(q["span"]) >= 15
