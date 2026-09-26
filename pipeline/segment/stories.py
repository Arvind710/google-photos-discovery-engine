"""Pass 1 — records → retrieval stories, bucketed, with `reaches_stage`
(implementationplan.md §4, architecture.md §5.3). gpt-5-mini.

The model never copies a story. It returns the post number and the story's
first and last few words (`prompts/segment_v1.md`); the span is then LOCATED in
`text_clean` by an exact search, so every stored story is verbatim by
construction (T-1, EC-SEG-3) and costs a fraction of the output tokens.
Matching tolerates only what cannot change a word: runs of whitespace, and
straight vs curly quotes. Case, spelling and punctuation must match.

Authorship is LOOKED UP, never asked: a story's author is the author of the post
its span sits in (`records.posts_json`, A.11, EC-COL-12).

Packing (the $15 ceiling). The prompt is ~1,700 tokens and most records are
short reviews, so a request carries several records (≤ PACK_CHARS of record
text, ≤ PACK_RECORDS records). A record longer than CHUNK_CHARS is split on
POST boundaries into parts (EC-COL-4, A.5): never truncated, parts merged back
under one record_id.

    python -m pipeline.segment.stories fixtures [--effort low]
    python -m pipeline.segment.stories estimate
    python -m pipeline.segment.stories submit           # Batch API
    python -m pipeline.segment.stories collect          # poll, then write
    python -m pipeline.segment.stories dual --n 60      # T-5 / T-6
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "segment_v1.md"
PROMPT_VERSION = "segment_v1"
FIX = ROOT / "evals" / "fixtures"
ARTIFACTS = ROOT / "data" / "artifacts"
BATCH_DIR = ROOT / "data" / "batch"          # gitignored: request/response files
MODEL = "gpt-5-mini"
SECOND_MODEL = "gpt-5"                       # T-5/T-6 second coder: a different model
EFFORT = "low"
ESTIMATE_USD = 1.20                          # architecture.md §8, Pass 1

CHUNK_CHARS = 10_000                         # ~2,500 tokens (EC-COL-4)
PACK_CHARS = 10_000
PACK_RECORDS = 12
CONTEXT_CHARS = 200

BUCKETS = ("core", "adjacent", "irrelevant")
STORY = {"type": "object", "additionalProperties": False,
         "properties": {"post": {"type": "integer"}, "start": {"type": "string"},
                        "end": {"type": "string"}, "bucket": {"type": "string", "enum": list(BUCKETS)},
                        "reason": {"type": "string"}, "confidence": {"type": "number"},
                        "reaches_stage": {"type": "integer"}},
         "required": ["post", "start", "end", "bucket", "reason", "confidence", "reaches_stage"]}
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"records": {"type": "array", "items": {
              "type": "object", "additionalProperties": False,
              "properties": {"id": {"type": "string"},
                             "stories": {"type": "array", "items": STORY}},
              "required": ["id", "stories"]}}},
          "required": ["records"]}


# ------------------------------------------------------------------ units
@dataclass
class Record:
    record_id: str
    source: str
    text: str                                 # text_clean — the ONLY span source (EC-CLEAN-4)
    posts: list[dict]                         # [{"author_key", "start", "end"}], global order
    context: str | None = None


@dataclass
class Unit:
    """One record, or one part of a long one. `first_post` is the 1-based
    global number of its first post."""
    record: Record
    part: int
    first_post: int
    post_idx: list[int]
    uid: str = ""


def record_from_row(r) -> Record:
    posts = json.loads(r["posts_json"]) if r["posts_json"] else [
        {"author_key": r["author_key"], "start": 0, "end": len(r["text_clean"])}]
    return Record(r["record_id"], r["source"], r["text_clean"], posts, r["thread_context"])


def units_of(rec: Record) -> list[Unit]:
    """Split on post boundaries into parts of ≤ CHUNK_CHARS. A single post
    longer than that is a part on its own — never cut (EC-COL-4)."""
    parts, cur, size = [], [], 0
    for i, p in enumerate(rec.posts):
        n = p["end"] - p["start"]
        if cur and size + n > CHUNK_CHARS:
            parts.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        parts.append(cur)
    return [Unit(rec, k, idx[0] + 1, idx) for k, idx in enumerate(parts)]


def _attr(s: str | None) -> str:
    return re.sub(r"[\"<>\n\r]+", " ", s or "")[:CONTEXT_CHARS].strip()


def render(u: Unit) -> str:
    ctx = f' context="{_attr(u.record.context)}"' if u.record.context else ""
    part = f' part="{u.part + 1}"' if len(units_of(u.record)) > 1 else ""
    body = "\n".join(f"[post {i + 1}]\n{u.record.text[u.record.posts[i]['start']:u.record.posts[i]['end']]}"
                     for i in u.post_idx)
    return f'<record id="{u.uid}" source="{u.record.source}"{ctx}{part}>\n{body}\n</record>'


def unit_chars(u: Unit) -> int:
    return sum(u.record.posts[i]["end"] - u.record.posts[i]["start"] for i in u.post_idx)


def pack(units: list[Unit]) -> list[list[Unit]]:
    """Greedy, in order. Ids are local to a request (R1, R2, …)."""
    reqs, cur, size = [], [], 0
    for u in units:
        n = unit_chars(u)
        if cur and (size + n > PACK_CHARS or len(cur) >= PACK_RECORDS):
            reqs.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += n
    if cur:
        reqs.append(cur)
    for req in reqs:
        for k, u in enumerate(req, 1):
            u.uid = f"R{k}"
    return reqs


def request_body(req: list[Unit], *, model: str = MODEL, effort: str = EFFORT,
                 system: str | None = None) -> dict:
    return {"model": model, "instructions": system or PROMPT.read_text(),
            "reasoning": {"effort": effort},
            "input": "\n\n".join(render(u) for u in req),
            "text": {"format": {"type": "json_schema", "name": "segmentation",
                                "schema": SCHEMA, "strict": True}}}


# ---------------------------------------------------------------- locating
_QUOTES = {"'": "['’‘`]", "’": "['’‘`]", "‘": "['’‘`]", '"': "[\"“”]", "“": "[\"“”]", "”": "[\"“”]"}


def _pattern(anchor: str) -> re.Pattern | None:
    words = anchor.split()
    if not words:
        return None
    esc = [re.sub(r"\\?(['’‘\"“”])", lambda m: _QUOTES[m.group(1)], re.escape(w)) for w in words]
    return re.compile(r"\s+".join(esc))


def locate(rec: Record, post_no: int, start: str, end: str) -> tuple[int, int] | None:
    """(char_start, char_end) in rec.text, end exclusive, or None. Searched
    inside the named post only; the end anchor is searched from the start."""
    if not 1 <= post_no <= len(rec.posts):
        return None
    p = rec.posts[post_no - 1]
    ps, pe = _pattern(start), _pattern(end)
    if ps is None or pe is None:
        return None
    m = ps.search(rec.text, p["start"], p["end"])
    if not m:
        return None
    me = pe.search(rec.text, m.start(), p["end"])
    if not me:
        return None
    return m.start(), max(me.end(), m.end())


# ---------------------------------------------------------------- results
@dataclass
class Located:
    char_start: int
    char_end: int
    text: str
    author_key: str | None
    post: int
    bucket: str
    reason: str
    confidence: float
    reaches_stage: int


@dataclass
class RecordResult:
    record: Record
    returned: int = 0                          # stories the model returned
    stories: list[Located] = field(default_factory=list)
    unlocated: list[dict] = field(default_factory=list)
    overlapping: list[dict] = field(default_factory=list)
    missing_parts: int = 0                     # a part the model gave no answer for


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def merge(rec: Record, answers: list[list[dict] | None]) -> RecordResult:
    """All parts' stories → one record, located, ordered, overlap-free
    (P2-INV-2). A story whose anchors are not found, or that overlaps an
    earlier one, is discarded and COUNTED — never silently kept or dropped."""
    res = RecordResult(rec)
    found: list[Located] = []
    for ans in answers:
        if ans is None:
            res.missing_parts += 1
            continue
        for s in ans:
            res.returned += 1
            span = locate(rec, s["post"], s["start"], s["end"])
            if span is None:
                res.unlocated.append(s)
                continue
            a, b = span
            found.append(Located(a, b, rec.text[a:b], rec.posts[s["post"] - 1]["author_key"],
                                 s["post"], s["bucket"], s["reason"].strip() or "—",
                                 float(_clamp(s["confidence"], 0, 1)),
                                 int(_clamp(s["reaches_stage"], 0, 10))))
    for st in sorted(found, key=lambda x: (x.char_start, x.char_end)):
        if res.stories and st.char_start < res.stories[-1].char_end:
            res.overlapping.append({"post": st.post, "start": st.char_start})
            continue
        res.stories.append(st)
    for st in res.stories:                    # T-1, asserted at write time
        assert rec.text[st.char_start:st.char_end] == st.text and st.text
    return res


def parse_output(text: str, req: list[Unit]) -> dict[str, list[dict] | None]:
    """uid → stories, or None where the model gave no answer for that id."""
    data = json.loads(text)
    got = {r["id"]: r["stories"] for r in data.get("records", [])}
    return {u.uid: got.get(u.uid) for u in req}


def _output_text(resp: dict) -> str:
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    return c["text"]
    raise ValueError(f"no output_text (status {resp.get('status')})")


def _usage(resp: dict) -> tuple[int, int, int]:
    u = resp.get("usage") or {}
    return (u.get("input_tokens", 0), u.get("output_tokens", 0),
            (u.get("input_tokens_details") or {}).get("cached_tokens", 0))


# ---------------------------------------------------------------- sync path
def call_sync(client, req: list[Unit], *, model: str, effort: str, system: str) -> tuple[dict, dict]:
    last = None
    for attempt in range(2):                  # one retry on a malformed answer (EC-CODE-11)
        resp = client.responses.create(**request_body(req, model=model, effort=effort,
                                                      system=system)).model_dump()
        try:
            return parse_output(_output_text(resp), req), resp
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"unparseable answer twice: {last}")


def run_sync(client, recs: list[Record], run: rmod.Run, *, model: str, effort: str,
             workers: int = 8) -> dict[str, RecordResult]:
    system = PROMPT.read_text()
    units = [u for r in recs for u in units_of(r)]
    reqs = pack(units)

    def one(req):
        return req, *call_sync(client, req, model=model, effort=effort, system=system)

    per: dict[str, list] = defaultdict(list)
    with ThreadPoolExecutor(workers) as ex:
        for req, answers, resp in ex.map(one, reqs):
            i, o, c = _usage(resp)
            run.add_usage(input_tokens=i, output_tokens=o, cached_tokens=c)
            for u in req:
                per[u.record.record_id].append(answers[u.uid])
    run.n_input = len(recs)
    return {r.record_id: merge(r, per[r.record_id]) for r in recs}


# ------------------------------------------------------------------ fixtures
def _fixture_record(fid: str, source: str, posts: list[tuple[str, str]]) -> Record:
    text, bounds, pos = [], [], 0
    for author, t in posts:
        t = " ".join(t.split()) if "\n" not in t else t
        if text:
            pos += 2
        bounds.append({"author_key": author, "start": pos, "end": pos + len(t)})
        pos += len(t)
        text.append(t)
    return Record(fid, source, "\n\n".join(text), bounds)


def fixture_records() -> tuple[list[Record], dict[str, dict]]:
    def jl(name):
        return [json.loads(x) for x in (FIX / name).read_text().splitlines() if x.strip()]
    recs, expect = [], {}
    for r in jl("segmentation_counts.jsonl"):
        recs.append(_fixture_record(r["id"], r["source"],
                                    [(c["author"], c["text"]) for c in r["comments"]]))
        expect[r["id"]] = {"kind": "seg", **r["expected"]}
    for r in jl("bucket_boundary.jsonl"):
        recs.append(_fixture_record(r["id"], "reddit", [("author", r["text"])]))
        expect[r["id"]] = {"kind": "bucket", "bucket": r["expected_bucket"]}
    for r in jl("stories_authored.jsonl"):
        recs.append(_fixture_record(r["id"], "reddit", [("author", r["text"])]))
        expect[r["id"]] = {"kind": "authored", "bucket": r["expected"]["bucket"]}
    random.Random(26).shuffle(recs)            # packed alongside strangers, as in the corpus
    return recs, expect


def record_bucket(res: RecordResult) -> str:
    """No story = irrelevant for the bucket fixtures; else the most retrieval-
    relevant bucket present."""
    got = {s.bucket for s in res.stories}
    return next((b for b in BUCKETS if b in got), "irrelevant")


def score_fixtures(results: dict[str, RecordResult], expect: dict[str, dict]) -> dict:
    out: dict[str, Any] = {"seg": [], "bucket": [], "authored": []}
    for fid, e in expect.items():
        res = results[fid]
        row = {"id": fid, "returned": res.returned, "located": len(res.stories),
               "unlocated": len(res.unlocated), "overlapping": len(res.overlapping),
               "stories": [{"author": s.author_key, "bucket": s.bucket, "stage": s.reaches_stage,
                            "text": s.text[:90], "reason": s.reason} for s in res.stories]}
        if e["kind"] == "seg":
            row["count_ok"] = len(res.stories) == e["n_stories"]
            checks = []
            for exp in e["stories"]:
                hit = next((s for s in res.stories
                            if exp["starts_with"][:25] in s.text or s.text[:25] in exp["starts_with"]),
                           None)
                checks.append({"expected": exp["starts_with"][:40], "found": hit is not None,
                               "author_ok": bool(hit and hit.author_key == exp["author"]),
                               "stage": hit.reaches_stage if hit else None,
                               "stage_ok": bool(hit and hit.reaches_stage >= exp["reaches_stage_min"])})
            row["checks"] = checks
            out["seg"].append(row)
        else:
            row["expected"], row["got"] = e["bucket"], record_bucket(res)
            row["ok"] = row["expected"] == row["got"]
            out[e["kind"]].append(row)
    seg = out["seg"]
    checks = [c for r in seg for c in r["checks"]]
    out["summary"] = {
        "P2_MET_3_count_exact": sum(r["count_ok"] for r in seg) / len(seg),
        "story_found": sum(c["found"] for c in checks) / max(len(checks), 1),
        "author_ok": sum(c["author_ok"] for c in checks) / max(len(checks), 1),
        "stage_floor_ok": sum(c["stage_ok"] for c in checks) / max(len(checks), 1),
        "T9_bucket_boundary": sum(r["ok"] for r in out["bucket"]) / len(out["bucket"]),
        "authored_bucket": sum(r["ok"] for r in out["authored"]) / len(out["authored"]),
        "unlocated": sum(r["unlocated"] for k in ("seg", "bucket", "authored") for r in out[k]),
        "returned": sum(r["returned"] for k in ("seg", "bucket", "authored") for r in out[k]),
        "overlapping": sum(r["overlapping"] for k in ("seg", "bucket", "authored") for r in out[k]),
    }
    return out


# ------------------------------------------------------------------ corpus
def corpus_records(con, ids: list[str] | None = None) -> list[Record]:
    sql = ("SELECT record_id, source, text_clean, posts_json, author_key, thread_context FROM records"
           " WHERE record_id NOT IN (SELECT record_id FROM exclusions WHERE story_id IS NULL)")
    rows = con.execute(sql + " ORDER BY source, record_id").fetchall()
    recs = [record_from_row(r) for r in rows]
    return [r for r in recs if ids is None or r.record_id in set(ids)]


def estimate(recs: list[Record], *, out_per_record: float, batch: bool = True) -> dict:
    reqs = pack([u for r in recs for u in units_of(r)])
    prompt_tok = len(PROMPT.read_text()) / 4 + 350          # + the JSON schema
    in_tok = sum(prompt_tok + sum(len(render(u)) for u in req) / 4 for req in reqs)
    out_tok = out_per_record * len(recs)
    usd = rmod.cost(MODEL, input_tokens=int(in_tok), output_tokens=int(out_tok), batch=batch)
    return {"records": len(recs), "requests": len(reqs), "input_tokens": int(in_tok),
            "output_tokens": int(out_tok), "usd": round(usd, 3)}


def write_results(con, results: list[RecordResult], run_id: str) -> dict[str, int]:
    """Stories + record-level marks. A record whose stories were returned but
    none could be located is marked `span_unverified`; a record with no story
    at all is `no_story` (EC-SEG-7) — logged, never dropped (P2-INV-5)."""
    n = Counter()
    for res in results:
        rid = res.record.record_id
        for k, s in enumerate(res.stories):
            con.execute(
                "INSERT INTO stories (story_id, record_id, ordinal, text, char_start, char_end,"
                " author_key, bucket, bucket_reason, bucket_conf, reaches_stage, run_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"{rid}:{k}", rid, k, s.text, s.char_start, s.char_end, s.author_key, s.bucket,
                 s.reason, s.confidence, s.reaches_stage, run_id))
            n[f"stories_{s.bucket}"] += 1
        if not res.stories:
            reason = "span_unverified" if res.returned else "no_story"
            con.execute("INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail,"
                        " run_id) VALUES (?,?,?,?,?,?)",
                        (rid, res.record.source, "segment", reason,
                         f"{res.returned} returned, {len(res.unlocated)} not located" if res.returned
                         else "no retrieval story in the record", run_id))
            n[reason] += 1
        n["unlocated"] += len(res.unlocated)
        n["overlapping"] += len(res.overlapping)
        n["missing_parts"] += res.missing_parts
        n["returned"] += res.returned
    con.commit()
    return dict(n)


# ------------------------------------------------------------------- batch
def _manifest_path() -> Path:
    return BATCH_DIR / "segment_manifest.json"


def submit(con, client, recs: list[Record], est: dict, *, replace: bool = False,
           stage: str | None = None) -> None:
    """`replace` re-segments records that already have stories: an explicit
    decision (EC-OPS-3), and collect then REPLACES their rows."""
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    if _manifest_path().exists():
        raise SystemExit(f"{_manifest_path()} exists — a batch is already in flight. Run `collect`.")
    already = {r[0] for r in con.execute("SELECT DISTINCT record_id FROM stories")}
    if already and not replace:
        raise SystemExit(f"{len(already)} records already have stories — re-runs need an explicit "
                         "decision (EC-OPS-3), not a second submit.")
    system = PROMPT.read_text()
    reqs = pack([u for r in recs for u in units_of(r)])
    run = rmod.Run(con, stage or ("segment-resegment" if replace else "segment"), model=MODEL,
                   estimate_usd=est["usd"] if replace else ESTIMATE_USD, batch=True,
                   prompt_version=PROMPT_VERSION, effort=EFFORT, n_records=len(recs),
                   n_requests=len(reqs), estimate_detail=est)
    run.__enter__()                            # ceiling check + the runs row, status running
    path = BATCH_DIR / f"{run.run_id}_input.jsonl"
    mapping = {}
    with path.open("w") as f:
        for k, req in enumerate(reqs):
            cid = f"req-{k:05d}"
            mapping[cid] = [[u.uid, u.record.record_id, u.part] for u in req]
            f.write(json.dumps({"custom_id": cid, "method": "POST", "url": "/v1/responses",
                                "body": request_body(req, system=system)}) + "\n")
    up = client.files.create(file=path.open("rb"), purpose="batch")
    b = client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                              completion_window="24h")
    _manifest_path().write_text(json.dumps({"run_id": run.run_id, "batch_id": b.id,
                                            "input_file_id": up.id, "replace": replace,
                                            "requests": mapping}))
    con.execute("UPDATE runs SET params_json=json_set(params_json,'$.batch_id',?) WHERE run_id=?",
                (b.id, run.run_id))
    con.commit()
    print(f"submitted {len(reqs)} requests for {len(recs)} records · batch {b.id} · run {run.run_id}")


def collect(con, client, *, accept_overrun: bool = False) -> None:
    man = json.loads(_manifest_path().read_text())
    b = client.batches.retrieve(man["batch_id"])
    print(f"batch {b.id}: {b.status} · {b.request_counts}")
    if b.status not in ("completed", "expired", "failed", "cancelled"):
        raise SystemExit(3)                    # not finished; poll again later
    run_id = man["run_id"]
    lines = client.files.content(b.output_file_id).text.splitlines() if b.output_file_id else []
    (BATCH_DIR / f"{run_id}_output.jsonl").write_text("\n".join(lines))
    tokens = [0, 0, 0]
    answers: dict[str, dict[tuple[str, int], list | None]] = defaultdict(dict)
    failed_reqs = []
    for line in lines:
        o = json.loads(line)
        units = man["requests"][o["custom_id"]]
        body = (o.get("response") or {}).get("body") or {}
        for i, v in enumerate(_usage(body)):
            tokens[i] += v
        try:
            got = parse_output(_output_text(body), [Unit(None, 0, 0, [], uid) for uid, _, _ in units])
        except (ValueError, json.JSONDecodeError, KeyError):
            failed_reqs.append(o["custom_id"])
            got = {}
        for uid, rid, part in units:
            answers[rid][(uid, part)] = got.get(uid)
    missing = set(man["requests"]) - {json.loads(x)["custom_id"] for x in lines}
    usd = rmod.cost(MODEL, input_tokens=tokens[0], output_tokens=tokens[1], cached_tokens=tokens[2],
                    batch=True)
    est = con.execute("SELECT estimate_usd FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]
    over = usd > rmod.HALT_MULTIPLE * est
    status = "halted_budget" if over and not accept_overrun else "ok"
    con.execute("UPDATE runs SET finished_at=?, status=?, input_tokens=?, output_tokens=?,"
                " cached_tokens=?, cost_usd=?, params_json=json_set(params_json,'$.failed_requests',"
                " json(?), '$.missing_requests', json(?)) WHERE run_id=?",
                (rmod._now(), status, tokens[0], tokens[1], tokens[2], round(usd, 6),
                 json.dumps(failed_reqs), json.dumps(sorted(missing)), run_id))
    con.commit()
    print(f"cost ${usd:.4f} against ${est:.2f} estimate · {len(failed_reqs)} unparseable · "
          f"{len(missing)} missing requests")
    if over and not accept_overrun:
        raise SystemExit(f"T-19: ${usd:.3f} > 1.5 × ${est:.2f}. Output saved; decide, then "
                         "re-run collect with --accept-overrun to write it.")
    if failed_reqs or missing:
        raise SystemExit("some requests failed — re-submit those before writing (nothing written)")
    recs = {r.record_id: r for r in _all_segmentable(con)}
    if man.get("replace"):
        ids = list(answers)
        for k in range(0, len(ids), 500):
            chunk = ids[k:k + 500]
            q = ",".join("?" * len(chunk))
            con.execute(f"DELETE FROM stories WHERE record_id IN ({q})", chunk)
            con.execute(f"DELETE FROM exclusions WHERE stage='segment' AND record_id IN ({q})",
                        chunk)
    results = []
    for rid, parts in answers.items():
        ordered = [v for _, v in sorted(parts.items(), key=lambda kv: kv[0][1])]
        results.append(merge(recs[rid], ordered))
    n = write_results(con, results, run_id)
    con.execute("UPDATE runs SET n_input=?, n_output=?, params_json=json_set(params_json,"
                "'$.written',json(?)) WHERE run_id=?",
                (len(results), sum(len(r.stories) for r in results), json.dumps(n), run_id))
    con.commit()
    _manifest_path().rename(BATCH_DIR / f"{run_id}_manifest.json")
    print(json.dumps(n, indent=1))


def results_from_output(con, run_id: str) -> list[RecordResult]:
    """Re-merge a collected batch from its saved files (no API call)."""
    man = json.loads((BATCH_DIR / f"{run_id}_manifest.json").read_text())
    answers: dict[str, dict[tuple[str, int], list | None]] = defaultdict(dict)
    for line in (BATCH_DIR / f"{run_id}_output.jsonl").read_text().splitlines():
        o = json.loads(line)
        units = man["requests"][o["custom_id"]]
        got = parse_output(_output_text(o["response"]["body"]),
                           [Unit(None, 0, 0, [], uid) for uid, _, _ in units])
        for uid, rid, part in units:
            answers[rid][(uid, part)] = got.get(uid)
    recs = {r.record_id: r for r in _all_segmentable(con)}
    return [merge(recs[rid], [v for _, v in sorted(p.items(), key=lambda kv: kv[0][1])])
            for rid, p in answers.items()]


def _all_segmentable(con) -> list[Record]:
    """Records not excluded BEFORE segmentation (a `segment` mark is Pass 1's own)."""
    rows = con.execute(
        "SELECT record_id, source, text_clean, posts_json, author_key, thread_context FROM records"
        " WHERE record_id NOT IN (SELECT record_id FROM exclusions WHERE story_id IS NULL"
        " AND stage <> 'segment') ORDER BY source, record_id").fetchall()
    return [record_from_row(r) for r in rows]


def retry(con, client, run_id: str) -> None:
    """Re-code ONCE, then keep and count (implementationplan.md §5.2 rule, applied
    to Pass 1). A record is retried if a part got no answer (it would otherwise
    read as `no_story` — a silent loss) or a story's anchors were not found.
    Its stories and `segment` mark are replaced by the retry's, whatever it
    returns; what still fails is marked and counted."""
    first = results_from_output(con, run_id)
    todo = [r.record for r in first if r.missing_parts or r.unlocated]
    if not todo:
        print("nothing to retry")
        return
    ids = [r.record_id for r in todo]
    with rmod.Run(con, "segment-retry", model=MODEL, estimate_usd=0.05,
                  prompt_version=PROMPT_VERSION, effort=EFFORT, of_run=run_id, n=len(ids)) as run:
        again = run_sync(client, todo, run, model=MODEL, effort=EFFORT)
        q = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM stories WHERE record_id IN ({q})", ids)
        con.execute(f"DELETE FROM exclusions WHERE stage='segment' AND record_id IN ({q})", ids)
        n = write_results(con, [again[i] for i in ids], run_id)
        before = {r.record.record_id: (len(r.stories), r.missing_parts, len(r.unlocated))
                  for r in first if r.record.record_id in set(ids)}
        after = {i: (len(again[i].stories), again[i].missing_parts, len(again[i].unlocated))
                 for i in ids}
        con.execute("UPDATE runs SET params_json=json_set(params_json,'$.written',json(?),"
                    "'$.before_after',json(?)) WHERE run_id=?",
                    (json.dumps(n), json.dumps({i: [before[i], after[i]] for i in ids}),
                     run.run_id))
        con.commit()
    print(f"retried {len(ids)} records · {json.dumps(n)}")


# -------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fixtures", "estimate", "submit", "submit-new", "resubmit", "collect", "retry", "dual"])
    ap.add_argument("--effort", default=EFFORT)
    ap.add_argument("--out-per-record", type=float, default=None,
                    help="estimate: output tokens per record, from the fixture run")
    ap.add_argument("--accept-overrun", action="store_true")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--with-stories", action="store_true", help="dual: sample story-bearing records")
    args = ap.parse_args()
    vals = envm.load()
    con = dbm.init()
    if args.cmd == "estimate":
        out = args.out_per_record or _fixture_out_per_record()
        print(json.dumps(estimate(corpus_records(con), out_per_record=out), indent=1))
        return 0
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=vals["OPENAI_API_KEY"])
    if args.cmd == "fixtures":
        recs, expect = fixture_records()
        with rmod.Run(con, "segment-fixtures", model=MODEL, estimate_usd=0.10,
                      prompt_version=PROMPT_VERSION, effort=args.effort) as run:
            results = run_sync(client, recs, run, model=MODEL, effort=args.effort)
            sc = score_fixtures(results, expect)
            sc["run_id"], sc["effort"] = run.run_id, args.effort
            sc["usage"] = {"input": run.input_tokens, "output": run.output_tokens,
                           "usd": run.cost_usd(), "records": len(recs)}
            con.execute("UPDATE runs SET params_json=json_set(params_json,'$.summary',json(?))"
                        " WHERE run_id=?", (json.dumps(sc["summary"]), run.run_id))
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / f"segment_fixtures_{sc['run_id']}.json").write_text(json.dumps(sc, indent=1))
        print(json.dumps(sc["summary"], indent=1), json.dumps(sc["usage"]))
        return 0
    if args.cmd == "submit":
        recs = corpus_records(con)
        est = estimate(recs, out_per_record=args.out_per_record or _fixture_out_per_record())
        print(json.dumps(est))
        # The §8 estimate stays the recorded one, so T-19 still halts at 1.5× it.
        # A projection that would already cross the halt is a decision, not a submit.
        if est["usd"] > rmod.HALT_MULTIPLE * ESTIMATE_USD:
            print(f"projected ${est['usd']} would cross the T-19 halt "
                  f"(${rmod.HALT_MULTIPLE * ESTIMATE_USD:.2f}) — decide first", file=sys.stderr)
            return 1
        submit(con, client, recs, est)
        return 0
    if args.cmd == "submit-new":
        # Records added by a top-up (the §0.4 loop-back) that Pass 1 has not read.
        done = {r[0] for r in con.execute("SELECT record_id FROM stories UNION SELECT record_id"
                                          " FROM exclusions WHERE stage='segment'")}
        recs = [r for r in _all_segmentable(con) if r.record_id not in done]
        est = estimate(recs, out_per_record=args.out_per_record or _fixture_out_per_record())
        print(json.dumps(est))
        submit(con, client, recs, est, replace=True, stage="segment-topup")
        return 0
    if args.cmd == "resubmit":
        ids = [r[0] for r in con.execute("SELECT DISTINCT record_id FROM stories")]
        recs = [r for r in _all_segmentable(con) if r.record_id in set(ids)]
        est = estimate(recs, out_per_record=args.out_per_record or _fixture_out_per_record())
        print(json.dumps(est))
        submit(con, client, recs, est, replace=True)
        return 0
    if args.cmd == "collect":
        collect(con, client, accept_overrun=args.accept_overrun)
        return 0
    if args.cmd == "retry":
        rid = con.execute("SELECT run_id FROM runs WHERE stage IN ('segment',"
                          "'segment-resegment','segment-topup') AND status='ok'"
                          " ORDER BY started_at DESC"
                          " LIMIT 1").fetchone()[0]
        retry(con, client, rid)
        return 0
    from pipeline.segment import dual
    return dual.main(con, client, n=args.n, with_stories=args.with_stories)


def _fixture_out_per_record(effort: str = EFFORT) -> float:
    """Measured output tokens per record from the latest fixture run AT THIS
    EFFORT — reasoning tokens make efforts differ ~3× (2026-09-26: an estimate
    taken from a `minimal` run under-projected a `low` batch by half)."""
    runs = [p for p in sorted(ARTIFACTS.glob("segment_fixtures_*.json"))
            if json.loads(p.read_text()).get("effort") == effort]
    if not runs:
        raise SystemExit(f"run `fixtures --effort {effort}` first — the estimate uses its "
                         "measured output tokens")
    u = json.loads(runs[-1].read_text())["usage"]
    return u["output"] / u["records"]


if __name__ == "__main__":
    raise SystemExit(main())
