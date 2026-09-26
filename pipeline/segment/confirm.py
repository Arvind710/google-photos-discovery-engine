"""Pass 1b — gpt-5 confirms every candidate story gpt-5-mini found
(Docs/decisions.md D-8).

The dual-model check found gpt-5-mini recall-first to a fault: on story-bearing
records gpt-5 returned fewer stories in 39 of 60, and more in none. Nearly every
disputed candidate was a general deletion, device or export problem with no
particular photo sought. gpt-5-mini stays the finder (cheap, run over every
record); gpt-5 becomes the precision step, run over its candidates only.

Per candidate:
- `is_story` false → the story is MARKED `no_story` at stage `segment` with its
  story_id (A.1: marked, not deleted; the row and its text stay).
- `bucket` → gpt-5's is kept. It is the stronger judge on the vague/precise
  boundary; the primary bucket is kept in the artifact.
- `reaches_stage` → the HIGHER of the two (EC-SEG-5: disagreements resolve upward).

The prompt reuses segment_v1.md's definitions verbatim, so the finder and the
confirmer cannot drift apart.

    python -m pipeline.segment.confirm fixtures
    python -m pipeline.segment.confirm submit
    python -m pipeline.segment.confirm collect
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod
from pipeline.segment import stories as seg

MODEL = "gpt-5"
EFFORT = "low"
PROMPT_VERSION = "confirm_v1+segment_v1"
PACK_CHARS = 12_000
PACK_N = 15
LATER_CHARS = 1_500
MANIFEST = seg.BATCH_DIR / "confirm_manifest.json"

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"stories": {"type": "array", "items": {
              "type": "object", "additionalProperties": False,
              "properties": {"id": {"type": "string"}, "is_story": {"type": "boolean"},
                             "bucket": {"type": "string", "enum": list(seg.BUCKETS)},
                             "reaches_stage": {"type": "integer"}, "reason": {"type": "string"}},
              "required": ["id", "is_story", "bucket", "reaches_stage", "reason"]}}},
          "required": ["stories"]}


def system_prompt() -> str:
    """confirm_v1.md + the definitions sections of segment_v1.md, verbatim."""
    s = seg.PROMPT.read_text()
    defs = s[s.index("## What a retrieval story is"):s.index("## Output")]
    return (seg.ROOT / "prompts" / "confirm_v1.md").read_text() + defs


@dataclass
class Candidate:
    story_id: str
    source: str
    context: str | None
    text: str
    later: str
    bucket: str
    reaches_stage: int
    uid: str = ""


def later_posts(rec: seg.Record, char_start: int, author: str | None) -> str:
    if not author or len(rec.posts) < 2:
        return ""
    k = next(i for i, p in enumerate(rec.posts) if p["start"] <= char_start < p["end"])
    out = [rec.text[p["start"]:p["end"]] for p in rec.posts[k + 1:] if p["author_key"] == author]
    return "\n---\n".join(out)[:LATER_CHARS]


def render(c: Candidate) -> str:
    later = f"\nlater posts by the same author:\n{c.later}" if c.later else ""
    return (f'<candidate id="{c.uid}" source="{c.source}" context="{seg._attr(c.context)}">\n'
            f"story:\n{c.text}{later}\n</candidate>")


def pack(cands: list[Candidate]) -> list[list[Candidate]]:
    reqs, cur, size = [], [], 0
    for c in cands:
        n = len(c.text) + len(c.later)
        if cur and (size + n > PACK_CHARS or len(cur) >= PACK_N):
            reqs.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += n
    if cur:
        reqs.append(cur)
    for req in reqs:
        for k, c in enumerate(req, 1):
            c.uid = f"S{k}"
    return reqs


def body(req: list[Candidate], system: str) -> dict:
    return {"model": MODEL, "instructions": system, "reasoning": {"effort": EFFORT},
            "input": "\n\n".join(render(c) for c in req),
            "text": {"format": {"type": "json_schema", "name": "confirmation", "schema": SCHEMA,
                                "strict": True}}}


def parse(text: str, req: list[Candidate]) -> dict[str, dict | None]:
    got = {s["id"]: s for s in json.loads(text).get("stories", [])}
    return {c.story_id: got.get(c.uid) for c in req}


def confirmed_ids() -> set[str]:
    """Stories gpt-5 has already judged, from the committed artifacts. A top-up
    confirms only its own new candidates; a judged story is never re-bought."""
    done: set[str] = set()
    for p in seg.ARTIFACTS.glob("segment_confirm_*.json"):
        done |= {c["story_id"] for c in json.loads(p.read_text())["changes"]}
    return done


def candidates(con) -> list[Candidate]:
    recs = {r.record_id: r for r in seg._all_segmentable(con)}
    done = confirmed_ids()
    out = []
    for s in con.execute("SELECT story_id, record_id, char_start, author_key, text, bucket,"
                         " reaches_stage FROM stories WHERE story_id NOT IN (SELECT story_id FROM"
                         " exclusions WHERE story_id IS NOT NULL) ORDER BY story_id"):
        if s["story_id"] in done:
            continue
        rec = recs[s["record_id"]]
        out.append(Candidate(s["story_id"], rec.source, rec.context, s["text"],
                             later_posts(rec, s["char_start"], s["author_key"]), s["bucket"],
                             s["reaches_stage"]))
    return out


def apply(con, cands: dict[str, Candidate], verdicts: dict[str, dict | None],
          run_id: str) -> dict:
    n: Counter = Counter()
    changes = []
    for sid, v in verdicts.items():
        c = cands[sid]
        if v is None:
            n["unanswered"] += 1                       # left as the finder had it; counted
            continue
        stage = max(c.reaches_stage, int(seg._clamp(v["reaches_stage"], 0, 10)))
        if not v["is_story"]:
            con.execute("INSERT OR IGNORE INTO exclusions (record_id, story_id, source, stage,"
                        " reason, detail, run_id) SELECT record_id, story_id, ?, 'segment',"
                        " 'no_story', ?, ? FROM stories WHERE story_id=?",
                        (c.source, f"rejected by gpt-5 confirmation: {v['reason']}"[:300],
                         run_id, sid))
            n[f"rejected_{c.bucket}"] += 1
        else:
            con.execute("UPDATE stories SET bucket=?, reaches_stage=?,"
                        " bucket_reason=CASE WHEN bucket=? THEN bucket_reason ELSE ? END"
                        " WHERE story_id=?", (v["bucket"], stage, v["bucket"],
                                              v["reason"].strip() or "—", sid))
            n[f"kept_{v['bucket']}"] += 1
            n["bucket_changed"] += v["bucket"] != c.bucket
            n["stage_raised"] += stage > c.reaches_stage
        changes.append({"story_id": sid, "primary": [c.bucket, c.reaches_stage],
                        "confirm": [v["is_story"], v["bucket"], v["reaches_stage"]],
                        "reason": v["reason"]})
    # A record whose every story was rejected is itself a `no_story` record.
    n["records_emptied"] = con.execute(
        "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
        " SELECT s.record_id, r.source, 'segment', 'no_story',"
        " 'every story rejected by gpt-5 confirmation', ? FROM stories s JOIN records r"
        " USING (record_id) GROUP BY s.record_id HAVING sum(s.story_id NOT IN (SELECT story_id"
        " FROM exclusions WHERE story_id IS NOT NULL)) = 0", (run_id,)).rowcount
    con.commit()
    return {"counts": dict(n), "changes": changes}


# ------------------------------------------------------------------ fixtures
def fixtures(con, client) -> None:
    """The two-stage system end to end on the fixtures: mini finds, gpt-5
    confirms, then the same scoring as `stories fixtures`."""
    recs, expect = seg.fixture_records()
    system = system_prompt()
    with rmod.Run(con, "segment-fixtures", model=seg.MODEL, estimate_usd=0.10,
                  prompt_version=seg.PROMPT_VERSION, effort=seg.EFFORT, pipeline="find") as r1:
        results = seg.run_sync(client, recs, r1, model=seg.MODEL, effort=seg.EFFORT)
    cands, where = {}, {}
    for rid, res in results.items():
        for k, s in enumerate(res.stories):
            sid = f"{rid}:{k}"
            cands[sid] = Candidate(sid, res.record.source, None, s.text,
                                   later_posts(res.record, s.char_start, s.author_key), s.bucket,
                                   s.reaches_stage)
            where[sid] = (rid, k)
    reqs = pack(list(cands.values()))
    verdicts: dict[str, dict | None] = {}
    with rmod.Run(con, "confirm-fixtures", model=MODEL, estimate_usd=0.15,
                  prompt_version=PROMPT_VERSION, effort=EFFORT) as r2:
        def one(req):
            resp = client.responses.create(**body(req, system)).model_dump()
            return req, resp
        with ThreadPoolExecutor(8) as ex:
            for req, resp in ex.map(one, reqs):
                i, o, cch = seg._usage(resp)
                r2.add_usage(input_tokens=i, output_tokens=o, cached_tokens=cch)
                verdicts.update(parse(seg._output_text(resp), req))
    for rid, res in results.items():
        kept = []
        for k, s in enumerate(res.stories):
            v = verdicts.get(f"{rid}:{k}")
            if v is None or v["is_story"]:
                if v:
                    s.bucket = v["bucket"]
                    s.reaches_stage = max(s.reaches_stage, int(seg._clamp(v["reaches_stage"], 0, 10)))
                kept.append(s)
        res.stories = kept
    sc = seg.score_fixtures(results, expect)
    sc.update(run_id=r2.run_id, effort=seg.EFFORT, pipeline="find+confirm",
              usage={"find_usd": r1.cost_usd(), "confirm_usd": r2.cost_usd(), "records": len(recs)})
    (seg.ARTIFACTS / f"segment_fixtures_{r2.run_id}.json").write_text(json.dumps(sc, indent=1))
    print(json.dumps(sc["summary"], indent=1), json.dumps(sc["usage"]))


# --------------------------------------------------------------------- batch
def submit(con, client) -> None:
    if MANIFEST.exists():
        raise SystemExit("a confirmation batch is already in flight — run `collect`")
    cands = candidates(con)
    reqs = pack(cands)
    system = system_prompt()
    in_tok = sum(len(system) / 4 + 300 + sum(len(render(c)) for c in r) / 4 for r in reqs)
    est = rmod.cost(MODEL, input_tokens=int(in_tok), output_tokens=1_400 * len(reqs), batch=True)
    print(f"{len(cands)} candidates in {len(reqs)} requests · projected ${est:.3f}")
    run = rmod.Run(con, "segment-confirm", model=MODEL, estimate_usd=round(max(est, 0.60), 2),
                   batch=True, prompt_version=PROMPT_VERSION, effort=EFFORT,
                   n_candidates=len(cands), n_requests=len(reqs), projected_usd=round(est, 3))
    run.__enter__()
    seg.BATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = seg.BATCH_DIR / f"{run.run_id}_input.jsonl"
    mapping = {}
    with path.open("w") as f:
        for k, req in enumerate(reqs):
            cid = f"req-{k:05d}"
            mapping[cid] = [[c.uid, c.story_id] for c in req]
            f.write(json.dumps({"custom_id": cid, "method": "POST", "url": "/v1/responses",
                                "body": body(req, system)}) + "\n")
    up = client.files.create(file=path.open("rb"), purpose="batch")
    b = client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                              completion_window="24h")
    MANIFEST.write_text(json.dumps({"run_id": run.run_id, "batch_id": b.id, "requests": mapping}))
    con.execute("UPDATE runs SET params_json=json_set(params_json,'$.batch_id',?) WHERE run_id=?",
                (b.id, run.run_id))
    con.commit()
    print(f"submitted · batch {b.id} · run {run.run_id}")


def collect(con, client) -> None:
    man = json.loads(MANIFEST.read_text())
    b = client.batches.retrieve(man["batch_id"])
    print(f"batch {b.id}: {b.status} · {b.request_counts}")
    if b.status not in ("completed", "expired", "failed", "cancelled"):
        raise SystemExit(3)
    run_id = man["run_id"]
    lines = client.files.content(b.output_file_id).text.splitlines() if b.output_file_id else []
    (seg.BATCH_DIR / f"{run_id}_output.jsonl").write_text("\n".join(lines))
    cands = {c.story_id: c for c in candidates(con)}
    tokens, verdicts, bad = [0, 0, 0], {}, []
    for line in lines:
        o = json.loads(line)
        rb = (o.get("response") or {}).get("body") or {}
        for i, v in enumerate(seg._usage(rb)):
            tokens[i] += v
        req = [cands[sid] for _, sid in man["requests"][o["custom_id"]]]
        for c, (uid, _) in zip(req, man["requests"][o["custom_id"]], strict=True):
            c.uid = uid
        try:
            verdicts.update(parse(seg._output_text(rb), req))
        except (ValueError, json.JSONDecodeError):
            bad.append(o["custom_id"])
    missing = set(man["requests"]) - {json.loads(x)["custom_id"] for x in lines}
    usd = rmod.cost(MODEL, input_tokens=tokens[0], output_tokens=tokens[1],
                    cached_tokens=tokens[2], batch=True)
    est = con.execute("SELECT estimate_usd FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]
    status = "halted_budget" if usd > rmod.HALT_MULTIPLE * est else "ok"
    con.execute("UPDATE runs SET finished_at=?, status=?, input_tokens=?, output_tokens=?,"
                " cached_tokens=?, cost_usd=? WHERE run_id=?",
                (rmod._now(), status, *tokens[:2], tokens[2], round(usd, 6), run_id))
    con.commit()
    print(f"cost ${usd:.4f} against ${est:.2f} · {len(bad)} unparseable · {len(missing)} missing")
    if status != "ok" or bad or missing:
        raise SystemExit("not applied — see above")
    res = apply(con, cands, verdicts, run_id)
    con.execute("UPDATE runs SET n_input=?, n_output=?, params_json=json_set(params_json,"
                "'$.result',json(?)) WHERE run_id=?",
                (len(cands), sum(v for k, v in res["counts"].items() if k.startswith("kept_")),
                 json.dumps(res["counts"]), run_id))
    con.commit()
    (seg.ARTIFACTS / f"segment_confirm_{run_id}.json").write_text(json.dumps(res, indent=1))
    MANIFEST.rename(seg.BATCH_DIR / f"{run_id}_manifest.json")
    print(json.dumps(res["counts"], indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fixtures", "submit", "collect"])
    args = ap.parse_args()
    vals = envm.load()
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=vals["OPENAI_API_KEY"])
    con = dbm.init()
    {"fixtures": fixtures, "submit": submit, "collect": collect}[args.cmd](con, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
