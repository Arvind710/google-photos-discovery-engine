"""Try it — the pipeline, live, on one pasted post ([CTX] §15.6; implementationplan
task 5.6). The SAME code as the corpus run, not a demo of it:

    find     pipeline.segment.stories — gpt-5-mini, the segment_v1 prompt, anchors
             located verbatim in the pasted text
    confirm  pipeline.segment.confirm — gpt-5 judges each candidate
    code     pipeline.classify.blocks — gpt-5, the frozen codebook, the story's
             blocks; every quote located in the pasted text or dropped

Nothing is written: the corpus is frozen and the app's database is read-only.
Only the FIRST confirmed story is coded, to bound the cost of one click.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

MAX_CHARS = 2500


@dataclass
class Trace:
    text: str
    stories: list[dict] = field(default_factory=list)   # finder + confirmer, per story
    coded: dict | None = None                            # the first confirmed story
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str = ""


def _cost(model: str, resp: dict) -> float:
    from pipeline.common.runs import cost
    from pipeline.segment import stories as seg
    i, o, c = seg._usage(resp)
    return cost(model, input_tokens=i, output_tokens=o, cached_tokens=c)


def run(client, text: str) -> Trace:
    from pipeline.classify import blocks as B
    from pipeline.common import codebook as cbm
    from pipeline.segment import confirm as C
    from pipeline.segment import stories as seg

    t0 = time.time()
    tr = Trace(text=text)
    rec = seg._fixture_record("tryit", "reddit", [("you", text)])
    req = seg.pack(seg.units_of(rec))[0]
    try:
        resp = client.responses.create(**seg.request_body(req, system=seg.PROMPT.read_text())
                                       ).model_dump()
        tr.cost_usd += _cost(seg.MODEL, resp)
        found = seg.merge(rec, [seg.parse_output(seg._output_text(resp), req)[u.uid]
                                for u in req])
    except Exception as exc:                                      # noqa: BLE001
        tr.error = f"The story finder could not be reached: {exc}"
        return tr
    if not found.stories:
        tr.notes.append("No retrieval story was found in this text — no one trying to find a "
                        "particular photo. In the corpus such records are kept and marked "
                        "'no story', never deleted.")
        tr.seconds = time.time() - t0
        return tr
    cands = [C.Candidate(f"s{k}", "reddit", None, s.text, "", s.bucket, s.reaches_stage)
             for k, s in enumerate(found.stories)]
    creq = C.pack(cands)[0]
    try:
        cresp = client.responses.create(**C.body(creq, C.system_prompt())).model_dump()
        tr.cost_usd += _cost(C.MODEL, cresp)
        verdicts = C.parse(seg._output_text(cresp), creq)
    except Exception as exc:                                      # noqa: BLE001
        tr.error = f"The confirmation step could not be reached: {exc}"
        return tr
    for s, c in zip(found.stories, cands, strict=True):
        v = verdicts.get(c.story_id) or {}
        tr.stories.append({
            "text": s.text, "finder_bucket": s.bucket, "finder_reason": s.reason,
            "confidence": s.confidence, "is_story": v.get("is_story", True),
            "bucket": v.get("bucket", s.bucket),
            "reaches_stage": max(s.reaches_stage, int(v.get("reaches_stage", 0) or 0)),
            "confirm_reason": v.get("reason", ""), "char_start": s.char_start,
            "char_end": s.char_end})
    kept = [s for s in tr.stories if s["is_story"]]
    if not kept:
        tr.notes.append("The finder proposed a story, and the stronger model rejected it "
                        "against the written definition — as it rejected most candidates in "
                        "the corpus.")
        tr.seconds = time.time() - t0
        return tr
    s = kept[0]
    cb = cbm.load()
    bl = B.blocks_for(s["bucket"], s["reaches_stage"])
    it = B.Item("tryit:0", "reddit", None, s["text"], "", s["bucket"], s["reaches_stage"],
                rec.text, [(s["char_start"], s["char_end"])], bl)
    try:
        body = B.request_body(cb, it, B.system_prompt(cb))
        kresp = client.responses.create(**body).model_dump()
        tr.cost_usd += _cost(B.MODEL, kresp)
        ans = B.answer_of(kresp)
    except Exception as exc:                                      # noqa: BLE001
        tr.error = f"The coder could not be reached: {exc}"
        return tr
    if isinstance(ans, str):
        tr.error = f"The coder's answer could not be used ({ans})."
        return tr
    c = B.validate(cb, it, ans)
    if c.fatal:
        tr.notes.append("The coder's quote for the stage could not be found in the text, so "
                        "in the corpus this story would be re-coded once, then marked "
                        "'span unverified' and counted — never written unverified.")
        tr.seconds = time.time() - t0
        return tr
    codes = {q: v for q, v in c.codes.items() if any(x != "not_stated" for x in v)}
    tr.coded = {"spine": {k: v for k, v in c.spine.items() if k != "severity_parts"},
                "blocks": bl, "codes": codes,
                "evidence": c.evidence, "queries": [q[0] for q in c.queries],
                "asked": len(B.questions_for(cb, bl)),
                "dropped_quotes": int(c.problems.get("quote_unverified", 0)),
                "stage_name": cb.stages[c.spine["primary_stage"]]["name"],
                "effort": B.EFFORT_BY_BUCKET[s["bucket"]]}
    tr.seconds = time.time() - t0
    return tr
