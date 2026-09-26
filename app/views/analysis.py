"""Analysis — where retrieval first breaks, for which photos, and what people
remember ([CTX] §8.4 views 2–10, 13; implementationplan.md task 4.6).

Every number is a SELECT from analysis_crosstab / analysis_derived (built by
pipeline.analyse.crosstabs and .derived); every share goes through
lib.evidence.share() (P4-INV-1); labels come from lib.words. Core stories are
the population; adjacent stories are reported apart and never pooled with
them. Headline claims use at most two dimensions (P4-INV-8): a stage, split by
photo type. Fields the two coders agreed on too little to trust are named as
such wherever they appear.
"""

import streamlit as st

from lib import db, ui, words
from lib.evidence import differs, share

st.title("Analysis")
st.html(f"<div style='color:{ui.MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>Where finding a half-remembered photo first goes wrong, for which "
        f"kinds of photo, and what people remember when they look. Counted over the retrieval "
        f"stories people told in public — each one coded against the same 60 questions.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

xt = db.query("SELECT * FROM analysis_crosstab")
dv = db.query("SELECT * FROM analysis_derived")
rel = db.query("SELECT field, value, verdict FROM analysis_reliability").set_index("field")
fun = db.query("SELECT step, n, n_authors FROM analysis_funnel WHERE source='_all'"
               ).set_index("step")
if xt.empty or fun.empty:
    st.info("The analysis tables have not been built yet (`python -m pipeline.analyse.crosstabs`).")
    st.stop()


def rows(dim_a: str, dim_b: str = "photo_class", val_b: str = "_all"):
    return xt[(xt["dim_a"] == dim_a) & (xt["dim_b"] == dim_b) & (xt["val_b"] == val_b)
              ].sort_values("n", ascending=False)


def low(field: str) -> bool:
    return field in rel.index and rel.loc[field, "verdict"] == "low_reliability"


n_core, p_core = int(fun.loc["stories:core", "n"]), int(fun.loc["stories:core", "n_authors"])
n_adj = int(fun.loc["stories:adjacent", "n"])
st.warning(words.proxy_warning(), icon="⚠️")
ui.note(f"<b>{n_core} core stories from {p_core} people</b> — a known photo, remembered only "
        f"vaguely. The engine was built for at least 300, so most splits below are too small for "
        f"a percentage: under 30 stories only the count is shown, and from 30 to 79 a share is "
        f"marked directional. {n_adj} adjacent stories (precise memories, or photos that were "
        f"never there) are reported separately at the end.")

# ================================================================= PART 1
stage = rows("core.primary_stage")
top = stage.iloc[0]
ui.section(1, f"Stage {top['val_a']} is where most core stories first go wrong",
           "Each story is placed at the FIRST point it went wrong, reading the journey in order — "
           "not the most dramatic point. Stage 9 means nothing went wrong: people post successes "
           "too.", slug="stages")
ui.hbar([f"{s} · {words.stage_title(s)}" for s in stage["val_a"]], stage["n"].astype(int).tolist(),
        [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
         zip(stage["n"], stage["denom"], stage["n_authors"], strict=True)],
        [ui.BLUE if s not in ("9", "1") else ui.GREY for s in stage["val_a"]])
ps = rel.loc["primary_stage"] if "primary_stage" in rel.index else None
ui.verdict(f"<b>{words.stage_title(top['val_a'])}</b> — {share(int(top['n']), int(top['denom'])).text}"
           f" of core stories first break where search should understand what they typed. "
           f"This is <i>inferred from what users say</i>: nobody outside Google can see why a "
           f"search missed.", ui.BLUE)
if ps is not None:
    ui.note(f"A second AI model re-coded 100 stories; on this field the two agree with κ "
            f"{ps['value']:.2f} (just above the 0.60 bar). " + words.metric("kappa"))

# ================================================================= PART 2
ui.section(2, "The split by kind of photo is too small to call",
           "Sentimental photos (a moment, a person, a trip) and utility photos (a receipt, an ID, "
           "a note) were expected to fail differently. Each column is the share of that kind's "
           "stories.", ui.PINK, slug="photo-type")
pc = rows("core.photo_class").set_index("val_a")
classes = [c for c in ("sentimental", "utility", "both", "unclear") if c in pc.index]
head = "".join(f"<th style='padding:.35rem .5rem;text-align:left'>{c.upper()} · "
               f"{int(pc.loc[c, 'n'])} stories</th>" for c in classes)
body = []
for s in stage["val_a"]:
    cells = []
    for c in classes:
        r = xt[(xt["dim_a"] == "core.primary_stage") & (xt["dim_b"] == "photo_class")
               & (xt["val_b"] == c) & (xt["val_a"] == s)]
        n = int(r["n"].iloc[0]) if len(r) else 0
        sh = share(n, int(pc.loc[c, "n"]))
        cells.append(f"<td style='padding:.35rem .5rem;color:"
                     f"{sh.colour if sh.tier == 'insufficient' else 'inherit'}'>{sh.text}</td>")
    body.append(f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.35rem .5rem'>"
                f"{s} · {words.stage_title(s)}</td>{''.join(cells)}</tr>")
st.html("<div style='overflow-x:auto'><table style='border-collapse:collapse;font-size:.85rem;"
        f"width:100%;max-width:900px'><tr style='color:{ui.MUTED};font-size:.7rem'>"
        f"<th style='padding:.35rem .5rem;text-align:left'>FIRST WENT WRONG</th>{head}</tr>"
        + "".join(body) + "</table></div>")


def cell(s, c):
    r = xt[(xt["dim_a"] == "core.primary_stage") & (xt["val_b"] == c) & (xt["val_a"] == s)
           & (xt["dim_b"] == "photo_class")]
    return int(r["n"].iloc[0]) if len(r) else 0


claim = (differs((cell(top["val_a"], "sentimental"), int(pc.loc["sentimental", "n"])),
                 (cell(top["val_a"], "utility"), int(pc.loc["utility", "n"])))
         if {"sentimental", "utility"} <= set(pc.index) else False)
ui.verdict(("A difference between sentimental and utility photos can be claimed at this stage."
            if claim else
            f"<b>No difference between sentimental and utility photos can be claimed.</b> Only "
            f"{int(pc.loc['utility', 'n']) if 'utility' in pc.index else 0} core stories are about "
            f"utility photos, and {int(pc.loc['unclear', 'n']) if 'unclear' in pc.index else 0} do "
            f"not say why the photo was kept. Which segment to build for is a question for the "
            f"interviews."), ui.PINK)

# ================================================================= PART 3
ui.section(3, "Who owns the failure", "Each stage has an owner — the user's memory, their "
           "choice of where to look, the words they used, or the system — taken directly from "
           "the stage.", ui.SKY, slug="owners")
own = rows("core.failure_owner")
ui.hbar([words.owner(o) for o in own["val_a"]], own["n"].astype(int).tolist(),
        [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
         zip(own["n"], own["denom"], own["n_authors"], strict=True)],
        [ui.SKY if o != "none" else ui.GREY for o in own["val_a"]])
sysrow = own[own["val_a"] == "system"]
ui.verdict(f"The system — search's understanding of the query — owns "
           f"{share(int(sysrow['n'].iloc[0]), n_core).text if len(sysrow) else '0'} of core "
           f"stories; the user's own memory owns far fewer. The problem people describe is the "
           f"product's, not their recall.", ui.SKY)
if low("metric_node"):
    ui.note("Which factor of the success formula each story drags down (the metric node) is not "
            "shown as a headline: the two coders agreed on it too little.")

# ================================================================= PART 4
ui.section(4, "What people remember is what was in the photo — not when",
           "The cue matrix: of the core stories, how many recall each kind of detail, and how "
           "many say they forgot it.", ui.GREEN, slug="memory")
core_dv = dv[dv["population"] == "core"]
fams = ["what", "when", "who", "where", "event", "perceptual", "capture", "meaning", "source"]
rem = core_dv[core_dv["metric"] == "cue_remembered"].set_index("key")
fog = core_dv[core_dv["metric"] == "cue_forgotten"].set_index("key")
lines = []
for f in fams:
    r = int(rem.loc[f, "n"]) if f in rem.index else 0
    g = int(fog.loc[f, "n"]) if f in fog.index else 0
    lines.append(f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.35rem .5rem'>"
                 f"{f}</td><td style='padding:.35rem .5rem'>{share(r, n_core).text}</td>"
                 f"<td style='padding:.35rem .5rem'>{share(g, n_core).text}</td></tr>")
st.html("<table style='border-collapse:collapse;font-size:.86rem;width:100%;max-width:640px'>"
        f"<tr style='color:{ui.MUTED};font-size:.7rem;text-align:left'><th style='padding:.35rem"
        " .5rem'>KIND OF DETAIL</th><th style='padding:.35rem .5rem'>REMEMBERED</th>"
        "<th style='padding:.35rem .5rem'>SAID THEY FORGOT</th></tr>" + "".join(lines)
        + "</table>")
wrong = core_dv[(core_dv["metric"] == "certain_wrong")]
ui.verdict("People lead with <b>what</b> was in the picture; the date is what they most often "
           "say they have lost. And no core story reveals a detail the teller was sure of and "
           f"later found wrong ({share(int(wrong['n'].iloc[0]), n_core).text if len(wrong) else '0'})"
           ".", ui.GREEN)
if low("q:2.1"):
    ui.note("<b>Read the REMEMBERED column as directional only.</b> The two AI coders agreed on "
            "which details a story recalls too little to rest a headline on it.")

# ================================================================= PART 5
ui.section(5, "How they looked", "The mode they used inside Google Photos, and the shape of the "
           "first thing they typed, among the core stories that say.", ui.ORANGE, slug="modes")
for dim, title in (("core.q:3.2", "Where they looked"), ("core.q:4.1", "What they typed first")):
    r = rows(dim).head(6)
    if r.empty:
        continue
    st.html(f"<div style='font-weight:700;font-size:.9rem;margin-top:.6rem'>{title}</div>")
    ui.hbar([str(v).replace("_", " ") for v in r["val_a"]], r["n"].astype(int).tolist(),
            [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
             zip(r["n"], r["denom"], r["n_authors"], strict=True)], [ui.ORANGE] * len(r))
ui.verdict("The typical search is <b>a single word</b> typed into the search bar; Ask Photos "
           "barely appears. Scrolling the timeline is the other common path.", ui.ORANGE)

# ================================================================= PART 6
ui.section(6, "Two ideas the public posts cannot test",
           "The research began from two hypotheses: that a detail the user is sure of but has "
           "wrong gets applied as a hard filter, and that seeing results jogs the memory. Public "
           "posts almost never describe either.", ui.RED, slug="hypotheses")
items = []
for metric, what in (("certain_wrong", "reveal a detail they were sure of and later found wrong"),
                     ("results_as_cues", "say the results reminded them of something new"),
                     ("anchor_and_pivot", "used a near-miss to reach the photo")):
    r = core_dv[core_dv["metric"] == metric]
    if len(r):
        items.append(f"<li>{share(int(r['n'].iloc[0]), int(r['denom'].iloc[0])).text} core "
                     f"stories {what}</li>")
st.html(f"<ul style='font-size:.92rem;line-height:1.6'>{''.join(items)}</ul>")
ui.verdict("Neither hypothesis is confirmed or refuted here — the posts are silent. Both go to "
           "the interviews as <b>observed search tasks</b>, where the moment of recognising "
           "(or misremembering) can be watched.", ui.RED)

# ================================================================= PART 7
ui.section(7, "Does the pattern hold across sources?",
           "How far each source's spread of first-failure stages sits from the pooled spread "
           "(0 = identical, 1 = nothing in common), for sources with at least 10 core stories.",
           ui.SKY, slug="sources")
js = core_dv[core_dv["metric"] == "js_divergence"].sort_values("value")
ui.hbar([words.source(s) for s in js["key"]], [round(100 * v) for v in js["value"]],
        [f" {v:.2f} · {int(n)} stories" for v, n in zip(js["value"], js["n"], strict=True)],
        [ui.SKY] * len(js), height=60 + 38 * len(js))
ui.verdict(f"Every source with enough stories sits close to the pooled pattern (largest "
           f"{js['value'].max():.2f}): the picture is not one community's artefact."
           if len(js) else "Too few stories per source to compare.", ui.SKY)

# ================================================================= PART 8
themes = db.query("SELECT theme, count(*) AS n FROM story_themes GROUP BY theme ORDER BY n DESC")
ui.section(8, "Emerging — found after the codebook",
           "Four themes a review of what the codebook could not hold turned up, approved after "
           "the coding began. Counts only: they were not planned for, so they are never ranked.",
           ui.GREY, slug="emerging")
labels = {"search_refuses_sensitive_terms": "Search refuses a word as sensitive (e.g. “monkey”)",
          "auto_creation_lost": "A Spotlight, collage or Memory can't be found again",
          "no_album_scoped_search": "Can't search within one album",
          "looked_in_other_photo_app": "Looked in another photo app or service"}
st.html("<ul style='font-size:.92rem;line-height:1.6'>" + "".join(
    f"<li>{ui.esc(labels.get(t, t))} — <b>{int(n)}</b> stories</li>"
    for t, n in zip(themes["theme"], themes["n"], strict=True)) + "</ul>")

# ================================================================= adjacent
adj = rows("adjacent.primary_stage")
a0 = adj[adj["val_a"] == "0"]
ui.note(f"<b>Adjacent stories, reported apart.</b> Of {n_adj}, "
        f"{share(int(a0['n'].iloc[0]), n_adj).text if len(a0) else '0'} first fail at Stage 0: "
        f"the photo was deleted, never backed up, or elsewhere. Most public talk about not "
        f"finding a photo is about photos that are gone — not the vaguely-remembered photos this "
        f"engine is about.")
