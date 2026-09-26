"""P0 gate — Foundation (evals.md §5). Before any paid call.

IDs in test names map 1:1 to evals.md so the gate report reads as the table.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from pipeline.common import codebook as cb_mod
from pipeline.common import env as env_mod
from pipeline.common import runs as runs_mod

pytestmark = pytest.mark.p0

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "evals" / "fixtures"


# ------------------------------------------------------------------ codebook
def test_P0_INV_1_sixty_unique_questions(codebook):
    ids = list(codebook.questions)
    assert len(ids) == 60 == len(set(ids))
    expected = {f"{s}.{q}" for s, n in
                [(0, 5), (1, 6), (2, 8), (3, 5), (4, 5), (5, 6), (6, 7), (7, 5),
                 (8, 4), (9, 6), (10, 3)] for q in range(1, n + 1)}
    assert set(ids) == expected, "IDs must be exactly 0.1 … 10.3 from [SOL-JOURNEY]"


def test_P0_INV_2_every_question_has_values_not_stated_other(codebook):
    for qid, q in codebook.questions.items():
        assert "not_stated" in q["values"] and "other" in q["values"], qid
        assert len(q["values"]) >= 4, f"{qid}: needs ≥2 substantive values"
        assert all(re.fullmatch(r"[a-z0-9_:]+", v) for v in q["values"]), qid


def test_P0_INV_3_stage_and_block_mapping(codebook):
    for qid, q in codebook.questions.items():
        assert q["stage"] in codebook.stages and qid.split(".")[0] == q["stage"]
        assert q["block"] in {"A", "B", "C", "D", "R", "S"}, qid
        assert q["metric_node"] in codebook.metric_nodes, qid
    assert {b: len(codebook.by_block(b)) for b in "ABCDRS"} == cb_mod.EXPECTED_PER_BLOCK
    assert codebook.by_block("S") == ["10.3"]


def test_P0_INV_4_danger_questions_carry_boundary_notes(codebook):
    for qid in ("5.2", "5.3", "5.4", "2.4", "4.2", "4.3"):
        note = " ".join(str(codebook.questions[qid].get("boundary_note", "")).split())
        assert len(note) >= 80, f"{qid}: boundary_note missing or thin"
    triple = codebook.questions["5.3"]["boundary_note"]
    assert all(k in triple for k in ("5.2", "5.3", "5.4"))
    pair = codebook.questions["4.3"]["boundary_note"]
    assert "STAGE 2" in pair and "STAGE 4" in pair
    assert codebook.spine["primary_stage"]["boundary_note"]


def test_stage5_is_inferred_and_owner_mapping_complete(codebook):
    assert codebook.is_inferred("5.3") and not codebook.is_inferred("2.1")
    assert codebook.failure_owner("5") == "system"
    assert codebook.failure_owner("0") == "library_data"
    assert codebook.failure_owner("4") == "expression"


def test_P0_INV_5_codebook_frozen(codebook):
    frozen = json.loads((ROOT / "codebook" / "FROZEN.json").read_text())
    assert frozen["frozen_at"] and frozen["content_hash"] == codebook.content_hash
    datetime.fromisoformat(frozen["frozen_at"])
    assert codebook.version_string == f"v1:{frozen['content_hash'][:8]}"


def test_P0_INV_5_mutation_after_freeze_is_refused(tmp_path, monkeypatch):
    """EC-CODE-13 enforced in code: edit one character, load() must raise."""
    work = tmp_path / "codebook"
    shutil.copytree(ROOT / "codebook", work)
    monkeypatch.setattr(cb_mod, "CODEBOOK_DIR", work)
    monkeypatch.setattr(cb_mod, "FREEZE_FILE", work / "FROZEN.json")
    cb_mod.load()                                       # intact copy loads
    p = work / "journey_v1.yaml"
    p.write_text(p.read_text().replace("hard_filter_single_cue", "hard_filter_one_cue", 1))
    with pytest.raises(cb_mod.CodebookError, match="CHANGED AFTER FREEZE"):
        cb_mod.load()


def test_codebook_value_check_accepts_other_prefix_only(codebook):
    assert codebook.is_valid_value("5.6", "zero_results")
    assert codebook.is_valid_value("5.6", "other:froze on the spinner")
    assert not codebook.is_valid_value("5.6", "other:")
    assert not codebook.is_valid_value("5.6", "invented_value")


def test_P0_INV_7_scoring_pre_registered():
    s = yaml.safe_load((ROOT / "codebook" / "scoring_v1.yaml").read_text())
    assert s["pre_registered_at"], "set before the first ranking run (EC-ANL-6)"
    datetime.fromisoformat(s["pre_registered_at"])
    assert s["gates"] == {"addressable_by_gp": {"min": 3}, "ai_necessity": {"min": 3}}
    assert s["weights"] == {"metric_leverage": 30, "severity": 25, "frequency": 20,
                            "evidence_strength": 15, "reach": 10}
    assert sum(s["weights"].values()) == 100


def test_supporting_codebook_files_load():
    for name in ("severity_v1.yaml", "metric_nodes_v1.yaml", "lexicon_v1.yaml",
                 "plain_language.yaml", "scoring_v1.yaml"):
        assert yaml.safe_load((ROOT / "codebook" / name).read_text()), name
    lex = yaml.safe_load((ROOT / "codebook" / "lexicon_v1.yaml").read_text())
    assert sum(len(v) for v in lex["terms"].values()) == 26   # [CTX] §6.2 seed, all present
    sev = yaml.safe_load((ROOT / "codebook" / "severity_v1.yaml").read_text())
    covered = sorted(t for band in sev["scale"].values() for t in band)
    assert covered == list(range(9)), "severity scale must cover totals 0–8 exactly"


# ------------------------------------------------------------------- schema
EXPECTED_TABLES = {"records", "exclusions", "stories", "story_spine", "story_codes",
                   "evidence", "queries", "double_coding", "analysis_reliability",
                   "analysis_coverage", "analysis_crosstab", "runs", "published"}


def _cols(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _record(con, rid="r1", text="I searched 'cafe goa' and it shows nothing at all."):
    con.execute("INSERT INTO records (record_id, source, collect_method, source_url, text_raw,"
                " text_clean, collected_at, ingest_run_id) VALUES (?,?,?,?,?,?,?,?)",
                (rid, "reddit", "apify", "https://reddit.com/x", text, text, "2026-09-26", "run"))
    return text


def _story(con, sid="s1", rid="r1", text="I searched 'cafe goa'", start=0, **kw):
    row = dict(story_id=sid, record_id=rid, ordinal=kw.pop("ordinal", 0), text=text,
               char_start=start, char_end=start + len(text), bucket="core",
               bucket_reason="vague", bucket_conf=0.9, reaches_stage=5, run_id="run")
    row.update(kw)
    con.execute(f"INSERT INTO stories ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                tuple(row.values()))


def test_P0_INV_6_schema_applies_cleanly_and_idempotently(blank_db, tmp_path):
    tables = {r[0] for r in blank_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    from pipeline.common import db as db_mod
    db_mod.init(tmp_path / "test.db")                     # second apply: no error


def test_P0_INV_6_appendix_a_deltas_present(blank_db):
    assert "author_key" in _cols(blank_db, "stories")                       # A.2
    pk = [r[1] for r in blank_db.execute("PRAGMA table_info(analysis_coverage)") if r[5]]
    assert pk == ["question", "source"]                                     # A.3
    assert "estimate_usd" in _cols(blank_db, "runs")                        # A.4
    assert {"char_start", "char_end"} <= _cols(blank_db, "stories")         # A.6
    assert {"raw_agreement", "top_share"} <= _cols(blank_db, "analysis_reliability")  # A.7
    assert "collect_method" in _cols(blank_db, "records")                   # A.10


def test_A9_A10_source_and_collect_method_enums(blank_db):
    """D-1: the nine sources are accepted, each with a disclosed method; an
    unknown source or a record with no method is refused."""
    ok = [("youtube", "official_api"), ("x", "apify"), ("gp_help", "headless_render"),
          ("appstore", "public_feed"), ("play", "public_scraper_lib")]
    for i, (src, method) in enumerate(ok):
        blank_db.execute("INSERT INTO records (record_id, source, collect_method, source_url,"
                         " text_raw, text_clean, collected_at, ingest_run_id)"
                         " VALUES (?,?,?,'u','t','t','d','r')", (f"ok{i}", src, method))
    for rid, src, method in (("b1", "tiktok", "apify"), ("b2", "reddit", "praw"),
                             ("b3", "reddit", None)):
        with pytest.raises(sqlite3.IntegrityError):
            blank_db.execute("INSERT INTO records (record_id, source, collect_method, source_url,"
                             " text_raw, text_clean, collected_at, ingest_run_id)"
                             " VALUES (?,?,?,'u','t','t','d','r')", (rid, src, method))


def test_P0_INV_6_exclusions_mark_not_remove(blank_db):
    """A.1: an excluded record is still in `records` — P1-MET-3 samples them."""
    _record(blank_db)
    blank_db.execute("INSERT INTO exclusions (record_id, stage, reason, run_id)"
                     " VALUES ('r1','prefilter','lexicon_rejected','run')")
    assert blank_db.execute("SELECT count(*) FROM records").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):          # reason outside the enum (P1-INV-5)
        blank_db.execute("INSERT INTO exclusions (record_id, stage, reason, run_id)"
                         " VALUES ('r1','clean','felt_like_it','run')")
    with pytest.raises(sqlite3.IntegrityError):          # a record is excluded once per stage
        blank_db.execute("INSERT INTO exclusions (record_id, stage, reason, run_id)"
                         " VALUES ('r1','prefilter','too_short','run')")


_BAD_ROWS = [
    ("INSERT INTO stories (story_id, record_id, ordinal, text, char_start, char_end, bucket,"
     " bucket_reason, bucket_conf, reaches_stage, run_id) VALUES"
     " ('s9','missing',0,'abc',0,3,'core','r',0.5,5,'run')", "foreign key"),
    ("INSERT INTO stories (story_id, record_id, ordinal, text, char_start, char_end, bucket,"
     " bucket_reason, bucket_conf, reaches_stage, run_id) VALUES"
     " ('s9','r1',1,'abc',0,3,'maybe','r',0.5,5,'run')", "bucket enum"),
    ("INSERT INTO stories (story_id, record_id, ordinal, text, char_start, char_end, bucket,"
     " bucket_reason, bucket_conf, reaches_stage, run_id) VALUES"
     " ('s9','r1',1,'abc',0,3,'core','r',0.5,11,'run')", "reaches_stage 0-10"),
    ("INSERT INTO stories (story_id, record_id, ordinal, text, char_start, char_end, bucket,"
     " bucket_reason, bucket_conf, reaches_stage, run_id) VALUES"
     " ('s9','r1',1,'abc',0,9,'core','r',0.5,5,'run')", "offsets match text length"),
    ("INSERT INTO story_codes (story_id, question, value, inferred, confidence, run_id)"
     " VALUES ('s1','5.3','hard_filter_single_cue',0,0.9,'run')", "stage 5 must be inferred"),
    ("INSERT INTO evidence (story_id, field, span, verified, run_id)"
     " VALUES ('s1','primary_stage','too short',1,'run')", "span ≥ 15 chars (T-3)"),
    ("INSERT INTO story_spine (story_id, photo_class, media_type, primary_stage, failure_owner,"
     " outcome, coding_conf, why, run_id) VALUES ('s1','sentimental','photo','11','system',"
     "'found',0.9,'w','run')", "primary_stage 0-10"),
    ("INSERT INTO story_spine (story_id, photo_class, media_type, primary_stage, failure_owner,"
     " outcome, coding_conf, why, run_id) VALUES ('s1','sentimental','gif','5','system',"
     "'found',0.9,'w','run')", "media_type enum"),
]


@pytest.mark.parametrize("sql, why", _BAD_ROWS, ids=[w for _, w in _BAD_ROWS])
def test_P0_INV_6_constraints_refuse_bad_rows(blank_db, sql, why):
    _record(blank_db)
    _story(blank_db)
    with pytest.raises(sqlite3.IntegrityError):
        blank_db.execute(sql)


def test_P0_INV_6_valid_rows_accepted(blank_db):
    _record(blank_db)
    _story(blank_db)
    blank_db.execute("INSERT INTO story_codes (story_id, question, value, inferred, confidence,"
                     " run_id) VALUES ('s1','5.3','hard_filter_single_cue',1,0.9,'run')")
    blank_db.execute("INSERT INTO evidence (story_id, field, span, verified, run_id)"
                     " VALUES ('s1','primary_stage','searched ''cafe goa''',1,'run')")
    blank_db.execute("INSERT INTO published (singleton, run_id, corpus_version, published_at)"
                     " VALUES (1,'run','Corpus v1.0','2026-09-30')")
    with pytest.raises(sqlite3.IntegrityError):          # only ever one published run
        blank_db.execute("INSERT INTO published VALUES (2,'x','y','z')")


def test_committed_corpus_db_matches_schema(root):
    con = sqlite3.connect(root / "data" / "corpus.db")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    # CHECK constraints cannot be altered in place, so a schema edit leaves the
    # committed file stale until it is rebuilt. Catch that here, not at the
    # first collector write.
    records_sql = con.execute("SELECT sql FROM sqlite_master WHERE name='records'").fetchone()[0]
    assert "collect_method" in records_sql and "'quora'" in records_sql, \
        "data/corpus.db predates A.9/A.10 — rebuild it from pipeline/schema.sql"


# --------------------------------------------------------- runs (T-19, X-1)
def test_runs_cost_uses_confirmed_rates_and_batch_half():
    std = runs_mod.cost("gpt-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert std == pytest.approx(11.25)
    assert runs_mod.cost("gpt-5", input_tokens=1_000_000, output_tokens=1_000_000,
                         batch=True) == pytest.approx(5.625)
    cached = runs_mod.cost("gpt-5-mini", input_tokens=1_000_000, cached_tokens=1_000_000,
                           output_tokens=0)
    assert cached == pytest.approx(0.025)
    with pytest.raises(KeyError):
        runs_mod.cost("gpt-9", input_tokens=1, output_tokens=1)


def test_runs_writes_row_with_estimate(blank_db):
    with runs_mod.Run(blank_db, "smoke", model="gpt-5-mini", estimate_usd=0.10,
                      prompt_version="p", codebook_version="v1:x") as run:
        run.add_usage(input_tokens=10_000, output_tokens=1_000)
    row = blank_db.execute("SELECT * FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
    assert row["status"] == "ok" and row["estimate_usd"] == 0.10
    assert row["cost_usd"] == pytest.approx(0.0045)


def test_T19_halts_at_one_and_a_half_times_estimate(blank_db):
    with pytest.raises(runs_mod.BudgetHalt):
        with runs_mod.Run(blank_db, "overrun", model="gpt-5", estimate_usd=0.01) as run:
            run.add_usage(input_tokens=1_000, output_tokens=1_000)     # $0.011 — fine
            run.add_usage(input_tokens=0, output_tokens=1_000)         # $0.021 > 1.5×
    row = blank_db.execute("SELECT status, cost_usd FROM runs").fetchone()
    assert row["status"] == "halted_budget" and row["cost_usd"] > 0   # spend still recorded


def test_ceiling_refuses_a_pass_that_would_cross_the_budget(blank_db):
    blank_db.execute("INSERT INTO runs (run_id, stage, started_at, cost_usd) VALUES"
                     " ('old','x','t',?)", (runs_mod.CEILING_USD - 0.50,))
    with pytest.raises(runs_mod.BudgetHalt, match="ceiling"):
        with runs_mod.Run(blank_db, "next", model="gpt-5", estimate_usd=0.80):
            pass


def test_rates_confirmed_recently():
    assert runs_mod.RATES_CONFIRMED_AT >= "2026-09-26"


# ----------------------------------------------------- share() — [CTX] §15.5
def test_share_helper_tiers():
    from lib.evidence import share
    low = share(7, 29)
    assert low.tier == "insufficient" and low.text == "7 of 29" and low.pct is None
    assert "%" not in low.text                           # no percentage below the floor
    mid = share(20, 50)
    assert mid.tier == "directional" and "40% (20 of 50" in mid.text and "rough guide" in mid.text
    hi = share(128, 412)
    assert hi.tier == "comparable" and hi.text == "31% (128 of 412)"
    for s in (mid, hi):
        assert f"of {s.denom}" in s.text                 # never a % without its denominator
    with pytest.raises(ValueError):
        share(5, 3)


def test_differs_needs_comparable_cells_and_separation():
    from lib.evidence import differs, fisher_p
    assert not differs((10, 50), (40, 50))               # directional cells: no claim
    assert differs((20, 200), (80, 200))
    assert not differs((50, 200), (52, 200))
    assert fisher_p((3, 10), (3, 10)) == pytest.approx(1.0)


def test_share_helper_has_no_streamlit_dependency():
    src = (ROOT / "app" / "lib" / "evidence.py").read_text()
    assert "import streamlit" not in src


# ------------------------------------------------------------------ fixtures
def _jsonl(name):
    return [json.loads(line) for line in (FIX / name).read_text().splitlines() if line.strip()]


def test_all_five_fixture_files_present_and_rebuildable():
    for name in ("stories_authored.jsonl", "segmentation_counts.jsonl",
                 "dedupe_consensus.jsonl", "bucket_boundary.jsonl", "injection_stories.jsonl"):
        assert _jsonl(name), name
    spec = importlib.util.spec_from_file_location("bf", FIX / "_build_fixtures.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    bf._check()                                           # composition asserts hold
    assert len(bf.STORIES) == len(_jsonl("stories_authored.jsonl"))


def test_authored_stories_composition_and_spans():
    rows = _jsonl("stories_authored.jsonl")
    groups = {}
    for r in rows:
        groups[r["group"]] = groups.get(r["group"], 0) + 1
        for span in r["expected"]["evidence"].values():
            assert span in r["text"] and len(span) >= 15, r["id"]
    assert groups == {"triple_5234": 9, "stage2_vs_4": 6, "bucket": 8, "primary_stage": 6,
                      "photo_class": 4, "media": 3, "hinglish": 4}
    assert all(r["expected"]["why"] for r in rows)


def test_authored_stories_use_only_codebook_values(codebook):
    for r in _jsonl("stories_authored.jsonl"):
        e = r["expected"]
        for q, vals in e["codes"].items():
            allowed = (codebook.questions[q]["accuracy_values"] if q == "2.2"
                       else codebook.questions[q]["values"])
            assert all(v in allowed for v in vals), (r["id"], q, vals)
        for f in ("photo_class", "media_type", "outcome", "primary_stage"):
            assert e[f] in codebook.spine[f]["values"], (r["id"], f)
        assert codebook.failure_owner(e["primary_stage"]) == e["failure_owner"], r["id"]
        if e["media_type"] == "video":
            assert e["bucket"] == "adjacent"             # P3-INV-9 by construction


def test_dedupe_fixture_pins_both_directions():
    rows = _jsonl("dedupe_consensus.jsonl")
    distinct = [r for r in rows if r["group"] == "distinct_authors"]
    same = [r for r in rows if r["group"] == "same_author"]
    assert len(distinct) == 40 and len({r["author_key"] for r in distinct}) == 40
    assert len(same) == 5 and len({r["author_key"] for r in same}) == 1


# --------------------------------------------------------------------- ops
def _tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True,
                             check=True).stdout.decode().split("\0")
        files = [root / f for f in out if f]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    skip = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    return [p for p in root.rglob("*") if p.is_file() and not skip & set(p.parts)]


SECRET_PATTERNS = [
    # OpenAI keys. The left boundary matters: without it "ask-golden-synth-2026…"
    # (a run id) matched, once the golden-sweep artifacts were committed.
    re.compile(rb"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),              # GitHub tokens
    re.compile(rb"(?i)client_secret[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9_-]{16,}"),
    re.compile(rb"(?i)AUTHOR_SALT[ \t]*[:=][ \t]*[\"']?\S{8,}"),
]


def test_P0_OPS_1_secret_scan_including_salt(root):
    """T-18 = 0. Scans every file that is (or would be) committed. The salt's
    VALUE is read from the environment/.env and searched for literally, so it
    is caught even if pasted somewhere without its variable name (EC-OPS-7)."""
    salt = env_mod.load(export=False).get("AUTHOR_SALT", "").encode()
    hits = []
    for p in _tracked_files(root):
        if p.name in {".env", "secrets.toml"}:
            hits.append(f"{p.relative_to(root)}: secret file present in the commit set")
            continue
        if p.suffix in {".db", ".pdf", ".zip", ".png", ".jpg"} or not p.exists():
            continue
        data = p.read_bytes()
        for pat in SECRET_PATTERNS:
            if pat.search(data):
                hits.append(f"{p.relative_to(root)}: {pat.pattern[:30]!r}")
        if len(salt) >= 8 and salt in data:
            hits.append(f"{p.relative_to(root)}: AUTHOR_SALT value")
    assert not hits, hits


def test_P0_OPS_1_scanner_catches_a_planted_secret():
    """Positive control: a scan that finds nothing must be a scan that COULD."""
    key = ("sk-" + "proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2").encode()
    salt_line = ("AUTHOR" + "_SALT=" + "correct-horse-battery").encode()
    secret_line = ("client" + "_secret: " + "abcdEFGH1234ijklMNOP").encode()
    for planted in (key, salt_line, secret_line):
        assert any(p.search(b"x = " + planted) for p in SECRET_PATTERNS), planted
    assert not any(p.search(b"AUTHOR" + b"_SALT=\nNEXT=value-here") for p in SECRET_PATTERNS)
    assert not any(p.search(b"run ask-golden-synth-20260926-170921-1deede") for p in SECRET_PATTERNS)


def test_P0_OPS_3_gitignore_covers_secrets(root):
    lines = {ln.strip() for ln in (root / ".gitignore").read_text().splitlines()}
    assert ".streamlit/secrets.toml" in lines or "secrets.toml" in lines
    assert ".env" in lines and "*.salt" in lines


def test_masked_never_reveals_a_secret():
    v = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz0123456789"   # split: keep the scan clean
    assert env_mod.masked(v).endswith("…6789)") and "abcdef" not in env_mod.masked(v)


@pytest.mark.manual
def test_P0_OPS_2_openai_hard_cap_recorded(root):
    m = yaml.safe_load((root / "evals" / "manual_checks.yaml").read_text())
    assert m["openai_hard_cap_usd"] == runs_mod.CEILING_USD, \
        "the recorded console budget and the in-code ceiling must agree"
    assert m["openai_hard_cap_confirmed_at"], "record when it was set"


# --------------------------------------------------------------------- app
def test_app_boots_without_exception_and_without_a_key(root, monkeypatch):
    """Placeholder app renders with no secrets at all (EC-OPS-5). AppTest cannot
    see st.html, so this proves boot only; the browser check proves the page."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(str(root / "app" / "Home.py"), default_timeout=30).run()
    assert not at.exception, at.exception
    # The app opens on Ask AI (the PM, 2026-09-27); with no key it says so plainly.
    assert at.title or at.info or len(at.main.children) > 0, "the front door must render"


def test_requirements_split_is_clean(root):
    app_reqs = (root / "requirements.txt").read_text()
    for heavy in ("praw", "httpx", "selectolax", "scraper", "datasketch"):
        assert heavy not in app_reqs, f"{heavy} is a pipeline dep (task 0.1)"
    assert re.search(r"rebuild-token:\s*\S+", app_reqs), "EC-OPS-10"
