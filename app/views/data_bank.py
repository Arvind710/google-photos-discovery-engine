"""Data Bank — what was read, how each source was obtained, what was set
aside, and where the collection is thinnest. Then every record, readable.

Shape and vocabulary from the Myntra engine's design language ([CTX] §16):
numbered PARTs, one conclusion and one visual each, a one-sentence verdict,
no tabs. Every number is read from `analysis_funnel` / `analysis_sources`
(built by `pipeline.analyse.funnel`), never aggregated here; every share goes
through `lib.evidence.share()` (P4-INV-1); labels come from `lib.words`.

Part 2 is the D-1 disclosure: three sources came through a third-party
scraper against their robots.txt, and the page says so rather than leaving it
to be discovered.
"""

import html

import plotly.graph_objects as go
import streamlit as st

from lib import db, nav, words
from lib.evidence import share

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
PLOT_HAIR = "rgba(128,128,128,0.35)"
OK, WARN, BAD = "#009E73", "#E69F00", "#D55E00"
BLUE = "#0072B2"
METHOD_COLOUR = {"official_api": OK, "public_feed": OK, "public_scraper_lib": "#56B4E9",
                 "headless_render": WARN, "apify": BAD}
METHOD_ORDER = ["official_api", "public_feed", "public_scraper_lib", "headless_render", "apify"]


# --------------------------------------------------------------- furniture
def section(num: int, title: str, sub: str = "", colour: str = BLUE, slug: str = "") -> None:
    if slug:
        st.html(nav.anchor(slug))
    st.html(
        f"<div style='margin:2.4rem 0 .5rem'>"
        f"<div style='display:flex;align-items:center;gap:.7rem'>"
        f"<span style='font-size:.68rem;font-weight:800;letter-spacing:.16em;"
        f"color:{colour}'>PART {num}</span>"
        f"<span style='flex:1;height:2px;background:{colour};opacity:.3'></span></div>"
        f"<div style='font-size:1.5rem;font-weight:750;line-height:1.25;"
        f"margin:.4rem 0 .2rem'>{title}</div>"
        + (f"<div style='color:{MUTED};font-size:.93rem;line-height:1.55;"
           f"max-width:70ch'>{sub}</div>" if sub else "")
        + "</div>")


def verdict(text: str, colour: str) -> None:
    st.html(f"<div style='border-left:4px solid {colour};padding:.6rem 0 .6rem .85rem;"
            f"margin:.9rem 0 .2rem;font-size:1.02rem;line-height:1.5;max-width:80ch'>"
            f"{text}</div>")


def note(text: str) -> None:
    st.html(f"<div style='color:{MUTED};font-size:.82rem;line-height:1.5;"
            f"margin:.35rem 0 0;max-width:80ch'>{text}</div>")


_MD = str.maketrans({c: "\\" + c for c in "\\`*_[]()#+-!<>|~$:{}"})


def md(text: str) -> str:
    """User text shown inside a Markdown-rendering widget (expander labels,
    captions): every character Markdown, Streamlit's `:colour[…]`/`:icon:`
    syntax or LaTeX (`$…$`) would act on is backslash-escaped, so a post is
    shown as written, never as formatting."""
    return str(text).translate(_MD)


def hbar(labels: list[str], values: list[int], texts: list[str], colours, height=None):
    fig = go.Figure(go.Bar(
        x=values[::-1], y=labels[::-1], orientation="h", marker_color=colours[::-1],
        text=texts[::-1], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,}<extra></extra>"))
    fig.update_layout(height=height or 70 + 38 * len(labels), margin=dict(l=10, r=10, t=10, b=10),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      showlegend=False, yaxis=dict(showgrid=False),
                      xaxis=dict(visible=False, range=[0, max(values or [1]) * 2.3]))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# ------------------------------------------------------------------- data
st.title("Data Bank")
st.html(f"<div style='color:{MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>Every post, thread and review this engine read about finding "
        f"photos in Google Photos — where it came from, how it was obtained, what was set "
        f"aside and why. Nothing here is a finding yet: this is the evidence the findings "
        f"will be counted from.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

src = db.query("SELECT * FROM analysis_sources ORDER BY n_records DESC")
funnel = db.query("SELECT * FROM analysis_funnel ORDER BY step_order")
if src.empty or funnel.empty:
    st.info("The collection has run but its summary tables have not been built yet "
            "(`python -m pipeline.analyse.funnel`).")
    st.stop()

allf = funnel[funnel["source"] == "_all"].set_index("step")
collected = int(allf.loc["collected", "n"])
people = int(allf.loc["collected", "n_authors"])
kept = int(allf.loc["kept", "n"])
excluded = collected - kept
n_sources = len(src)
by_method = src.groupby("collect_method")["n_records"].sum().to_dict()
apify_n = int(by_method.get("apify", 0))
apify_share = share(apify_n, collected)

st.warning(words.proxy_warning(), icon="⚠️")

CHAIN = [
    (f"<b>{collected:,}</b> records read", f"from {n_sources} public sources, "
     f"{people:,} people", BLUE),
    ("<b>How</b> each was<br>obtained", f"{apify_share.text} through a third-party "
     "scraper", BAD),
    (f"<b>{excluded:,}</b> set aside,<br>none deleted", "every one with its reason", WARN),
    ("Where it is<br><b>thinnest</b>", "dates, threads and authors, per source", "#56B4E9"),
]
arrow = (f"<div style='align-self:center;color:{MUTED};font-size:1.4rem;"
         f"padding:0 .25rem'>&rsaquo;</div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.25rem;margin:.8rem 0 .2rem'>"
        + arrow.join(
            f"<div style='flex:1;min-width:150px;border-top:4px solid {c};"
            f"padding:.55rem .5rem .1rem 0'><div style='font-size:.64rem;letter-spacing:.12em;"
            f"color:{MUTED};font-weight:700'>{i}</div><div style='font-size:.95rem;"
            f"line-height:1.35;margin:.15rem 0 .3rem'>{h}</div><div style='font-size:.76rem;"
            f"color:{MUTED};line-height:1.35'>{f}</div></div>"
            for i, (h, f, c) in enumerate(CHAIN, 1))
        + "</div>")

# ================================================================= PART 1
section(1, f"{collected:,} records from {n_sources} sources, written by {people:,} people",
        "A record is one review, one post, or one whole thread — a question with every "
        "reply under it. Threads are kept whole because a single thread can hold several "
        "people's attempts to find a photo, and the replies hold the workarounds.",
        slug="what-was-read")
cols = st.columns(3)
for col, value, label, sub in (
        (cols[0], f"{collected:,}", "records read", f"across {n_sources} sources"),
        (cols[1], f"{people:,}", "different people", "counted beside every number"),
        (cols[2], f"{kept:,}", "kept for analysis", f"{excluded:,} set aside, none deleted")):
    col.html(f"<div style='border-top:3px solid {BLUE};padding-top:.5rem'>"
             f"<div style='font-size:1.9rem;font-weight:750;line-height:1'>{value}</div>"
             f"<div style='font-size:.9rem;margin-top:.15rem'>{label}</div>"
             f"<div style='font-size:.76rem;color:{MUTED}'>{sub}</div></div>")
note(words.metric("n_authors"))
hbar([words.source(s) for s in src["source"]], src["n_records"].astype(int).tolist(),
     [f" {int(n):,} records · {int(a):,} people" for n, a in zip(src["n_records"],
                                                                src["n_authors"], strict=True)],
     [BLUE] * len(src))
top = src.iloc[0]
verdict(f"Source sizes reflect <b>how each was collected</b>, not where the problem is "
        f"most common: {words.source(top['source'])} is the largest "
        f"({share(int(top['n_records']), collected).text} of records) because every recent "
        f"review was read, while the forums were searched.", BLUE)

# ================================================================= PART 2
section(2, "How each source was obtained",
        "Stated per source and stored on every record, because an evaluator will ask. "
        "Where a platform's robots.txt was not followed, that is said here in plain words.",
        BAD, slug="how-obtained")
cards = []
for m in METHOD_ORDER:
    rows = src[src["collect_method"] == m]
    if rows.empty:
        continue
    names = ", ".join(f"{words.source(r['source'])} ({int(r['n_records']):,})"
                      for _, r in rows.iterrows())
    usd = float(rows["collect_usd"].fillna(0).sum())
    cost = f" · third-party cost ${usd:.2f}" if usd else ""
    cards.append(
        f"<div style='border:1px solid {HAIR};border-left:4px solid {METHOD_COLOUR[m]};"
        f"border-radius:7px;padding:.7rem .9rem;margin:.45rem 0'>"
        f"<div style='display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap'>"
        f"<div style='font-weight:700;font-size:.95rem'>{names}</div>"
        f"<div style='font-size:.76rem;color:{MUTED}'>"
        f"{share(int(rows['n_records'].sum()), collected).text} of records{cost}</div></div>"
        f"<div style='font-size:.86rem;line-height:1.5;margin-top:.3rem;max-width:80ch'>"
        f"{words.method(m)}</div></div>")
st.html("".join(cards))
verdict(f"<b>{apify_share.text}</b> of what was read came through a third-party scraper "
        f"against the platforms' stated robots policy. It is public, not login-walled, "
        f"stripped of names, emails, phone numbers and handles before it was stored, and "
        f"marked on every record — so any finding can be re-checked without it.", BAD)

# ================================================================= PART 3
section(3, f"{excluded:,} set aside — nothing deleted",
        "Every record removed at any step is still in the database with its reason, "
        "because what a collection leaves out shapes its answer as much as what it keeps.",
        WARN, slug="set-aside")
ex = funnel[(funnel["source"] == "_all") & funnel["step"].str.startswith("excluded:")]
if ex.empty:
    st.info("Nothing has been set aside yet.")
else:
    reasons = [s.split(":", 1)[1] for s in ex["step"]]
    hbar([words.exclusion(r) for r in reasons], ex["n"].astype(int).tolist(),
         [f" {int(n):,} · {int(a or 0):,} people" for n, a in zip(ex["n"], ex["n_authors"],
                                                                 strict=True)],
         [WARN] * len(ex))
    balances = collected == kept + excluded
    note(f"{collected:,} read = {kept:,} kept + {excluded:,} set aside "
         f"{'— balances' if balances else '— DOES NOT BALANCE'}. The same short sentence "
         f"written by two different people is <b>kept twice</b>: that is two voices, not a "
         f"duplicate. Only the same person repeating themselves, or a long passage copied "
         f"word for word, is set aside.")
    with st.expander("Read what was set aside"):
        pick = st.selectbox("Reason", reasons, format_func=words.exclusion)
        rows = db.query("SELECT r.source, e.detail, r.text_clean, r.source_url"
                        " FROM exclusions e JOIN records r USING (record_id)"
                        " WHERE e.reason = ? AND e.story_id IS NULL LIMIT 30", (pick,))
        for _, r in rows.iterrows():
            # Users' own text: escaped, so a '<' in a post is shown, not parsed.
            t = str(r["text_clean"])
            st.html(f"<div style='border-left:2px solid {HAIR};padding:.15rem 0 .15rem .7rem;"
                    f"margin:.45rem 0;font-size:.85rem;line-height:1.45'>"
                    f"{html.escape(t[:300])}{'…' if len(t) > 300 else ''}<div style='color:{MUTED};"
                    f"font-size:.74rem;margin-top:.2rem'>{words.source(r['source'])} · "
                    f"{html.escape(r['detail'] or '')}</div></div>")

# ================================================================= PART 4
section(4, "Where the collection is thinnest",
        "Three things later analysis depends on, per source: a date (for before and after "
        "Ask Photos), more than one post (replies carry the workarounds), and many "
        "different people rather than a few loud ones.", "#56B4E9", slug="thinnest")
TD = "padding:.4rem .5rem;vertical-align:top"
lines = ["<table style='border-collapse:collapse;font-size:.86rem;width:100%;max-width:900px'>"
         "<tr style='text-align:left;color:" + MUTED + ";font-size:.72rem;letter-spacing:.06em'>"
         "<th style='padding:.35rem .5rem'>SOURCE</th><th style='padding:.35rem .5rem'>RECORDS</th>"
         "<th style='padding:.35rem .5rem'>HAS A DATE</th><th style='padding:.35rem .5rem'>A THREAD, "
         "NOT ONE POST</th><th style='padding:.35rem .5rem'>RECORDS PER PERSON</th></tr>"]
for _, r in src.iterrows():
    n = int(r["n_records"])
    dated, threads = share(int(r["n_dated"]), n), share(int(r["n_threads"]), n)
    per = n / max(int(r["n_authors"]), 1)
    lines.append(
        f"<tr style='border-top:1px solid {HAIR}'><td style='padding:.4rem .5rem'>"
        f"{words.source(r['source'])}<div style='font-size:.72rem;color:{MUTED}'>"
        f"{words.source_kind(r['source'])}</div></td><td style='{TD}'>{n:,}</td>"
        f"<td style='{TD};color:{dated.colour if dated.tier == 'insufficient' else 'inherit'}'>"
        f"{dated.text}</td><td style='{TD}'>{threads.text}</td>"
        f"<td style='{TD};color:{BAD if per > 1.5 else 'inherit'}'>{per:.1f}</td></tr>")
st.html("".join(lines) + "</table>")
thin = src[src["n_records"] < 30]
verdict(("Every source is above the floor where a share can be shown."
         if thin.empty else
         f"<b>{', '.join(words.source(s) for s in thin['source'])}</b> "
         f"{'is' if len(thin) == 1 else 'are'} below 30 records, so "
         f"{'its' if len(thin) == 1 else 'their'} shares appear as counts only, and no "
         f"comparison is drawn from {'it' if len(thin) == 1 else 'them'}."), "#56B4E9")
note("Grey counts with no percentage are below 30 records: too few for a share to mean "
     "anything. From 30 to 79 a share is marked directional.")

# ================================================================= PART 5
# From P2: the unit changes from records to retrieval stories ([CTX] §5).
stor = funnel[funnel["step"].str.startswith("stories")]
if not stor.empty:
    sall = stor[stor["source"] == "_all"].set_index("step")
    n_st, n_core = int(sall.loc["stories", "n"]), int(sall.loc["stories:core", "n"])
    section(5, f"{n_st:,} retrieval stories, {n_core:,} of them core",
            "A story is one person's attempt to find one photo they believe exists. A thread "
            "can hold several people's stories; most reviews hold none. From here on, every "
            "number counts stories and the people who told them, not records.",
            OK, slug="stories")
    cols = st.columns(3)
    for col, b, label, sub in (
            (cols[0], "stories:core", "core", "a known photo, vaguely remembered"),
            (cols[1], "stories:adjacent", "adjacent", "precise cues, or the photo was never there"),
            (cols[2], "stories:irrelevant", "irrelevant", "a search story outside the scope")):
        sh = share(int(sall.loc[b, "n"]), n_st)
        col.html(f"<div style='border-top:3px solid {OK};padding-top:.5rem'>"
                 f"<div style='font-size:1.9rem;font-weight:750;line-height:1'>"
                 f"{int(sall.loc[b, 'n']):,}</div><div style='font-size:.9rem;margin-top:.15rem'>"
                 f"{label} · {int(sall.loc[b, 'n_authors'] or 0):,} people</div>"
                 f"<div style='font-size:.76rem;color:{MUTED}'>{sh.text} of stories · {sub}"
                 f"</div></div>")
    per_src = (stor[(stor["source"] != "_all") & (stor["step"] == "stories:core")]
               .sort_values("n", ascending=False))
    hbar([words.source(s) for s in per_src["source"]], per_src["n"].astype(int).tolist(),
         [f" {int(n):,} core of {int(d):,} stories · {int(a or 0):,} people" for n, d, a in
          zip(per_src["n"], per_src["denom"], per_src["n_authors"], strict=True)],
         [OK] * len(per_src))
    floor = 300                                            # [CTX] §14.3, T-20
    verdict((f"<b>{n_core:,} core stories</b> clears the {floor} the engine needs to compare "
             f"segments ([CTX] §14.3). Which of them are coded, and how, is the next step."
             if n_core >= floor else
             f"<b>{n_core:,} core stories</b> is below the {floor} the engine was designed "
             f"for, after two rounds of extra collection. That is itself a finding: most public "
             f"talk about not finding a photo is about photos that were lost or deleted, not "
             f"about photos someone remembers only vaguely. Comparisons between groups are "
             f"therefore directional at best."), OK if n_core >= floor else WARN)
    note("One AI model reads every record and proposes stories. A second, stronger model "
         "then checks each one against the project's written definitions: it drops "
         "complaints that are not an attempt to find a photo, and settles core versus "
         "adjacent. Each story is stored as an exact passage of the post it came from, never "
         "a paraphrase. Stories the second model dropped are kept, marked, not deleted.")

# ================================================================= PART 6
# From P3: what the coded stories can answer, and how far the coding agrees
# with itself. Read from analysis_coverage / analysis_reliability only.
cov = db.query("SELECT * FROM analysis_coverage WHERE source = '_all'")
rel = db.query("SELECT * FROM analysis_reliability")
if not cov.empty:
    n_q = len(cov)
    coded = cov[cov["disposition"] == "coded"]
    section(6, f"{len(coded)} of {n_q} questions can be answered from public stories",
            "Every story was asked every question its length allows. A question that nearly "
            "every story leaves unanswered is not dropped: it becomes an interview question for "
            "the next part of the research.", "#CC79A7", slug="coverage")
    cov = cov.assign(asked=cov["n_coded"] + cov["n_not_stated"],
                     _k=cov["question"].map(lambda q: tuple(int(x) for x in q.split("."))))
    cov = cov.sort_values("_k")
    shown = cov[cov["asked"] > 0]
    hbar([f"{q} · {words.stage(str(st))}" for q, st in zip(shown["question"], shown["stage"],
                                                          strict=True)],
         shown["n_coded"].astype(int).tolist(),
         [f" {share(int(n), int(a)).text}" + (" · interview" if d == "register" else "")
          for n, a, d in zip(shown["n_coded"], shown["asked"], shown["disposition"], strict=True)],
         ["#CC79A7" if d == "coded" else "#BBBBBB" for d in shown["disposition"]],
         height=60 + 22 * len(shown))
    verdict(f"<b>{n_q - len(coded)} questions</b> are answered by so few stories that they "
            f"go to the interview guide instead — public posts rarely say how many attempts "
            f"were made or how people scan results, so only watching someone search can.",
            "#CC79A7")
    note(words.metric("coverage"))
    if not rel.empty:
        spine = rel[~rel["field"].str.startswith("q:")].set_index("field")
        ps = spine.loc["primary_stage"] if "primary_stage" in spine.index else None
        counts = rel["verdict"].value_counts().to_dict()
        note(f"A second AI model coded {int(rel['n'].max())} of the stories again. "
             + (f"On the stage where a story first went wrong, the two agree "
                f"{share(round(ps['raw_agreement'] * ps['n']), int(ps['n'])).text} of the time "
                f"(κ {ps['value']:.2f}). " if ps is not None else "")
             + f"Of {len(rel)} coded fields, {counts.get('ok', 0)} agree well, "
             f"{counts.get('degenerate', 0)} are nearly constant, and "
             f"{counts.get('low_reliability', 0)} agree too little to carry a headline. "
             + words.metric("kappa"))

# ========================================================== read it yourself
st.html(nav.anchor("browse"))
st.html(f"<div style='margin:2.6rem 0 .4rem'><div style='height:1px;background:{HAIR}'></div>"
        f"<div style='font-size:1.15rem;font-weight:700;margin-top:1rem'>Read any of it "
        f"yourself</div><div style='color:{MUTED};font-size:.9rem;max-width:70ch;"
        f"line-height:1.5'>Every kept record, as stored — names, emails, phone numbers and "
        f"handles replaced with placeholders — with a link back to where it was posted."
        f"</div></div>")
f1, f2 = st.columns([1, 2])
opts = src["source"].tolist()
sel = f1.multiselect("Source", opts, default=opts, format_func=words.source)
q = f2.text_input("Search the text", placeholder="e.g. screenshot, receipt, which year")
where = ["record_id NOT IN (SELECT record_id FROM exclusions WHERE story_id IS NULL)"]
params: list = []
if sel:
    where.append(f"source IN ({','.join('?' * len(sel))})")
    params += sel
if q.strip():
    where.append("text_clean LIKE ?")
    params.append(f"%{q.strip()}%")
clause = " AND ".join(where)
cnt = db.query(f"SELECT count(*) AS n, count(DISTINCT author_key) AS a FROM records"
               f" WHERE {clause}", tuple(params)).iloc[0]
st.caption(f"{int(cnt['n']):,} records from {int(cnt['a']):,} different people")
rows = db.query(f"SELECT record_id, source, created_at, lang, collect_query, thread_context,"
                f" text_clean, source_url FROM records WHERE {clause}"
                f" ORDER BY created_at DESC LIMIT 60", tuple(params))
for _, r in rows.iterrows():
    t = str(r["text_clean"])
    head = (t[:110] + "…") if len(t) > 110 else t
    with st.expander(f"{words.source(r['source'])} · {str(r['created_at'] or '')[:10]} · "
                     f"{md(head)}"):
        st.text(t[:4000] + ("…" if len(t) > 4000 else ""))
        st.caption(f"found by: {md(r['collect_query'] or '—')} · context: "
                   f"{md(r['thread_context'] or '—')} · language: {r['lang'] or '—'}")
        st.link_button("Open where it was posted ↗", r["source_url"])
if len(rows) == 60:
    st.caption("Showing the 60 most recent matches. Narrow the filters to see others.")
