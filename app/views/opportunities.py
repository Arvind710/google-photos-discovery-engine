"""Opportunities — candidates, gates, scores, the recommendation and the Part 3
handoff ([CTX] §9, architecture.md §6, implementationplan.md task 4.6).

Read from analysis_opportunity, analysis_weight_sensitivity and
analysis_synthesis only. The recommendation's text comes from a model and is
escaped before it reaches st.html. Gated-out and below-floor candidates are
shown, greyed, with the reason named (P4-INV-5, EC-ANL-2). Weights are
adjustable ([CTX] §9.2); the headline ranking always uses the pre-registered
set, shown with its timestamp.
"""

import json

import plotly.graph_objects as go
import streamlit as st
import yaml

from lib import db, plain, ui, words
from lib.evidence import share

ROOT = db.ROOT
SCORING = yaml.safe_load((ROOT / "codebook" / "scoring_v1.yaml").read_text())
# Plain names (2026-09-27: no internal concept a newcomer cannot read at once).
CRIT = {"metric_leverage": "How much fixing it helps people find the photo",
        "frequency": "How often it happens", "evidence_strength": "How solid the evidence is",
        "reach": "How many different people it affects", "severity": "How serious it is"}
GATES = {"addressable_by_gp": "Google Photos can fix it",
         "ai_necessity": "Fixing it needs AI, not just a design change"}
KIND_NAME = {"sentimental": "kept as memories", "utility": "kept for information",
             "both": "both", "unclear": "reason not said"}
HEADLINE = ("metric_leverage", "frequency", "evidence_strength", "reach")
STATUS = {"ranked": ("RANKED", ui.GREEN), "below_floor": ("TOO FEW CASES TO RANK", ui.ORANGE),
          "gated_out": ("RULED OUT — FAILS A CHECK", ui.RED),
          "not_a_failure": ("NOT A FAILURE", ui.GREY)}

st.title("Opportunities")
st.html(f"<div style='color:{ui.MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>What to fix first, why, and what the interviews should test."
        f"</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

opp = db.query("SELECT * FROM analysis_opportunity ORDER BY rank_headline IS NULL, n_core DESC")
sens = db.query("SELECT * FROM analysis_weight_sensitivity")
syn = db.query("SELECT kind, content_json FROM analysis_synthesis")
if opp.empty:
    st.info("Opportunities have not been scored yet (`python -m pipeline.analyse.opportunity`).")
    st.stop()
syn = {k: json.loads(c) for k, c in zip(syn["kind"], syn["content_json"], strict=True)}
opp = opp.assign(scores=opp["scores_json"].map(json.loads), gates=opp["gates_json"].map(json.loads),
                 detail=opp["detail_json"].map(json.loads))
cands = opp[opp["status"] != "not_a_failure"]
denom = int(opp["denom"].iloc[0])
ranked = cands[cands["status"] == "ranked"]

ui.note(f"Built from {denom} cases — a starting point for interviews, not a fact about all "
        "Google Photos users.")


# The stored recommendation was written in the study's own vocabulary; the reader sees
# plain words (2026-09-27). Display only — the stored text and its checks are unchanged.
_PLAIN_TERMS = [
    (r"\bin the Part 3 (?:interviews|research)\b", "in the follow-up interviews"),
    (r"\bPart 3\b", "the follow-up interviews"),
    (r"\bhypothes[ie]s\b", "idea to test"),
    (r"\bsensitivity (?:tests?|analysis|rows?)\b", "re-runs with the scores weighted differently"),
    (r"\bmain pool\b", "vaguely remembered cases"),
    (r"\bleverage\b", "gain"),
    (r"[“\"]?\bunclear\b[”\"]?(?= (?:everyday )?photos| \(| cases| and| contexts)",
     "reason-not-said"),
    (r"\bsentimental\b", "kept-as-memory"), (r"\bSentimental\b", "Kept-as-memory"),
    (r"\bpractical\b(?= \(| photos| cases| \d)", "kept-for-information"),
    (r"\butility\b", "kept-for-information"),
    (r"\bsearch (?:did not|didn't|fails? to|failed to) understand(?: or match)? (?:what "
     r"(?:they|people|the person) typed|the (?:query|cue|words))",
     "search did not bring up the photo when people searched for something really in it"),
    (r"\(not practical\)", "(not kept-for-information)"),
    (r"\bunclear\b(?= \d)", "reason-not-said"),
    (r"\bcodebook questions?\b", "study questions"), (r"\bcodebook\b", "study's questions"),
    (r"\bkappa\b|κ", "agreement score"),
    (r"\badjacent cases?\b", "cases where the photo was known exactly or already gone"),
    (r"\badjacent\b", "known-exactly-or-gone"),
    (r"\bevidence floor\b", "minimum of 30 cases"),
    (r"\s*\(\[?CTX\]?\s*§[\d.]+\)", ""),
    (r"\benters gp retrieval path\b", "sits on Google Photos' search path"),
    (r"\bgp retrieval\b", "Google Photos search"), (r"\bretrieval\b", "finding the photo"),
    (r"\bpure practical\b", "purely kept-for-information"),
]


def _plain_terms(t: str) -> str:
    import re
    for pat, rep in _PLAIN_TERMS:
        t = re.sub(pat, rep, t)
    return t


def fmt(text: str) -> str:
    # Stored, model-written text says "stories"; the reader sees "cases" (D-15).
    # Also its stage numbers and code names ("Stage 5", "core stories", "metric node").
    return ui.esc(_plain_terms(plain.reader_words(plain.desnake(plain.label_(str(text))))))


def first_sentence(text: str) -> str:
    """The first sentence only: the page shows the point; the rest is one click away."""
    import re
    t = fmt(text)
    m = re.search(r"^(.+?[.!?])(?:\s|$)", t)
    t = m.group(1) if m else t
    return t.split(";")[0].rstrip(".") + "." if ";" in t else t


def label_of(cid: str) -> str:
    r = cands[cands["candidate_id"] == cid]
    return fmt(r.iloc[0]["label"]) if len(r) else fmt(cid)


# The page answers four questions, in order (the PM, 2026-09-27: "too much text … organise
# the info better"): what to fix first; what else was considered; does the ranking hold;
# what the interviews should test. Detail sits in fold-outs under each.

# ================================================================= PART 1
rec = syn.get("recommendation")
if rec:
    top = cands[cands["candidate_id"] == rec["top"]["candidate_id"]].iloc[0]
    ui.section(1, "What to fix first", "", ui.GREEN, slug="recommendation")
    ui.verdict(f"<b>{fmt(top['label'])}.</b> It is the first thing to go wrong in "
               f"{share(int(top['n_core']), denom).text} of the cases, told by "
               f"{int(top['n_authors'])} people — the only problem with enough cases to rank.",
               ui.GREEN)
    facts = [("Design for", fmt(rec["target_segment"]["direction"])),
             ("Likely cause", first_sentence(rec["root_cause_hypothesis"]["text"])),
             ("Where AI helps", first_sentence(rec["intelligence_needed"]["text"])),
             ("Second choice", label_of(rec["runner_up"]["candidate_id"]))]
    st.html("<table style='font-size:.92rem;line-height:1.5;max-width:860px;margin:.4rem 0'>"
            + "".join(f"<tr><td style='padding:.3rem 1rem .3rem 0;color:{ui.MUTED};white-space:"
                      f"nowrap;vertical-align:top'>{h}</td><td style='padding:.3rem 0'>{b}</td></tr>"
                      for h, b in facts) + "</table>")
    with st.expander("Why — the full reasoning, and what would prove it wrong"):
        step_name = {"metric_node": "Which part of finding a photo it breaks",
                     "evidence": "The evidence", "stage": "Where in the hunt",
                     "root_cause": "Why, as a best guess to test"}
        st.html("".join(f"<div style='margin:.5rem 0'><div style='font-size:.7rem;font-weight:700;"
                        f"letter-spacing:.08em;color:{ui.MUTED}'>{step_name[c['step']].upper()}</div>"
                        f"<div style='font-size:.9rem;line-height:1.5'>{fmt(c['text'])}</div></div>"
                        for c in rec["top"]["chain"])
                + f"<div style='margin:.6rem 0'><b>Who to design for.</b> "
                  f"{fmt(rec['target_segment']['why']['text'])}</div>"
                + f"<div style='margin:.6rem 0'><b>Why not the second choice.</b> "
                  f"{fmt(rec['runner_up']['why_not_top']['text'])}</div>"
                + "<div style='margin:.6rem 0 .2rem'><b>What would prove this wrong</b></div><ul>"
                + "".join(f"<li>{fmt(f['text'])}</li>" for f in rec["falsifiers"]) + "</ul>"
                + "<div style='margin:.6rem 0 .2rem'><b>Limits</b></div><ul>"
                + "".join(f"<li>{fmt(c['text'])}</li>" for c in rec["caveats"]) + "</ul>")
        ui.note("Written by an AI model from the study's own figures; every number in it was "
                "checked against those figures by the software.")
else:
    ui.section(1, "What to fix first", "Not generated yet.", ui.GREEN, slug="recommendation")

# ================================================================= PART 2
ui.section(2, "Every problem considered", "One per point where the hunt can go wrong. A "
           "problem needs 30 cases to be ranked.", ui.BLUE, slug="candidates")
SHORT = {"ranked": "Ranked", "below_floor": "Too few cases to rank",
         "gated_out": "Ruled out", "not_a_failure": "Not a failure"}
rows_html = []
for _, c in cands.iterrows():
    colour = STATUS[c["status"]][1]
    if c["status"] == "below_floor":
        why = f" — only {int(c['n_core'])}"
    elif c["status"] == "gated_out":
        failed = [g for g, v in c["gates"].items() if not v["passed"]]
        why = " — " + " and ".join({"addressable_by_gp": "better search can't fix it",
                                     "ai_necessity": "it doesn't need AI"}.get(g, g)
                                    for g in failed)
    else:
        why = ""
    rows_html.append(
        f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.4rem .6rem .4rem 0'>"
        f"{fmt(c['label'])}</td><td style='padding:.4rem .6rem;white-space:nowrap'>"
        f"{share(int(c['n_core']), denom).text}</td><td style='padding:.4rem .6rem'>"
        f"{int(c['n_authors'])}</td><td style='padding:.4rem 0;color:{colour}'>"
        f"<b>{SHORT[c['status']]}</b><span style='color:{ui.MUTED}'>{why}</span></td></tr>")
st.html("<div style='overflow-x:auto'><table style='border-collapse:collapse;font-size:.86rem;"
        f"width:100%;max-width:960px'><tr style='color:{ui.MUTED};font-size:.7rem;text-align:left'>"
        "<th style='padding:.3rem .6rem .3rem 0'>PROBLEM</th><th style='padding:.3rem .6rem'>CASES"
        "</th><th style='padding:.3rem .6rem'>PEOPLE</th><th style='padding:.3rem 0'>STATUS</th>"
        "</tr>" + "".join(rows_html) + "</table></div>")
with st.expander("How each problem was scored"):
    st.caption("Two checks first — can Google Photos fix it, and does it need AI rather than a "
               "design change — then five scores from 1 to 5, each with its reason.")
    for _, c in cands.iterrows():
        label, colour = STATUS[c["status"]]
        d = c["detail"]
        scores = "".join(f"<tr><td style='padding:.15rem .5rem .15rem 0;white-space:nowrap'>"
                         f"{CRIT[k]}{' ⚠︎' if k == 'severity' else ''}</td><td style='padding:"
                         f".15rem .5rem;font-weight:700'>{v['score']}</td><td style='padding:"
                         f".15rem 0;color:{ui.MUTED};font-size:.8rem'>{fmt(v['why'])}</td></tr>"
                         for k, v in c["scores"].items())
        gates = "".join(f"<tr><td style='padding:.15rem .5rem .15rem 0;white-space:nowrap'>"
                        f"{GATES[g]}</td><td style='padding:.15rem .5rem;font-weight:700;color:"
                        f"{ui.GREEN if v['passed'] else ui.RED}'>{v['score']}</td><td style='padding:"
                        f".15rem 0;color:{ui.MUTED};font-size:.8rem'>{fmt(v['why'])}</td></tr>"
                        for g, v in c["gates"].items())
        quotes = "".join(ui.quote(q["span"], words.source(q["source"])) for q in d["quotes"][:2])
        st.html(ui.card(f"<div style='font-weight:700'>{fmt(c['label'])} "
                        f"{ui.chip(label, colour)}</div>"
                        f"<table style='font-size:.84rem;margin:.4rem 0'>{gates}</table>"
                        f"<table style='font-size:.84rem;margin:.4rem 0'>{scores}</table>{quotes}",
                        colour, dim=c["status"] != "ranked"))
    ui.note("⚠︎ How serious it is: the two AI readers agreed on it too rarely (score 0.33, "
            "where 1 is perfect), so it is left out of the main score.")

# ================================================================= PART 3
ui.section(3, "Does the ranking hold?", "", ui.ORANGE, slug="weights")
sh = sens[(sens["variant"] == "headline") & (sens["pool"] == "gates_passed")].sort_values(
    "top_share", ascending=False)
if len(sh):
    lead = sh.iloc[0]
    ui.verdict(f"Yes. <b>{label_of(lead['candidate_id'])}</b> stays first in "
               f"{share(round(lead['top_share'] * lead['draws']), int(lead['draws'])).text} of "
               f"1,000 re-runs with the scores weighted differently — it scores at least as high "
               f"as every other problem on every score.", ui.ORANGE)
with st.expander("Try it yourself — change how much each score counts"):
    w0 = SCORING["weights"]
    st.caption(f"The weights were fixed before any ranking ran "
               f"({SCORING['pre_registered_at'][:10]}).")
    cols = st.columns(2)
    w = {k: cols[i % 2].slider(CRIT[k], 0, 50, int(w0[k]), key=f"w_{k}")
         for i, k in enumerate(HEADLINE)}
    pool = cands[cands["status"].isin(["ranked", "below_floor"])]
    tot = sum(w.values()) or 1
    order = sorted(((sum(w[k] * c["scores"][k]["score"] for k in HEADLINE) / tot, c)
                    for _, c in pool.iterrows()), key=lambda x: -x[0])
    st.html("<ol style='font-size:.9rem;line-height:1.6'>" + "".join(
        f"<li>{fmt(c['label'])} — {sc:.2f}"
        + ("" if c["status"] == "ranked" else f" <span style='color:{ui.MUTED}'>(too few cases "
                                             f"to rank)</span>") + "</li>"
        for sc, c in order) + "</ol>")

# ================================================================= PART 4
ui.section(4, "Two scores at a time", "Pick any two scores; each dot is a problem, sized by its "
           "number of cases. Greyed dots are too few to rank.", ui.PINK, slug="two-by-two")
axes = {**CRIT, **GATES}
c1, c2 = st.columns(2)
ax = c1.selectbox("Across", list(axes), index=list(axes).index("frequency"),
                  format_func=axes.get)
ay = c2.selectbox("Up", list(axes), index=list(axes).index("ai_necessity"),
                  format_func=axes.get)

def val(c, k):
    return (c["gates"] if k in GATES else c["scores"])[k]["score"]

fig = go.Figure(go.Scatter(
    x=[val(c, ax) for _, c in cands.iterrows()], y=[val(c, ay) for _, c in cands.iterrows()],
    mode="markers+text", text=[words.stage(s) for s in cands["primary_stage"]],
    textposition="top center",
    marker=dict(size=[10 + int(n) for n in cands["n_core"]],
                color=[STATUS[s][1] for s in cands["status"]], opacity=.8),
    hovertext=list(cands["label"]), hoverinfo="text"))
fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10),
                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                  xaxis=dict(title=axes[ax], range=[0.5, 5.5],
                             gridcolor="rgba(128,128,128,0.35)"),
                  yaxis=dict(title=axes[ay], range=[0.5, 5.5],
                             gridcolor="rgba(128,128,128,0.35)"))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ================================================================= PART 5
ho = syn.get("handoff")
ui.section(5, "What the interviews should test", "", ui.SKY, slug="handoff")
if ho:
    st.html("<ol style='font-size:.92rem;line-height:1.6;max-width:80ch'>" + "".join(
        f"<li>{fmt(h['text'])}</li>" for h in ho["hypotheses"]) + "</ol>")
    with st.expander("How to test each idea"):
        st.html("<ol style='font-size:.88rem;line-height:1.55'>" + "".join(
            f"<li>{fmt(h['text'])}<div style='color:{ui.MUTED};font-size:.8rem'>Test: "
            f"{fmt(h['test_how'])}</div></li>" for h in ho["hypotheses"]) + "</ol>")
    with st.expander("Who to recruit"):
        st.html("<ul style='font-size:.88rem;line-height:1.55'>" + "".join(
            f"<li><b>{fmt(s['criterion'])}</b> — {fmt(s['text'])}</li>"
            for s in ho["screener"]) + "</ul>")
    with st.expander("Search tasks to watch people do"):
        st.html("".join(ui.card(f"<div style='font-size:.9rem'>{fmt(t['task'])}</div><div "
                                f"style='color:{ui.MUTED};font-size:.8rem;margin-top:.2rem'>"
                                f"Watch for: {fmt(t['watch_for'])}</div>", ui.SKY)
                        for t in ho["observed_tasks"]))
    by_stage: dict[str, list] = {}
    for p in ho["interview_prompts"]:
        by_stage.setdefault(str(p["stage"]), []).append(p)
    with st.expander(f"Interview questions for the {len(ho.get('register', []))} things public "
                     f"posts could not answer"):
        for s in sorted(by_stage, key=lambda x: int(x) if x.isdigit() else 99):
            st.html(f"<div style='font-weight:700;margin-top:.5rem'>"
                    f"{words.stage_title(s)}</div><ul style='font-size:.88rem'>" + "".join(
                        f"<li>{fmt(p['prompt'])}</li>" for p in by_stage[s]) + "</ul>")
    with st.expander("Questions about the four patterns noticed later"):
        st.html("<ul style='font-size:.88rem'>" + "".join(
            f"<li>{fmt(p['prompt'])}</li>" for p in ho["theme_probes"]) + "</ul>")
else:
    ui.note("Not generated yet.")
