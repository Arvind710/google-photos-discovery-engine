"""The recommendation ([CTX] §9.4, architecture.md §6, implementationplan.md
task 4.5). gpt-5, one request through the Batch API.

The model sees the FACTS PACK only (synthesise/facts.py) — never raw stories —
and writes a structured recommendation in which every statement cites fact
ids. Code then checks what a prompt alone cannot hold (AR-9, "rules backed by
the checker hold"):

    cites      every statement cites ≥ 1 fact, and every cited id exists (P4-INV-6)
    numbers    every number in a statement appears in a fact it cites (T-14's
               rule applied here), except stage numbers and question ids
    top        the top opportunity IS the rank-1 candidate of analysis_opportunity
    falsifier  at least one, non-empty (P4-INV-7)
    proxy      no count or share is attached to users, searches or attempts
               (EC-ASK-1: a share of stories is never a share of users)

A failing check gets ONE synchronous repair with the problems listed; if it
still fails, nothing is stored and the command exits non-zero.

It is labelled everywhere as a hypothesis to be validated in Part 3.

    python -m pipeline.synthesise.recommendation
"""

from __future__ import annotations

import json
import re
import sys

from pipeline.classify import blocks as B
from pipeline.common import codebook as cbm
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod
from pipeline.segment import stories as seg
from pipeline.synthesise import facts as F

PROMPT_VERSION = "recommendation_v1.1"   # v1.1: named factor, gate-passing runner-up
EFFORT = "medium"
LABEL = "A hypothesis to be validated in the Part 3 interviews — not a finding."

PROMPT = """You write the recommendation of a discovery engine that analysed public posts
about failing to find a vaguely remembered photo in Google Photos. The goal metric is the
share of users who succeed at retrieving a photo they remember but cannot precisely
describe. The recommendation is a HYPOTHESIS for user interviews, not a conclusion.

You may use ONLY the facts inside <facts>. Every statement you write cites the ids of the
facts that support it (e.g. ["F02", "F23"]). A number you write must appear in a fact you
cite; do not compute new percentages. Write counts as "36 of 115 core stories".

Rules that are checked in code:
- Every share is a share of coded PUBLIC STORIES. Never write it as a share of users, of
  searches or of attempts, and never as a success or failure rate.
- Fields marked low_reliability may be mentioned only as caveats, never as evidence.
- Name what is thin: 115 core stories, below the 300 the engine was designed for; only
  one candidate clears the evidence floor.
- Plain words; stage numbers and question ids only in brackets.

Return:
- top: the rank-1 opportunity (its candidate_id), a one-sentence problem statement framed
  as WHY retrieval fails despite partial memory (not "search is hard"), and the reasoning
  chain in four steps — metric_node, evidence, stage, root_cause — each with cites. The
  metric_node step names the factor of the goal-metric decomposition this stage drags
  down and why improving it moves retrieval success. Never say a fix changes a share of
  public stories: those shares describe what people wrote, not an outcome.
- runner_up: the best OTHER candidate that passes both gates (status ranked or
  below_floor — never a gated_out one), and why it is not the top, with cites.
- target_segment: the recommended direction (e.g. sentimental vs utility photos) and why,
  with cites; say plainly if the evidence cannot yet decide it.
- root_cause_hypothesis and intelligence_needed (where in the journey an AI capability
  would act, and what kind of inference), each with cites.
- falsifiers: 2–4 observations in the interviews that would prove this wrong, each with cites.
- caveats: 2–4, each with cites."""


def _item(extra: dict | None = None) -> dict:
    return B._obj({"text": B.STR, "cites": {"type": "array", "items": B.STR}, **(extra or {})})


SCHEMA = B._obj({
    "top": B._obj({"candidate_id": B.STR, "problem_statement": _item(),
                   "chain": {"type": "array", "items": _item({"step": {
                       "type": "string",
                       "enum": ["metric_node", "evidence", "stage", "root_cause"]}})}}),
    "runner_up": B._obj({"candidate_id": B.STR, "why_not_top": _item()}),
    "target_segment": B._obj({"direction": B.STR, "why": _item()}),
    "root_cause_hypothesis": _item(),
    "intelligence_needed": _item(),
    "falsifiers": {"type": "array", "items": _item()},
    "caveats": {"type": "array", "items": _item()}})

_NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
_MOVE_SHARE = re.compile(r"\b(rais|increas|improv|reduc|lower|boost)\w*\b[^.;]{0,60}\bshare of"
                         r"\b[^.;]{0,30}\bstories", re.I)
_PROXY = re.compile(r"(\d+%|\d+ of \d+|\bmost|\bmajority)[^.;]{0,50}\b(users|searches|attempts|"
                    r"people who search)\b", re.I)


def statements(x, path="") -> list[tuple[str, dict]]:
    """Every {text, cites} object in the output, with its path."""
    out = []
    if isinstance(x, dict):
        if "text" in x and "cites" in x:
            out.append((path, x))
        for k, v in x.items():
            out += statements(v, f"{path}.{k}")
    elif isinstance(x, list):
        for k, v in enumerate(x):
            out += statements(v, f"{path}[{k}]")
    return out


def allowed_numbers(cb: cbm.Codebook) -> set[str]:
    return {str(i) for i in range(11)} | set(cb.questions)


def check(out: dict, pack: F.Pack, cb: cbm.Codebook, *, top_id: str | None,
          candidates: set[str], runner_ok: set[str] | None = None) -> list[str]:
    problems = []
    facts = {f["id"]: f["text"] for f in pack.facts}
    free = allowed_numbers(cb)
    for path, s in statements(out):
        if not s["text"].strip():
            problems.append(f"{path}: empty text")
        if not s["cites"]:
            problems.append(f"{path}: cites no fact")
        bad = [c for c in s["cites"] if c not in facts]
        if bad:
            problems.append(f"{path}: cites unknown facts {bad}")
        cited = re.sub(r"(?<=\d),(?=\d{3})", "", " ".join(facts.get(c, "") for c in s["cites"]))
        for n in (x.replace(",", "") for x in _NUM.findall(s["text"])):
            if n not in free and not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", cited):
                problems.append(f"{path}: number {n} is not in the facts it cites")
        if _PROXY.search(s["text"]):
            problems.append(f"{path}: a count or share attached to users/searches/attempts")
        if _MOVE_SHARE.search(s["text"]):
            problems.append(f"{path}: treats a share of public stories as an outcome to move")
    if "top" in out:
        if top_id and out["top"]["candidate_id"] != top_id:
            problems.append(f"top is {out['top']['candidate_id']}, the ranking's first is {top_id}")
        steps = [c["step"] for c in out["top"]["chain"]]
        if sorted(set(steps)) != sorted(["metric_node", "evidence", "stage", "root_cause"]):
            problems.append(f"chain steps {steps} are not the four required")
        ru = out["runner_up"]["candidate_id"]
        if ru == out["top"]["candidate_id"] or ru not in candidates:
            problems.append(f"runner_up {ru} is not another candidate")
        elif runner_ok is not None and ru not in runner_ok:
            problems.append(f"runner_up {ru} does not pass both gates; choose from "
                            f"{sorted(runner_ok)}")
        if not [f for f in out["falsifiers"] if f["text"].strip()]:
            problems.append("no falsifier (P4-INV-7)")
    return problems


def request(model_input: str, system: str, schema: dict, name: str) -> dict:
    return {"model": B.MODEL, "instructions": system, "reasoning": {"effort": EFFORT},
            "input": model_input,
            "text": {"format": {"type": "json_schema", "name": name, "schema": schema,
                                "strict": True}}}


def run_one(con, client, *, stage: str, name: str, body: dict, validate, prompt_version: str,
            estimate_usd: float) -> tuple[dict, list[str], bool, str]:
    """Batch once; on failing checks, one synchronous repair. Returns
    (output, problems left, repaired?, run_id)."""
    with rmod.Run(con, stage, model=B.MODEL, batch=True, estimate_usd=estimate_usd,
                  prompt_version=prompt_version) as run:
        out = B.batch_and_wait(client, run.run_id, [(name, body)], poll_s=20)
        resp = (out[0].get("response") or {}).get("body") or {} if out else {}
        u = seg._usage(resp)
        run.add_usage(input_tokens=u[0], output_tokens=u[1], cached_tokens=u[2])
        ans = B.answer_of(resp)
        run_id = run.run_id
    problems = [ans] if isinstance(ans, str) else validate(ans)
    repaired = False
    if problems:
        with rmod.Run(con, f"{stage}-repair", model=B.MODEL, estimate_usd=estimate_usd,
                      prompt_version=prompt_version, of_run=run_id) as r2:
            fix = dict(body)
            fix["input"] = (body["input"] + "\n\n<previous_answer>\n"
                            + (json.dumps(ans) if isinstance(ans, dict) else ans)
                            + "\n</previous_answer>\n\nThe previous answer failed these checks;"
                            " return a corrected answer that passes them:\n- "
                            + "\n- ".join(problems))
            resp = client.responses.create(**fix).model_dump()
            u = seg._usage(resp)
            r2.add_usage(input_tokens=u[0], output_tokens=u[1], cached_tokens=u[2])
        ans = B.answer_of(resp)
        problems = [ans] if isinstance(ans, str) else validate(ans)
        repaired = True
    return (ans if isinstance(ans, dict) else {}), problems, repaired, run_id


def store(con, kind: str, content: dict, pack: F.Pack, checks: dict, run_id: str) -> None:
    con.execute("INSERT OR REPLACE INTO analysis_synthesis (kind, content_json, facts_json,"
                " checks_json, run_id) VALUES (?,?,?,?,?)",
                (kind, json.dumps(content), json.dumps(pack.facts), json.dumps(checks), run_id))
    con.commit()
    (seg.ARTIFACTS / f"{kind}_{run_id}.json").write_text(json.dumps(
        {"run_id": run_id, "content": content, "facts": pack.facts, "checks": checks}, indent=1))


def client_or_exit():
    vals = envm.load()
    if not vals.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY must be set in .env", file=sys.stderr)
        raise SystemExit(2)
    from openai import OpenAI
    return OpenAI(api_key=vals["OPENAI_API_KEY"])


def main() -> int:
    client = client_or_exit()
    con = dbm.init()
    cb = cbm.load()
    pack = F.build(con, cb)
    top = con.execute("SELECT candidate_id FROM analysis_opportunity WHERE rank_headline=1"
                      ).fetchone()
    status = {r[0] for r in con.execute("SELECT DISTINCT inputs_status FROM analysis_opportunity")}
    if status != {"approved"}:
        raise SystemExit(f"scoring inputs are {status}, not approved — nothing to recommend yet")
    cands = {r[0] for r in con.execute("SELECT candidate_id FROM analysis_opportunity"
                                       " WHERE status <> 'not_a_failure'")}
    passing = {r[0] for r in con.execute("SELECT candidate_id FROM analysis_opportunity"
                                         " WHERE status IN ('ranked','below_floor')")}
    fact_text = "\n".join(f"{f['id']}: {f['text']}" for f in pack.facts)
    body = request(f"<facts>\n{fact_text}\n</facts>", PROMPT, SCHEMA, "recommendation")
    out, problems, repaired, run_id = run_one(
        con, client, stage="synth-recommendation", name="recommendation", body=body,
        validate=lambda a: check(a, pack, cb, top_id=top and top[0], candidates=cands,
                                 runner_ok=(passing - {top and top[0]}) or None),
        prompt_version=PROMPT_VERSION, estimate_usd=0.30)
    if problems:
        print("recommendation failed its checks after one repair:\n- " + "\n- ".join(problems))
        return 1
    out["label"] = LABEL
    store(con, "recommendation", out, pack, {"problems": [], "repaired": repaired}, run_id)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
