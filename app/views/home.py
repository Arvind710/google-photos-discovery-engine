"""How it works — the method on one screen, then the full Methodology
(implementationplan.md task 6.1, [CTX] §11 and §15.7, architecture.md §12).

Written last, "because only then is it true". Every figure is a SELECT from the
published tables (`analysis_*`, and `analysis_methodology` for what otherwise
lives in artifact files — pipeline/analyse/publish.py); every share goes
through `share()`. The no-gold-standard disclosure (P6-BR-12) is stated first
in its part and without a hedge. The gate reports are rendered from
`evals/reports/` so "how do you know?" has an answer at a URL (evals.md §4).
"""

import json
import re

import streamlit as st
import yaml

from lib import db, ui, words
from lib.evidence import share

ROOT = db.ROOT

st.title("Google Photos Discovery Engine")
st.html("<div style='font-size:1.02rem;max-width:72ch;margin:-.4rem 0 1rem;line-height:1.55'>"
        "Why do people fail to find a photo they <i>partly</i> remember? This engine reads public "
        "posts, reviews and forum threads about searching Google Photos, splits them into "
        "individual retrieval stories, and codes each one against an eleven-stage retrieval "
        "journey — to find where retrieval breaks, and where intelligence is actually needed. "
        "This page is how it was done, and how far to trust it.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

fun = db.query("SELECT step, n, n_authors FROM analysis_funnel WHERE source='_all'"
               " ORDER BY step_order").set_index("step")
meth = {k: json.loads(v) for k, v in db.query(
    "SELECT key, value_json FROM analysis_methodology").itertuples(index=False)}
if fun.empty or not meth:
    st.info("The corpus has not been published yet (`python -m pipeline.analyse.publish`).")
    st.stop()


def n(step: str, col: str = "n") -> int:
    return int(fun.loc[step, col])


collected, kept = n("collected"), n("kept")
stories, core, core_people = n("stories"), n("stories:core"), n("stories:core", "n_authors")
cb = meth["codebook"]

# ============================================================ the one-slide diagram
STEPS = [
    ("1 · Collect", f"<b>{collected:,}</b> public records", "9 sources: reviews, forums, "
     "Reddit, X, YouTube…", ui.BLUE),
    ("2 · Clean", "PII scrubbed, repeats by the same person removed", "consensus from different "
     "people kept", ui.SKY),
    ("3 · Find stories", f"<b>{stories}</b> retrieval stories", "one AI model proposes, a "
     "stronger one confirms", ui.GREEN),
    ("4 · Code", f"<b>{core}</b> core stories × 60 questions", f"frozen codebook "
     f"{ui.esc(cb['version'])}; every code backed by a quote", ui.ORANGE),
    ("5 · Check", "quotes found verbatim; a second model re-codes", "agreement, adjudication, "
     "a blind read", ui.PINK),
    ("6 · Rank and ask", "opportunities scored on pre-registered weights", "Ask AI answers only "
     "from the stories, checked in code", ui.RED),
]
arrow = f"<div style='align-self:center;color:{ui.MUTED};font-size:1.3rem'>&rsaquo;</div>"
st.html("<div style='display:flex;flex-wrap:wrap;gap:.25rem;margin:.6rem 0 .3rem'>" + arrow.join(
    f"<div style='flex:1;min-width:140px;border-top:4px solid {c};padding:.5rem .45rem .1rem 0'>"
    f"<div style='font-size:.64rem;letter-spacing:.1em;color:{ui.MUTED};font-weight:700'>{h}"
    f"</div><div style='font-size:.9rem;line-height:1.35;margin:.15rem 0 .25rem'>{a}</div>"
    f"<div style='font-size:.74rem;color:{ui.MUTED};line-height:1.35'>{b}</div></div>"
    for h, a, b, c in STEPS) + "</div>")
st.warning(words.proxy_warning(), icon="⚠️")

# ================================================================= PART 1
ui.section(1, "What the numbers are — and what they are not",
           "Google Photos' goal is the share of users who find a photo they remember but cannot "
           "precisely describe. That rate needs usage logs, which no one outside Google has.",
           ui.BLUE, slug="what")
ui.verdict(f"Every figure here counts <b>stories people chose to post</b> — {core} core "
           f"stories from {core_people} people. It says how often something appears in what "
           "people wrote, which is evidence about <i>why</i> retrieval fails. It is never a "
           "retrieval success rate, a share of users, or a share of searches.", ui.BLUE)

# ================================================================= PART 2
ui.section(2, f"From {collected:,} records to {core} core stories",
           "What was read, what was set aside, and what was left. Nothing is deleted: every "
           "record set aside is still in the database with its reason (the Data Bank shows "
           "them).", ui.GREEN, slug="funnel")
steps = [("records read", collected, n("collected", "n_authors")),
         ("never mention a photo", n("excluded:lexicon_rejected"), None),
         ("too short to say anything", n("excluded:too_short"), None),
         ("about photos, no attempt to find one", n("excluded:no_story"), None),
         ("retrieval stories", stories, n("stories", "n_authors")),
         ("core: a known photo, vaguely remembered", core, core_people),
         ("adjacent: precise memories, or photos that were gone", n("stories:adjacent"),
          n("stories:adjacent", "n_authors"))]
ui.hbar([s for s, _, _ in steps], [v for _, v, _ in steps],
        [f" {v:,}" + (f" · {p:,} people" if p else "") for _, v, p in steps],
        [ui.GREEN if i >= 4 else ui.GREY for i in range(len(steps))])
ui.verdict(f"<b>{core} core stories</b> — fewer than the 300 the engine was designed for. Most "
           "public talk about not finding a photo is about photos that were deleted or never "
           "backed up, not photos remembered vaguely; that is itself a finding. Every comparison "
           "below 30 stories is shown as a count only.", ui.ORANGE)
with st.expander(f"The search lexicon — {len(meth['lexicon'])} terms, with how many records "
                 "each surfaced first"):
    st.html("<table style='font-size:.84rem;border-collapse:collapse'><tr style='color:"
            f"{ui.MUTED};font-size:.7rem;text-align:left'><th style='padding:.2rem .6rem .2rem 0'>"
            "TERM</th><th style='padding:.2rem .6rem'>KIND</th><th style='padding:.2rem .6rem'>"
            "RECORDS</th><th style='padding:.2rem .6rem'>CORE STORIES</th></tr>" + "".join(
                f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.2rem .6rem .2rem 0'>"
                f"{ui.esc(t['term'])}</td><td style='padding:.2rem .6rem;color:{ui.MUTED}'>"
                f"{ui.esc(t['group'].replace('_', ' '))}</td><td style='padding:.2rem .6rem'>"
                f"{t['hits']:,}</td><td style='padding:.2rem .6rem'>{t['core_stories']}</td></tr>"
                for t in sorted(meth["lexicon"], key=lambda t: -t["hits"])) + "</table>")
    ui.note("A record is counted under the term that found it first. Store reviews and the "
            "Google Photos Help listing were read whole, not searched, so their stories trace "
            "to no term.")

# ================================================================= PART 3
journey = yaml.safe_load((ROOT / "codebook" / "journey_v1.yaml").read_text())
cov = db.query("SELECT question, n_coded, n_not_stated, disposition FROM analysis_coverage"
               " WHERE source='_all'").set_index("question")
ui.section(3, "Sixty questions, frozen before the stories were read",
           "The codebook is an eleven-stage journey and 60 questions with fixed answers, written "
           "from the case's solution document. A model may answer only with a listed value or "
           "'not stated', and every key answer needs a quote found word for word in the story.",
           ui.ORANGE, slug="codebook")
rows = []
for stg in journey["stages"]:
    qs = [q["id"] for q in stg["questions"]]
    coded = sum(cov.loc[q, "disposition"] == "coded" for q in qs if q in cov.index)
    rows.append(f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.3rem .6rem .3rem 0'>"
                f"{stg['id']}</td><td style='padding:.3rem .6rem'>{ui.esc(words.stage_title(stg['id']))}"
                f"</td><td style='padding:.3rem .6rem;color:{ui.MUTED}'>"
                f"{ui.esc(words.owner(stg['owner']))}</td><td style='padding:.3rem .6rem'>{len(qs)}"
                f"</td><td style='padding:.3rem .6rem'>{coded} of {len(qs)}</td></tr>")
st.html("<div style='overflow-x:auto'><table style='font-size:.85rem;border-collapse:collapse;"
        f"width:100%;max-width:900px'><tr style='color:{ui.MUTED};font-size:.7rem;text-align:left'>"
        "<th style='padding:.3rem .6rem .3rem 0'>STAGE</th><th style='padding:.3rem .6rem'>WHAT "
        "HAPPENS</th><th style='padding:.3rem .6rem'>A FAILURE HERE IS</th><th style='padding:"
        ".3rem .6rem'>QUESTIONS</th><th style='padding:.3rem .6rem'>ANSWERABLE FROM POSTS</th>"
        "</tr>" + "".join(rows) + "</table></div>")
ui.verdict(f"Frozen as <b>{ui.esc(cb['version'])}</b> on {ui.esc(cb['frozen_at'][:10])}; the "
           "code refuses to run if a single character changes. Stage 5 — what search did — is "
           "always <i>inferred</i> from what the person says: nobody outside Google can see why a "
           "search missed.", ui.ORANGE)
sev = yaml.safe_load((ROOT / "codebook" / "severity_v1.yaml").read_text())
with st.expander("The severity rubric"):
    st.html("<ul style='font-size:.86rem;line-height:1.55'>" + "".join(
        f"<li><b>{ui.esc(k.replace('_', ' '))}</b> — " + " · ".join(
            f"{lv}: {ui.esc(str(txt))}" for lv, txt in c["levels"].items()) + "</li>"
        for k, c in sev["components"].items()) + "</ul>")
    ui.note("Each part scores 0–2 and the total (0–8) maps to 1–5. The two AI coders agreed on "
            "severity too little to trust it (see PART 5), so it is left out of the headline "
            "ranking and shown only as a sensitivity check.")

# ================================================================= PART 4
ui.section(4, f"{int((cov['disposition'] == 'coded').sum())} of 60 questions can be answered "
              "from public stories — the rest go to the interviews",
           "For every question: of the stories asked it, how many said anything at all. Above "
           "85% 'not stated', the question moves to the interview guide for the next part of "
           "the research — named, not dropped.", ui.PINK, slug="register")
reg_rows = []
for stg in journey["stages"]:
    for q in stg["questions"]:
        if q["id"] not in cov.index:
            continue
        c = cov.loc[q["id"]]
        asked = int(c["n_coded"] + c["n_not_stated"])
        sh = share(int(c["n_coded"]), asked).text if asked else "—"
        reg = c["disposition"] == "register"
        reg_rows.append(
            f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.25rem .6rem .25rem 0;"
            f"color:{ui.MUTED}'>{q['id']}</td><td style='padding:.25rem .6rem'>{ui.esc(q['plain'])}"
            f"</td><td style='padding:.25rem .6rem;white-space:nowrap'>{sh}</td><td style='padding:"
            f".25rem .6rem;color:{ui.GREY if reg else ui.PINK}'>{'interview' if reg else 'coded'}"
            "</td></tr>")
with st.expander("All 60 questions, with how often posts answer them", expanded=False):
    st.html("<div style='overflow-x:auto'><table style='font-size:.83rem;border-collapse:"
            f"collapse;width:100%'><tr style='color:{ui.MUTED};font-size:.7rem;text-align:left'>"
            "<th style='padding:.25rem .6rem .25rem 0'>ID</th><th style='padding:.25rem .6rem'>"
            "QUESTION</th><th style='padding:.25rem .6rem'>STORIES THAT ANSWER IT</th><th "
            "style='padding:.25rem .6rem'>ROUTE</th></tr>" + "".join(reg_rows) + "</table></div>")
ui.verdict("Public posts say what people remember, typed and saw; they rarely say how deep they "
           "scrolled, how many attempts they made, or why search dropped a photo. Those are "
           "exactly the questions an observed search task in an interview can answer.", ui.PINK)

# ================================================================= PART 5
rel = db.query("SELECT field, metric, value, raw_agreement, n, verdict FROM analysis_reliability")
spine = rel[~rel["field"].str.startswith("q:")].set_index("field")
counts = rel["verdict"].value_counts().to_dict()
low = sorted(f.replace("q:", "question ").replace("_", " ")
             for f in rel[rel["verdict"] == "low_reliability"]["field"])
br, adj, sp, fx = meth["blind_read"], meth["adjudication"], meth["spans"], meth["coding_fixtures"]
ui.section(5, "How far the coding can be trusted", "", ui.RED, slug="reliability")
ui.verdict("<b>There is no human-checked gold standard.</b> No person reviewed a sample of the "
           "coding. Every reliability figure below is agreement between two AI models, plus a "
           "mechanical check that every quote exists in the post. Agreement measures "
           "consistency, not correctness: <b>two models can agree and both be wrong.</b>", ui.RED)
checks = [
    ("Every quote is real", f"{sp['n']:,} evidence quotes, each found word for word in the post it "
     f"came from and at least {sp['min_len']} characters long. A code whose quote could not be "
     "found was dropped and counted."),
    ("A second model coded 100 stories again",
     f"On where a story first went wrong they agree "
     f"{share(round(spine.loc['primary_stage', 'raw_agreement'] * spine.loc['primary_stage', 'n']), int(spine.loc['primary_stage', 'n'])).text}"
     f" (κ {spine.loc['primary_stage', 'value']:.2f}). Of {len(rel)} coded fields, "
     f"{counts.get('ok', 0)} agree well, {counts.get('degenerate', 0)} are nearly constant, and "
     f"{counts.get('low_reliability', 0)} agree too little to carry a finding: "
     f"{ui.esc(', '.join(low))}. Those never feed a headline or a score."),
    ("A third call settled the disagreements",
     f"On {adj['disputed']} stories where the coders differed, a stronger model sided with the "
     f"first coder {adj['primary']} times, the second {adj['secondary']}, and neither "
     f"{adj['neither']} — a working reference, not proof."),
    ("A blind reader, with no codebook",
     f"Read {br['n']} confidently coded stories and named where each went wrong in its own "
     f"words: it matched the coded stage in "
     f"{share(round(br['stage_agreement'] * br['n']), br['n']).text}. The misses are listed for "
     "inspection — the only view of the coding the codebook did not shape."),
    ("Hand-written test stories",
     f"{fx['n']} stories written with a known right answer: the stage was right in "
     f"{share(round(fx['primary_stage'] * fx['n']), fx['n']).text}. They prove the rules are "
     "applied as written — not accuracy on messy real posts."),
]
st.html("".join(ui.card(f"<div style='font-weight:700;font-size:.92rem'>{h}</div><div style="
                        f"'font-size:.86rem;line-height:1.5;margin-top:.2rem'>{b}</div>", ui.RED)
                for h, b in checks))
ui.note(words.metric("kappa"))

# ================================================================= PART 6
ui.section(6, "Judge the coding yourself — ten stories, chosen at random",
           "Each story as it was posted (names and handles replaced), the codes the engine gave "
           "it, and the quote behind each code.", ui.SKY, slug="sanity")
ids = meth["sanity_strip"]
ph = ",".join("?" * len(ids))
ss = db.query("SELECT s.story_id, s.text, r.source, p.primary_stage, p.photo_class, p.outcome,"
              " p.why FROM stories s JOIN records r USING (record_id) JOIN story_spine p USING"
              f" (story_id) WHERE s.story_id IN ({ph})", tuple(ids)).set_index("story_id")
ev = db.query(f"SELECT story_id, field, span FROM evidence WHERE story_id IN ({ph})", tuple(ids))
for sid in ids:
    if sid not in ss.index:
        continue
    s = ss.loc[sid]
    quotes = ev[ev["story_id"] == sid]
    shown = quotes[~quotes["field"].eq("failure_owner")].head(4)
    st.html(ui.card(
        f"<div style='font-size:.86rem;line-height:1.5'>“{ui.esc(s['text'][:600])}"
        f"{'…' if len(s['text']) > 600 else ''}”</div>"
        f"<div style='font-size:.76rem;color:{ui.MUTED};margin:.25rem 0'>"
        f"{ui.esc(words.source(s['source']))}</div>"
        f"<div style='font-size:.86rem'><b>Stage {s['primary_stage']} — "
        f"{ui.esc(words.stage_title(s['primary_stage']))}</b> · {ui.esc(s['photo_class'])} · "
        f"outcome {ui.esc(str(s['outcome']).replace('_', ' '))}</div>"
        f"<div style='font-size:.8rem;color:{ui.MUTED}'>Why: {ui.esc(s['why'])}</div>"
        + "".join(ui.quote(q, f"for {f.replace('_', ' ')}")
                  for f, q in zip(shown["field"], shown["span"], strict=True)), ui.SKY))
ui.verdict("If these codes look wrong to you, that is the check working: the engine's reliability "
           "rests on inter-model agreement, and this strip is where a person can overrule it.",
           ui.SKY)

# ================================================================= PART 7
sc = yaml.safe_load((ROOT / "codebook" / "scoring_v1.yaml").read_text())
ui.section(7, "How opportunities are ranked", "Two gates, then weighted scores — the weights "
           "written down before any ranking was run.", ui.ORANGE, slug="scoring")
w = sc["weights"]
ui.verdict("A candidate must pass two gates — Google Photos can fix it, and fixing it needs "
           "intelligence rather than a UI tweak — each scored at least 3 of 5. Then: metric "
           f"leverage {w['metric_leverage']}, frequency {w['frequency']}, evidence strength "
           f"{w['evidence_strength']}, reach {w['reach']}, registered "
           f"{ui.esc(sc['pre_registered_at'][:16].replace('T', ' '))} IST. Severity (weight "
           f"{w['severity']}) is left out of the headline because the coders did not agree on it, "
           "and shown as a sensitivity row. A candidate with fewer than 30 core stories is scored "
           "but not ranked; 1,000 random reweightings test whether the order holds.", ui.ORANGE)
ui.note("The gates and reach are judgements: proposed by the AI, approved by the product manager "
        "before the ranking ran, with a one-line reason each (Opportunities page).")

# ================================================================= PART 8
flags = db.query("SELECT flag, text FROM analysis_method_flags").set_index("flag")["text"]
ui.section(8, "What this engine cannot tell you", "Stated here so they are not discovered "
           "later.", ui.GREY, slug="limits")
standing = ["public_selection_bias", "thin_core", "stage5_inferred", "missing_cuts",
            "interview_register", "low_reliability_fields", "adjacent_apart", "emerging_themes"]
st.html("<ul style='font-size:.9rem;line-height:1.6;max-width:80ch'>" + "".join(
    f"<li>{ui.esc(flags[f])}</li>" for f in standing if f in flags.index) + "</ul>")
LIM_PLAIN = {"P2-MET-1": "Two AI models agreed on how many stories a post holds in 35 of 100 "
                         "cases; the stronger model now confirms every story",
             "P2-MET-2": "They agreed on how far a story goes in 55 of 100; the higher of the two "
                         "is always kept, so no coding is skipped",
             "P2-MET-4": "97 of every 100 records read held no retrieval story at all",
             "T-20": "115 core stories, not the 300 planned — paid collection ran out",
             "P3-MET-9-B": "Posts answer the memory questions less often than hoped",
             "P3-MET-9-C": "Posts rarely describe what search did or how results looked",
             "P3-MET-9-D": "Posts rarely describe what people did after a miss"}
with st.expander(f"The {len(meth['limitations'])} measured targets the engine missed, and how "
                 "each is handled"):
    st.html("<ul style='font-size:.86rem;line-height:1.55'>" + "".join(
        f"<li><b>{ui.esc(LIM_PLAIN.get(x['id'], x['id']))}.</b> {ui.esc(x['mitigation'])}</li>"
        for x in meth["limitations"]) + "</ul>")
ui.note("Collection method, disclosed: Reddit, X and Quora were collected through a third-party "
        "scraper although their robots.txt disallows automated access (Data Bank, PART 2). "
        f"AI spend: ${meth['spend']['openai_recorded_usd']:.2f} recorded of a "
        f"${meth['spend']['openai_budget_usd']:.0f} budget at publication.")

# ================================================================= PART 9
ui.section(9, "The gates each phase passed", "Every phase was built against a written test "
           "suite and signed off only when all of it passed. The reports, as committed.",
           ui.GREEN, slug="gates")
for path in sorted((ROOT / "evals" / "reports").glob("gate_P*.md")):
    txt = path.read_text()
    title = re.search(r"^# Gate report — (.+)$", txt, re.M)
    checks = re.search(r"\*\*Checks:\*\* (.+)$", txt, re.M)
    verdict = re.search(r"\*\*Verdict:\*\* (.+)$", txt, re.M)
    with st.expander(f"{title.group(1) if title else path.stem} — "
                     f"{checks.group(1) if checks else ''}"):
        st.markdown(txt.split("## Spend by pass")[0] + (
            txt[txt.index("## What this gate rests on"):] if "## What this gate rests on" in txt
            else ""))
        if verdict:
            st.caption(verdict.group(1).replace("*", ""))
