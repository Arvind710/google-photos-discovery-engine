"""Pass 2 — code every live story against the frozen codebook
(implementationplan.md §5, architecture.md §5.3). gpt-5, Batch API.

ONE request per story, carrying the whole codebook as a stable prefix (cached)
and asking only the questions that story's blocks cover (Docs/decisions.md D-9):

    core      A + B + C + D + R   all 59 bank questions — with only 115 core
                                  stories, the plan's pilot and its coverage
                                  register are the same run (arch §3.4)
    adjacent  A, + C if reaches_stage ≥ 5, + D if reaches_stage ≥ 7

Decided in CODE, never asked of the model:
- `failure_owner` — from primary_stage (the codebook's spine map).
- `metric_node` — `metric_node()` below, a fixed rule from primary_stage plus
  the 5.4 and 7.2 codes and the outcome.
- `severity` — the model scores three rubric parts 0–2; the outcome part comes
  from `outcome`; the total maps to 1–5 by `severity_v1.yaml`.
- 10.3 (block S) — structural: every story IS a public post, so its value is
  the source's kind.
- 2.2 — one `story_codes` row per remembered cue: the cue (a 2.1 value) in
  `value`, the judgement in `accuracy`, as the codebook comment and the schema
  describe.

Every quote is located in `text_clean` (validate/spans.py) and stored as the
exact slice, or not at all. A story whose primary_stage quote cannot be found is
re-coded once, then marked `span_unverified` and counted (P3-INV-4, [CTX] §15.7).

    python -m pipeline.classify.blocks fixtures          # the T-8 loop, 40 stories
    python -m pipeline.classify.blocks estimate
    python -m pipeline.classify.blocks submit            # Batch API; resumes by diff
    python -m pipeline.classify.blocks collect           # exit 3 = not finished
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod
from pipeline.segment import stories as seg
from pipeline.validate import spans

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "code_v1.md"
PROMPT_VERSION = "code_v1.2"     # v1.0 first fixture run · v1.1 T-8 iteration 1 · v1.2 Stage 0 rule
MODEL = "gpt-5"
EFFORT = "low"
# Core stories carry every analysis, so they get reasoning; adjacent stories mostly
# get Block A only and run at `minimal` (the $15 ceiling, Docs/decisions.md D-9).
EFFORT_BY_BUCKET = {"core": "low", "adjacent": "minimal", "irrelevant": "minimal"}
ARTIFACTS = seg.ARTIFACTS
BATCH_DIR = seg.BATCH_DIR
MANIFEST = BATCH_DIR / "code_manifest.json"
QUARANTINE = ROOT / "data" / "quarantine"
LATER_CHARS = 3_000
ESTIMATE_USD = 7.25 - 0.50 - 0.60     # arch §8 blocks A–D + pilot, less reliability & themes

CORE_BLOCKS = ("A", "B", "C", "D", "R")
SOURCE_KIND_103 = {"play": "reviews", "appstore": "reviews", "reddit": "reddit",
                   "gp_help": "community_forums", "stackexchange": "community_forums",
                   "quora": "community_forums", "hackernews": "community_forums",
                   "youtube": "other:youtube_comments", "x": "other:x_posts"}
OUTCOME_SEVERITY = {"found": 0, "found_later_by_accident": 0, "not_stated": 0,
                    "found_after_struggle": 1, "substitute_accepted": 1,
                    "abandoned_with_fallback": 2, "abandoned_without_fallback": 2,
                    "false_positive": 2}


def blocks_for(bucket: str, reaches_stage: int) -> tuple[str, ...]:
    if bucket == "core":
        return CORE_BLOCKS
    return ("A",) + (("C",) if reaches_stage >= 5 else ()) + (("D",) if reaches_stage >= 7 else ())


def questions_for(cb: cbm.Codebook, blocks: tuple[str, ...]) -> list[str]:
    return [q for q, d in cb.questions.items() if d["block"] in blocks]


# ------------------------------------------------------------------- prompt
def _clean(s: Any) -> str:
    return " ".join(str(s).split())


def render_codebook(cb: cbm.Codebook) -> str:
    """The codebook as the model reads it, generated from journey_v1.yaml so the
    prompt and the frozen codebook cannot drift."""
    sp = cb.spine
    out = ["### Spine fields",
           f"- photo_class: {', '.join(sp['photo_class']['values'])}. "
           f"{_clean(sp['photo_class']['boundary_note'])}",
           f"- media_type: {', '.join(sp['media_type']['values'])}. "
           f"{_clean(sp['media_type']['boundary_note'])}",
           f"- outcome: {', '.join(sp['outcome']['values'])}.",
           "- primary_stage: 0–10, the stage names below. "
           f"{_clean(sp['primary_stage']['boundary_note'])}", ""]
    for sid, st in cb.stages.items():
        head = f"### Stage {sid} — {st['name']}"
        if st.get("inferred"):
            head += " (system side: inferred from the user's account)"
        out.append(head)
        if st.get("boundary_note"):
            out.append(f"Boundary: {_clean(st['boundary_note'])}")
        for qid in [q for q, d in cb.questions.items() if d["stage"] == sid]:
            q = cb.questions[qid]
            if q["block"] == "S":
                continue
            out.append(f"**{qid}** {q['text']} [{q['select']}]")
            notes = q.get("value_notes") or {}
            vals = q["accuracy_values"] if qid == "2.2" else q["values"]
            out.append("  values: " + "; ".join(
                f"{v} ({_clean(notes[v])})" if v in notes else v for v in vals))
            if qid == "2.2":
                out.append("  (answered as a list of {cue: a 2.1 value, accuracy: one of the "
                           "values above})")
            if q.get("boundary_note") and q.get("boundary_note") != st.get("boundary_note"):
                out.append(f"  Boundary: {_clean(q['boundary_note'])}")
            for v, n in (q.get("value_boundary") or {}).items():
                out.append(f"  Boundary for {v}: {_clean(n)}")
        out.append("")
    return "\n".join(out)


def system_prompt(cb: cbm.Codebook) -> str:
    return PROMPT.read_text() + "\n" + render_codebook(cb)


# ------------------------------------------------------------------- schema
def qkey(qid: str) -> str:
    return "q" + qid.replace(".", "_")


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": list(props)}


STR = {"type": "string"}


def question_schema(cb: cbm.Codebook, qid: str) -> dict:
    q = cb.questions[qid]
    if qid == "2.2":
        cues = [v for v in cb.questions["2.1"]["values"] if v not in ("not_stated", "other")]
        return _obj({"cues": {"type": "array", "items": _obj({
            "cue": {"type": "string", "enum": cues},
            "accuracy": {"type": "string", "enum": q["accuracy_values"]}})}, "q": STR})
    enum = {"type": "string", "enum": q["values"]}
    if q["select"] == "single":
        return _obj({"v": enum, "o": STR, "q": STR})
    return _obj({"v": {"type": "array", "items": enum}, "o": STR, "q": STR})


def schema(cb: cbm.Codebook, qids: list[str]) -> dict:
    sp = cb.spine
    part = {"type": "integer", "enum": [0, 1, 2]}
    spine = _obj({
        "primary_stage": {"type": "string", "enum": sp["primary_stage"]["values"]},
        "primary_stage_quote": STR,
        "photo_class": {"type": "string", "enum": sp["photo_class"]["values"]},
        "photo_class_quote": STR,
        "media_type": {"type": "string", "enum": sp["media_type"]["values"]},
        "photo_subtype": STR,
        "outcome": {"type": "string", "enum": sp["outcome"]["values"]},
        "severity": _obj({"stakes": part, "effort": part, "emotional_intensity": part}),
        "workaround": {"type": "boolean"}, "workaround_text": STR,
        "coding_conf": {"type": "number"}, "why": STR})
    queries = {"type": "array", "items": _obj({
        "text": STR, "worked": {"type": "string", "enum": ["yes", "no", "unknown"]}})}
    return _obj({"spine": spine, "queries": queries,
                 **{qkey(q): question_schema(cb, q) for q in qids}})


# -------------------------------------------------------------------- items
@dataclass
class Item:
    story_id: str
    source: str
    context: str | None
    text: str                      # the story (a slice of text_clean)
    later: str                     # the same author's later posts, as shown
    bucket: str
    reaches_stage: int
    text_clean: str                # the record's canonical text — the ONLY span source
    regions: list[tuple[int, int]]
    blocks: tuple[str, ...] = ()


def live_items(con, *, skip_done: bool = True) -> list[Item]:
    recs = {r.record_id: r for r in seg._all_segmentable(con)}
    done = ({r[0] for r in con.execute("SELECT story_id FROM story_spine UNION SELECT story_id"
                                       " FROM exclusions WHERE stage='code' AND story_id IS NOT"
                                       " NULL")} if skip_done else set())
    out = []
    for s in con.execute("SELECT story_id, record_id, char_start, char_end, author_key, text,"
                         " bucket, reaches_stage FROM stories WHERE story_id NOT IN (SELECT"
                         " story_id FROM exclusions WHERE story_id IS NOT NULL)"
                         " ORDER BY story_id"):
        if s["story_id"] in done:
            continue
        rec = recs[s["record_id"]]
        reg = spans.regions(rec.text, rec.posts, s["char_start"], s["char_end"], s["author_key"])
        later = "\n---\n".join(rec.text[a:b] for a, b in reg[1:])[:LATER_CHARS]
        out.append(Item(s["story_id"], rec.source, rec.context, s["text"], later, s["bucket"],
                        s["reaches_stage"], rec.text, reg,
                        blocks_for(s["bucket"], s["reaches_stage"])))
    return out


def render(it: Item) -> str:
    ctx = f' context="{seg._attr(it.context)}"' if it.context else ""
    later = f"\n\nlater posts by the same author:\n{it.later}" if it.later else ""
    return f'<story id="{it.story_id}" source="{it.source}"{ctx}>\nstory:\n{it.text}{later}\n</story>'


def request_body(cb: cbm.Codebook, it: Item, system: str, *, model: str = MODEL,
                 effort: str | None = None) -> dict:
    effort = effort or EFFORT_BY_BUCKET[it.bucket]
    return {"model": model, "instructions": system, "reasoning": {"effort": effort},
            "input": render(it),
            "text": {"format": {"type": "json_schema", "name": "coding",
                                "schema": schema(cb, questions_for(cb, it.blocks)),
                                "strict": True}}}


# --------------------------------------------------------------- validation
def substantive(vals: list[str]) -> bool:
    return any(v != "not_stated" for v in vals)


# 0.2 values that say the photo's own data was wrong or missing — Stage 0 evidence.
DATA_WRONG = {"date:received_date_not_capture", "date:scan_date", "date:wrong_clock_or_timezone",
              "location:absent", "location:inaccurate", "faces:grouping_off_or_unavailable"}


def stage0_without_evidence(stage: str, codes: dict[str, list[str]],
                            outcome: str = "not_stated") -> bool:
    """Stage 0 (library_data) contradicted by the story itself: it ends with the
    photo found, and nothing in 0.1 or 0.2 says the photo was unreachable. Found in the v1.1 corpus run: quiet
    successes ("searched 'passport' and found it") coded 0, because the codebook
    has no "nothing went wrong" stage (D-9). A story that says the photo
    vanished from the library — even one that was backed up first — is Stage 0,
    and is not flagged."""
    if stage != "0":
        return False
    reach = [v for v in codes.get("0.1", []) if v not in ("yes_backed_up", "not_stated")]
    if reach or DATA_WRONG & set(codes.get("0.2", [])):
        return False
    return outcome in ("found", "found_after_struggle")


def metric_node(stage: str, codes: dict[str, list[str]], outcome: str) -> str:
    """The fixed rule (Docs/decisions.md D-9). primary_stage alone does not
    decide it: Stage 5 splits on whether the photo came back buried (5.4), and
    Stages 7–8 on whether trying again found it."""
    if stage == "0":
        return "target_retrievable"
    if stage in ("2", "4"):
        return "query_captures_usable_cue"
    if stage == "3":
        return "enters_gp_retrieval_path"
    if stage == "5":
        return ("target_ranked_visible" if substantive(codes.get("5.4", []))
                else "query_captures_usable_cue")
    if stage == "6":
        return "user_recognises_target"
    if stage in ("7", "8"):
        tactic = [v for v in codes.get("7.2", []) if v not in ("not_stated", "quit")]
        found = outcome in ("found", "found_after_struggle")
        return "found_after_refinement" if tactic and found else "refines_instead_of_quitting"
    if stage == "1":
        return "context"
    return "outcome_measure"                                    # 9, 10


def severity(cb: cbm.Codebook, parts: dict, outcome: str) -> int:
    total = (int(parts["stakes"]) + int(parts["effort"]) + int(parts["emotional_intensity"])
             + OUTCOME_SEVERITY[outcome])
    return next(int(k) for k, band in cb.severity["scale"].items() if total in band)


@dataclass
class Coded:
    story_id: str
    spine: dict = field(default_factory=dict)
    rows: list[tuple] = field(default_factory=list)     # (question, value, accuracy, seq)
    evidence: dict[str, str] = field(default_factory=dict)
    queries: list[tuple] = field(default_factory=list)  # (text, attempt_no, worked)
    codes: dict[str, list[str]] = field(default_factory=dict)
    problems: Counter = field(default_factory=Counter)
    fatal: str | None = None                            # span_unverified | coding_failed | model_refusal


def validate(cb: cbm.Codebook, it: Item, out: dict) -> Coded:
    c = Coded(it.story_id)
    sp = out["spine"]
    stage = sp["primary_stage"]
    span = spans.find(it.text_clean, sp["primary_stage_quote"], it.regions)
    if span is None:
        c.fatal = "span_unverified"
        return c
    c.evidence["primary_stage"] = c.evidence["failure_owner"] = span
    pc = spans.find(it.text_clean, sp["photo_class_quote"], it.regions)
    if pc:
        c.evidence["photo_class"] = pc
    for qid in questions_for(cb, it.blocks):
        a = out[qkey(qid)]
        if qid == "2.2":
            seen = []
            for x in a["cues"]:
                if x["cue"] not in [s[0] for s in seen]:
                    seen.append((x["cue"], x["accuracy"]))
            vals = [v for v, _ in seen]
            c.rows += ([("2.2", v, acc, None) for v, acc in seen] if seen
                       else [("2.2", "not_stated", None, None)])
        else:
            raw = [a["v"]] if isinstance(a["v"], str) else list(dict.fromkeys(a["v"]))
            if substantive(raw):
                raw = [v for v in raw if v != "not_stated"]
            else:
                raw = ["not_stated"]
            vals = []
            for v in raw:
                if v == "other":
                    t = "_".join(_clean(a["o"]).lower().split())[:60]
                    if not t:
                        c.problems["other_without_text"] += 1
                    v = f"other:{t or 'unspecified'}"
                if not cb.is_valid_value(qid, v):                       # P3-INV-5
                    c.problems["invalid_value"] += 1
                    continue
                vals.append(v)
            vals = vals or ["not_stated"]
            seq = qid == "7.2"
            c.rows += [(qid, v, None, k if seq else None) for k, v in enumerate(vals, 1)]
        c.codes[qid] = vals
        if substantive(vals) and a["q"].strip():
            q = spans.find(it.text_clean, a["q"], it.regions)
            if q:
                c.evidence[qid] = q
            else:
                c.problems["quote_unverified"] += 1
    c.rows.append(("10.3", SOURCE_KIND_103[it.source], None, None))
    if stage0_without_evidence(stage, c.codes, sp["outcome"]):
        c.problems["stage0_without_evidence"] += 1
    for k, qq in enumerate(out["queries"], 1):
        t = " ".join(qq["text"].split()).strip("'\"‘’“”")
        if t and t.lower() in " ".join(it.text_clean.split()).lower():
            c.queries.append((t, k, {"yes": 1, "no": 0}.get(qq["worked"])))
        elif t:
            c.problems["query_not_in_text"] += 1
    mode = next((v for v in c.codes.get("3.2", []) if v != "not_stated"), None)
    urg = next((v for v in c.codes.get("1.4", []) if v.startswith("urgency:")), None)
    c.spine = {
        "photo_class": sp["photo_class"], "media_type": sp["media_type"],
        "photo_subtype": _clean(sp["photo_subtype"])[:60] or None,
        "primary_stage": stage, "failure_owner": cb.failure_owner(stage),
        "metric_node": metric_node(stage, c.codes, sp["outcome"]), "outcome": sp["outcome"],
        "mode_used": mode, "severity": severity(cb, sp["severity"], sp["outcome"]),
        "urgency": urg, "workaround": int(bool(sp["workaround"])),
        "workaround_text": _clean(sp["workaround_text"])[:120] or None,
        "coding_conf": float(seg._clamp(sp["coding_conf"], 0, 1)),
        "why": _clean(sp["why"])[:200] or "—", "severity_parts": sp["severity"]}
    return c


# -------------------------------------------------------------------- write
def clear(con, story_ids: list[str]) -> None:
    for k in range(0, len(story_ids), 500):
        ch = story_ids[k:k + 500]
        q = ",".join("?" * len(ch))
        for t in ("story_spine", "story_codes", "evidence", "queries"):
            con.execute(f"DELETE FROM {t} WHERE story_id IN ({q})", ch)
        con.execute(f"DELETE FROM exclusions WHERE stage='code' AND story_id IN ({q})", ch)


def write(con, cb: cbm.Codebook, it: Item, c: Coded, run_id: str) -> None:
    if c.fatal:
        con.execute("INSERT OR IGNORE INTO exclusions (record_id, story_id, source, stage, reason,"
                    " detail, run_id) SELECT record_id, story_id, ?, 'code', ?, ?, ? FROM stories"
                    " WHERE story_id=?", (it.source, c.fatal, "after one re-code", run_id,
                                          it.story_id))
        return
    s = c.spine
    con.execute("INSERT INTO story_spine (story_id, photo_class, media_type, photo_subtype,"
                " primary_stage, failure_owner, metric_node, outcome, mode_used, severity,"
                " urgency, workaround, workaround_text, coding_conf, why, run_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (it.story_id, s["photo_class"], s["media_type"], s["photo_subtype"],
                 s["primary_stage"], s["failure_owner"], s["metric_node"], s["outcome"],
                 s["mode_used"], s["severity"], s["urgency"], s["workaround"],
                 s["workaround_text"], s["coding_conf"], s["why"], run_id))
    con.executemany("INSERT OR IGNORE INTO story_codes (story_id, question, value, accuracy, seq,"
                    " inferred, confidence, run_id) VALUES (?,?,?,?,?,?,?,?)",
                    [(it.story_id, q, v, acc, seq, int(cb.is_inferred(q)), s["coding_conf"],
                      run_id) for q, v, acc, seq in c.rows])
    con.executemany("INSERT INTO evidence (story_id, field, span, verified, run_id)"
                    " VALUES (?,?,?,1,?)",
                    [(it.story_id, f, sp, run_id) for f, sp in c.evidence.items()])
    con.executemany("INSERT INTO queries (story_id, query_text, attempt_no, worked, run_id)"
                    " VALUES (?,?,?,?,?)",
                    [(it.story_id, t, k, w, run_id) for t, k, w in c.queries])
    # [CTX] §15.1: a video-only story is adjacent, whatever Pass 1 said (P3-INV-9).
    if s["media_type"] == "video":
        con.execute("UPDATE stories SET bucket='adjacent', bucket_reason='video_out_of_scope:"
                    " media_type coded video' WHERE story_id=? AND bucket<>'adjacent'",
                    (it.story_id,))


# --------------------------------------------------------------- responses
def answer_of(resp: dict) -> dict | str:
    """The parsed coding, or a failure reason."""
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for ct in item.get("content", []):
                if ct.get("type") == "refusal":
                    return "model_refusal"
                if ct.get("type") == "output_text":
                    try:
                        return json.loads(ct["text"])
                    except json.JSONDecodeError:
                        return "coding_failed"
    return "coding_failed"


def quarantine(story_id: str, resp: dict) -> None:
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    (QUARANTINE / f"code_{story_id.replace(':', '_')}.json").write_text(json.dumps(resp)[:200_000])


def code_sync(client, cb, items: list[Item], run: rmod.Run, *, model: str = MODEL,
              effort: str | None = None, workers: int = 8) -> dict[str, tuple[Coded, dict]]:
    """Synchronous path (fixtures, retries, dual coding). One re-code on a
    fatal result, then the result stands and is counted."""
    system = system_prompt(cb)

    def one(it):
        last = None
        for _ in range(2):
            resp = client.responses.create(**request_body(cb, it, system, model=model,
                                                          effort=effort)).model_dump()
            i, o, ch = seg._usage(resp)
            run.add_usage(input_tokens=i, output_tokens=o, cached_tokens=ch)
            a = answer_of(resp)
            c = Coded(it.story_id, fatal=a) if isinstance(a, str) else validate(cb, it, a)
            last = (c, (i, o, ch))
            if not c.fatal:
                return it.story_id, last
            quarantine(it.story_id, resp)
        return it.story_id, last

    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, items))


def batch_and_wait(client, name: str, bodies: list[tuple[str, dict]], *, poll_s: int = 30,
                   timeout_s: int = 5400) -> list[dict]:
    """Submit a small batch and block until it finishes (half price; minutes,
    not hours, for tens of requests). Returns the output lines, parsed."""
    import time
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = BATCH_DIR / f"{name}_input.jsonl"
    path.write_text("".join(json.dumps({"custom_id": cid, "method": "POST",
                                        "url": "/v1/responses", "body": b}) + "\n"
                            for cid, b in bodies))
    up = client.files.create(file=path.open("rb"), purpose="batch")
    b = client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                              completion_window="24h")
    waited = 0
    while b.status not in ("completed", "expired", "failed", "cancelled"):
        if waited > timeout_s:
            raise SystemExit(f"batch {b.id} still {b.status} after {waited}s — collect it later")
        time.sleep(poll_s)
        waited += poll_s
        b = client.batches.retrieve(b.id)
        print(f"  batch {b.id}: {b.status} {b.request_counts}", flush=True)
    lines = client.files.content(b.output_file_id).text.splitlines() if b.output_file_id else []
    (BATCH_DIR / f"{name}_output.jsonl").write_text("\n".join(lines))
    return [json.loads(x) for x in lines]


# ----------------------------------------------------------------- fixtures
def fixture_items() -> tuple[list[Item], dict[str, dict]]:
    rows = [json.loads(x) for x in (seg.FIX / "stories_authored.jsonl").read_text().splitlines()
            if x.strip()]
    items = [Item(r["id"], "reddit", None, r["text"], "", r["expected"]["bucket"], 10, r["text"],
                  [(0, len(r["text"]))], CORE_BLOCKS) for r in rows]
    return items, {r["id"]: r for r in rows}


TRIPLE = ("5.2", "5.3", "5.4")


def score_fixtures(res: dict[str, tuple[Coded, dict]], exp: dict[str, dict]) -> dict:
    rows, n = [], Counter()
    for sid, r in exp.items():
        c, use = res[sid]
        e = r["expected"]
        row = {"id": sid, "group": r["group"], "fatal": c.fatal, "bucket": e["bucket"],
               "usage": list(use)}
        if c.fatal:
            rows.append(row)
            n["fatal"] += 1
            continue
        s = c.spine
        row.update(primary_stage=[e["primary_stage"], s["primary_stage"]],
                   photo_class=[e["photo_class"], s["photo_class"]],
                   media_type=[e["media_type"], s["media_type"]],
                   outcome=[e["outcome"], s["outcome"]], why=s["why"])
        exp_codes, got_hits, missed = e["codes"], 0, []
        for q, vals in exp_codes.items():
            got = ([acc for qq, _, acc, _ in c.rows if qq == "2.2"] if q == "2.2"
                   else c.codes.get(q, []))
            for v in vals:
                if v in got:
                    got_hits += 1
                else:
                    missed.append(f"{q}:{v} (got {got})")
        row["codes_hit"] = [got_hits, sum(len(v) for v in exp_codes.values())]
        row["codes_missed"] = missed
        if r["group"] == "triple_5234":
            want = next(q for q in TRIPLE if q in exp_codes)
            # EC-CODE-3 is about WHICH of the three a story lands in; the value
            # inside it is scored separately (Docs/decisions.md D-9).
            row["triple_question"] = substantive(c.codes.get(want, [])) and not any(
                substantive(c.codes.get(q, [])) for q in TRIPLE if q != want)
            row["triple_values"] = row["triple_question"] and all(
                v in c.codes.get(want, []) for v in exp_codes[want])
            row["triple_got"] = {q: c.codes.get(q) for q in TRIPLE}
        row["problems"] = dict(c.problems)
        row["evidence_fields"] = len(c.evidence)
        rows.append(row)

    def acc(field, group=None):
        rs = [r for r in rows if not r["fatal"] and (group is None or r["group"] == group)]
        return sum(r[field][0] == r[field][1] for r in rs) / max(len(rs), 1)

    tri = [r for r in rows if r["group"] == "triple_5234" and not r["fatal"]]
    hits = [r["codes_hit"] for r in rows if not r["fatal"]]
    summary = {
        "T8_primary_stage": acc("primary_stage"),
        "P3_MET_2_triple_question": sum(r["triple_question"] for r in tri) / max(len(tri), 1),
        "triple_question_and_values": sum(r["triple_values"] for r in tri) / max(len(tri), 1),
        "P3_MET_3_stage2_vs_4": acc("primary_stage", "stage2_vs_4"),
        "photo_class": acc("photo_class"), "media_type": acc("media_type"),
        "outcome": acc("outcome"),
        "codes_recall": sum(h for h, _ in hits) / max(sum(t for _, t in hits), 1),
        "fatal": n["fatal"], "n": len(rows),
        "by_group_primary_stage": {g: acc("primary_stage", g) for g in
                                   sorted({r["group"] for r in rows})},
    }
    return {"summary": summary, "rows": rows}


# -------------------------------------------------------------------- batch
def estimate(items: list[Item], cb) -> dict:
    fx = latest_fixture()
    u = fx["usage"]
    in_per = u["input"] / u["requests"]
    out_by = {}
    for b in ("core", "adjacent"):
        rs = [r["usage"][1] for r in fx["rows"] if r.get("bucket") == b and r.get("usage")]
        out_by[b] = sum(rs) / len(rs)
    n_all = len(questions_for(cb, CORE_BLOCKS))
    in_tok = out_tok = 0.0
    for it in items:
        k = len(questions_for(cb, it.blocks))
        in_tok += in_per + len(render(it)) / 4
        out_tok += out_by["core" if it.bucket == "core" else "adjacent"] * (0.35 + 0.65 * k / n_all)
    cached = in_tok * u["cached"] / max(u["input"], 1)
    usd = rmod.cost(MODEL, input_tokens=int(in_tok), cached_tokens=int(cached),
                    output_tokens=int(out_tok), batch=True)
    return {"stories": len(items), "by_blocks": dict(Counter("+".join(i.blocks) for i in items)),
            "input_tokens": int(in_tok), "cached_share": round(cached / max(in_tok, 1), 2),
            "output_tokens": int(out_tok), "out_per_story_fixture": out_by, "usd": round(usd, 3),
            "from_fixture_run": fx["run_id"]}


def latest_fixture() -> dict:
    runs = sorted(ARTIFACTS.glob("code_fixtures_*.json"))
    if not runs:
        raise SystemExit("run `fixtures` first — the estimate uses its measured tokens")
    return json.loads(runs[-1].read_text())


def submit(con, client, cb, items: list[Item], est: dict, *, stage: str = "code",
           estimate_usd: float = ESTIMATE_USD) -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        raise SystemExit(f"{MANIFEST} exists — a coding batch is in flight. Run `collect`.")
    if not items:
        raise SystemExit("nothing to code — every live story is coded or marked")
    system = system_prompt(cb)
    run = rmod.Run(con, stage, model=MODEL, batch=True, estimate_usd=estimate_usd,
                   prompt_version=PROMPT_VERSION, codebook_version=cb.version_string,
                   effort=EFFORT_BY_BUCKET, n_stories=len(items), projection=est)
    run.__enter__()
    path = BATCH_DIR / f"{run.run_id}_input.jsonl"
    with path.open("w") as f:
        for k, it in enumerate(items):
            f.write(json.dumps({"custom_id": f"req-{k:05d}", "method": "POST",
                                "url": "/v1/responses",
                                "body": request_body(cb, it, system)}) + "\n")
    up = client.files.create(file=path.open("rb"), purpose="batch")
    b = client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                              completion_window="24h")
    MANIFEST.write_text(json.dumps({"run_id": run.run_id, "batch_id": b.id,
                                    "requests": {f"req-{k:05d}": it.story_id
                                                 for k, it in enumerate(items)}}))
    con.execute("UPDATE runs SET params_json=json_set(params_json,'$.batch_id',?) WHERE run_id=?",
                (b.id, run.run_id))
    con.commit()
    print(f"submitted {len(items)} stories · batch {b.id} · run {run.run_id}")


def collect(con, client, cb, *, accept_overrun: bool = False) -> None:
    """Writes every story that coded cleanly; re-codes the rest ONCE,
    synchronously; what still fails is marked and counted. A request missing
    from the output is left un-coded, so the next `submit` picks it up by diff
    (X-6: a completed story is never re-submitted)."""
    man = json.loads(MANIFEST.read_text())
    b = client.batches.retrieve(man["batch_id"])
    print(f"batch {b.id}: {b.status} · {b.request_counts}")
    if b.status not in ("completed", "expired", "failed", "cancelled"):
        raise SystemExit(3)
    run_id = man["run_id"]
    lines = client.files.content(b.output_file_id).text.splitlines() if b.output_file_id else []
    (BATCH_DIR / f"{run_id}_output.jsonl").write_text("\n".join(lines))
    items = {i.story_id: i for i in live_items(con, skip_done=False)}
    tokens, results, retry = [0, 0, 0], {}, []
    for line in lines:
        o = json.loads(line)
        sid = man["requests"][o["custom_id"]]
        body = (o.get("response") or {}).get("body") or {}
        for i, v in enumerate(seg._usage(body)):
            tokens[i] += v
        it = items.get(sid)
        if it is None:
            continue
        a = answer_of(body)
        c = Coded(sid, fatal=a) if isinstance(a, str) else validate(cb, it, a)
        if c.fatal:
            quarantine(sid, body)
            retry.append(it)
        else:
            results[sid] = c
    got = {man["requests"][json.loads(x)["custom_id"]] for x in lines}
    missing = sorted(set(man["requests"].values()) - got)
    usd = rmod.cost(MODEL, input_tokens=tokens[0], output_tokens=tokens[1],
                    cached_tokens=tokens[2], batch=True)
    est = con.execute("SELECT estimate_usd FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]
    over = usd > rmod.HALT_MULTIPLE * est
    status = "halted_budget" if over and not accept_overrun else "ok"
    con.execute("UPDATE runs SET finished_at=?, status=?, input_tokens=?, output_tokens=?,"
                " cached_tokens=?, cost_usd=?, params_json=json_set(params_json,"
                "'$.missing_requests',json(?)) WHERE run_id=?",
                (rmod._now(), status, tokens[0], tokens[1], tokens[2], round(usd, 6),
                 json.dumps(missing), run_id))
    con.commit()
    print(f"cost ${usd:.4f} against ${est:.2f} estimate · {len(results)} coded · "
          f"{len(retry)} to re-code · {len(missing)} missing")
    if status != "ok":
        raise SystemExit(f"T-19: ${usd:.3f} > 1.5 × ${est:.2f}. Output saved; decide, then "
                         "re-run collect with --accept-overrun.")
    clear(con, list(results))
    for sid, c in results.items():
        write(con, cb, items[sid], c, run_id)
    con.commit()
    probs: Counter = sum((c.problems for c in results.values()), Counter())
    if retry:
        with rmod.Run(con, "code-retry", model=MODEL, estimate_usd=0.30,
                      prompt_version=PROMPT_VERSION, codebook_version=cb.version_string,
                      effort=EFFORT_BY_BUCKET, of_run=run_id, n=len(retry)) as r2:
            again = code_sync(client, cb, retry, r2)
            clear(con, [i.story_id for i in retry])
            for it in retry:
                c, _ = again[it.story_id]
                write(con, cb, it, c, run_id)
                probs["retried"] += 1
                probs[f"after_retry_{c.fatal or 'ok'}"] += 1
            con.commit()
    con.execute("UPDATE runs SET n_input=?, n_output=?, params_json=json_set(params_json,"
                "'$.problems',json(?)) WHERE run_id=?",
                (len(man["requests"]), len(results) + probs.get("after_retry_ok", 0),
                 json.dumps(dict(probs)), run_id))
    con.commit()
    MANIFEST.rename(BATCH_DIR / f"{run_id}_manifest.json")
    print(json.dumps(dict(probs), indent=1))


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fixtures", "estimate", "submit", "collect", "prompt",
                                    "recode"])
    ap.add_argument("--accept-overrun", action="store_true")
    ap.add_argument("--yes", action="store_true", help="submit: the projection was reviewed")
    ap.add_argument("--batch", action="store_true", help="fixtures: through the Batch API")
    args = ap.parse_args()
    cb = cbm.load()
    con = dbm.init()
    if args.cmd == "prompt":
        print(system_prompt(cb))
        return 0
    if args.cmd == "estimate":
        print(json.dumps(estimate(live_items(con), cb), indent=1))
        return 0
    vals = envm.load()
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=vals["OPENAI_API_KEY"])
    if args.cmd == "fixtures":
        items, exp = fixture_items()
        with rmod.Run(con, "code-fixtures", model=MODEL, estimate_usd=0.80 if args.batch else 1.20,
                      prompt_version=PROMPT_VERSION, codebook_version=cb.version_string,
                      effort=EFFORT_BY_BUCKET, batch=args.batch) as run:
            if args.batch:
                system = system_prompt(cb)
                out = batch_and_wait(client, run.run_id,
                                     [(it.story_id, request_body(cb, it, system)) for it in items])
                byid = {it.story_id: it for it in items}
                res = {}
                for o in out:
                    body = (o.get("response") or {}).get("body") or {}
                    u = seg._usage(body)
                    run.add_usage(input_tokens=u[0], output_tokens=u[1], cached_tokens=u[2])
                    a = answer_of(body)
                    it = byid[o["custom_id"]]
                    res[it.story_id] = ((Coded(it.story_id, fatal=a) if isinstance(a, str)
                                         else validate(cb, it, a)), u)
                for it in items:
                    res.setdefault(it.story_id, (Coded(it.story_id, fatal="coding_failed"),
                                                 (0, 0, 0)))
            else:
                res = code_sync(client, cb, items, run)
            sc = score_fixtures(res, exp)
            sc["run_id"], sc["prompt_version"] = run.run_id, PROMPT_VERSION
            sc["usage"] = {"input": run.input_tokens, "cached": run.cached_tokens,
                           "output": run.output_tokens, "usd": run.cost_usd(),
                           "requests": len(items)}
            con.execute("UPDATE runs SET params_json=json_set(params_json,'$.summary',json(?))"
                        " WHERE run_id=?", (json.dumps(sc["summary"]), run.run_id))
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / f"code_fixtures_{sc['run_id']}.json").write_text(json.dumps(sc, indent=1))
        print(json.dumps(sc["summary"], indent=1), json.dumps(sc["usage"]))
        return 0
    if args.cmd == "submit":
        items = live_items(con)
        est = estimate(items, cb)
        print(json.dumps(est))
        if est["usd"] > rmod.HALT_MULTIPLE * ESTIMATE_USD or not args.yes:
            print("review the projection, then re-run with --yes", file=sys.stderr)
            return 1
        submit(con, client, cb, items, est)
        return 0
    if args.cmd == "recode":
        # Stories whose stored coding breaks the Stage 0 rule (D-9), re-coded
        # with the current prompt. collect() replaces their rows.
        ids = stage0_suspects(con)
        items = [i for i in live_items(con, skip_done=False) if i.story_id in ids]
        est = estimate(items, cb)
        print(json.dumps(est))
        if not args.yes:
            print("review the projection, then re-run with --yes", file=sys.stderr)
            return 1
        submit(con, client, cb, items, est, stage="code-recode",
               estimate_usd=max(round(est["usd"], 2), 0.20))
        return 0
    collect(con, client, cb, accept_overrun=args.accept_overrun)
    return 0


def stage0_suspects(con) -> set[str]:
    codes: dict[str, dict[str, list[str]]] = {}
    for r in con.execute("SELECT story_id, question, value FROM story_codes"
                         " WHERE question IN ('0.1','0.2')"):
        codes.setdefault(r[0], {}).setdefault(r[1], []).append(r[2])
    return {r[0] for r in con.execute("SELECT story_id, outcome FROM story_spine"
                                      " WHERE primary_stage='0'")
            if stage0_without_evidence("0", codes.get(r[0], {}), r[1])}


if __name__ == "__main__":
    raise SystemExit(main())
