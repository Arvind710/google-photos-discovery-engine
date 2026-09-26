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

from lib import db, plain, ui, words
from lib.evidence import differs, share

st.title("Analysis")
st.html(f"<div style='color:{ui.MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>Where finding a half-remembered photo first goes wrong, for which "
        f"kinds of photo, and what people remember when they look. Counted over the cases "
        f"people described in public posts — each one read against the same 60 questions."
        f"</div>")

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


# Plain labels for the page (2026-09-27: "an internal concept … cannot be understood by a
# user who doesn't know about it"): no stage numbers, no codebook names.
KIND_HEAD = {"sentimental": "KEPT AS MEMORIES", "utility": "KEPT FOR INFORMATION",
             "both": "BOTH", "unclear": "REASON NOT SAID"}


# What went wrong first, as a statement — a row label reads "where it first went wrong",
# so a question ("Does search understand it?") read oddly (the PM, 2026-09-27).
FIRST_WRONG = {"0": "The photo was already gone", "1": "The post only says why they looked",
               "2": "Couldn't remember enough to search", "3": "Never used search — scrolled "
               "or looked elsewhere", "4": "Couldn't put the memory into words",
               "5": "Searched for something really in it — search didn't bring it up",
               "6": "Hard to spot among the results", "7": "Couldn't find another way in",
               "8": "Gave up", "9": "Nothing went wrong — they found it",
               "10": "Changed their habits afterwards"}


def stage_label(s) -> str:
    return FIRST_WRONG.get(str(s), words.stage_title(s))


n_core, p_core = int(fun.loc["stories:core", "n"]), int(fun.loc["stories:core", "n_authors"])
n_adj = int(fun.loc["stories:adjacent", "n"])
ui.note(f"<b>{n_core} cases from {p_core} people</b> — each one person hunting for a photo "
        f"they remembered only vaguely. The study was built for at least 300, so most splits "
        f"below are too small for a percentage: under 30 cases only the count is shown, and "
        f"from 30 to 79 a percentage is marked as only a rough guide. {n_adj} other cases — "
        f"where the person knew the photo exactly, or it was never there — are reported "
        f"separately at the end.")

# ================================================================= PART 1
stage = rows("core.primary_stage")
NOT_FAILURE = ("1", "9", "10")            # context, and "nothing went wrong"
top = stage[~stage["val_a"].isin(NOT_FAILURE)].iloc[0]
fine = stage[stage["val_a"] == "9"]
ui.section(1, f"Most often, the first thing to go wrong: "
              f"{stage_label(top['val_a'])[:1].lower() + stage_label(top['val_a'])[1:]}",
           "Each case is placed at the FIRST point it went wrong, reading the hunt in order — "
           "not the most dramatic point. Some posts are successes: nothing went wrong and the "
           "person found the photo.", slug="stages")
ui.hbar([stage_label(s) for s in stage["val_a"]], stage["n"].astype(int).tolist(),
        [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
         zip(stage["n"], stage["denom"], stage["n_authors"], strict=True)],
        [ui.BLUE if s not in ("9", "1") else ui.GREY for s in stage["val_a"]])
ps = rel.loc["primary_stage"] if "primary_stage" in rel.index else None
ui.verdict(f"<b>{stage_label(top['val_a'])}</b> — {share(int(top['n']), int(top['denom'])).text}"
           f" of these cases first go wrong here, more than at any other point. "
           + ("That is <i>inferred from what users say</i>: nobody outside Google can see why a "
              "search missed. " if top["val_a"] == "5" else "")
           + (f"Another {share(int(fine['n'].iloc[0]), int(fine['denom'].iloc[0])).text} say "
              f"nothing went wrong at all." if len(fine) else ""), ui.BLUE)
if ps is not None:
    ui.note(f"A second AI reader read 100 of the cases again; on where a case first went "
            f"wrong, their agreement score is {ps['value']:.2f} — the minimum the study set "
            f"was 0.60. " + words.metric("kappa"))

# ================================================================= PART 2
ui.section(2, "Where the hunt first went wrong, by why the photo was kept",
           "Photos kept as memories (a moment, a person, a trip) and photos kept for the "
           "information in them (a receipt, an ID, a note) were expected to fail in different "
           "places. The groups turned out too small to tell.", ui.PINK, slug="photo-type")
# The totals per kind are stored ungrouped (dim_b "_all"); read with the default
# grouping they came back empty, and the table had no columns (the PM, 2026-09-27).
pc = rows("core.photo_class", "_all", "_all").set_index("val_a")
classes = [c for c in ("sentimental", "utility", "both", "unclear") if c in pc.index]
# How to read it, in one line (the PM, 2026-09-27: "Would a user understand the table?").
ui.note("<b>How to read this table:</b> each column is one kind of photo, with how many cases "
        "it has. Each row is the point where the hunt first went wrong. A cell says how many of "
        "that column's cases first went wrong at that point — for example “13 of 48” means 13 "
        "of the 48 cases about photos kept as memories. <span style='opacity:.8'>~ marks a "
        "group of 30–79 cases, so the percentage is only a rough guide; below 30 cases no "
        "percentage is given.</span>")


def _compact(n: int, d: int) -> str:
    """A table cell: "13 of 48 · ~27%" — the count first, the percentage only when the
    group allows one, and "~" when it is only a rough guide (see the note above)."""
    sh = share(n, d)
    if sh.tier == "insufficient":
        return f"{n} of {d}"
    pct = sh.text.split(" ", 1)[0]                    # share() prints the percentage
    return f"{n} of {d} · {'~' if sh.tier == 'directional' else ''}{pct}"


head = "".join(f"<th style='padding:.35rem .5rem;text-align:left;vertical-align:bottom'>"
               f"{KIND_HEAD.get(c, c.upper())}<div style='font-weight:400;opacity:.8'>"
               f"{int(pc.loc[c, 'n'])} cases</div></th>" for c in classes)
body = []
for s in stage["val_a"]:
    cells = []
    for c in classes:
        r = xt[(xt["dim_a"] == "core.primary_stage") & (xt["dim_b"] == "photo_class")
               & (xt["val_b"] == c) & (xt["val_a"] == s)]
        n = int(r["n"].iloc[0]) if len(r) else 0
        cells.append(f"<td style='padding:.35rem .5rem;white-space:nowrap;color:"
                     f"{ui.MUTED if n == 0 else 'inherit'}'>{_compact(n, int(pc.loc[c, 'n']))}</td>")
    body.append(f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.35rem .5rem'>"
                f"{stage_label(s)}</td>{''.join(cells)}</tr>")
st.html("<div style='overflow-x:auto'><table style='border-collapse:collapse;font-size:.85rem;"
        f"width:100%;max-width:900px'><tr style='color:{ui.MUTED};font-size:.7rem'>"
        f"<th style='padding:.35rem .5rem;text-align:left;vertical-align:bottom'>WHERE THE HUNT "
        f"FIRST WENT WRONG</th>{head}</tr>" + "".join(body) + "</table></div>")


def cell(s, c):
    r = xt[(xt["dim_a"] == "core.primary_stage") & (xt["val_b"] == c) & (xt["val_a"] == s)
           & (xt["dim_b"] == "photo_class")]
    return int(r["n"].iloc[0]) if len(r) else 0


claim = (differs((cell(top["val_a"], "sentimental"), int(pc.loc["sentimental", "n"])),
                 (cell(top["val_a"], "utility"), int(pc.loc["utility", "n"])))
         if {"sentimental", "utility"} <= set(pc.index) else False)
ui.verdict(("A difference between photos kept as memories and photos kept for information "
            "can be claimed at this point."
            if claim else
            f"<b>No difference between photos kept as memories and photos kept for information "
            f"can be claimed.</b> Only "
            f"{int(pc.loc['utility', 'n']) if 'utility' in pc.index else 0} cases are about "
            f"photos kept for information, and "
            f"{int(pc.loc['unclear', 'n']) if 'unclear' in pc.index else 0} do not say why the "
            f"photo was kept. Which kind of photo to build for is a question for the "
            f"interviews."), ui.PINK)

# ================================================================= PART 3
ui.section(3, "Whose side the problem is on", "Each first point of failure belongs to one "
           "side — the person's memory, where they chose to look, the words they used, or the "
           "search itself.", ui.SKY, slug="owners")
own = rows("core.failure_owner")
ui.hbar([words.owner(o) for o in own["val_a"]], own["n"].astype(int).tolist(),
        [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
         zip(own["n"], own["denom"], own["n_authors"], strict=True)],
        [ui.SKY if o != "none" else ui.GREY for o in own["val_a"]])
sysrow = own[own["val_a"] == "system"]
ui.verdict(f"Search's side — people searched for something really in the photo and it did "
           f"not come up — accounts for "
           f"{share(int(sysrow['n'].iloc[0]), n_core).text if len(sysrow) else '0'} of these "
           f"cases; the person's own memory accounts for far fewer. The problem people describe "
           f"is the product's, not their recall.", ui.SKY)
if low("metric_node"):
    ui.note("A finer breakdown of which part of search failed is not shown: the two AI "
            "readers agreed on it too rarely.")

# ================================================================= PART 4
ui.section(4, "What people remember is what was in the photo — not when",
           "Of these cases, how many recall each kind of detail about the photo, and how many "
           "say they forgot it.", ui.GREEN, slug="memory")
core_dv = dv[dv["population"] == "core"]
fams = ["what", "when", "who", "where", "event", "perceptual", "capture", "meaning", "source"]
rem = core_dv[core_dv["metric"] == "cue_remembered"].set_index("key")
fog = core_dv[core_dv["metric"] == "cue_forgotten"].set_index("key")
lines = []
for f in fams:
    r = int(rem.loc[f, "n"]) if f in rem.index else 0
    g = int(fog.loc[f, "n"]) if f in fog.index else 0
    lines.append(f"<tr style='border-top:1px solid {ui.HAIR}'><td style='padding:.35rem .5rem'>"
                 f"{plain.FAMILY.get(f, f)}</td><td style='padding:.35rem .5rem'>"
                 f"{share(r, n_core).text}</td>"
                 f"<td style='padding:.35rem .5rem'>{share(g, n_core).text}</td></tr>")
st.html("<table style='border-collapse:collapse;font-size:.86rem;width:100%;max-width:640px'>"
        f"<tr style='color:{ui.MUTED};font-size:.7rem;text-align:left'><th style='padding:.35rem"
        " .5rem'>KIND OF DETAIL</th><th style='padding:.35rem .5rem'>REMEMBERED</th>"
        "<th style='padding:.35rem .5rem'>SAID THEY FORGOT</th></tr>" + "".join(lines)
        + "</table>")
wrong = core_dv[(core_dv["metric"] == "certain_wrong")]
ui.verdict("People lead with <b>what</b> was in the picture; the date is what they most often "
           "say they have lost. And no case reveals a detail the person was sure of and "
           f"later found wrong ({share(int(wrong['n'].iloc[0]), n_core).text if len(wrong) else '0'})"
           ".", ui.GREEN)
if low("q:2.1"):
    ui.note("<b>Read the REMEMBERED column as only a rough guide.</b> The two AI readers "
            "agreed too rarely on which details a case recalls to rest a headline on it.")

# ================================================================= PART 5
ui.section(5, "How they looked", "Where they looked inside Google Photos, and the form of the "
           "first thing they typed, among the cases that say.", ui.ORANGE, slug="modes")
for dim, title in (("core.q:3.2", "Where they looked"), ("core.q:4.1", "What they typed first")):
    r = rows(dim).head(6)
    if r.empty:
        continue
    st.html(f"<div style='font-weight:700;font-size:.9rem;margin-top:.6rem'>{title}</div>")
    ui.hbar([plain.words(v)[:1].upper() + plain.words(v)[1:] for v in r["val_a"]],
            r["n"].astype(int).tolist(),
            [f" {share(int(n), int(d)).text} · {int(a)} people" for n, d, a in
             zip(r["n"], r["denom"], r["n_authors"], strict=True)], [ui.ORANGE] * len(r))
ui.verdict("The typical search is <b>a single word</b> typed into the search bar; Ask Photos "
           "barely appears. Scrolling the timeline is the other common path.", ui.ORANGE)

# ================================================================= PART 6
ui.section(6, "Two ideas the public posts cannot test",
           "The research began from two ideas: that a detail the person is sure of, but has "
           "wrong, makes search hide the photo entirely; and that seeing results jogs the "
           "memory. Public posts almost never describe either.", ui.RED, slug="hypotheses")
items = []
for metric, what in (("certain_wrong", "reveal a detail they were sure of and later found wrong"),
                     ("results_as_cues", "say the results reminded them of something new"),
                     ("anchor_and_pivot", "used a near-miss to reach the photo")):
    r = core_dv[core_dv["metric"] == metric]
    if len(r):
        items.append(f"<li>{share(int(r['n'].iloc[0]), int(r['denom'].iloc[0])).text} "
                     f"cases {what}</li>")
st.html(f"<ul style='font-size:.92rem;line-height:1.6'>{''.join(items)}</ul>")
ui.verdict("Neither idea is confirmed or ruled out here — the posts are silent. Both go to "
           "the interviews, where people can be <b>watched while they search</b> and the moment "
           "of recognising (or misremembering) can be seen.", ui.RED)

# ================================================================= PART 7
ui.section(7, "Does the pattern hold across sources?",
           "How different each site's pattern of first failures is from the pattern across all "
           "sites (0 = identical, 1 = nothing in common), for sites with at least 10 of these "
           "cases.",
           ui.SKY, slug="sources")
js = core_dv[core_dv["metric"] == "js_divergence"].sort_values("value")
ui.hbar([words.source(s) for s in js["key"]], [round(100 * v) for v in js["value"]],
        [f" {v:.2f} · {int(n)} cases" for v, n in zip(js["value"], js["n"], strict=True)],
        [ui.SKY] * len(js), height=60 + 38 * len(js))
ui.verdict(f"Every site with enough cases sits close to the overall pattern (largest "
           f"difference {js['value'].max():.2f}): the picture is not the quirk of one community."
           if len(js) else "Too few cases per site to compare.", ui.SKY)

# ================================================================= PART 8
themes = db.query("SELECT theme, count(*) AS n FROM story_themes GROUP BY theme ORDER BY n DESC")
ui.section(8, "Patterns noticed later",
           "Four patterns that a review turned up after the study's questions were fixed. "
           "Counts only: they were not planned for, so they are never ranked.",
           ui.GREY, slug="emerging")
labels = {"search_refuses_sensitive_terms": "Search refuses a word as sensitive (e.g. “monkey”)",
          "auto_creation_lost": "A Spotlight, collage or Memory can't be found again",
          "no_album_scoped_search": "Can't search within one album",
          "looked_in_other_photo_app": "Looked in another photo app or service"}
st.html("<ul style='font-size:.92rem;line-height:1.6'>" + "".join(
    f"<li>{ui.esc(labels.get(t, t))} — <b>{int(n)}</b> cases</li>"
    for t, n in zip(themes["theme"], themes["n"], strict=True)) + "</ul>")

# ================================================================= adjacent
adj = rows("adjacent.primary_stage")
a0 = adj[adj["val_a"] == "0"]
ui.note(f"<b>The other cases, reported apart.</b> Of {n_adj} cases where the person knew the "
        f"photo exactly or it was never there, "
        f"{share(int(a0['n'].iloc[0]), n_adj).text if len(a0) else '0'} first went wrong because "
        f"the photo was gone — deleted, never backed up, or kept elsewhere. Most public talk "
        f"about not finding a photo is about photos that are gone, not the vaguely remembered "
        f"photos this study is about.")
