"""Ask AI, steps 2 and 3 — retrieval and the answerability gate
(architecture.md §7; the Myntra engine's pattern, [CTX] §16). Deterministic:
no model call anywhere in this file.

FOUR CHANNELS
  1 structured facts   whitelisted, parameterised queries over the materialised
                       analysis tables. The planner picks from QUERIES by name;
                       it never writes SQL.
  2 verbatim evidence  BM25 over the live coded stories, filtered to the
                       stages, questions and populations the plan names.
  3 disconfirming      ALWAYS: the rival stages, and stories where nothing went
                       wrong — the evidence against the emerging answer.
  4 method             ALWAYS: the registered method flags, and the reliability
                       and coverage rows for whatever the plan names.

THE GATE decides FULL / PARTIAL / NONE by comparing the plan's closed list of
evidence needs with what came back. Refusing is therefore a property of code:
the same question routes the same way every time, and the golden set can assert
it. Every share handed onward is already formatted by `share()`, so an answer
that copies it inherits the [CTX] §15.5 floor (EC-ASK-5).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from lib import plain, words
from lib.evidence import FLOOR, share

LIVE = "s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT NULL)"
POPULATIONS = ("core", "adjacent")
DIMS = ("primary_stage", "failure_owner", "metric_node", "outcome", "media_type",
        "photo_class", "source")


# ------------------------------------------------------------------ helpers
def _pop(a: dict) -> str:
    p = str(a.get("population") or "core").lower()
    return p if p in POPULATIONS else "core"


def _qid(a: dict) -> str | None:
    m = re.search(r"\b(10|[0-9])\.(\d)\b", str(a.get("question") or ""))
    return f"{m.group(1)}.{m.group(2)}" if m else None


def _dim(a: dict) -> str:
    d = str(a.get("dim") or "").lower()
    return d if d in DIMS else "primary_stage"


def _limit(a: dict, default: int = 12, cap: int = 40) -> int:
    try:
        v = int(a.get("limit") or 0)
    except (TypeError, ValueError):
        return default
    return default if v <= 0 else min(v, cap)


def _xt(con, dim_a: str, dim_b: str, segment: bool, limit: int) -> list[dict]:
    """Cross-tab rows as the model sees them: counts, people, and the share
    already formatted by share() — never a raw fraction to compute from."""
    op = "<>" if segment else "="
    out = []
    for r in con.execute("SELECT * FROM analysis_crosstab WHERE dim_a=? AND dim_b=? AND"
                         f" val_b {op} '_all' ORDER BY val_b, n DESC LIMIT ?",
                         (dim_a, dim_b, limit)):
        out.append({"about": _about(dim_a, r["val_a"]), "group": r["val_b"],
                    "stories": r["n"], "of": r["denom"], "people": r["n_authors"],
                    "share": share(r["n"], r["denom"]).text,
                    "_cite": {"table": "analysis_crosstab",
                              "key": f"{dim_a}={r['val_a']}@{dim_b}:{r['val_b']}"}})
    return out


@cache
def _question_plain(qid: str) -> str:
    """What a codebook question MEANS, from the frozen codebook's `plain` line:
    without it the model read "8.1 one attempt" as quitting and filed 5.2 index
    gaps under hard filters (sweep 9)."""
    import yaml
    cb = yaml.safe_load((Path(__file__).resolve().parents[2] / "codebook" /
                         "journey_v1.yaml").read_text())
    for st in cb["stages"]:
        for q in st["questions"]:
            if q["id"] == qid:
                return q["plain"]
    return ""


def _about(dim_a: str, val: str) -> str:
    pop, _, f = dim_a.partition(".")
    if f == "primary_stage" and val == "9":
        return f"{pop} stories where NOTHING went wrong (Stage 9: found, or found by accident)"
    if f == "primary_stage" and val == "1":
        return f"{pop} stories placed at Stage 1 (why they looked — context, not a failure)"
    if f == "primary_stage":
        return f"{pop} stories first going wrong at Stage {val} ({words.stage_title(val)})"
    if f == "failure_owner":
        return f"{pop} stories whose failure is owned by: {words.owner(val)}"
    if f.startswith("q:"):
        return (f"{pop} stories answering question {f[2:]} ({_question_plain(f[2:])}) "
                f"with {val}")
    return f"{pop} stories with {f} = {val}"


@dataclass(frozen=True)
class Spec:
    """`describe` is what the planner reads when it chooses — a vague one makes a
    wrong choice, which nothing downstream can catch."""
    describe: str
    kinds: tuple[str, ...]
    run: Callable[[sqlite3.Connection, dict], list[dict]]


def _rows(con, sql: str, params: tuple, table: str, key: Callable[[dict], str],
          keep: tuple[str, ...]) -> list[dict]:
    out = []
    for r in con.execute(sql, params):
        d = {k: r[k] for k in keep}
        d["_cite"] = {"table": table, "key": key(dict(r))}
        out.append(d)
    return out


def _derived(con, metrics: tuple[str, ...], pop: str) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM analysis_derived WHERE population=? AND metric IN"
                         f" ({','.join('?' * len(metrics))}) ORDER BY metric, n DESC",
                         (pop, *metrics)):
        d = {"measure": r["metric"], "which": r["key"], "stories": r["n"], "of": r["denom"],
             "people": r["n_authors"]}
        if r["metric"] == "js_divergence":
            d = {"measure": "divergence of this source's stage pattern from the pooled one "
                            "(0 = same, 1 = nothing in common)", "source": r["key"],
                 "divergence": round(r["value"], 2), "stories": r["n"]}
        else:
            d["share"] = share(r["n"], r["denom"]).text
        if r["note"]:
            d["note"] = r["note"]
        d["_cite"] = {"table": "analysis_derived", "key": f"{r['metric']}:{r['key']}:{pop}"}
        out.append(d)
    return out


def _synthesis(con, kind: str) -> list[dict]:
    row = con.execute("SELECT content_json FROM analysis_synthesis WHERE kind=?",
                      (kind,)).fetchone()
    if not row:
        return []
    c = json.loads(row[0])
    out = []
    if kind == "recommendation":
        items = [("top", f"{c['top']['candidate_id']}: {c['top']['problem_statement']['text']}"),
                 *[(f"chain:{x['step']}", x["text"]) for x in c["top"]["chain"]],
                 ("runner_up", f"{c['runner_up']['candidate_id']}: "
                               f"{c['runner_up']['why_not_top']['text']}"),
                 ("target_segment", f"{c['target_segment']['direction']} — "
                                    f"{c['target_segment']['why']['text']}"),
                 ("root_cause", c["root_cause_hypothesis"]["text"]),
                 ("intelligence_needed", c["intelligence_needed"]["text"]),
                 *[(f"falsifier:{k}", x["text"]) for k, x in enumerate(c["falsifiers"], 1)],
                 ("label", c.get("label", ""))]
    else:
        items = [(f"hypothesis:{k}", f"{x['text']} (test: {x['test_how']})")
                 for k, x in enumerate(c["hypotheses"], 1)]
    for k, text in items:
        out.append({"part": k, "text": text, "_cite": {"table": "analysis_synthesis",
                                                        "key": f"{kind}:{k}"}})
    return out


QUERIES: dict[str, Spec] = {
    "funnel": Spec(
        "THE query for totals: how many records were read and kept, how many stories, how "
        "many CORE and ADJACENT stories, and from how many different people.",
        ("composition",),
        lambda con, a: _rows(con, "SELECT step, n, n_authors FROM analysis_funnel WHERE"
                             " source='_all' AND step IN ('collected','kept','stories',"
                             "'stories:core','stories:adjacent') ORDER BY step_order", (),
                             "analysis_funnel", lambda r: r["step"], ("step", "n", "n_authors"))),
    "sources": Spec(
        "Per source: how it was collected, records, people, and records kept. For where "
        "the data came from.", ("composition", "source_breakdown"),
        lambda con, a: _rows(con, "SELECT source, collect_method, n_records, n_authors, n_kept"
                             " FROM analysis_sources ORDER BY n_records DESC", (),
                             "analysis_sources", lambda r: r["source"],
                             ("source", "collect_method", "n_records", "n_authors", "n_kept"))),
    "stage_prevalence": Spec(
        "THE default. For each journey stage 0–10, how many stories FIRST went wrong there "
        "(Stage 9 = nothing went wrong). Args: population core|adjacent. Use for where "
        "retrieval breaks, which stage, how common a stage is.",
        ("prevalence", "ranking", "stage"),
        lambda con, a: _xt(con, f"{_pop(a)}.primary_stage", "photo_class", False, 12)),
    "stage_by_photo_class": Spec(
        "Stages split by kind of photo (sentimental, utility, both, unclear), each share "
        "within that kind. Use for sentimental vs utility, or which photos are hardest.",
        ("segment_split", "stage"),
        lambda con, a: _xt(con, f"{_pop(a)}.primary_stage", "photo_class", True, 40)),
    "stage_by_source": Spec(
        "Stages split by source (Reddit, X, YouTube…). Use for whether a pattern holds "
        "across sources.", ("source_breakdown",),
        lambda con, a: _xt(con, f"{_pop(a)}.primary_stage", "source", True, 40)),
    "field_values": Spec(
        "The spread of one coded field. Args: dim = failure_owner | metric_node | outcome | "
        "media_type | photo_class | source; population.", ("prevalence",),
        lambda con, a: _xt(con, f"{_pop(a)}.{_dim(a)}", "photo_class", False, 12)),
    "question_values": Spec(
        "The answers to ONE codebook question (arg: question, e.g. '5.6', '3.2', '4.1', "
        "'2.4', '9.4'), among stories asked it. Use for what search showed, how they looked, "
        "what they typed, what they forgot, what they did instead.",
        ("prevalence", "detail"),
        lambda con, a: _xt(con, f"{_pop(a)}.q:{_qid(a)}", "photo_class", False, _limit(a))
        if _qid(a) else []),
    "question_by_photo_class": Spec(
        "One question's answers split by kind of photo (arg: question).",
        ("segment_split", "detail"),
        lambda con, a: _xt(con, f"{_pop(a)}.q:{_qid(a)}", "photo_class", True, 40)
        if _qid(a) else []),
    "memory": Spec(
        "The cue matrix: per kind of detail (what, when, who, where, event…), how many "
        "stories remember it, say they forgot it, or were certain and wrong about it.",
        ("memory", "prevalence"),
        lambda con, a: _derived(con, ("cue_remembered", "cue_forgotten", "cue_wrong",
                                      "certain_wrong"), _pop(a))),
    "behaviours": Spec(
        "How often stories show: results jogging memory (results_as_cues), using a near-miss "
        "to reach the photo (anchor_and_pivot), a workaround, each fallback, and new habits "
        "afterwards.", ("workaround", "prevalence"),
        lambda con, a: _derived(con, ("results_as_cues", "anchor_and_pivot", "workaround",
                                      "fallback", "preventive_habit"), _pop(a))),
    "source_divergence": Spec(
        "How far each source's spread of stages sits from the pooled spread. Use for "
        "whether findings are one community's artefact.", ("robustness", "source_breakdown"),
        lambda con, a: _derived(con, ("js_divergence",), _pop(a))),
    "opportunities": Spec(
        "The opportunity candidates: each failure stage with its core stories, people, "
        "gates, scores, status (ranked / too few to rank / gated out) and rank.",
        ("opportunity", "ranking"),
        lambda con, a: [{"candidate": r["candidate_id"], "label": r["label"],
                         "core_stories": r["n_core"], "of": r["denom"], "people": r["n_authors"],
                         "status": r["status"], "why_status": r["status_reason"],
                         "rank": r["rank_headline"], "headline_score": r["score_headline"],
                         "scores": {k: v["score"] for k, v in
                                    json.loads(r["scores_json"]).items()},
                         "gates": {k: v["score"] for k, v in
                                   json.loads(r["gates_json"]).items()},
                         "_cite": {"table": "analysis_opportunity", "key": r["candidate_id"]}}
                        for r in con.execute("SELECT * FROM analysis_opportunity WHERE"
                                             " status <> 'not_a_failure'")]),
    "sensitivity": Spec(
        "How often each candidate comes first across 1000 random weightings.",
        ("robustness",),
        lambda con, a: _rows(con, "SELECT variant, candidate_id, top_share, draws, pool FROM"
                             " analysis_weight_sensitivity WHERE top_share > 0", (),
                             "analysis_weight_sensitivity",
                             lambda r: f"{r['variant']}:{r['pool']}:{r['candidate_id']}",
                             ("variant", "candidate_id", "top_share", "draws", "pool"))),
    "recommendation": Spec(
        "The engine's recommendation (a hypothesis for interviews): top opportunity, "
        "runner-up, target segment, root cause, where intelligence is needed, falsifiers.",
        ("recommendation",), lambda con, a: _synthesis(con, "recommendation")),
    "interview_hypotheses": Spec(
        "The hypotheses handed to the Part 3 interviews.", ("hypothesis",),
        lambda con, a: _synthesis(con, "handoff")),
    "coverage": Spec(
        "How often public stories answer each codebook question, and whether it is coded "
        "or left to interviews (arg: question, or empty for all).", ("coverage",),
        lambda con, a: _rows(con, "SELECT question, n_coded, n_not_stated, disposition FROM"
                             " analysis_coverage WHERE source='_all'"
                             + (" AND question=?" if _qid(a) else ""),
                             (_qid(a),) if _qid(a) else (), "analysis_coverage",
                             lambda r: r["question"],
                             ("question", "n_coded", "n_not_stated", "disposition"))),
    "reliability": Spec(
        "How well two AI coders agreed, per field (kappa, raw agreement, verdict).",
        ("reliability",),
        lambda con, a: _rows(con, "SELECT field, value AS kappa_or_jaccard, raw_agreement, n,"
                             " verdict FROM analysis_reliability ORDER BY verdict, field", (),
                             "analysis_reliability", lambda r: r["field"],
                             ("field", "kappa_or_jaccard", "raw_agreement", "n", "verdict"))),
    "emerging_themes": Spec(
        "Four themes found after the codebook (search refusing sensitive words, lost "
        "Spotlight/Memories creations, no album-scoped search, looking in another photo "
        "app): story counts only.", ("theme",),
        lambda con, a: _rows(con, "SELECT theme, count(*) AS stories FROM story_themes"
                             " GROUP BY theme ORDER BY stories DESC", (), "story_themes",
                             lambda r: r["theme"], ("theme", "stories"))),
}


def describe_registry() -> str:
    return "\n".join(f"- {n}: {s.describe}" for n, s in QUERIES.items())


# ------------------------------------------------------------- channel 2
_TOKEN = re.compile(r"[a-z0-9']+|[ऀ-ॿ]+")
_STOP = set("the a an and or but if of to in on at for with by from is are was were be "
            "it this that what which how why do does did i my me you your they their "
            "photo photos picture pictures google find found search".split())


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(str(text).lower()) if t not in _STOP and len(t) > 1]


def _stories(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT s.story_id, s.bucket AS population, s.text, r.source, r.source_url,"
        " p.primary_stage,"
        " p.photo_class, p.outcome, p.why FROM stories s JOIN records r USING (record_id)"
        f" JOIN story_spine p USING (story_id) WHERE {LIVE}")]


def _answered(con, qid: str) -> set[str]:
    return {r[0] for r in con.execute("SELECT DISTINCT story_id FROM story_codes WHERE"
                                      " question=? AND value<>'not_stated'", (qid,))}


def channel2(con, plan: dict, k: int = 6) -> list[dict]:
    from rank_bm25 import BM25Okapi
    ent = plan.get("entities") or {}
    pops = [p for p in ent.get("populations") or [] if p in POPULATIONS] or ["core"]
    stages = [str(s) for s in ent.get("stages") or []]
    classes = [c for c in ent.get("photo_classes") or []]
    pool = [s for s in _stories(con) if s["population"] in pops
            and (not stages or s["primary_stage"] in stages)
            and (not classes or s["photo_class"] in classes)]
    # The SUBJECT question only (the first named); the rest are context.
    subject = next((m for m in (_qid({"question": q}) for q in ent.get("questions") or [])
                    if m), None)
    if subject:
        got = _answered(con, subject)
        narrowed = [s for s in pool if s["story_id"] in got]
        pool = narrowed if len(narrowed) >= 3 else pool
    if not pool:
        return []
    # What the post itself says ON the subject — the coder's verbatim evidence span
    # for that question (what they typed first: "passport", "chicken coop"…), or for
    # where it first went wrong. Posts that have one come first, and the writer is
    # shown the span (the PM, 2026-09-27: "where are the user quotations or the words
    # that people tried?" — the spans existed; retrieval never passed them on).
    field_ = subject or ("primary_stage" if stages else None)
    spans: dict[str, str] = {}
    if field_:
        for sid, span in con.execute("SELECT story_id, span FROM evidence WHERE field=? AND "
                                     "verified=1", (field_,)):
            spans.setdefault(sid, span)
    about = plain.question(subject) if subject else "where it first went wrong"
    terms = tokenise(" ".join([str(plan.get("restated", "")),
                               " ".join(plan.get("sub_questions") or [])]))
    bm = BM25Okapi([tokenise(s["text"]) or ["_"] for s in pool])
    scores = bm.get_scores(terms or ["_"])
    ranked = sorted(zip(scores, range(len(pool)), strict=True),
                    key=lambda x: (pool[x[1]]["story_id"] not in spans, -x[0]))
    out = []
    for _, i in ranked[:(k + 2 if spans else k)]:
        s = pool[i]
        t, span = s["text"], spans.get(s["story_id"])
        if len(t) > 700:
            at = t.find(span) if span else -1
            lo = max(0, at - 250) if at > 450 else 0
            t = ("… " if lo else "") + t[lo:lo + 700] + " …[cut]"
        row = {**s, "text": t, "_cite": {"table": "story", "key": s["story_id"]}}
        if span:
            row["said"], row["said_on"] = span, about
        out.append(row)
    return out


# ------------------------------------------------------- channels 3 and 4
def channel3(con, plan: dict) -> dict:
    """Evidence AGAINST the emerging answer, always: the other stages' counts,
    and core stories where nothing went wrong."""
    stages = [str(s) for s in (plan.get("entities") or {}).get("stages") or []]
    rivals = [r for r in _xt(con, "core.primary_stage", "photo_class", False, 12)
              if r["_cite"]["key"].split("=")[1].split("@")[0] not in stages]
    fine = [s for s in _stories(con) if s["population"] == "core" and s["primary_stage"] == "9"]
    terms = set(tokenise(plan.get("restated", "")))
    fine.sort(key=lambda s: -len(terms & set(tokenise(s["text"]))))
    return {"rivals": rivals[:5],
            "successes": [{**s, "text": s["text"][:400],
                           "_cite": {"table": "story", "key": s["story_id"]}} for s in fine[:2]]}


def channel4(con, plan: dict) -> dict:
    """ALWAYS: the flags, the corpus totals, and the reliability and coverage rows
    for what the plan names — an answer's caveat and its denominators must never
    depend on the planner remembering to ask for them."""
    ent = plan.get("entities") or {}
    flags = _rows(con, "SELECT flag, text FROM analysis_method_flags", (),
                  "analysis_method_flags", lambda r: r["flag"], ("flag", "text"))
    fields = set(ent.get("fields") or []) | {f"q:{q}" for q in
                                             (_qid({"question": x}) for x in
                                              ent.get("questions") or []) if q}
    fields |= {"primary_stage"}
    qs = [q for q in (_qid({"question": x}) for x in ent.get("questions") or []) if q]
    kind_, _, ref = str(plan.get("subject") or "").partition(":")
    if kind_ == "question" and _qid({"question": ref}) and _qid({"question": ref}) not in qs:
        qs.insert(0, _qid({"question": ref}))
        fields.add(f"q:{_qid({'question': ref})}")
    if kind_ == "field":
        fields.add(ref)
    rel = [r for r in _rows(con, "SELECT field, value AS kappa_or_jaccard, raw_agreement, n,"
                            " verdict FROM analysis_reliability", (), "analysis_reliability",
                            lambda r: r["field"], ("field", "kappa_or_jaccard",
                                                   "raw_agreement", "n", "verdict"))
           if r["field"] in fields]
    cov = [r for q in qs for r in _rows(
        con, "SELECT question, n_coded, n_not_stated, disposition FROM analysis_coverage"
        " WHERE source='_all' AND question=?", (q,), "analysis_coverage",
        lambda r: r["question"], ("question", "n_coded", "n_not_stated", "disposition"))]
    totals = [{**r, "_query": "funnel"} for r in QUERIES["funnel"].run(con, {})]
    return {"flags": flags, "reliability": rel, "coverage": cov, "totals": totals}


@dataclass
class Retrieved:
    facts: list[dict] = field(default_factory=list)          # channel 1
    stories: list[dict] = field(default_factory=list)        # channel 2
    counter: dict = field(default_factory=dict)              # channel 3
    method: dict = field(default_factory=dict)               # channel 4

    def rows(self) -> list[dict]:
        """Every citable analysis row, from any channel: what numbers are checked against."""
        return (list(self.facts) + self.counter.get("rivals", []) + self.method.get("flags", [])
                + self.method.get("reliability", []) + self.method.get("coverage", [])
                + self.method.get("totals", []))

    def records(self) -> list[dict]:
        """Every story retrieved: what a quote must come from."""
        return list(self.stories) + self.counter.get("successes", [])


# The query that answers each evidence kind when the plan asks for the kind but
# runs nothing that returns it (Myntra's fulfil_plan). Without it a plan that
# requests "stage" and forgets stage_prevalence downgrades a well-evidenced answer.
DEFAULT_QUERY = {"prevalence": "stage_prevalence", "ranking": "stage_prevalence",
                 "stage": "stage_prevalence", "segment_split": "stage_by_photo_class",
                 "source_breakdown": "stage_by_source", "memory": "memory",
                 "workaround": "behaviours", "robustness": "source_divergence",
                 "opportunity": "opportunities", "recommendation": "recommendation",
                 "hypothesis": "interview_hypotheses", "coverage": "coverage",
                 "reliability": "reliability", "theme": "emerging_themes",
                 "composition": "funnel"}


def fulfil(plan: dict) -> list[dict]:
    qs = list(plan.get("queries") or [])
    have = {k for q in qs if q.get("query") in QUERIES for k in QUERIES[q["query"]].kinds}
    pop = next((p for p in (plan.get("entities") or {}).get("populations") or []
                if p in POPULATIONS), "core")
    for kind in plan.get("evidence_needed") or []:
        name = DEFAULT_QUERY.get(str(kind))
        if name and kind not in have:
            qs.append({"query": name, "args": {"population": pop, "dim": "", "question": "",
                                               "limit": 0}})
            have |= set(QUERIES[name].kinds)
    return qs


def channel1(con, plan: dict) -> list[dict]:
    out, seen = [], set()
    for q in fulfil(plan):
        spec = QUERIES.get(q.get("query"))
        if not spec:
            continue
        for r in spec.run(con, q.get("args") or {}):
            key = (r["_cite"]["table"], r["_cite"]["key"])
            if key not in seen:
                seen.add(key)
                out.append({**r, "_query": q["query"]})
    return out


def retrieve(con, plan: dict) -> Retrieved:
    return Retrieved(facts=channel1(con, plan), stories=channel2(con, plan),
                     counter=channel3(con, plan), method=channel4(con, plan))


# ------------------------------------------------------------------ gate
REQUIREMENT_KINDS = ("prevalence", "ranking", "stage", "segment_split", "source_breakdown",
                     "detail", "memory", "workaround", "robustness", "opportunity",
                     "recommendation", "hypothesis", "coverage", "reliability", "theme",
                     "composition", "verbatim", "method")
KIND_PHRASE = {"prevalence": "how often this happens in the stories",
               "ranking": "an ordering of these", "stage": "where in the journey this happens",
               "segment_split": "how this differs by kind of photo",
               "source_breakdown": "whether this holds across sources",
               "detail": "what the stories say about this in detail",
               "memory": "what people remember and forget",
               "workaround": "what people do instead", "robustness": "whether this is robust",
               "opportunity": "how this ranks among the problems worth fixing",
               "recommendation": "the engine's recommendation",
               "hypothesis": "ideas to test in interviews",
               "coverage": "how often public posts answer this",
               "reliability": "how reliably the stories were read",
               "theme": "the patterns noticed after the study was designed",
               "composition": "what was collected", "verbatim": "what people actually wrote",
               "method": "how this was measured"}

MISSING_CUTS: list[tuple[str, str]] = [
    (r"\bmen\b|\bwomen\b|\bgender|\bage\b|\bage group|\bolder|\byounger|\bdemographic|"
     r"\bparents?\b.*\bvs\b", "the posts say nothing reliable about people's age or gender, so "
                             "no split by age or gender is possible"),
    (r"\bindia(n)?\b|\busa\b|\bcountr|\bregion|\bcity|\bgeograph",
     "the posts say nothing reliable about where people live, so no country or region "
     "comparison is possible"),
    (r"\bover time\b|\btrend|\bbefore\b.*\bafter\b|\bsince\b.*\bask photos|\bgot worse|"
     r"\bgetting (better|worse)", "the stories were not compared across time, so there is no "
                               "before-and-after"),
    (r"\bandroid\b.*\bios\b|\bios\b.*\bandroid\b|\biphone users\b|\bplatform",
     "the posts do not reliably say which phone people use, so there is no Android vs iPhone "
     "split"),
    (r"\b(apple photos|icloud|samsung gallery|amazon photos|onedrive)\b",
     "the stories do not compare how well other photo apps search"),
]

HARD_OUT_OF_SCOPE = re.compile(
    r"\b(what(?:'s| is| are)?|which|how (?:much|many|big|large|often)|give me|tell me|"
    r"show me|calculate|estimate)\b[^?.]{0,70}?\b("
    r"success rate|failure rate|retrieval rate|abandonment rate|conversion|revenue|profit|"
    r"market share|daily active|monthly active|active users|users (?:does|do|have|has)|"
    r"number of users|(?:people|users) (?:use|using)|share price|valuation)\b", re.I)


# WHAT A QUESTION IS ABOUT, read from its own words. The gate is deterministic
# given a plan, but the planner's subject moved between runs (S2 routed PARTIAL
# on one sweep and FULL on the next), and "a route that moves cannot be
# asserted" (the Myntra engine's MISSING_CUTS, for the same reason). Where the
# question's words settle the subject, they override the plan. First match wins.
SUBJECT_RULES: list[tuple[str, str]] = [
    (r"^(?:how many|what is the number of) (?:core |adjacent )?(?:stories|records)"
     r"(?: are there)?\b(?!.*\b(?:stage|go wrong|fail|search))|how many different people",
     "corpus"),
    (r"\bforg[oe]t", "question:2.4"),
    (r"\bremember(?:s|ed)?\b", "question:2.1"),
    (r"\bhow many attempts|\bbefore (?:they |people )?give up|\bhow long do (?:they|people)",
     "question:8.1"),
    (r"\bhow (?:deep|far)\b.*\bscroll|\bscroll\w* through (?:the )?(?:search )?results",
     "question:6.6"),
    (r"\bwrong (?:year|date|month)\b|\bhard filter", "question:5.3"),
    (r"\b(?:understand|match|misread|misinterpret)\w*\b.*\b(?:search|typ(?:e|ed|es|ing)|"
     r"clues?|quer|words?)|"
     r"\bsearch\b.*\b(?:understand|match)", "stage:5"),
    # After stage:5, which is first-match ("Does the search misread what people type?").
    # What people typed first (the PM, 2026-09-27: "Show which words people tried first"
    # was planned with no subject, so no typed words were retrieved).
    (r"\b(?:words?|terms?|quer(?:y|ies)|phrases?|keywords?)\b.*\b(?:tried|typed|used|type|"
     r"search(?:ed)?)\b|\b(?:typed|type|tried|search(?:ed)? for)\b.*\bfirst\b|"
     r"\bwhat (?:do |did )?(?:people|users|they) (?:type|typed|search)|\bformulate (?:a )?searches",
     "question:4.1"),
    # Hard questions, 2026-09-27 (H9, H11, H13): each was answered with the generic first-
    # failure figures because no rule named the codebook question it is about.
    (r"\bfeel|\bfelt\b|\bemotion|\bfrustrat|\bupset\b|\bangry\b|\bsad\b|\bpanic",
     "question:7.4"),
    (r"\bhow (?:did|do|does) (?:they|people|users|someone) (?:finally |eventually )?find\b|"
     r"\bhow (?:they|people) (?:finally |eventually )?found\b|\bfound (?:the photo|it) in the end",
     "question:9.1"),
    (r"\bgive up\b|\bgave up\b|\bgiving up\b|\babandon", "question:9.4"),
]
CLASS_WORDS = [(r"\bboth\b.*\b(?:sentimental|practical|reasons)\b", "both"),
               # The everyday names too: "Does that differ for photos of receipts and
               # documents?" was answered "we cannot split by kind of photo" (browser
               # check, 2026-09-27) because only the words utility/practical counted.
               (r"\butility\b|\bpractical\b|\breceipts?\b|\bdocuments?\b|\bbills?\b|"
                r"\bprescriptions?\b|\bwhiteboards?\b|\bid cards?\b|\binvoices?\b", "utility"),
               (r"\bsentimental\b", "sentimental")]


# The other cases — the person knew the photo exactly, or it was already gone — enter an
# answer only when the question is about them or about everything collected (the PM,
# 2026-09-27: "include adjacent records in ask ai answers only if they are needed").
ADJACENT_NEEDED = re.compile(
    r"\b(?:adjacent|exact(?:ly)?|knew|known|precise(?:ly)?|deleted|gone|lost|missing|never "
    r"backed|backed up|backup|all (?:the )?(?:cases|stories|posts)|overall|in total|altogether|"
    r"how many (?:stories|cases|posts|records|people)|every case|whole (?:set|collection))\b", re.I)


def normalise_plan(plan: dict, question: str) -> dict:
    """Apply the registered subject and photo-type rules to the plan."""
    q = (question or "").lower()
    p = {**plan, "entities": dict(plan.get("entities") or {})}
    p["adjacent_needed"] = bool(ADJACENT_NEEDED.search(q))
    if not p["adjacent_needed"]:
        p["entities"]["populations"] = ["core"]
        p["queries"] = [{**x, "args": {**(x.get("args") or {}), "population": "core"}}
                        for x in (p.get("queries") or [])]
    subj = next((s for pat, s in SUBJECT_RULES if re.search(pat, q)), None)
    if subj:
        p["subject"] = subj
    named = []
    for pat, c in CLASS_WORDS:
        if re.search(pat, q):
            named.append(c)
            if c == "both":
                break                            # "both sentimental and practical" is one class
    p["named_classes"] = named                # what the QUESTION names, not the planner's context
    if named:
        p["entities"]["photo_classes"] = named
        if "segment_split" not in (p.get("evidence_needed") or []):
            p["evidence_needed"] = list(p.get("evidence_needed") or []) + ["segment_split"]
    return p


def subject_is(plan: dict, kind: str) -> bool:
    return str(plan.get("subject") or "").split(":")[0] == kind


def R_qid(x) -> str | None:
    return _qid({"question": x})


def missing_cuts(q: str) -> list[str]:
    return [why for pat, why in MISSING_CUTS if re.search(pat, q.lower())]


@dataclass
class Verdict:
    route: str
    met: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def gap(self) -> str:
        return "; ".join(self.reasons)


def _rows_for(kind: str, got: Retrieved) -> list[dict]:
    return [r for r in got.facts + got.method.get("totals", [])
            if kind in QUERIES[r["_query"]].kinds]


def _satisfied(kind: str, got: Retrieved, classes: list[str] | None = None) -> tuple[bool, str]:
    if kind == "method":
        return bool(got.method.get("flags")), "the method notes could not be loaded"
    if kind == "verbatim":
        n = len(got.stories)
        return n >= 2, ("no post matches it closely enough to quote" if n == 0 else
                        "too few posts match it to quote from")
    if kind == "detail" and not _rows_for(kind, got):
        return len(got.stories) >= 2, "no stories bear on this in detail"
    if kind == "reliability":
        return bool(got.method.get("reliability") or _rows_for(kind, got)), \
            "there is no check of how reliably that detail was read"
    if kind == "coverage":
        return bool(got.method.get("coverage") or _rows_for(kind, got)), \
            "there is no count of how many posts mention that"
    rows = _rows_for(kind, got)
    if not rows:
        return False, f"the stories hold nothing on {KIND_PHRASE.get(kind, kind)}"
    # [CTX] §15.5, applied as it is to charts: a share needs a group of 30.
    counted = [r for r in rows if isinstance(r.get("of"), int)]
    if kind in ("prevalence", "segment_split", "ranking") and counted:
        if not any(r["of"] >= FLOOR for r in counted):
            big = max(r["of"] for r in counted)
            return True, (f"!only {big} stories fit — too few (under {FLOOR}) for a percentage"
                          " or a comparison, so only counts are given")
        thin = sorted({r["group"] for r in counted if r["of"] < FLOOR and r.get("group")})
        # The group the question is ABOUT decides it: "what share of utility
        # stories…" with 21 utility stories cannot be given a share at all.
        missing = [c for c in classes or [] if not any(r.get("group") == c for r in counted)]
        if kind == "segment_split" and missing:
            return True, ("!none of the stories is about " + " or ".join(
                plain.kind(c) for c in missing) + ", so nothing can be said about them")
        asked = [c for c in classes or [] if any(r.get("group") == c for r in counted)]
        if kind == "segment_split" and asked and all(c in thin for c in asked):
            # The size that IS too few, and the main population's when both are
            # retrieved: the 32 other stories about information photos once
            # overwrote the 21 and the answer said "32 … too few (under 30)" (v2.9, U2).
            sizes = {r["group"]: r["of"] for r in sorted(
                (r for r in counted if r.get("group") in asked and r["of"] < FLOOR),
                key=lambda r: str((r.get("_cite") or {}).get("key", "")).startswith("core."))}
            return True, ("!only " + " and ".join(f"{n} stories are about {plain.kind(c)}"
                                                   for c, n in sizes.items())
                          + f" — too few (under {FLOOR}) for a percentage, so only counts are "
                          "given")
        if thin and kind == "segment_split":
            return True, (f"~fewer than {FLOOR} stories are "
                          + " or ".join(plain.about(g) for g in thin) + ", so those get counts only")
    return True, ""


def gate(plan: dict, got: Retrieved, question: str = "") -> Verdict:
    """FULL / PARTIAL / NONE. No model involvement."""
    intent = str(plan.get("intent", "")).lower()
    disowned = intent == "out_of_scope" or str(plan.get("answerable", "")).lower() == "no"
    if HARD_OUT_OF_SCOPE.search(question or ""):
        return Verdict("NONE", [], list(plan.get("evidence_needed") or []),
                       ["these are public stories, not usage data: no rate of success or "
                        "failure, and no count of users, can be produced from them"])
    if disowned and not got.facts:
        return Verdict("NONE", [], [], ["the question falls outside what these stories cover"])
    if subject_is(plan, "method") or (intent == "methodological" and not got.facts):
        return Verdict("FULL", ["method"], [], [])
    needs = [k for k in dict.fromkeys(str(x).lower() for x in plan.get("evidence_needed") or [])
             if k in REQUIREMENT_KINDS] or ["prevalence"]
    if str(plan.get("subject", "")).startswith("corpus"):
        needs = ["composition"]            # the totals are always retrieved (channel 4)
    met, unmet, reasons, caveats = [], [], [], []
    for kind in needs:
        ok, why = _satisfied(kind, got, plan.get("named_classes"))
        if ok and why.startswith("!"):
            # Below the floor: the counts exist and are given, the share is not —
            # an answer with a named gap, never a refusal and never FULL.
            met.append(kind)
            unmet.append(f"{kind}:floor")
            reasons.append(why[1:])
        elif ok:
            met.append(kind)
            if why.startswith("~"):
                caveats.append(why[1:])
        else:
            unmet.append(kind)
            reasons.append(why)
    # A question the stories rarely answer is an interview question (arch §3.4),
    # and a field the coders disagreed on cannot carry a finding — but only when
    # it is what the question is ABOUT. The planner names its subject once;
    # questions and fields listed as context never downgrade an answer.
    kind_, _, ref = str(plan.get("subject") or "none").partition(":")
    subj_q = R_qid(ref) if kind_ == "question" else None
    subj_f = ({f"q:{subj_q}"} if subj_q else set()) | ({ref} if kind_ == "field" else set())
    for c in got.method.get("coverage", []):
        if c["question"] == subj_q and c["disposition"] == "register":
            asked = c["n_coded"] + c["n_not_stated"]
            unmet.append("register")
            reasons.append(f"few public posts say anything about {plain.question(c['question'])}"
                           f" — {c['n_coded']} of {asked} stories do — so it is left for "
                           "interviews with real users")
    # A field the two coders disagreed on cannot carry a finding (P4-INV-3's rule).
    for r in got.method.get("reliability", []):
        if r["verdict"] == "low_reliability" and r["field"] in subj_f:
            unmet.append("reliability")
            what = plain.FIELD.get(r["field"]) or plain.question(r["field"][2:])
            reasons.append(f"two AI readers went through the stories separately and agreed too "
                           f"rarely on {what} to rely on it")
    absent = missing_cuts(f"{question} {plan.get('restated', '')}")
    if absent:
        unmet.append("missing_cut")
        reasons += absent
    if not met:
        return Verdict("NONE", met, unmet, reasons or ["nothing in the stories bears on this"],
                       caveats)
    if unmet or disowned:
        return Verdict("PARTIAL", met, unmet,
                       reasons or ["parts of this question reach past what the stories cover"],
                       caveats)
    return Verdict("FULL", met, [], [], caveats)
