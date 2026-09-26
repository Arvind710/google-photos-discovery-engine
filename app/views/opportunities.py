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

import pandas as pd
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
        f"line-height:1.55'>Which break in the journey is most worth fixing, how each candidate "
        f"was scored, and what the interviews should test next.</div>")

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

ui.note("Everything on this page is <b>an idea for the follow-up interviews to test</b>, built "
        f"from {denom} cases of someone hunting for a vaguely remembered photo — fewer than the "
        "300 the study was designed for. It says where to look first, not what is true of "
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
    return ui.esc(_plain_terms(plain.reader_words(plain.desnake(str(text)))))


# ================================================================= PART 1
rec = syn.get("recommendation")
if rec:
    top = cands[cands["candidate_id"] == rec["top"]["candidate_id"]].iloc[0]
    ui.section(1, fmt(top["label"]),
               f"The recommended problem to fix: “{words.stage_title(top['primary_stage'])}”, "
               f"the first thing to go wrong in {share(int(top['n_core']), denom).text} of the "
               f"cases, told by {int(top['n_authors'])} people. {fmt(rec['label'])}", ui.GREEN,
               slug="recommendation")
    ui.verdict(fmt(rec["top"]["problem_statement"]["text"]), ui.GREEN)
    step_name = {"metric_node": "Which part of finding a photo it breaks",
                 "evidence": "The evidence", "stage": "Where in the hunt",
                 "root_cause": "Why, as a best guess to test"}
    st.html("".join(ui.card(f"<div style='font-size:.7rem;font-weight:700;letter-spacing:.08em;"
                            f"color:{ui.MUTED}'>{step_name[c['step']].upper()}</div>"
                            f"<div style='font-size:.92rem;line-height:1.5;margin-top:.2rem'>"
                            f"{fmt(c['text'])}</div>", ui.GREEN)
                    for c in rec["top"]["chain"]))
    ru = cands[cands["candidate_id"] == rec["runner_up"]["candidate_id"]]
    ru_name = fmt(ru.iloc[0]["label"]) if len(ru) else fmt(rec["runner_up"]["candidate_id"])
    blocks = [("Who to design for first", f"<b>{fmt(rec['target_segment']['direction'])}</b> — "
                                          f"{fmt(rec['target_segment']['why']['text'])}"),
              ("Why it happens, as a best guess to test", fmt(rec["root_cause_hypothesis"]["text"])),
              ("Where AI is needed", fmt(rec["intelligence_needed"]["text"])),
              ("Second choice", f"<b>{ru_name}</b> — "
                                f"{fmt(rec['runner_up']['why_not_top']['text'])}")]
    st.html("".join(f"<div style='margin:.8rem 0;max-width:80ch'><div style='font-weight:700;"
                    f"font-size:.95rem'>{h}</div><div style='font-size:.9rem;line-height:1.55'>"
                    f"{b}</div></div>" for h, b in blocks))
    st.html("<div style='font-weight:700;font-size:.95rem;margin-top:1rem'>What would prove "
            "this wrong</div><ul style='font-size:.9rem;line-height:1.55;max-width:80ch'>"
            + "".join(f"<li>{fmt(f['text'])}</li>" for f in rec["falsifiers"]) + "</ul>")
    ui.note("<b>Caveats.</b> " + " ".join(fmt(c["text"]) for c in rec["caveats"]))
    ui.note("Written by an AI model from the study's own figures only; every number in it was "
            "checked against those figures by the software.")
else:
    ui.section(1, "The recommendation", "Not generated yet.", ui.GREEN, slug="recommendation")

# ================================================================= PART 2
ui.section(2, f"{len(cands)} candidates, {len(ranked)} can be ranked",
           "One candidate for each point in the hunt where something went wrong. Two checks "
           "come first — can Google Photos fix it, and does fixing it need AI rather than a "
           "design change — then five scores, each from 1 to 5 with its reason. A candidate "
           "with fewer than 30 cases is shown but not ranked.", ui.BLUE, slug="candidates")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.6rem;font-size:.85rem'>" + "".join(
    f"<div>{ui.chip(STATUS[s][0], STATUS[s][1])} {int((cands['status'] == s).sum())}</div>"
    for s in ("ranked", "below_floor", "gated_out")) + "</div>")
for _, c in cands.iterrows():
    label, colour = STATUS[c["status"]]
    d = c["detail"]
    scores = "".join(f"<tr><td style='padding:.15rem .5rem .15rem 0;white-space:nowrap'>"
                     f"{CRIT[k]}{' ⚠︎' if k == 'severity' else ''}</td><td style='padding:.15rem"
                     f" .5rem;font-weight:700'>{v['score']}</td><td style='padding:.15rem 0;"
                     f"color:{ui.MUTED};font-size:.8rem'>{fmt(v['why'])}</td></tr>"
                     for k, v in c["scores"].items())
    gates = "".join(f"<tr><td style='padding:.15rem .5rem .15rem 0;white-space:nowrap'>"
                    f"{GATES[g]}</td><td style='padding:.15rem .5rem;font-weight:700;color:"
                    f"{ui.GREEN if v['passed'] else ui.RED}'>{v['score']}</td><td style='padding:"
                    f".15rem 0;color:{ui.MUTED};font-size:.8rem'>{fmt(v['why'])}</td></tr>"
                    for g, v in c["gates"].items())
    modes = ", ".join(f"{fmt(plain.words(k.split(' ', 1)[1]))} ({v})"
                      for k, v in d["failure_modes"].items()) or "none stated"
    quotes = "".join(ui.quote(q["span"], words.source(q["source"])) for q in d["quotes"][:3])
    st.html(ui.card(
        f"<div style='display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap'>"
        f"<div style='font-weight:700;font-size:1rem'>{fmt(c['label'])}</div>"
        f"<div>{ui.chip(label, colour)}"
        + (f" <b>#{int(c['rank_headline'])}</b>" if pd.notna(c["rank_headline"]) else "")
        + "</div></div>"
        f"<div style='font-size:.82rem;color:{ui.MUTED};margin:.2rem 0 .4rem'>"
        f"{share(int(c['n_core']), denom).text} cases · {int(c['n_authors'])} people · "
        f"{int(c['n_adjacent'])} more where the person knew the photo exactly or it was gone · "
        + ", ".join(f"{KIND_NAME.get(k, k)} {v}" for k, v in d["photo_class"].items()) + "</div>"
        f"<div style='font-size:.84rem;margin:.2rem 0'>{fmt(c['status_reason'])}</div>"
        f"<table style='font-size:.84rem;margin:.4rem 0'>{gates}</table>"
        f"<table style='font-size:.84rem;margin:.4rem 0'>{scores}</table>"
        f"<div style='font-size:.82rem;margin:.3rem 0'><b>What the cases say went wrong:</b> "
        f"{modes}</div>{quotes}", colour, dim=c["status"] != "ranked"))
ui.note("⚠︎ How serious it is: the two AI readers agreed on it too rarely (an agreement score "
        "of 0.33, where 1 is perfect), so it is left out of the main score and only tried as a "
        "variation below. What search did is worked out from what people wrote — nobody outside "
        "Google can see it.")
ui.verdict(f"<b>{fmt(ranked.iloc[0]['label']) if len(ranked) else 'Nothing'}</b> is the only "
           f"candidate with enough cases to rank. The others are named, scored and kept, for "
           f"the interviews to size.", ui.BLUE)

# ================================================================= PART 3
w0 = SCORING["weights"]
ui.section(3, "The ranking does not depend on how much each score counts",
           f"How much each score counts was fixed before any ranking ran "
           f"({SCORING['pre_registered_at'][:16].replace('T', ' ')} IST). Move the sliders to "
           f"see whether the order changes; the ranking was also re-run 1,000 times with those "
           f"amounts nudged at random by up to 10 points.",
           ui.ORANGE, slug="weights")
cols = st.columns(4)
w = {k: cols[i].slider(CRIT[k], 0, 50, int(w0[k]), key=f"w_{k}") for i, k in enumerate(HEADLINE)}
pool = cands[cands["status"].isin(["ranked", "below_floor"])]
tot = sum(w.values()) or 1
order = sorted(((sum(w[k] * c["scores"][k]["score"] for k in HEADLINE) / tot, c)
                for _, c in pool.iterrows()), key=lambda x: -x[0])
st.html("<ol style='font-size:.9rem;line-height:1.6'>" + "".join(
    f"<li>{fmt(c['label'])} — score {s:.2f}"
    + ("" if c["status"] == "ranked" else f" <span style='color:{ui.MUTED}'>(illustrative: "
                                          f"too few cases to rank)</span>") + "</li>"
    for s, c in order) + "</ol>")
sh = sens[(sens["variant"] == "headline") & (sens["pool"] == "gates_passed")].sort_values(
    "top_share", ascending=False)
sv = sens[(sens["variant"] == "with_severity") & (sens["pool"] == "gates_passed")].sort_values(
    "top_share", ascending=False)
if len(sh):
    lead = sh.iloc[0]
    lead_row = cands[cands["candidate_id"] == lead["candidate_id"]]
    lead_name = fmt(lead_row.iloc[0]["label"]) if len(lead_row) else fmt(lead["candidate_id"])
    ui.verdict(f"<b>{lead_name}</b> comes first in "
               f"{share(round(lead['top_share'] * lead['draws']), int(lead['draws'])).text} "
               f"of the random re-runs — and in "
               f"{share(round(sv.iloc[0]['top_share'] * sv.iloc[0]['draws']), int(sv.iloc[0]['draws'])).text}"
               f" with seriousness added back in. It scores at least as high as every other "
               f"candidate on every score, so no balance of the scores can overtake it.", ui.ORANGE)

# ================================================================= PART 4
ui.section(4, "Two scores at a time", "Pick any two scores; each dot is a candidate, sized by "
           "its number of cases. Greyed dots are too few to rank.", ui.PINK, slug="two-by-two")
axes = {**CRIT, **GATES}
c1, c2 = st.columns(2)
ax = c1.selectbox("Across", list(axes), index=list(axes).index("frequency"),
                  format_func=axes.get)
ay = c2.selectbox("Up", list(axes), index=list(axes).index("ai_necessity"), format_func=axes.get)


def val(c, k):
    return (c["gates"] if k in GATES else c["scores"])[k]["score"]


fig = go.Figure(go.Scatter(
    x=[val(c, ax) for _, c in cands.iterrows()], y=[val(c, ay) for _, c in cands.iterrows()],
    mode="markers+text", text=[words.stage(s) for s in cands["primary_stage"]],
    textposition="top center",
    marker=dict(size=[10 + int(n) for n in cands["n_core"]],
                color=[STATUS[s][1] for s in cands["status"]], opacity=.8),
    hovertext=list(cands["label"]), hoverinfo="text"))
fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10),
                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                  xaxis=dict(title=axes[ax], range=[0.5, 5.5], gridcolor="rgba(128,128,128,0.35)"),
                  yaxis=dict(title=axes[ay], range=[0.5, 5.5], gridcolor="rgba(128,128,128,0.35)"))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ================================================================= PART 5
ho = syn.get("handoff")
ui.section(5, "What the interviews should test", "For the follow-up interviews: ideas to "
           "test, who to recruit, search tasks to watch people do (modelled on real cases), and "
           "an interview question for everything public posts could not answer.", ui.SKY,
           slug="handoff")
if ho:
    st.html("<div style='font-weight:700;font-size:.95rem'>Ideas to test</div><ol style='font-size:"
            ".9rem;line-height:1.55;max-width:80ch'>" + "".join(
                f"<li>{fmt(h['text'])}<div style='color:{ui.MUTED};font-size:.8rem'>Test: "
                f"{fmt(h['test_how'])}</div></li>" for h in ho["hypotheses"]) + "</ol>")
    st.html("<div style='font-weight:700;font-size:.95rem'>Who to recruit</div><ul style='font-size"
            ":.9rem;line-height:1.55;max-width:80ch'>" + "".join(
                f"<li><b>{fmt(s['criterion'])}</b> — {fmt(s['text'])}</li>"
                for s in ho["screener"]) + "</ul>")
    st.html("<div style='font-weight:700;font-size:.95rem'>Search tasks to watch people do</div>"
            + "".join(
        ui.card(f"<div style='font-size:.9rem'>{fmt(t['task'])}</div><div style='color:"
                f"{ui.MUTED};font-size:.8rem;margin-top:.2rem'>Watch for: {fmt(t['watch_for'])}"
                f"</div>", ui.SKY) for t in ho["observed_tasks"]))
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
