"""How it works — P0 PLACEHOLDER.

Deployed on day 1 so every later phase ships to a URL already known to work
(implementationplan.md §2.2). The real page — method, funnel, the one-slide
diagram and full Methodology — is written in P6, "because only then is it
true". Until then this page says honestly what the engine is and what is built.
"""

import streamlit as st

from lib import nav

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
ACCENT = "#0072B2"

st.title("Google Photos Discovery Engine")
st.html("<div style='font-size:1.02rem;max-width:70ch;margin:-.4rem 0 1.4rem'>"
        "Why do people fail to find a photo they <i>partly</i> remember? This engine reads "
        "public posts, reviews and forum threads about searching Google Photos, splits them "
        "into individual retrieval stories, and codes each one against an eleven-stage "
        "retrieval journey — to find where retrieval breaks, and where intelligence is "
        "actually needed.</div>")

st.html(f"<div style='border:1px solid {HAIR};border-left:4px solid {ACCENT};"
        f"border-radius:7px;padding:.75rem .9rem;max-width:70ch;font-size:.9rem'>"
        "<b>Being finished.</b> The Data Bank, Analysis, Opportunities, Ask AI and Try it are "
        "live in the sidebar. This page — the method and its full methodology — is written "
        "last, because only then is it true.</div>")

if nav.PLANNED:
    st.html(f"<div style='font-size:.68rem;font-weight:800;letter-spacing:.16em;color:{MUTED};"
            "margin:1.8rem 0 .6rem'>COMING, IN THIS ORDER</div>")
cards = "".join(
    f"<div style='flex:1;min-width:150px;border:1px solid {HAIR};border-top:4px solid "
    f"{HAIR};border-radius:7px;padding:.7rem .8rem'>"
    f"<div style='font-size:.64rem;color:{MUTED}'>{i}</div>"
    f"<div style='font-size:.95rem;font-weight:700;margin:.15rem 0 .3rem'>{title}</div>"
    f"<div style='font-size:.8rem;color:{MUTED};line-height:1.4'>{blurb}</div></div>"
    for i, (title, blurb) in enumerate(nav.PLANNED, start=1))
if cards:
    st.html(f"<div style='display:flex;flex-wrap:wrap;gap:.6rem'>{cards}</div>")

st.html(f"<div style='font-size:.82rem;color:{MUTED};max-width:80ch;margin-top:1.4rem'>"
        "Every share this engine will show is a share of coded public stories — never a "
        "retrieval success rate, never a share of users, never a share of searches.</div>")
