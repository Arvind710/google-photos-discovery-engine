"""P1 gate — Data Bank (evals.md §6). Written before the pilot collect runs
(implementationplan.md task 1.10).

Two kinds of test. UNIT tests exercise the collection and cleaning code on
fixtures and canned payloads, so they run in CI now. CORPUS tests
(`needs_corpus`) check the real `data/corpus.db`; they skip until the pilot has
written records, and `evals/report.py` counts a skip as NOT passed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from pipeline.clean import dedupe, language, scrub
from pipeline.collect import base

pytestmark = pytest.mark.p1

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "evals" / "fixtures"


@pytest.fixture(autouse=True)
def _salt():
    base.set_salt("test-salt-not-the-real-one")
    yield
    base.set_salt("")


def _rec(source="reddit", native="t3_x", posts=None, **kw):
    rec, n_del = base.make_record(source=source, native_id=native,
                                  source_url="https://example.org/p", ingest_run_id="run",
                                  collect_query="q", posts=posts or [base.Post("alice", "hi")],
                                  **kw)
    return rec, n_del


# =============================================================== UNIT — collect
def test_P1_INV_3_record_id_is_sha1_of_source_and_native_id():
    rec, _ = _rec(native="t3_abc")
    assert rec["record_id"] == hashlib.sha1("reddit‖t3_abc".encode()).hexdigest()
    assert _rec(native="t3_abc")[0]["record_id"] == rec["record_id"]        # stable
    assert _rec(source="x", native="t3_abc")[0]["record_id"] != rec["record_id"]


def test_P1_INV_3_reingest_is_idempotent(blank_db):
    rec, _ = _rec()
    assert base.write_records(blank_db, [rec]) == (1, 0)
    assert base.write_records(blank_db, [rec]) == (0, 1)
    assert blank_db.execute("SELECT count(*) FROM records").fetchone()[0] == 1


def test_P1_INV_2_no_record_without_permalink():
    with pytest.raises(ValueError, match="permalink"):
        base.make_record(source="reddit", native_id="1", source_url="", ingest_run_id="r",
                         collect_query=None, posts=[base.Post("a", "text")])


def test_every_source_has_its_D1_method(blank_db):
    """A.10: collect_method is set from D-1, never left to the caller."""
    assert set(base.SOURCES) == {"reddit", "gp_help", "play", "appstore", "youtube",
                                 "stackexchange", "hackernews", "x", "quora"}
    for i, src in enumerate(base.SOURCES):
        rec, _ = _rec(source=src, native=str(i))
        assert rec["collect_method"] == base.SOURCE_METHOD[src]
        base.write_records(blank_db, [rec])                      # the schema accepts it
    fallback, _ = _rec(source="gp_help", native="fb", method="apify")
    assert fallback["collect_method"] == "apify"


def test_author_key_is_salted_and_refuses_without_salt():
    k1 = base.author_key("reddit", "SomeUser")
    assert k1 == base.author_key("reddit", " someuser ") and len(k1) == 32
    assert k1 != base.author_key("x", "SomeUser")                 # source-scoped
    assert "someuser" not in k1.lower()
    base.set_salt("a-different-salt")
    assert base.author_key("reddit", "SomeUser") != k1
    base.set_salt("")
    with pytest.raises(RuntimeError, match="AUTHOR_SALT"):
        base.author_key("reddit", "SomeUser")


def test_thread_is_one_record_with_per_post_authors():
    """A.11 / EC-COL-12: post offsets index text_clean exactly, and each post
    keeps its own author — segmentation looks authors up from spans."""
    posts = [base.Post("op", "Can't find the photo of my son's ID card.  Searched 'ID'."),
             base.Post("[deleted]", "[deleted]"),
             base.Post("helper", "Try the Documents category."),
             base.Post("op", "Thanks,\r\n\r\n\r\nthat worked!")]
    rec, n_del = _rec(posts=posts)
    bounds = json.loads(rec["posts_json"])
    assert n_del == 1 and len(bounds) == 3
    assert [rec["text_clean"][b["start"]:b["end"]] for b in bounds] == [
        "Can't find the photo of my son's ID card. Searched 'ID'.",
        "Try the Documents category.", "Thanks,\n\nthat worked!"]
    assert bounds[0]["author_key"] == bounds[2]["author_key"] != bounds[1]["author_key"]
    assert rec["author_key"] == bounds[0]["author_key"]
    single, _ = _rec(posts=[base.Post("a", "one review")])
    assert single["posts_json"] is None


def test_all_deleted_thread_writes_nothing_and_is_counted():
    rec, n_del = _rec(posts=[base.Post("a", "[removed]"), base.Post("b", "  ")])
    assert rec is None and n_del == 2


def test_P1_INV_1_tally_identity(blank_db):
    t = base.Tally()
    r1, d1 = _rec(native="1")
    t.add(blank_db, r1, d1, "q1")
    t.add(blank_db, r1, 0, "q2")                                   # same thread, second query
    t.add(blank_db, *_rec(native="2", posts=[base.Post("a", "[deleted]")]), "q1")
    t.check()
    assert (t.fetched, t.written_new, t.duplicate_in_batch, t.all_deleted) == (3, 1, 1, 1)
    t.fetched += 1
    with pytest.raises(AssertionError, match="identity"):
        t.check()


def test_P1_INV_6_no_truncation_of_long_text():
    long = " ".join(f"word{i}" for i in range(20_000))            # ~130k chars
    rec, _ = _rec(posts=[base.Post("a", long)])
    assert rec["text_clean"] == long and rec["text_raw"] == long


def test_normalise_keeps_case_punctuation_and_line_breaks():
    assert base.normalise("WHY  can't\tI find it!!!\r\n\r\n\r\nplease ") == \
        "WHY can't I find it!!!\n\nplease"


# ================================================================= UNIT — scrub
@pytest.mark.parametrize("text, kind", [
    ("mail me at priya.s+photos@gmail.com please", "EMAIL"),
    ("call +91 98765 43210 if found", "PHONE"),
    ("my number is 9876543210", "PHONE"),
    ("US folks: (415) 555-0132", "PHONE"),
    ("thanks u/photo_hunter_99 for the tip", "HANDLE"),
    ("as @GooglePhotos said", "HANDLE"),
    ("see https://photos.app.goo.gl/AbCdEf123", "URL"),
    ("PAN ABCDE1234F on the card", "PAN"),
    ("aadhaar 1234 5678 9012 photo", "AADHAAR"),
])
def test_P1_INV_4_scrub_replaces_pii_with_typed_placeholders(text, kind):
    out, found = scrub.scrub(text)
    assert kind in found, (text, out)
    assert not scrub.leaks(out), out
    assert "[" in out and out.split()[0] == text.split()[0]        # sentence preserved


@pytest.mark.parametrize("text", [
    "it was 2019 or 2020, maybe December 2022",
    "I have 40,000 photos and 3 phones",
    "searched 'cafe goa 2019' and got nothing",
    "the photo from 12/03/2021 at 10:30",
])
def test_scrub_leaves_ordinary_numbers_and_years_alone(text):
    assert scrub.scrub(text) == (text, [])


def test_scrub_runs_before_the_first_write():
    rec, _ = _rec(posts=[base.Post("a", "email me: x.y@z.com, or u/someone")],
                  thread_context="r/googlephotos | asked by u/someone")
    for field in ("text_raw", "text_clean", "thread_context"):
        assert not scrub.leaks(rec[field]), field


# ============================================================== UNIT — language
@pytest.mark.parametrize("text, lang", [
    ("I can never find old screenshots in Google Photos", "en"),
    ("photo nahi mil rahi, 'shaadi' search kiya kuch nahi aaya", "hi-Latn"),
    ("Goa trip wali cafe ki photo dhoondh rahi hu. Cafe ka naam yaad nahi", "hi-Latn"),
    ("मेरी पुरानी फोटो नहीं मिल रही", "hi"),
    ("🙁🙁", "unknown"),
])
def test_language_tags_and_never_drops(text, lang):
    assert language.detect(text) == lang


# ================================================= PROBE — consensus (never cut)
def _dedupe_fixture():
    return [json.loads(line) for line in (FIX / "dedupe_consensus.jsonl").read_text().splitlines()
            if line.strip()]


def test_P1_PROBE_1_consensus_preserved_and_same_author_collapsed():
    """EC-CLEAN-1, the most important P1 test. 40 distinct authors saying the
    same thing must ALL survive; 5 near-identical posts from one author must
    collapse to 1."""
    rows = [{"record_id": r["record_id"], "source": r["source"], "author_key": r["author_key"],
             "created_at": None, "text": r["text"]} for r in _dedupe_fixture()]
    removed = {loser for loser, _ in dedupe.find_exact(rows)}
    removed |= {loser for loser, _ in
                dedupe.find_near_same_author([r for r in rows if r["record_id"] not in removed])}
    distinct = {r["record_id"] for r in rows if r["author_key"] != "author-same"}
    same = {r["record_id"] for r in rows if r["author_key"] == "author-same"}
    assert not removed & distinct, "cross-author consensus was deleted (EC-CLEAN-1)"
    assert len(removed & same) == 4, f"same-author repeats: {len(removed & same)} of 5 removed"
    assert dedupe.cross_author_echoes(rows) >= 3                   # measured, reported, kept


def test_P1_PROBE_1_through_the_database(blank_db):
    """Same probe end to end: marks in `exclusions`, nothing deleted (A.1)."""
    for r in _dedupe_fixture():
        blank_db.execute("INSERT INTO records (record_id, source, collect_method, source_url,"
                         " author_key, text_raw, text_clean, collected_at, ingest_run_id)"
                         " VALUES (?,?,?,?,?,?,?,?,?)",
                         (r["record_id"], r["source"], "public_scraper_lib", "https://x/y",
                          r["author_key"], r["text"], r["text"], "2026-09-26", "run"))
    dedupe.run(blank_db, "clean-run")
    ex = dict(blank_db.execute("SELECT record_id, reason FROM exclusions").fetchall())
    assert blank_db.execute("SELECT count(*) FROM records").fetchone()[0] == 45
    assert sorted(ex) == [f"dd-same-{j}" for j in range(1, 5)]
    # Variants differing only in case/punctuation are exact; the rest near.
    assert set(ex.values()) <= {"exact_duplicate", "near_duplicate_same_author"}


def test_exact_duplicate_short_text_from_different_authors_is_consensus():
    """The hole in Myntra's rule: two people writing the identical short line
    are two voices. Same author, or long copied text, is a duplicate."""
    short = "search cant find my old photos"
    long = " ".join(["the same long copied paragraph about google photos search"] * 4)
    rows = [{"record_id": "a", "source": "play", "author_key": "p1", "created_at": "1", "text": short},
            {"record_id": "b", "source": "play", "author_key": "p2", "created_at": "2", "text": short},
            {"record_id": "c", "source": "play", "author_key": "p1", "created_at": "3", "text": short},
            {"record_id": "d", "source": "reddit", "author_key": "r1", "created_at": "4", "text": long},
            {"record_id": "e", "source": "x", "author_key": "x1", "created_at": "5", "text": long}]
    assert sorted(dedupe.find_exact(rows)) == [("c", "a"), ("e", "d")]


def test_near_dupe_never_touches_records_without_an_author():
    rows = [{"record_id": str(i), "source": "play", "author_key": None, "created_at": None,
             "text": "google photos search cannot find my old screenshots at all"}
            for i in range(3)]
    assert dedupe.find_near_same_author(rows) == []


# ================================================================ CORPUS — gate
@pytest.fixture(scope="module")
def con(corpus):
    return corpus


@pytest.mark.needs_corpus
def test_P1_INV_1_accounting_identity(con):
    """No record vanishes unlogged. Per collect run: fetched == written +
    already present + all-deleted + surfaced twice. Across the corpus: every
    record is kept or excluded, and the runs' new-row counts sum to the table."""
    runs = con.execute("SELECT run_id, n_output, params_json FROM runs"
                       " WHERE stage LIKE 'collect-%' AND status='ok'").fetchall()
    assert runs, "no successful collect run"
    for r in runs:
        t = json.loads(r["params_json"])["tally"]
        assert t["fetched"] == (t["written_new"] + t["already_present"] + t["all_deleted"]
                                + t["duplicate_in_batch"]), r["run_id"]
        assert r["n_output"] == t["written_new"]
    n = con.execute("SELECT count(*) FROM records").fetchone()[0]
    written = con.execute("SELECT count(*) FROM records WHERE ingest_run_id IN"
                          " (SELECT run_id FROM runs WHERE stage LIKE 'collect-%')").fetchone()[0]
    assert written == n, "records exist that no collect run accounts for"


@pytest.mark.needs_corpus
def test_P1_INV_2_source_url_and_text_present(con):
    bad = con.execute("SELECT count(*) FROM records WHERE trim(source_url)='' OR"
                      " trim(text_raw)='' OR trim(text_clean)=''").fetchone()[0]
    assert bad == 0


@pytest.mark.needs_corpus
def test_P1_INV_3_record_ids_match_their_definition(con):
    rows = con.execute("SELECT record_id, source, native_id FROM records").fetchall()
    wrong = [r["record_id"] for r in rows
             if r["record_id"] != base.record_id(r["source"], r["native_id"])]
    assert not wrong, wrong[:5]


PERMALINK_PII = re.compile(r"(?:x|twitter)\.com/(?!i/)[^/]+/status|/answer/|reddit\.com/u(?:ser)?/")


@pytest.mark.needs_corpus
def test_P1_INV_4_zero_pii_in_the_committed_corpus(con):
    hits = []
    for r in con.execute("SELECT record_id, text_raw, text_clean, thread_context, source_url"
                         " FROM records"):
        for f in ("text_raw", "text_clean", "thread_context"):
            if r[f] and scrub.leaks(r[f]):
                hits.append((r["record_id"], f, scrub.leaks(r[f])))
        # Permalinks can carry a handle too: x.com/<user>/status, Quora's
        # /answer/<Name>, reddit /user/ (found 2026-09-26).
        if PERMALINK_PII.search(r["source_url"]):
            hits.append((r["record_id"], "source_url", "handle in permalink"))
    assert not hits, hits[:5]


@pytest.mark.needs_corpus
def test_P1_INV_5_exclusion_reasons_in_enum(con):
    allowed = {"deleted", "too_short", "low_quality", "exact_duplicate",
               "near_duplicate_same_author", "lexicon_rejected", "out_of_window", "no_story",
               "span_unverified", "coding_failed", "model_refusal"}
    found = {r[0] for r in con.execute("SELECT DISTINCT reason FROM exclusions")}
    assert found <= allowed


@pytest.mark.needs_corpus
def test_P1_INV_6_no_silent_truncation(con):
    """Collectors store full text. A text ending in an ellipsis or a 'read
    more' marker, or sitting exactly on a round API cap, is a truncation."""
    caps = {280, 500, 1000, 2000, 4000, 5000, 10000}
    bad = [r["native_id"] for r in con.execute("SELECT source, native_id, text_raw FROM records")
           if (r["text_raw"].rstrip().endswith(("… (more)", "...more", "Read more"))
               or len(r["text_raw"]) in caps)
           and r["native_id"] not in VERIFIED_FULL_LENGTH
           and len(r["text_raw"]) != PLATFORM_MAX.get(r["source"])]
    assert not bad, bad[:5]
    # A platform maximum is only an excuse if the collector is not ALSO capping:
    # X allows long posts to some users, so longer X text must exist.
    assert con.execute("SELECT count(*) FROM records WHERE source='x' AND"
                       " length(text_raw) > 280").fetchone()[0] > 0, "X text capped at 280"
    assert con.execute("SELECT max(length(text_raw)) FROM records WHERE source='play'"
                       ).fetchone()[0] <= 500, "Play text longer than Play allows?"


# The platform's OWN maximum, not a collector cap: Google Play reviews stop at
# 500 characters; a standard X post at 280.
PLATFORM_MAX = {"play": 500, "x": 280}


# Records that sit exactly on a cap and were CHECKED to be whole, with how.
VERIFIED_FULL_LENGTH = {
    "1466829442806947842": "X post from Dec 2021 — before X allowed posts over 280 characters",
    "49797968": "HN comment; the item API returns the same 280-character text",
    # GP Help: the 'Read more' closes a Help Center ARTICLE PREVIEW a Product
    # Expert embedded in a reply — Google truncates those by design and links
    # the article. Clicking it does not expand in place (checked). Every
    # user-written post in the thread is whole.
    "463935872": "GP Help thread; 'Read more' ends an embedded Help Center article preview",
    "469005917": "GP Help thread; 'Read more' ends embedded Help Center article previews",
}


@pytest.mark.needs_corpus
def test_P1_MET_1_every_configured_source_contributed(con):
    got = {r[0] for r in con.execute("SELECT DISTINCT source FROM records")}
    missing = set(base.SOURCES) - got
    assert not missing, f"sources with zero records (EC-COL-1): {sorted(missing)}"


@pytest.mark.needs_corpus
def test_P1_MET_2_distinct_authors_reported_per_source(con):
    rows = con.execute("SELECT source, count(*) AS n, count(DISTINCT author_key) AS a"
                       " FROM records GROUP BY source").fetchall()
    for r in rows:
        assert r["a"] > 0, f"{r['source']}: no author keys at all"


@pytest.mark.needs_corpus
def test_P1_MET_4_collect_method_matches_D1(con):
    rows = con.execute("SELECT source, collect_method, count(*) FROM records"
                       " GROUP BY 1, 2").fetchall()
    for src, method, _ in rows:
        assert method == base.SOURCE_METHOD[src] or (src == "gp_help" and method == "apify")


@pytest.mark.needs_corpus
def test_P1_PROBE_2_collector_field_survival(con):
    """EC-COL-13/14: an Apify actor or the GP Help renderer changing shape shows
    up as records that arrive but are hollow. Per source: author and date on
    ≥ 80% of records, and threads really carry more than one post where the
    source is threaded."""
    threaded = {"reddit", "gp_help", "stackexchange", "youtube"}
    for r in con.execute("SELECT source, count(*) AS n, sum(author_key IS NOT NULL) AS a,"
                         " sum(created_at IS NOT NULL) AS d, sum(posts_json IS NOT NULL) AS t,"
                         " avg(length(text_clean)) AS len FROM records GROUP BY source"):
        assert r["a"] / r["n"] >= 0.8, f"{r['source']}: authors on {r['a']}/{r['n']}"
        assert r["d"] / r["n"] >= 0.8, f"{r['source']}: dates on {r['d']}/{r['n']}"
        if r["source"] in threaded:
            assert r["t"] > 0, f"{r['source']}: no record carries more than one post"
        if r["source"] == "gp_help":
            assert r["len"] >= 150, "GP Help records look like titles only (EC-COL-14)"


@pytest.mark.needs_corpus
def test_distinct_author_share_is_not_dominated(con):
    """EC-COL-6: report, and fail only if one author wrote > 5% of a source."""
    for src, in con.execute("SELECT DISTINCT source FROM records").fetchall():
        c = Counter(r[0] for r in con.execute(
            "SELECT author_key FROM records WHERE source=? AND author_key IS NOT NULL", (src,)))
        total = sum(c.values())
        if total >= 100:
            assert c.most_common(1)[0][1] / total <= 0.05, src


# ================================================================== app — P1
def test_P4_INV_1_data_bank_formats_no_share_itself():
    """Every share on the page comes from lib.evidence.share(); a view that
    formats a percentage itself can drop the denominator ([CTX] §15.5)."""
    src = (ROOT / "app" / "views" / "data_bank.py").read_text()
    assert not re.search(r":\.\d*%|\{[^}]*%\}|\* ?100\b", src), "view formats a share itself"


def test_data_bank_is_in_the_nav_and_planned_no_longer_lists_it():
    from lib import nav
    assert "data_bank.py" in [p[0] for p in nav.PAGES]
    assert "Data Bank" not in [t for t, _ in nav.PLANNED]


@pytest.mark.needs_corpus
def test_data_bank_page_renders_without_exception(con):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "views" / "data_bank.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    assert at.title and at.title[0].value == "Data Bank"


@pytest.mark.needs_corpus
def test_funnel_tables_balance_and_carry_run_ids(con):
    rows = con.execute("SELECT source, step, n, denom, run_id FROM analysis_funnel").fetchall()
    assert rows, "analysis_funnel is empty — run pipeline.analyse.funnel"
    by = {}
    for r in rows:
        assert r["run_id"] and r["denom"] >= r["n"] >= 0
        by.setdefault(r["source"], {})[r["step"]] = r["n"]
    for s, steps in by.items():
        excluded = sum(v for k, v in steps.items() if k.startswith("excluded:"))
        assert steps["collected"] >= steps["kept"], s
        assert steps["collected"] - steps["kept"] <= excluded, s   # a record may carry 2 marks


# ============================================ UNIT — collector mappings (EC-COL-13)
# Synthetic payloads in the shapes the 2026-09-26 probes returned. The real raw
# payloads are unscrubbed and never committed (data/raw/ is gitignored).
def test_reddit_mapping_flattens_nested_comments_and_keys_on_reddit_id():
    from pipeline.collect import apify_sources as a
    item = {"id": "APIFY-RUN-ULID", "reddit_id": "abc123", "subreddit": "googlephotos",
            "title": "Can't find a photo of a receipt", "body": "Searched 'receipt', nothing.",
            "author": "op_user", "reddit_url": "https://www.reddit.com/r/googlephotos/comments/abc123/x/",
            "created_utc": "2026-08-01T18:00:45.000Z", "score": 3,
            "comments": [{"reddit_id": "c1", "author": "helper", "body": "Try 'bill'.",
                          "created_utc": "2026-08-01T19:00:00Z",
                          "replies": [{"reddit_id": "c2", "author": "op_user",
                                       "body": "'bill' worked, thanks!", "replies": []}]},
                         {"reddit_id": "c3", "author": "AutoModerator", "body": "Rule 1",
                          "replies": []}]}
    rec, n_del, bots = a.reddit_records(item, query="q", run_id="r")
    bounds = json.loads(rec["posts_json"])
    assert rec["native_id"] == "t3_abc123"                   # never Apify's per-run id
    assert len(bounds) == 3 and bots == 1                     # nested reply kept, bot dropped
    assert rec["text_clean"].startswith("Can't find a photo of a receipt\n\nSearched")
    assert bounds[0]["author_key"] == bounds[2]["author_key"] # OP's follow-up, same author
    assert rec["collect_method"] == "apify" and rec["created_at"].startswith("2026-08-01")


def test_reddit_payload_asks_for_post_text_explicitly():
    from pipeline.collect import apify_sources as a
    p = a.reddit_payload("can't find photo", 2)
    assert p["includePostText"] is True and p["includeComments"] is True


def test_x_and_quora_mappings():
    from pipeline.collect import apify_sources as a
    x, _, _ = a.x_records({"id": "1370774199015456772", "url": "https://x.com/u/status/1",
                           "fullText": "Google Photos search can't find my old receipt",
                           "createdAt": "Sat Mar 13 16:30:11 +0000 2021",
                           "author": {"userName": "someone"}, "likeCount": 2},
                          query="q", run_id="r")
    assert x["created_at"] == "2021-03-13T16:30:11+00:00" and x["author_key"]
    assert x["source_url"] == "https://x.com/i/status/1370774199015456772"     # no handle
    long_x, _, _ = a.x_records({"id": "9", "fullText": "clipped at 280…", "text": "the whole post, "
                                "much longer than the clipped field", "createdAt": None,
                                "author": {"userName": "u"}}, query="q", run_id="r")
    assert long_x["text_clean"].startswith("the whole post")                   # the longer field
    assert a.x_records({"id": "2", "isRetweet": True}, query="q", run_id="r")[0] is None
    qa, _, _ = a.quora_records({"url": "https://quora.com/q", "title": "How to find old photos?",
                                "answer": {"id": 13299264, "url": "https://quora.com/a",
                                           "text": "Use the search bar with a place name.",
                                           "posted_at": "2015-06-15T09:13:57Z",
                                           "author": {"name": "A Person"}}},
                               query="q", run_id="r")
    assert qa["native_id"] == "13299264" and qa["thread_context"] == "How to find old photos?"
    qn, _, _ = a.quora_records({"url": "https://www.quora.com/How-do-I/answer/Jane-Doe",
                                "answer": {"id": 7, "text": "Search by place.",
                                           "url": "https://www.quora.com/How-do-I/answer/Jane-Doe"}},
                               query="q", run_id="r")
    assert qn["source_url"] == "https://www.quora.com/How-do-I#answer-7"


def test_gp_help_mapping_drops_the_promoted_duplicate_and_keeps_authors():
    from pipeline.collect import gp_help
    ans = {"author": "Expert", "date": "9/21/2026, 7:53:44 AM", "text": "Check Archive."}
    data = {"title": "Can't find my photo", "posts": [
        {"author": "Asker", "date": "9/21/2026, 2:51:13 AM", "text": "It was from 2019."},
        ans, dict(ans), {"author": "Asker", "date": "9/21/2026, 10:29:12 AM", "text": "Found it!"}]}
    rec, _ = gp_help.thread_record("468864665", data, run_id="r", query="q")
    bounds = json.loads(rec["posts_json"])
    assert len(bounds) == 3                                     # duplicate kept once
    assert rec["text_clean"].startswith("Can't find my photo\n\nIt was from 2019.")
    assert rec["created_at"] == "2026-09-21T02:51:13+00:00"
    assert gp_help.SCREEN.search("I can't find my photos from Goa")
    assert not gp_help.SCREEN.search("Storage full, stop asking me to pay")


def test_store_and_official_api_mappings():
    from pipeline.collect import official_apis as o
    from pipeline.collect import stores
    play, _ = stores.play_record({"reviewId": "gp:1", "userName": "R", "content": "search is bad",
                                  "score": 2, "at": "2026-09-01T10:00:00"},
                                 lang="en", country="in", run_id="r")
    assert play["region_hint"] is None and play["rating"] == 2   # country param is not region
    lab = {"label": "x"}
    ios, _ = stores.appstore_record({"id": {"label": "99"}, "title": {"label": "Search"},
                                     "content": {"label": "Can't find anything"},
                                     "im:rating": {"label": "1"}, "author": {"name": lab},
                                     "updated": {"label": "2026-09-01T10:00:00-07:00"}},
                                    country="in", run_id="r")
    assert ios["native_id"] == "in-99" and ios["region_hint"] == "IN"
    hn, _ = o.hn_record({"objectID": "5", "author": "h", "comment_text": "<p>Photos search &amp; "
                         "dates</p>", "created_at": "2024-01-01T00:00:00Z"}, query="q", run_id="r")
    assert hn["text_clean"] == "Photos search & dates"
    assert o.html_to_text("<p>a</p><p>b &lt;3</p>") == "a\n\nb <3"


# ========================================================= UNIT — prefilter (EC-PRE)
def test_prefilter_passes_every_authored_core_story():
    """A gate that rejects the project's own hand-written retrieval stories —
    English, utility, sentimental, Hinglish — would certainly reject real ones.
    Free, deterministic; the paid measurement is P1-MET-3."""
    from pipeline.clean import prefilter
    lex = prefilter._lexicon()
    rows = [json.loads(line) for line in (FIX / "stories_authored.jsonl").read_text().splitlines()
            if line.strip()]
    rows += [{"id": r["id"], "text": r["text"], "expected": {"bucket": r["expected_bucket"]}}
             for r in map(json.loads, (FIX / "bucket_boundary.jsonl").read_text().splitlines())]
    missed = [r["id"] for r in rows
              if r["expected"]["bucket"] == "core" and not prefilter.passes(r["text"], lex)[0]]
    assert not missed, f"core stories the gate would reject: {missed}"


@pytest.mark.parametrize("text", ["Storage is full, stop asking me to pay.",
                                  "The new editor keeps crashing when I try to crop.",
                                  "Love this app, five stars"])
def test_prefilter_rejects_plainly_off_topic_text(text):
    from pipeline.clean import prefilter
    assert not prefilter.passes(text)[0]


@pytest.mark.needs_corpus
def test_P1_MET_3_lexicon_recall_probe_recorded_and_passed(con):
    """T-4 ≤ 5%: the probe must have run on the committed corpus and passed."""
    row = con.execute("SELECT params_json FROM runs WHERE stage='probe-lexicon-recall'"
                      " AND status='ok' ORDER BY started_at DESC LIMIT 1").fetchone()
    assert row, "P1-MET-3 has not run — python -m pipeline.validate.lexicon_probe"
    res = json.loads(row[0])["result"]
    assert res["n"] >= 150 and res["t4_core_share"] <= 0.05, res
