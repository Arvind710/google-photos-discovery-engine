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


# ============================================================ recommendation
def _pack():
    from pipeline.synthesise import facts
    p = facts.Pack()
    p.add("Stage 5: 36 of 115 core stories (31%).", "analysis_crosstab", {})
    p.add("Headline score 4.467, rank 1.", "analysis_opportunity", {})
    return p


def _rec(**over):
    s = {"text": "Search misses the cue in 36 of 115 core stories.", "cites": ["F01"]}
    out = {"top": {"candidate_id": "stage5", "problem_statement": s,
                   "chain": [dict(s, step=k) for k in ("metric_node", "evidence", "stage",
                                                       "root_cause")]},
           "runner_up": {"candidate_id": "stage2", "why_not_top": s},
           "target_segment": {"direction": "sentimental", "why": s},
           "root_cause_hypothesis": s, "intelligence_needed": s,
           "falsifiers": [s], "caveats": [s]}
    out.update(over)
    return out


def test_recommendation_checker_passes_a_clean_answer(codebook):
    from pipeline.synthesise import recommendation as R
    assert R.check(_rec(), _pack(), codebook, top_id="stage5",
                   candidates={"stage5", "stage2"}) == []


@pytest.mark.parametrize("bad, why", [
    ({"caveats": [{"text": "It is 42 of 115.", "cites": ["F01"]}]}, "number 42"),
    ({"caveats": [{"text": "Stage 5 dominates.", "cites": ["F99"]}]}, "unknown facts"),
    ({"caveats": [{"text": "Stage 5 dominates.", "cites": []}]}, "cites no fact"),
    ({"caveats": [{"text": "31% of users fail at Stage 5.", "cites": ["F01"]}]},
     "users/searches"),
    ({"falsifiers": []}, "P4-INV-7"),
    ({"runner_up": {"candidate_id": "stage5", "why_not_top": {"text": "x", "cites": ["F01"]}}},
     "runner_up"),
])
def test_recommendation_checker_catches(codebook, bad, why):
    from pipeline.synthesise import recommendation as R
    probs = R.check(_rec(**bad), _pack(), codebook, top_id="stage5",
                    candidates={"stage5", "stage2"})
    assert any(why in p for p in probs), probs


def test_recommendation_checker_refuses_a_different_top(codebook):
    from pipeline.synthesise import recommendation as R
    assert any("ranking's first" in p for p in R.check(
        _rec(), _pack(), codebook, top_id="stage2", candidates={"stage5", "stage2"}))


def test_handoff_checker_requires_every_register_question(codebook):
    from pipeline.synthesise import handoff as H
    s = {"text": "Ask about a recent attempt.", "cites": ["F01"]}
    out = {"hypotheses": [dict(s, test_how="t")] * 3, "screener": [dict(s, criterion="c")] * 3,
           "interview_prompts": [{"question_id": "8.1", "stage": "8", "prompt": "How long?"}],
           "observed_tasks": [{"story_id": "a", "task": "t", "watch_for": "w"}] * 4,
           "theme_probes": [{"theme": "x", "prompt": "p"}]}
    reg = [{"question_id": "8.1"}, {"question_id": "6.2"}]
    probs = H.check(out, _pack(), codebook, reg, {"a"}, {"x"})
    assert any("6.2" in p for p in probs) and len(probs) == 1


@pytest.fixture(scope="module")
def synth(corpus):
    rows = {r[0]: r for r in corpus.execute("SELECT kind, content_json, facts_json, checks_json"
                                            " FROM analysis_synthesis")}
    if not rows:
        pytest.skip("no synthesis yet — python -m pipeline.synthesise.recommendation")
    return rows


@pytest.mark.needs_corpus
def test_P4_INV_6_every_claim_cites_a_fact_whose_row_exists(corpus, synth):
    from pipeline.synthesise import facts
    from pipeline.synthesise import recommendation as R
    for kind, content, facts_json, _ in synth.values():
        fs = {f["id"]: f for f in json.loads(facts_json)}
        assert all(facts.row_exists(corpus, f) for f in fs.values()), kind
        for path, s in R.statements(json.loads(content)):
            assert s["cites"] and all(c in fs for c in s["cites"]), (kind, path)


@pytest.mark.needs_corpus
def test_P4_INV_7_recommendation_has_a_falsifier_and_the_ranked_top(corpus, synth):
    rec = json.loads(synth["recommendation"][1])
    assert [f for f in rec["falsifiers"] if f["text"].strip()]
    top = corpus.execute("SELECT candidate_id FROM analysis_opportunity WHERE rank_headline=1"
                         ).fetchone()[0]
    assert rec["top"]["candidate_id"] == top and "hypothesis" in rec["label"]


@pytest.mark.needs_corpus
def test_P4_MET_3_handoff_built_from_the_coverage_register(corpus, synth):
    assert "handoff" in synth, "python -m pipeline.synthesise.handoff"
    h = json.loads(synth["handoff"][1])
    reg = {r[0] for r in corpus.execute("SELECT question FROM analysis_coverage WHERE"
                                        " source='_all' AND disposition='register'")}
    assert {p["question_id"] for p in h["interview_prompts"]} >= reg
    live = {r[0] for r in corpus.execute("SELECT story_id FROM stories WHERE story_id NOT IN"
                                         " (SELECT story_id FROM exclusions WHERE story_id IS"
                                         " NOT NULL)")}
    assert h["observed_tasks"] and all(t["story_id"] in live for t in h["observed_tasks"])


def test_recommendation_checker_refuses_moving_a_share_and_a_gated_runner_up(codebook):
    from pipeline.synthesise import recommendation as R
    bad = _rec(caveats=[{"text": "Fixing it would raise the share of coded public stories.",
                         "cites": ["F01"]}])
    assert any("outcome to move" in p for p in R.check(
        bad, _pack(), codebook, top_id="stage5", candidates={"stage5", "stage2"}))
    ru = _rec(runner_up={"candidate_id": "stage0", "why_not_top": {"text": "x", "cites": ["F01"]}})
    assert any("does not pass both gates" in p for p in R.check(
        ru, _pack(), codebook, top_id="stage5", candidates={"stage5", "stage0", "stage2"},
        runner_ok={"stage2"}))


# ====================================================================== pages
import re  # noqa: E402
from pathlib import Path  # noqa: E402

VIEWS = Path(__file__).resolve().parents[1] / "app" / "views"


@pytest.mark.parametrize("page", ["analysis.py", "opportunities.py"])
def test_P4_INV_1_pages_format_no_share_themselves(page):
    """Every share through lib.evidence.share(): no view builds a percentage."""
    src = (VIEWS / page).read_text()
    assert not re.search(r":\.\d*%|\{[^}]*%\}|\* ?100\b", src), page
    assert "share(" in src


def test_opportunities_escapes_model_and_user_text():
    """Recommendation text comes from a model and quotes from users: both are
    escaped before st.html (fmt → html.escape; ui.quote escapes the span)."""
    src = (VIEWS / "opportunities.py").read_text()
    for field in (r"\['text'\]", r"\['label'\]", r"\['prompt'\]", r"\['task'\]"):
        uses = re.findall(rf"\{{[^{{}}]*{field}[^{{}}]*\}}", src)
        assert uses and all("fmt(" in u for u in uses), (field, uses)
    ui = (VIEWS.parent / "lib" / "ui.py").read_text()
    assert "esc(span)" in ui


def test_P4_INV_8_crosstabs_are_two_dimensional_only():
    """Headline claims use at most two dimensions: the cross-tab has exactly
    one row dimension and one segment dimension, and no view joins a third."""
    for page in ("analysis.py", "opportunities.py"):
        src = (VIEWS / page).read_text()
        assert src.count("JOIN") == 0, page


def test_pages_are_in_the_nav_and_no_longer_planned():
    from lib import nav
    files = [p[0] for p in nav.PAGES]
    assert {"analysis.py", "opportunities.py"} <= set(files)
    assert not {"Analysis", "Opportunities"} & {t for t, _ in nav.PLANNED}


@pytest.mark.needs_corpus
@pytest.mark.parametrize("page, title", [("analysis.py", "Analysis"),
                                         ("opportunities.py", "Opportunities")])
def test_pages_render_without_exception(corpus, page, title):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(VIEWS / page), default_timeout=60).run()
    assert not at.exception, at.exception
    assert at.title and at.title[0].value == title


@pytest.mark.needs_corpus
def test_analysis_headline_names_a_failure_stage_not_stage_9(corpus):
    """Found live 2026-09-26: after the D-11 re-code Stage 9 ("nothing went wrong")
    is the largest bar, and PART 1 named it as where stories go wrong."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(VIEWS / "analysis.py"), default_timeout=60).run()
    src = (VIEWS / "analysis.py").read_text()
    assert not at.exception and 'NOT_FAILURE = ("1", "9", "10")' in src
    assert '~stage["val_a"].isin(NOT_FAILURE)' in src


def test_recommendation_checker_refuses_a_percentage_without_its_denominator(codebook):
    from pipeline.synthesise import recommendation as R
    ok = _rec(caveats=[{"text": "Stage 5 is 36 of 115 (31%).", "cites": ["F01"]}])
    bad = _rec(caveats=[{"text": "Stage 5 is 31% of core.", "cites": ["F01"]}])
    kw = dict(top_id="stage5", candidates={"stage5", "stage2"})
    assert R.check(ok, _pack(), codebook, **kw) == []
    assert any("no 'n of N'" in p for p in R.check(bad, _pack(), codebook, **kw))


def test_the_kind_of_photo_table_has_its_columns():
    """2026-09-27, the PM: "is part 2 in Analysis correctly shown?" — it was not: the
    per-kind totals were read under the wrong grouping and the table had no columns."""
    import sqlite3
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    src = (root / "app" / "views" / "analysis.py").read_text()
    assert 'rows("core.photo_class", "_all", "_all")' in src
    con = sqlite3.connect(f"file:{root / 'data' / 'corpus.db'}?mode=ro", uri=True)
    n = con.execute("SELECT count(*) FROM analysis_crosstab WHERE dim_a='core.photo_class' "
                    "AND dim_b='_all' AND val_b='_all'").fetchone()[0]
    assert n >= 3
