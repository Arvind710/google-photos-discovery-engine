"""P3 gate — Coding and reliability (evals.md §8).

UNIT tests pin the deterministic half of Pass 2 and run in CI: quotes located
verbatim in text_clean or dropped, the fixed rules for failure_owner,
metric_node, severity and 10.3, 2.2 stored as cue + accuracy, block gating, κ
and its verdicts, coverage. CORPUS tests (`needs_corpus`) check the stored
codes and read the measured metrics from the committed artifacts.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from evals.test_p2_segmentation import met_or_limitation
from pipeline.classify import blocks as B
from pipeline.validate import agreement, spans

pytestmark = pytest.mark.p3

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "artifacts"


# ======================================================================= UNIT
def test_spans_are_exact_slices_within_regions_and_at_least_15_chars():
    text = "Other person: I found it.\n\nI searched ‘cafe goa’   and it showed nothing at all."
    reg = [(27, len(text))]
    got = spans.find(text, "I searched 'cafe goa' and it showed nothing", reg)
    assert got == "I searched ‘cafe goa’   and it showed nothing" and got in text
    assert spans.find(text, "Other person: I found it", reg) is None      # outside the story
    assert spans.find(text, "nothing at all", reg) is None                  # < 15 chars (T-3)
    assert spans.find(text, "I searched cafe goa and it showed nothing", reg) is None


def test_block_gating():
    assert B.blocks_for("core", 2) == ("A", "B", "C", "D", "R")
    assert B.blocks_for("adjacent", 4) == ("A",)
    assert B.blocks_for("adjacent", 5) == ("A", "C")
    assert B.blocks_for("adjacent", 9) == ("A", "C", "D")


@pytest.mark.parametrize("stage, codes, outcome, node", [
    ("0", {}, "not_stated", "target_retrievable"),
    ("2", {}, "not_stated", "query_captures_usable_cue"),
    ("3", {}, "abandoned_without_fallback", "enters_gp_retrieval_path"),
    ("4", {}, "found", "query_captures_usable_cue"),
    ("5", {"5.4": ["not_stated"]}, "found", "query_captures_usable_cue"),
    ("5", {"5.4": ["buried_below_fold"]}, "found", "target_ranked_visible"),
    ("6", {}, "found", "user_recognises_target"),
    ("7", {"7.2": ["rephrase_synonyms"]}, "found_after_struggle", "found_after_refinement"),
    ("7", {"7.2": ["quit"]}, "abandoned_without_fallback", "refines_instead_of_quitting"),
    ("8", {"7.2": ["switch_mode"]}, "abandoned_with_fallback", "refines_instead_of_quitting"),
    ("1", {}, "found", "context"),
    ("9", {}, "found", "outcome_measure"),
])
def test_metric_node_rule(stage, codes, outcome, node, codebook):
    assert B.metric_node(stage, codes, outcome) == node
    assert node in codebook.metric_nodes


def test_severity_follows_the_rubric(codebook):
    assert B.severity(codebook, {"stakes": 0, "effort": 0, "emotional_intensity": 0},
                      "found") == 1
    assert B.severity(codebook, {"stakes": 2, "effort": 2, "emotional_intensity": 2},
                      "abandoned_without_fallback") == 5
    assert B.severity(codebook, {"stakes": 1, "effort": 1, "emotional_intensity": 1},
                      "substitute_accepted") == 3


def test_every_source_has_a_10_3_value(codebook):
    from pipeline.collect import base
    assert set(B.SOURCE_KIND_103) == set(base.SOURCES)
    assert all(codebook.is_valid_value("10.3", v) for v in B.SOURCE_KIND_103.values())


def test_prompt_is_generated_from_the_frozen_codebook(codebook):
    p = B.system_prompt(codebook)
    for qid, q in codebook.questions.items():
        if q["block"] != "S":
            assert f"**{qid}**" in p, qid
    for qid in ("5.3", "4.3"):
        assert " ".join(codebook.questions[qid]["boundary_note"].split()) in p
    assert "untrusted" in p and "not_stated" in p


def test_schema_fits_strict_mode_limits(codebook):
    s = B.schema(codebook, B.questions_for(codebook, B.CORE_BLOCKS))
    enums = []

    def walk(x):
        if isinstance(x, dict):
            enums.extend(x.get("enum", []))
            assert x.get("type") != "object" or x["required"] == list(x["properties"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(s)
    assert len(enums) < 1000 and sum(len(str(e)) for e in enums) < 15_000
    assert len(B.questions_for(codebook, B.CORE_BLOCKS)) == 59


def _answer(codebook, blocks, **over):
    out = {"spine": {"primary_stage": "5", "primary_stage_quote": "searched 'cafe goa' and it "
                     "showed nothing", "photo_class": "sentimental",
                     "photo_class_quote": "", "media_type": "photo", "photo_subtype": "café",
                     "outcome": "not_stated",
                     "severity": {"stakes": 1, "effort": 0, "emotional_intensity": 1},
                     "workaround": False, "workaround_text": "", "coding_conf": 0.9,
                     "why": "usable cues typed, nothing returned"},
           "queries": [{"text": "cafe goa", "worked": "no"}]}
    for q in B.questions_for(codebook, blocks):
        sel = codebook.questions[q]["select"]
        out[B.qkey(q)] = ({"cues": [], "q": ""} if q == "2.2" else
                          {"v": "not_stated" if sel == "single" else ["not_stated"],
                           "o": "", "q": ""})
    out.update(over)
    return out


def _item(text, blocks=("A",)):
    return B.Item("s1", "reddit", None, text, "", "core", 9, text, [(0, len(text))], blocks)


def test_validate_builds_rows_evidence_and_derived_fields(codebook):
    text = "Goa trip, no idea which year. I searched 'cafe goa' and it showed nothing. It was 2018."
    it = _item(text, B.CORE_BLOCKS)
    a = _answer(codebook, B.CORE_BLOCKS)
    a["q5_6"] = {"v": "zero_results", "o": "", "q": "I searched 'cafe goa' and it showed nothing"}
    a["q2_2"] = {"cues": [{"cue": "when:year", "accuracy": "certain_wrong"}], "q": ""}
    a["q7_2"] = {"v": ["rephrase_synonyms", "other", "quit"], "o": "Asked My Mum", "q": ""}
    c = B.validate(codebook, it, a)
    assert not c.fatal
    assert c.evidence["primary_stage"] == c.evidence["failure_owner"] in text
    assert c.evidence["5.6"] in text
    assert ("2.2", "when:year", "certain_wrong", None) in c.rows          # cue + accuracy
    assert [r for r in c.rows if r[0] == "7.2"] == [
        ("7.2", "rephrase_synonyms", None, 1), ("7.2", "other:asked_my_mum", None, 2),
        ("7.2", "quit", None, 3)]                                         # order kept
    assert ("10.3", "reddit", None, None) in c.rows
    s = c.spine
    assert s["failure_owner"] == "system" and s["metric_node"] == "query_captures_usable_cue"
    assert s["severity"] == 2 and c.queries == [("cafe goa", 1, 0)]


def test_unverifiable_primary_stage_quote_is_fatal(codebook):
    a = _answer(codebook, ("A",))
    a["spine"]["primary_stage_quote"] = "words that are nowhere in the story at all"
    c = B.validate(codebook, _item("I searched for my photo and nothing came up."), a)
    assert c.fatal == "span_unverified"


def test_written_rows_satisfy_the_schema(codebook, blank_db):
    text = "Goa trip, no idea which year. I searched 'cafe goa' and it showed nothing."
    blank_db.execute("INSERT INTO records (record_id, source, collect_method, source_url, text_raw,"
                     " text_clean, collected_at, ingest_run_id) VALUES ('r','reddit','apify',"
                     "'u',?,?,'d','run')", (text, text))
    blank_db.execute("INSERT INTO stories (story_id, record_id, ordinal, text, char_start,"
                     " char_end, bucket, bucket_reason, bucket_conf, reaches_stage, run_id)"
                     " VALUES ('s1','r',0,?,0,?,'core','x',0.9,9,'run')", (text, len(text)))
    it = _item(text, B.CORE_BLOCKS)
    a = _answer(codebook, B.CORE_BLOCKS)
    a["q5_3"] = {"v": ["hard_filter_single_cue"], "o": "", "q": ""}
    B.write(blank_db, codebook, it, B.validate(codebook, it, a), "run")
    assert blank_db.execute("SELECT inferred FROM story_codes WHERE question='5.3'"
                            ).fetchone()[0] == 1                           # EC-CODE-15
    n = blank_db.execute("SELECT count(DISTINCT question) FROM story_codes").fetchone()[0]
    assert n == 60                                                         # 59 asked + 10.3


def test_kappa_and_verdicts():
    k, po = agreement.kappa([("a", "a"), ("b", "b"), ("a", "b"), ("b", "a")])
    assert po == 0.5 and k == pytest.approx(0.0)
    assert agreement.kappa([("a", "a")] * 5) == (1.0, 1.0)
    assert agreement.verdict(0.7, 0.5) == "ok"
    assert agreement.verdict(0.2, 0.92) == "degenerate"                   # EC-VAL-2
    assert agreement.verdict(0.2, 0.5) == "low_reliability"
    assert agreement.verdict(None, 0.95) == "degenerate"


def test_coverage_register_rule(codebook, blank_db):
    from pipeline.analyse import coverage
    blank_db.execute("INSERT INTO records (record_id, source, collect_method, source_url, text_raw,"
                     " text_clean, collected_at, ingest_run_id) VALUES ('r','reddit','apify',"
                     "'u','t','t','d','run')")
    for i in range(10):
        blank_db.execute("INSERT INTO stories (story_id, record_id, ordinal, text, char_start,"
                         " char_end, bucket, bucket_reason, bucket_conf, reaches_stage, run_id)"
                         f" VALUES ('s{i}','r',{i},'t',0,1,'core','x',0.9,9,'run')")
        blank_db.execute("INSERT INTO story_codes (story_id, question, value, confidence, run_id)"
                         f" VALUES ('s{i}','8.2',?,0.9,'run')",
                         ("stakes" if i == 0 else "not_stated",))
        blank_db.execute("INSERT INTO story_codes (story_id, question, value, confidence, run_id)"
                         f" VALUES ('s{i}','8.1',?,0.9,'run')",
                         ("one_attempt" if i < 5 else "not_stated",))
    rows, _ = coverage.measure(blank_db, codebook)
    pooled = {r[0]: r for r in rows if r[1] == "_all"}
    assert len(pooled) == 60                                               # T-11
    assert pooled["8.2"][7] == "register" and pooled["8.1"][7] == "coded"  # R measured, not assumed


# ===================================================================== CORPUS
@pytest.fixture(scope="module")
def con(corpus):
    if corpus.execute("SELECT count(*) FROM story_spine").fetchone()[0] == 0:
        pytest.skip("no coded stories yet — Pass 2 has not been collected")
    return corpus


LIVE = "story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)"


def _latest(prefix: str, **match) -> dict:
    for p in sorted(ART.glob(f"{prefix}_*.json"), reverse=True):
        d = json.loads(p.read_text())
        if all(d.get(k) == v for k, v in match.items()):
            return d
    pytest.fail(f"no {prefix} artifact matching {match}")


@pytest.mark.needs_corpus
def test_every_live_story_is_coded_or_marked(con):
    left = con.execute(f"SELECT count(*) FROM stories WHERE {LIVE} AND story_id NOT IN"
                       " (SELECT story_id FROM story_spine)").fetchone()[0]
    marked = con.execute("SELECT count(*) FROM exclusions WHERE stage='code'").fetchone()[0]
    assert left == 0, f"{left} live stories neither coded nor marked (marked: {marked})"


@pytest.mark.needs_corpus
def test_P3_INV_1_primary_stage_and_failure_owner(con, codebook):
    bad = 0
    for r in con.execute("SELECT primary_stage, failure_owner FROM story_spine"):
        bad += r["failure_owner"] != codebook.failure_owner(r["primary_stage"])
    assert bad == 0


@pytest.mark.needs_corpus
def test_P3_INV_2_and_3_every_span_is_verbatim_text_clean_and_long_enough(con):
    """T-2 = 100% and T-3, absolute. Against text_clean, never text_en."""
    bad = [r["story_id"] for r in con.execute(
        "SELECT e.story_id, e.span, r.text_clean FROM evidence e JOIN stories s USING (story_id)"
        " JOIN records r USING (record_id)") if r["span"] not in r["text_clean"]
        or len(r["span"]) < 15]
    assert not bad, bad[:5]


@pytest.mark.needs_corpus
def test_P3_INV_4_primary_stage_and_failure_owner_carry_a_verified_span(con):
    missing = con.execute("SELECT count(*) FROM story_spine p WHERE (SELECT count(*) FROM"
                          " evidence e WHERE e.story_id = p.story_id AND e.verified = 1 AND"
                          " e.field IN ('primary_stage','failure_owner')) < 2").fetchone()[0]
    assert missing == 0


@pytest.mark.needs_corpus
def test_P3_INV_5_every_value_is_in_the_codebook(con, codebook):
    two1 = set(codebook.questions["2.1"]["values"])
    bad = []
    for r in con.execute("SELECT question, value, accuracy FROM story_codes"):
        if r["question"] == "2.2":
            ok = (r["value"] == "not_stated" and r["accuracy"] is None) or (
                r["value"] in two1 and r["accuracy"] in codebook.questions["2.2"]["accuracy_values"])
        else:
            ok = codebook.is_valid_value(r["question"], r["value"]) and r["accuracy"] is None
        if not ok:
            bad.append(tuple(r))
    assert not bad, bad[:5]


@pytest.mark.needs_corpus
def test_P3_INV_6_stage5_rows_are_inferred(con):
    assert con.execute("SELECT count(*) FROM story_codes WHERE question LIKE '5.%' AND"
                       " inferred <> 1").fetchone()[0] == 0


@pytest.mark.needs_corpus
def test_P3_INV_7_every_block_that_ran_has_a_row_for_every_question(con, codebook):
    """EC-CODE-14: a story that looks coded but is silently missing a block."""
    asked = defaultdict(set)
    for r in con.execute("SELECT story_id, question FROM story_codes"):
        asked[r["story_id"]].add(r["question"])
    bad = []
    for r in con.execute("SELECT p.story_id, s.bucket, s.reaches_stage FROM story_spine p"
                         " JOIN stories s USING (story_id)"):
        want = set(B.questions_for(codebook, B.blocks_for(r["bucket"], r["reaches_stage"])))
        if r["bucket"] == "adjacent" and "B" in {codebook.block_of(q) for q in asked[r[0]]}:
            want |= set(B.questions_for(codebook, B.CORE_BLOCKS))     # coded as core, then moved
        if want - asked[r["story_id"]]:
            bad.append((r["story_id"], sorted(want - asked[r["story_id"]])[:3]))
    assert not bad, bad[:5]


@pytest.mark.needs_corpus
def test_P3_INV_8_one_codebook_version_per_run(con, codebook):
    versions = {r[0] for r in con.execute(
        "SELECT DISTINCT r.codebook_version FROM runs r WHERE r.run_id IN"
        " (SELECT run_id FROM story_codes UNION SELECT run_id FROM story_spine)")}
    assert versions == {codebook.version_string}


@pytest.mark.needs_corpus
def test_P3_INV_9_video_implies_adjacent(con):
    assert con.execute("SELECT count(*) FROM story_spine p JOIN stories s USING (story_id)"
                       " WHERE p.media_type='video' AND s.bucket<>'adjacent'").fetchone()[0] == 0


@pytest.mark.needs_corpus
def test_P3_INV_10_analysis_rows_carry_n_and_run_id(con):
    for t, ncol in (("analysis_coverage", "n_coded"), ("analysis_reliability", "n")):
        assert con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] > 0, t
        assert con.execute(f"SELECT count(*) FROM {t} WHERE {ncol} IS NULL OR run_id IS NULL"
                           " OR run_id=''").fetchone()[0] == 0, t


@pytest.mark.needs_corpus
def test_metric_node_follows_the_rule(con):
    codes = defaultdict(lambda: defaultdict(list))
    for r in con.execute("SELECT story_id, question, value FROM story_codes WHERE question IN"
                         " ('5.4','7.2') ORDER BY seq"):
        codes[r[0]][r[1]].append(r[2])
    bad = [r[0] for r in con.execute("SELECT story_id, primary_stage, outcome, metric_node"
                                     " FROM story_spine")
           if B.metric_node(r[1], codes[r[0]], r[2]) != r[3]]
    assert not bad, bad[:5]


def _fixture():
    return _latest("code_fixtures", prompt_version=B.PROMPT_VERSION)["summary"]


@pytest.mark.needs_corpus
def test_P3_MET_1_T8_fixture_primary_stage():
    met_or_limitation("P3-MET-1", _fixture()["T8_primary_stage"], 0.85)


@pytest.mark.needs_corpus
def test_P3_MET_2_the_5_2_5_3_5_4_triple():
    met_or_limitation("P3-MET-2", _fixture()["P3_MET_2_triple_question"], 0.80)


@pytest.mark.needs_corpus
def test_P3_MET_3_stage_2_vs_stage_4():
    met_or_limitation("P3-MET-3", _fixture()["P3_MET_3_stage2_vs_4"], 0.80)


@pytest.mark.needs_corpus
def test_P3_MET_4_and_5_reliability_with_verdicts_for_every_spine_field(con):
    rows = {r["field"]: dict(r) for r in con.execute("SELECT * FROM analysis_reliability")}
    for f in agreement.SPINE:
        assert f in rows and rows[f]["verdict"] in ("ok", "low_reliability", "degenerate"), f
        assert rows[f]["raw_agreement"] is not None and rows[f]["marginals_json"], f
    assert rows["primary_stage"]["metric"] == "kappa"                    # reported on its own
    assert rows["primary_stage"]["n"] >= 80                              # [CTX] §15.7: 80–100


@pytest.mark.needs_corpus
def test_P3_MET_9_T7_block_yield(con, codebook):
    """≥ 25% non-not_stated where a block ran (EC-SEG-5, never cut)."""
    n, yes = Counter(), Counter()
    for r in con.execute("SELECT question, value FROM story_codes WHERE question <> '10.3'"):
        b = codebook.block_of(r["question"])
        n[b] += 1
        yes[b] += r["value"] != "not_stated"
    for b in ("A", "B", "C", "D"):
        met_or_limitation(f"P3-MET-9-{b}", yes[b] / n[b], 0.25)


@pytest.mark.needs_corpus
def test_P3_MET_10_T11_coverage_for_all_60_and_P3_MET_11_per_source(con):
    pooled = con.execute("SELECT count(*) FROM analysis_coverage WHERE source='_all'"
                         ).fetchone()[0]
    per = con.execute("SELECT count(DISTINCT source) FROM analysis_coverage WHERE source<>'_all'"
                      ).fetchone()[0]
    assert pooled == 60 and per >= 3


@pytest.mark.needs_corpus
def test_P3_MET_8_T12_other_rate(con):
    ans, oth = Counter(), Counter()
    # 10.3 is structural and set in code from the source (D-9); YouTube and X
    # have no listed value, so its `other:` is by construction, not the coder's.
    for r in con.execute("SELECT question, value FROM story_codes WHERE value <> 'not_stated'"
                         " AND question <> '10.3'"):
        ans[r[0]] += 1
        oth[r[0]] += r[1].startswith("other:")
    worst = max((oth[q] / ans[q], q) for q in ans if ans[q] >= 10)
    met_or_limitation("P3-MET-8", worst[0], 0.20, higher_is_better=False)   # on EVERY question


@pytest.mark.needs_corpus
def test_P3_MET_12_blind_read_ran_and_listed_disagreements():
    d = _latest("blind_read")
    assert d["n"] >= 40 and "disagreement_candidates" in d


@pytest.mark.needs_corpus
def test_T20_core_story_count(con):
    n = con.execute(f"SELECT count(*) FROM stories WHERE bucket='core' AND {LIVE}").fetchone()[0]
    met_or_limitation("T-20", n, 300)


def test_stage0_needs_library_evidence():
    """D-9: a quiet success is not a library-state failure. A story saying the
    photo vanished is, even when it cannot say where it went (0.1 not_stated) or
    it had been backed up first."""
    assert B.stage0_without_evidence("0", {"0.1": ["yes_backed_up"]}, "found")
    assert B.stage0_without_evidence("0", {"0.1": ["not_stated"]}, "found_after_struggle")
    assert not B.stage0_without_evidence("0", {"0.1": ["yes_backed_up"]}, "not_stated")
    assert not B.stage0_without_evidence("0", {"0.1": ["not_stated"]}, "not_stated")
    assert not B.stage0_without_evidence("0", {"0.1": ["deleted"]}, "found")
    assert not B.stage0_without_evidence("0", {"0.1": ["yes_backed_up"],
                                               "0.2": ["date:received_date_not_capture"]},
                                         "found")
    assert not B.stage0_without_evidence("5", {"0.1": ["yes_backed_up"]})


@pytest.mark.needs_corpus
def test_no_stage0_story_without_library_evidence(con):
    """EC-CODE-2's twin: Stage 0 inflated by stories where nothing says the
    photo was unreachable. Fixed by `blocks recode` (D-9)."""
    bad = B.stage0_suspects(con)
    assert not bad, f"{len(bad)} stories coded Stage 0 without library evidence"


def test_other_text_that_spells_a_listed_value_becomes_that_value(codebook):
    text = "The photo was only in WhatsApp, never in Google Photos, so search found nothing."
    a = _answer(codebook, ("A",))
    a["spine"]["primary_stage"] = "0"
    a["spine"]["primary_stage_quote"] = "only in WhatsApp, never in Google Photos"
    a["q0_1"] = {"v": "other", "o": "only in other app", "q": ""}
    c = B.validate(codebook, _item(text), a)
    assert ("0.1", "only_in_other_app", None, None) in c.rows


@pytest.mark.needs_corpus
def test_no_other_value_duplicates_a_listed_value(con, codebook):
    dup = [(q, v) for q, v in con.execute("SELECT question, value FROM story_codes WHERE"
                                          " value LIKE 'other:%' AND question <> '10.3'")
           if any(x == v[6:] or x.split(":")[-1] == v[6:] for x in codebook.questions[q]["values"])]
    assert not dup, dup[:5]


def test_emergent_themes_live_outside_the_frozen_codebook():
    from pipeline.common import codebook as cbm
    from pipeline.synthesise import themes
    t = themes.load_themes()
    assert set(t) == {"search_refuses_sensitive_terms", "auto_creation_lost",
                      "no_album_scoped_search", "looked_in_other_photo_app"}
    assert all(v["definition"] and v["label"] for v in t.values())
    assert "emergent_themes_v1.yaml" not in cbm.FROZEN_FILES               # D-10: not in the hash


@pytest.mark.needs_corpus
def test_emergent_theme_tags_are_verified_and_on_live_stories(con):
    from pipeline.synthesise import themes
    known = set(themes.load_themes())
    rows = con.execute("SELECT t.story_id, t.theme, t.span, r.text_clean FROM story_themes t"
                       " JOIN stories s USING (story_id) JOIN records r USING (record_id)"
                       ).fetchall()
    assert rows, "no emergent-theme tags — python -m pipeline.synthesise.themes"
    assert all(r["theme"] in known for r in rows)
    assert all(r["span"] in r["text_clean"] and len(r["span"]) >= 15 for r in rows)  # T-2/T-3
    dead = con.execute("SELECT count(*) FROM story_themes WHERE story_id IN (SELECT story_id"
                       " FROM exclusions WHERE story_id IS NOT NULL)").fetchone()[0]
    assert dead == 0
