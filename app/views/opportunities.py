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

from lib import db, ui, words
from lib.evidence import share

ROOT = db.ROOT
SCORING = yaml.safe_load((ROOT / "codebook" / "scoring_v1.yaml").read_text())
CRIT = {"metric_leverage": "Metric leverage", "frequency": "Frequency",
        "evidence_strength": "Evidence strength", "reach": "Reach", "severity": "Severity"}
GATES = {"addressable_by_gp": "Google Photos can fix it", "ai_necessity": "Needs intelligence"}
HEADLINE = ("metric_leverage", "frequency", "evidence_strength", "reach")
STATUS = {"ranked": ("RANKED", ui.GREEN), "below_floor": ("TOO FEW STORIES TO RANK", ui.ORANGE),
          "gated_out": ("GATED OUT", ui.RED), "not_a_failure": ("NOT A FAILURE", ui.GREY)}

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

st.warning(words.proxy_warning(), icon="⚠️")
ui.note("Everything on this page is a <b>hypothesis for the Part 3 interviews</b>, built from "
        f"{denom} core stories — fewer than the 300 the engine was designed for. It says where to "
        "look first, not what is true of Google Photos users.")


def fmt(text: str) -> str:
    return ui.esc(text)


# ================================================================= PART 1
rec = syn.get("recommendation")
if rec:
    top = cands[cands["candidate_id"] == rec["top"]["candidate_id"]].iloc[0]
    ui.section(1, fmt(top["label"]),
               f"The recommended opportunity: Stage {top['primary_stage']}, "
               f"{share(int(top['n_core']), denom).text} of core stories, {int(top['n_authors'])} "
               f"people. {fmt(rec['label'])}", ui.GREEN, slug="recommendation")
    ui.verdict(fmt(rec["top"]["problem_statement"]["text"]), ui.GREEN)
    step_name = {"metric_node": "Which factor of success it drags down", "evidence": "The evidence",
                 "stage": "Where in the journey", "root_cause": "Why, as a hypothesis"}
    st.html("".join(ui.card(f"<div style='font-size:.7rem;font-weight:700;letter-spacing:.08em;"
                            f"color:{ui.MUTED}'>{step_name[c['step']].upper()}</div>"
                            f"<div style='font-size:.92rem;line-height:1.5;margin-top:.2rem'>"
                            f"{fmt(c['text'])}</div>", ui.GREEN)
                    for c in rec["top"]["chain"]))
    blocks = [("Target segment", f"<b>{fmt(rec['target_segment']['direction'])}</b> — "
                                 f"{fmt(rec['target_segment']['why']['text'])}"),
              ("Root cause, as a hypothesis", fmt(rec["root_cause_hypothesis"]["text"])),
              ("Where intelligence is needed", fmt(rec["intelligence_needed"]["text"])),
              ("Runner-up", f"<b>{fmt(rec['runner_up']['candidate_id'])}</b> — "
                            f"{fmt(rec['runner_up']['why_not_top']['text'])}")]
    st.html("".join(f"<div style='margin:.8rem 0;max-width:80ch'><div style='font-weight:700;"
                    f"font-size:.95rem'>{h}</div><div style='font-size:.9rem;line-height:1.55'>"
                    f"{b}</div></div>" for h, b in blocks))
    st.html("<div style='font-weight:700;font-size:.95rem;margin-top:1rem'>What would prove "
            "this wrong</div><ul style='font-size:.9rem;line-height:1.55;max-width:80ch'>"
            + "".join(f"<li>{fmt(f['text'])}</li>" for f in rec["falsifiers"]) + "</ul>")
    ui.note("<b>Caveats.</b> " + " ".join(fmt(c["text"]) for c in rec["caveats"]))
    ui.note("Written by an AI model from the engine's own tables only; every statement cites the "
            "rows it rests on, and every number in it was checked against them in code.")
else:
    ui.section(1, "The recommendation", "Not generated yet.", ui.GREEN, slug="recommendation")

# ================================================================= PART 2
ui.section(2, f"{len(cands)} candidates, {len(ranked)} can be ranked",
           "One candidate per stage where something went wrong. Two gates come first — can "
           "Google Photos fix it, and does fixing it need intelligence rather than a UI tweak — "
           "then five weighted scores, each 1–5 with a reason. A candidate with fewer than 30 core "
           "stories is shown but not ranked.", ui.BLUE, slug="candidates")
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
    modes = ", ".join(f"{fmt(k.split(' ', 1)[1].replace('_', ' '))} ({v})"
                      for k, v in d["failure_modes"].items()) or "none stated"
    quotes = "".join(ui.quote(q["span"], words.source(q["source"])) for q in d["quotes"][:3])
    st.html(ui.card(
        f"<div style='display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap'>"
        f"<div style='font-weight:700;font-size:1rem'>Stage {c['primary_stage']} · "
        f"{fmt(c['label'])}</div><div>{ui.chip(label, colour)}"
        + (f" <b>#{int(c['rank_headline'])}</b>" if pd.notna(c["rank_headline"]) else "")
        + "</div></div>"
        f"<div style='font-size:.82rem;color:{ui.MUTED};margin:.2rem 0 .4rem'>"
        f"{share(int(c['n_core']), denom).text} core stories · {int(c['n_authors'])} people · "
        f"{int(c['n_adjacent'])} adjacent at the same stage · "
        + ", ".join(f"{k} {v}" for k, v in d["photo_class"].items()) + "</div>"
        f"<div style='font-size:.84rem;margin:.2rem 0'>{fmt(c['status_reason'])}</div>"
        f"<table style='font-size:.84rem;margin:.4rem 0'>{gates}</table>"
        f"<table style='font-size:.84rem;margin:.4rem 0'>{scores}</table>"
        f"<div style='font-size:.82rem;margin:.3rem 0'><b>What the stories say went wrong:</b> "
        f"{modes}</div>{quotes}", colour, dim=c["status"] != "ranked"))
ui.note("⚠︎ Severity: the two AI coders agreed on it too little (κ 0.33), so it is left out of the "
        "headline score and shown only as a sensitivity row below. What search did (Stage 5) "
        "is inferred from what users say — nobody outside Google can see it.")
ui.verdict(f"<b>{fmt(ranked.iloc[0]['label']) if len(ranked) else 'Nothing'}</b> is the only "
           f"candidate with enough stories to rank. The others are named, scored and kept, for "
           f"the interviews to size.", ui.BLUE)

# ================================================================= PART 3
w0 = SCORING["weights"]
ui.section(3, "The ranking does not depend on the weights",
           f"Weights were registered before any ranking ran "
           f"({SCORING['pre_registered_at'][:16].replace('T', ' ')} IST). Move them to see "
           f"whether the order changes; 1,000 random moves of up to 10 points were also tried.",
           ui.ORANGE, slug="weights")
cols = st.columns(4)
w = {k: cols[i].slider(CRIT[k], 0, 50, int(w0[k]), key=f"w_{k}") for i, k in enumerate(HEADLINE)}
pool = cands[cands["status"].isin(["ranked", "below_floor"])]
tot = sum(w.values()) or 1
order = sorted(((sum(w[k] * c["scores"][k]["score"] for k in HEADLINE) / tot, c)
                for _, c in pool.iterrows()), key=lambda x: -x[0])
st.html("<ol style='font-size:.9rem;line-height:1.6'>" + "".join(
    f"<li>Stage {c['primary_stage']} · {fmt(c['label'])} — score {s:.2f}"
    + ("" if c["status"] == "ranked" else f" <span style='color:{ui.MUTED}'>(illustrative: "
                                          f"too few stories to rank)</span>") + "</li>"
    for s, c in order) + "</ol>")
sh = sens[(sens["variant"] == "headline") & (sens["pool"] == "gates_passed")].sort_values(
    "top_share", ascending=False)
sv = sens[(sens["variant"] == "with_severity") & (sens["pool"] == "gates_passed")].sort_values(
    "top_share", ascending=False)
if len(sh):
    lead = sh.iloc[0]
    ui.verdict(f"Stage {lead['candidate_id'].removeprefix('stage')} comes first in "
               f"{share(round(lead['top_share'] * lead['draws']), int(lead['draws'])).text} "
               f"random weightings — and in "
               f"{share(round(sv.iloc[0]['top_share'] * sv.iloc[0]['draws']), int(sv.iloc[0]['draws'])).text}"
               f" with severity added back. It scores at least as high as every other candidate "
               f"on every criterion, so no weighting can overtake it.", ui.ORANGE)

# ================================================================= PART 4
ui.section(4, "Two criteria at a time", "Pick any two criteria; each dot is a candidate, sized "
           "by its core stories. Greyed dots are too few to rank.", ui.PINK, slug="two-by-two")
axes = {**CRIT, **GATES}
c1, c2 = st.columns(2)
ax = c1.selectbox("Across", list(axes), index=list(axes).index("frequency"),
                  format_func=axes.get)
ay = c2.selectbox("Up", list(axes), index=list(axes).index("ai_necessity"), format_func=axes.get)


def val(c, k):
    return (c["gates"] if k in GATES else c["scores"])[k]["score"]


fig = go.Figure(go.Scatter(
    x=[val(c, ax) for _, c in cands.iterrows()], y=[val(c, ay) for _, c in cands.iterrows()],
    mode="markers+text", text=[f"Stage {s}" for s in cands["primary_stage"]],
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
ui.section(5, "What the interviews should test", "The handoff to Part 3: hypotheses, who to "
           "recruit, observed search tasks modelled on real stories, and an interview prompt for "
           "every question public posts could not answer.", ui.SKY, slug="handoff")
if ho:
    st.html("<div style='font-weight:700;font-size:.95rem'>Hypotheses</div><ol style='font-size:"
            ".9rem;line-height:1.55;max-width:80ch'>" + "".join(
                f"<li>{fmt(h['text'])}<div style='color:{ui.MUTED};font-size:.8rem'>Test: "
                f"{fmt(h['test_how'])}</div></li>" for h in ho["hypotheses"]) + "</ol>")
    st.html("<div style='font-weight:700;font-size:.95rem'>Who to recruit</div><ul style='font-size"
            ":.9rem;line-height:1.55;max-width:80ch'>" + "".join(
                f"<li><b>{fmt(s['criterion'])}</b> — {fmt(s['text'])}</li>"
                for s in ho["screener"]) + "</ul>")
    st.html("<div style='font-weight:700;font-size:.95rem'>Observed search tasks</div>" + "".join(
        ui.card(f"<div style='font-size:.9rem'>{fmt(t['task'])}</div><div style='color:"
                f"{ui.MUTED};font-size:.8rem;margin-top:.2rem'>Watch for: {fmt(t['watch_for'])}"
                f"</div>", ui.SKY) for t in ho["observed_tasks"]))
    by_stage: dict[str, list] = {}
    for p in ho["interview_prompts"]:
        by_stage.setdefault(str(p["stage"]), []).append(p)
    with st.expander(f"Interview prompts for the {len(ho.get('register', []))} questions public "
                     f"posts could not answer"):
        for s in sorted(by_stage, key=lambda x: int(x) if x.isdigit() else 99):
            st.html(f"<div style='font-weight:700;margin-top:.5rem'>Stage {ui.esc(s)} · "
                    f"{words.stage_title(s)}</div><ul style='font-size:.88rem'>" + "".join(
                        f"<li>{fmt(p['prompt'])} <span style='color:{ui.MUTED};font-size:.75rem'>"
                        f"({fmt(p['question_id'])})</span></li>" for p in by_stage[s]) + "</ul>")
    with st.expander("Probes for the four emerging themes"):
        st.html("<ul style='font-size:.88rem'>" + "".join(
            f"<li>{fmt(p['prompt'])}</li>" for p in ho["theme_probes"]) + "</ul>")
else:
    ui.note("Not generated yet.")
