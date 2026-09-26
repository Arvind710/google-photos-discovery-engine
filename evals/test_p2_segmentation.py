"""P2 gate — Segmentation (evals.md §7).

UNIT tests pin the deterministic half of Pass 1 — anchors located verbatim,
long threads split on post boundaries and never cut, overlaps and unfound
stories discarded AND counted, authorship looked up from the post — and run in
CI. CORPUS tests (`needs_corpus`) check the stored stories and read the
measured metrics from the committed artifacts in `data/artifacts/`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from pipeline.segment import stories as seg

pytestmark = pytest.mark.p2

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "artifacts"


def _rec(*posts, rid="r1"):
    return seg._fixture_record(rid, "reddit", list(posts))


# ======================================================================= UNIT
def test_locate_is_exact_within_the_named_post():
    rec = _rec(("op", "I can’t find the photo of my son's ID card. Searched 'ID', nothing."),
               ("helper", "Try the Documents category, I can’t find mine either."))
    a, b = seg.locate(rec, 1, "I can’t find the photo", "Searched 'ID', nothing.")
    assert rec.text[a:b] == rec.text[:rec.posts[0]["end"]]
    # Straight vs curly apostrophe and a run of whitespace are the only tolerance.
    assert seg.locate(rec, 1, "I can't  find the photo", "nothing.") is not None
    # Another post's words are never matched from this post.
    assert seg.locate(rec, 1, "Try the Documents", "either.") is None
    assert seg.locate(rec, 2, "Try the Documents", "either.") is not None
    # Paraphrase, case change or a post that does not exist → not found.
    assert seg.locate(rec, 1, "i cannot find the photo", "nothing.") is None
    assert seg.locate(rec, 3, "I can’t", "nothing.") is None


def test_locate_end_is_searched_from_the_start_anchor():
    rec = _rec(("op", "It was there. Later I searched again and it was there."))
    a, b = seg.locate(rec, 1, "Later I searched", "it was there.")
    assert rec.text[a:b] == "Later I searched again and it was there."


def test_long_records_split_on_post_boundaries_and_are_never_cut():
    posts = [(f"u{i}", ("word " * 900).strip()) for i in range(6)]        # ~4,500 chars each
    posts.append(("big", "x" * 25_000))                                   # longer than a chunk
    rec = _rec(*posts)
    units = seg.units_of(rec)
    covered = [i for u in units for i in u.post_idx]
    assert covered == list(range(len(posts)))                             # every post, once, in order
    assert all(seg.unit_chars(u) <= seg.CHUNK_CHARS or len(u.post_idx) == 1 for u in units)
    assert any(seg.unit_chars(u) == 25_000 for u in units)               # the long post, whole
    assert units[1].first_post == units[0].post_idx[-1] + 2


def test_rendered_post_numbers_are_global_across_parts():
    rec = _rec(*[(f"u{i}", ("word " * 900).strip()) for i in range(4)])
    parts = seg.units_of(rec)
    seg.pack(parts)
    assert "[post 3]" in seg.render(parts[1]) and "[post 1]" not in seg.render(parts[1])


def test_pack_respects_size_and_count_and_numbers_locally():
    recs = [_rec(("a", f"review number {i} " * 20), rid=f"r{i}") for i in range(30)]
    reqs = seg.pack([u for r in recs for u in seg.units_of(r)])
    assert all(len(q) <= seg.PACK_RECORDS for q in reqs)
    assert all(sum(seg.unit_chars(u) for u in q) <= seg.PACK_CHARS for q in reqs)
    assert [u.uid for u in reqs[0]] == [f"R{k}" for k in range(1, len(reqs[0]) + 1)]
    assert sum(len(q) for q in reqs) == 30


def _story(post, start, end, bucket="core", stage=6):
    return {"post": post, "start": start, "end": end, "bucket": bucket, "reason": "r",
            "confidence": 0.8, "reaches_stage": stage}


def test_merge_counts_unfound_and_overlapping_stories_and_looks_up_authors():
    rec = _rec(("op", "First target was a receipt, searched receipt, nothing. Second target a "
                      "beach photo, gave up."),
               ("helper", "My own story: lost my PAN photo, found it in Documents."))
    res = seg.merge(rec, [[_story(1, "First target", "receipt, nothing."),
                           _story(1, "Second target", "gave up."),
                           _story(1, "searched receipt", "nothing."),              # overlaps #1
                           _story(1, "invented words", "not here"),              # not in text
                           _story(2, "My own story", "in Documents.", stage=99)]])
    assert res.returned == 5 and len(res.stories) == 3
    assert len(res.unlocated) == 1 and len(res.overlapping) == 1
    assert [s.author_key for s in res.stories] == ["op", "op", "helper"]
    assert res.stories[-1].reaches_stage == 10                               # clamped 0–10
    for s in res.stories:                                                    # T-1 by construction
        assert rec.text[s.char_start:s.char_end] == s.text


def test_a_part_the_model_skipped_is_counted_not_silent():
    rec = _rec(("op", "some text about a photo"))
    assert seg.merge(rec, [None]).missing_parts == 1


def test_parse_output_marks_ids_the_model_skipped():
    reqs = seg.pack([u for r in (_rec(("a", "x"), rid="a"), _rec(("b", "y"), rid="b"))
                     for u in seg.units_of(r)])
    got = seg.parse_output(json.dumps({"records": [{"id": "R1", "stories": []}]}), reqs[0])
    assert got == {"R1": [], "R2": None}


def test_prompt_carries_the_ctx_calibration_table_verbatim():
    ctx = (ROOT / "Docs" / "NextLeap Grad Projects.code-workspace.md").read_text()
    table = [ln for ln in ctx.splitlines() if ln.startswith("| \"")]
    assert len(table) == 5
    prompt = seg.PROMPT.read_text()
    assert all(row in prompt for row in table)
    assert "untrusted" in prompt and "GENEROUSLY" in prompt


def test_record_bucket_scores_no_story_as_irrelevant():
    rec = _rec(("a", "Storage is full"))
    assert seg.record_bucket(seg.merge(rec, [[]])) == "irrelevant"


# ===================================================================== CORPUS
@pytest.fixture(scope="module")
def con(corpus):
    if corpus.execute("SELECT count(*) FROM stories").fetchone()[0] == 0:
        pytest.skip("no stories yet — Pass 1 has not been collected")
    return corpus


def _latest(prefix: str, **match) -> dict:
    for p in sorted(ART.glob(f"{prefix}_*.json"), reverse=True):
        d = json.loads(p.read_text())
        if all(d.get(k) == v for k, v in match.items()):
            return d
    pytest.fail(f"no {prefix} artifact matching {match}")


@pytest.mark.needs_corpus
def test_P2_INV_1_every_story_is_verbatim_text_clean(con):
    """T-1 = 100%, absolute."""
    bad = con.execute("SELECT count(*) FROM stories s JOIN records r USING (record_id)"
                      " WHERE substr(r.text_clean, s.char_start + 1, s.char_end - s.char_start)"
                      " <> s.text").fetchone()[0]
    assert bad == 0


@pytest.mark.needs_corpus
def test_P2_INV_2_spans_do_not_overlap_and_fit_the_record(con):
    bad = con.execute("SELECT count(*) FROM stories a JOIN stories b ON a.record_id = b.record_id"
                      " AND a.ordinal < b.ordinal AND b.char_start < a.char_end").fetchone()[0]
    out = con.execute("SELECT count(*) FROM stories s JOIN records r USING (record_id)"
                      " WHERE s.char_end > length(r.text_clean)").fetchone()[0]
    assert bad == 0 and out == 0


@pytest.mark.needs_corpus
def test_P2_INV_3_and_4_bucket_reason_confidence_stage(con):
    bad = con.execute("SELECT count(*) FROM stories WHERE bucket NOT IN ('core','adjacent',"
                      "'irrelevant') OR trim(bucket_reason) = '' OR bucket_conf NOT BETWEEN 0 AND 1"
                      " OR reaches_stage NOT BETWEEN 0 AND 10").fetchone()[0]
    assert bad == 0


@pytest.mark.needs_corpus
def test_P2_INV_5_every_segmented_record_has_stories_or_a_logged_reason(con):
    """A record Pass 1 read has ≥ 1 story, or is marked no_story /
    span_unverified at stage `segment` — never silently dropped (EC-SEG-7)."""
    n_read = con.execute("SELECT count(*) FROM records WHERE record_id NOT IN (SELECT record_id"
                         " FROM exclusions WHERE story_id IS NULL AND stage <> 'segment')"
                         ).fetchone()[0]
    accounted = con.execute(
        "SELECT count(*) FROM (SELECT record_id FROM stories UNION SELECT record_id FROM"
        " exclusions WHERE stage='segment' AND story_id IS NULL)").fetchone()[0]
    assert accounted == n_read


@pytest.mark.needs_corpus
def test_P2_INV_6_author_is_the_author_of_the_post_the_story_sits_in(con):
    wrong = 0
    for r in con.execute("SELECT s.char_start, s.author_key, r.posts_json, r.author_key AS ra"
                         " FROM stories s JOIN records r USING (record_id)"):
        if r["posts_json"]:
            post = next(p for p in json.loads(r["posts_json"])
                        if p["start"] <= r["char_start"] < p["end"])
            wrong += post["author_key"] != r["author_key"]
        else:
            wrong += r["author_key"] != r["ra"]
    assert wrong == 0


@pytest.mark.needs_corpus
def test_video_only_stories_are_adjacent(con):
    bad = con.execute("SELECT count(*) FROM stories WHERE bucket_reason LIKE"
                      " 'video_out_of_scope%' AND bucket <> 'adjacent'").fetchone()[0]
    assert bad == 0


@pytest.mark.needs_corpus
def met_or_limitation(met_id: str, value: float, threshold: float, *, higher_is_better=True):
    """implementationplan.md §0.3: a measured metric below threshold after its
    remediation loop passes ONLY as a stated limitation — recorded in
    evals/limitations.yaml with the value this artifact measured, the iterations
    spent, the mitigation and where it is disclosed. Absolute thresholds never
    come through here."""
    ok = value >= threshold if higher_is_better else value <= threshold
    if ok:
        return
    lim = (yaml.safe_load((ROOT / "evals" / "limitations.yaml").read_text()) or {}).get(met_id)
    assert lim, f"{met_id} = {value:.3f} misses {threshold} and is not a stated limitation"
    assert abs(float(lim["measured"]) - value) < 0.005, (met_id, lim["measured"], value)
    assert lim["iterations"] >= 3 or lim.get("why_fewer"), met_id
    assert lim["mitigation"] and lim["disclosed_in"], met_id


def test_P2_MET_3_fixture_story_counts_and_P2_PROBE_1_bucket_boundary():
    """Scored on the pipeline as run on the corpus: gpt-5-mini finds, gpt-5 confirms."""
    fx = _latest("segment_fixtures", pipeline="find+confirm")["summary"]
    assert fx["P2_MET_3_count_exact"] >= 0.85, fx
    assert fx["T9_bucket_boundary"] >= 0.90, fx
    assert fx["unlocated"] == 0, fx


@pytest.mark.needs_corpus
def test_P2_MET_1_and_2_dual_model_agreement():
    d = _latest("segment_dual", with_stories=True)
    met_or_limitation("P2-MET-1", d["T5_count_agreement"], 0.80)
    met_or_limitation("P2-MET-2", d["T6_band_agreement"], 0.75)


@pytest.mark.needs_corpus
def test_P2_MET_4_zero_story_rate_among_lexicon_hits(con):
    """≤ 25%, else the gate in front of Pass 1 is too broad (EC-SEG-7)."""
    read = con.execute("SELECT count(*) FROM (SELECT record_id FROM stories UNION SELECT"
                       " record_id FROM exclusions WHERE stage='segment')").fetchone()[0]
    zero = con.execute("SELECT count(*) FROM exclusions WHERE stage='segment' AND"
                       " reason='no_story' AND story_id IS NULL").fetchone()[0]
    met_or_limitation("P2-MET-4", zero / read, 0.25, higher_is_better=False)


def test_segment_module_formats_no_share_itself():
    src = (ROOT / "pipeline" / "segment" / "stories.py").read_text()
    assert not re.search(r"\* ?100\b", src)
