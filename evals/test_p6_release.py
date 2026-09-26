"""P6 gate — release (evals.md §11, §12). The How it works page and its
Methodology, the pinned published run, the cross-cutting checks X-1…X-6, and
the browser sweep P6-BR-1…12 read from its committed report.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.p6

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "app" / "views" / "home.py"
REPORTS = ROOT / "evals" / "reports"


@pytest.fixture(scope="module")
def con(corpus):
    c = sqlite3.connect(f"file:{ROOT / 'data' / 'corpus.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


# ======================================================== the page (source checks: CI)
def test_P6_BR_12_no_gold_standard_disclosure_is_present_and_unhedged():
    """EC-VAL-1: stated plainly — no person reviewed the coding; the figures are
    inter-model agreement; agreement is consistency, not correctness."""
    src = " ".join(HOME.read_text().split())
    for must in ("There is no human-checked gold standard", "No person reviewed",
                 "agreement between two AI models", "consistency, not correctness",
                 "two models can agree and both be wrong"):
        assert must in src, must
    part = src[src.index("There is no human-checked"):src.index("two models can agree")]
    assert not re.search(r"\b(largely|mostly|broadly|somewhat|arguably|generally)\b", part)


def test_P4_INV_1_how_it_works_formats_no_share_itself():
    src = HOME.read_text()
    assert not re.search(r":\.\d*%|\{[^}]*%\}|\* ?100\b", src) and "share(" in src


def test_the_page_carries_every_part_the_plan_names():
    """implementationplan task 6.1: method, funnel, the one-slide diagram, sources and
    lexicon, codebook, severity rubric, weights, the 60-question register, reliability,
    the sanity strip, limitations; evals.md §4: the gate reports, in the app."""
    src = HOME.read_text()
    for slug in ("what", "funnel", "codebook", "register", "reliability", "sanity", "scoring",
                 "limits", "gates"):
        assert f'slug="{slug}"' in src, slug
    for piece in ("STEPS = [", "lexicon", "severity rubric", "sanity_strip", "pre_registered_at",
                  "limitations", 'glob("gate_P*.md")'):
        assert piece in src, piece
    from lib import nav
    home = next(p for p in nav.PAGES if p[0] == "home.py")
    assert [s for s, _ in home[4]] == ["what", "funnel", "codebook", "register", "reliability",
                                      "sanity", "scoring", "limits", "gates"]


def test_user_text_on_how_it_works_is_escaped():
    src = HOME.read_text()
    for field in (r"s\['text'\]", r"s\['why'\]", r"q\['plain'\]", r"t\['term'\]"):
        uses = [u for u in re.findall(rf"\{{[^{{}}]*{field}[^{{}}]*\}}", src)
                if "len(" not in u]                       # a length check prints no text
        assert uses and all("esc(" in u for u in uses), (field, uses)


# ============================================================ published (X-3, corpus)
@pytest.mark.needs_corpus
def test_X3_the_app_serves_a_pinned_published_run_that_matches_every_table(con):
    """EC-OPS-11: a table rebuilt after publishing no longer matches the
    manifest — re-publish (python -m pipeline.analyse.publish)."""
    from pipeline.analyse import publish
    pub = con.execute("SELECT run_id, corpus_version FROM published WHERE singleton=1").fetchone()
    assert pub, "nothing published"
    assert pub["run_id"].startswith("publish-") and "core stories" in pub["corpus_version"]
    rows = {r["key"]: r for r in con.execute("SELECT key, value_json, run_id FROM"
                                               " analysis_methodology")}
    assert {r["run_id"] for r in rows.values()} == {pub["run_id"]}
    assert json.loads(rows["manifest"]["value_json"]) == publish.manifest(con), \
        "an analysis table changed after publishing — re-publish"


@pytest.mark.needs_corpus
def test_P6_BR_9_the_footer_stamp_is_the_published_corpus_version(con):
    src = (ROOT / "app" / "lib" / "nav.py").read_text()
    assert "db.published()" in src and 'pub["corpus_version"]' in src
    stamp = con.execute("SELECT corpus_version FROM published").fetchone()[0]
    core = con.execute("SELECT n FROM analysis_funnel WHERE source='_all' AND"
                       " step='stories:core'").fetchone()[0]
    assert stamp.startswith("Corpus v1.0") and f"{core} core stories" in stamp


@pytest.mark.needs_corpus
def test_the_sanity_strip_is_ten_live_coded_core_stories(con):
    ids = json.loads(con.execute("SELECT value_json FROM analysis_methodology WHERE"
                                 " key='sanity_strip'").fetchone()[0])
    ph = ",".join("?" * len(ids))
    ok = con.execute(f"SELECT count(*) FROM story_spine p JOIN stories s USING (story_id) WHERE"
                     f" s.story_id IN ({ph}) AND s.bucket='core' AND s.story_id NOT IN (SELECT"
                     " story_id FROM exclusions WHERE story_id IS NOT NULL)", ids).fetchone()[0]
    assert len(ids) == len(set(ids)) == 10 == ok


@pytest.mark.needs_corpus
def test_P6_BR_8_register_and_reliability_are_complete(con):
    assert con.execute("SELECT count(*) FROM analysis_coverage WHERE source='_all'"
                       ).fetchone()[0] == 60
    spine = {r[0] for r in con.execute("SELECT field FROM analysis_reliability")}
    assert {"primary_stage", "photo_class", "outcome", "severity"} <= spine


@pytest.mark.needs_corpus
def test_how_it_works_renders_without_exception(corpus):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(HOME), default_timeout=60).run()
    assert not at.exception, at.exception
    assert at.title and at.title[0].value == "Google Photos Discovery Engine"


# ============================================================== cross-cutting (X-1…X-6)
@pytest.mark.needs_corpus
def test_X1_every_paid_pass_recorded_its_cost_against_an_estimate(con):
    """T-19: no pass finished over 1.5× its estimate without halting."""
    bad = [r["run_id"] for r in con.execute(
        "SELECT run_id, estimate_usd, cost_usd, status FROM runs WHERE model IS NOT NULL")
        if r["estimate_usd"] is None or r["cost_usd"] is None
        or (r["estimate_usd"] > 0 and r["cost_usd"] > 1.5 * r["estimate_usd"]
            and r["status"] != "halted_budget")]
    assert not bad, bad


def test_X2_every_gate_report_states_spend_against_the_ceiling_and_passed():
    for phase in ("P0", "P1", "P2", "P3", "P4", "P5"):
        rep = sorted(REPORTS.glob(f"gate_{phase}_*.md"))
        assert rep, phase
        txt = rep[-1].read_text()
        assert "**Spend to date:**" in txt and "**Verdict:** **GATE PASSED.**" in txt, phase


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout


def test_X4_the_rebuild_token_changed_with_the_last_change_to_app_lib():
    """EC-OPS-10: Streamlit Cloud keeps old modules unless requirements.txt changes."""
    last = _git("log", "-1", "--format=%H", "--", "app/lib").strip()
    if not last:
        pytest.skip("no git history")
    token = re.compile(r"rebuild-token:\s*(\S+)")
    before = token.search(_git("show", f"{last}^:requirements.txt"))
    now = token.search((ROOT / "requirements.txt").read_text())
    assert before and now and before.group(1) != now.group(1), \
        "app/lib changed without a rebuild-token bump"


def test_X5_every_ctx_14_criterion_maps_to_an_eval():
    txt = (ROOT / "Docs" / "evals.md").read_text()
    table = txt[txt.index("### [CTX] §14 definition-of-done coverage"):]
    rows = [ln for ln in table.splitlines()[4:12] if ln.startswith("| ")]
    assert len(rows) == 8 and all(re.search(r"\bP\d\b|P\d-|T-\d", r) for r in rows)


# ========================================================== the browser sweep (report)
BR = [f"P6-BR-{i}" for i in range(1, 13)]


@pytest.mark.manual
def test_P6_browser_sweep_recorded_every_check_passing():
    """A green CI build is not a verified deploy (implementationplan §0.3, class BR).
    Every P6-BR row must be ✅ in the committed report — including BR-10, cold
    start after the app has SLEPT, which a warm load cannot stand in for."""
    rep = sorted(REPORTS.glob("browser_P6_*.md"))
    assert rep, "no P6 browser report"
    txt = rep[-1].read_text()
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| (P6-BR-\d+) \|[^|]*\| ([^|]+)\|",
                                                        txt, re.M)}
    missing = [b for b in BR if b not in rows]
    failing = [b for b in BR if b in rows and "✅" not in rows[b]]
    assert not missing and not failing, {"missing": missing, "not passed": failing}


def test_limitations_shown_are_the_committed_ones(corpus):
    lim = yaml.safe_load((ROOT / "evals" / "limitations.yaml").read_text())
    shown = json.loads(corpus.execute("SELECT value_json FROM analysis_methodology WHERE"
                                      " key='limitations'").fetchone()[0])
    assert [x["id"] for x in shown] == list(lim)
