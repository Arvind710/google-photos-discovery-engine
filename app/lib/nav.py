"""The navigation shell — ported from the Myntra engine ([CTX] §16), unchanged
in behaviour.

- The sidebar is PINNED above 900px (collapse control hidden, fixed width): a
  collapsed sidebar is a hamburger icon on a page that has just said it has six
  sections. Below 900px the normal toggle returns, or it would cover the page.
- Sub-links are same-page `#fragment` links only. `st.html` strips <script>, so
  a cross-page anchor cannot be re-applied after Streamlit finishes rendering.
- `PAGES` is the single source of truth for app structure. A page appears here
  only once it is BUILT: a nav entry that leads nowhere tells an evaluator the
  section exists. Build order is nav order (implementationplan.md §0.5).
"""

from __future__ import annotations

import streamlit as st

from lib import db

# (module filename, title, icon, url_path, [(slug, label), ...])
# P0 shipped the front door, P1 the Data Bank, P4 Analysis and Opportunities;
# P5 Ask AI and Try it; P6 the full How it works and Methodology.
# 2026-09-27 (the PM): "hide 'How it works' and 'Try it'" — both pages stay in
# app/views/ but are not routed; Data Bank, the first section, is the front door.
HIDDEN = ["home.py", "try_it.py"]
PAGES: list[tuple[str, str, str, str, list[tuple[str, str]]]] = [
    ("data_bank.py", "Data Bank", "🗂️", "data_bank", [
        ("what-was-read", "What was read"),
        ("how-obtained", "How each source was obtained"),
        ("set-aside", "What was set aside"),
        ("thinnest", "Where it is thinnest"),
        ("stories", "From records to cases"),
        ("coverage", "What the cases can answer"),
        ("browse", "Read the records"),
    ]),
    ("analysis.py", "Analysis", "📊", "analysis", [
        ("stages", "Where it first breaks"),
        ("photo-type", "By kind of photo"),
        ("owners", "Whose side the problem is on"),
        ("memory", "What people remember"),
        ("modes", "How they looked"),
        ("hypotheses", "Ideas the posts can't test"),
        ("sources", "Across sources"),
        ("emerging", "Patterns noticed later"),
    ]),
    ("opportunities.py", "Opportunities", "🎯", "opportunities", [
        ("recommendation", "What to fix first"),
        ("candidates", "Every problem considered"),
        ("weights", "Does the ranking hold?"),
        ("two-by-two", "Two scores at a time"),
        ("handoff", "What the interviews should test"),
    ]),
    ("ask.py", "Ask AI", "💬", "ask", []),
]

# Pinned in implementationplan.md §0.5 — shown on the front door as "coming",
# never as nav links, until each is built.
PLANNED: list[tuple[str, str]] = [
]

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"


def anchor(slug: str) -> str:
    """Scroll target for a sidebar sub-link. `scroll-margin-top` keeps the
    landing point below Streamlit's floating header."""
    return f"<div id='{slug}' style='position:relative;scroll-margin-top:4.5rem'></div>"


def _css() -> str:
    return (
        "<style>"
        "@media (min-width: 900px){"
        "[data-testid='stSidebarCollapseButton'],"
        "[data-testid='stSidebarCollapsedControl']{display:none !important}"
        "[data-testid='stSidebar']{min-width:16.5rem !important;"
        "max-width:16.5rem !important;transform:none !important;"
        "visibility:visible !important}"
        "}"
        ".navsub a{display:block;padding:.16rem 0 .16rem .2rem;font-size:.82rem;"
        "line-height:1.35;color:inherit;opacity:.62;text-decoration:none}"
        ".navsub a:hover{opacity:1;text-decoration:underline}"
        "</style>")


def render(current_url_path: str, views_dir) -> None:
    """Draw the whole nav. `current_url_path` is '' for the front door."""
    with st.sidebar:
        st.html(_css())
        st.html(f"<div style='font-size:.66rem;font-weight:800;letter-spacing:.16em;"
                f"color:{MUTED};margin:.2rem 0 .5rem'>THE ENGINE</div>")
        for filename, title, icon, url_path, subs in PAGES:
            st.page_link(str(views_dir / filename), label=f"**{title}**", icon=icon)
            if url_path == current_url_path and subs:
                st.html("<div class='navsub' style='margin:.1rem 0 .5rem .95rem;"
                        f"border-left:1px solid {HAIR};padding-left:.6rem'>"
                        + "".join(f"<a href='#{slug}'>{label}</a>" for slug, label in subs)
                        + "</div>")
        st.html(f"<div style='margin-top:1.2rem;padding-top:.7rem;"
                f"border-top:1px solid {HAIR};font-size:.72rem;color:{MUTED};"
                f"line-height:1.5'>Public data only · authors pseudonymised · "
                f"no personal information in outputs.</div>")


def plain_stamp(stamp: str) -> str:
    """The corpus stamp without the project's own words, for the Ask AI page,
    where nothing may need them (D-14): "Corpus v1.0 — 115 core stories from 109
    people, in 31,235 public records collected A to B · codebook v1:…" →
    "Data version 1.0 — 115 cases of someone hunting for a photo they only vaguely
    remembered, from 109 people, in 31,235 public posts collected A to B" (a reader
    does not know the study's word "stories", ask_v3)."""
    import re
    m = re.match(r"Corpus v([\d.]+) — (\d[\d,]*) core stories from (\d[\d,]*) people, in "
                 r"(\d[\d,]*) public records collected (\S+) to (\S+)", stamp or "")
    if not m:
        return stamp
    v, n, p, recs, lo, hi = m.groups()
    return (f"Data version {v} — {n} cases of someone hunting for a photo they only vaguely "
            f"remembered, from {p} people, in {recs} public posts collected {lo} to {hi}")


def footer(*, plain: bool = False) -> None:
    """The corpus stamp on every page (EC-OPS-11, P6-BR-9). Reads the PINNED
    run; says so plainly when nothing has been published yet. `plain` drops the
    project's own words (the Ask AI page)."""
    pub = db.published()
    stamp = (pub["corpus_version"] if pub
             else "Corpus not yet published — the engine is being built")
    if plain:
        stamp = plain_stamp(stamp)
    st.html(f"<div style='margin-top:3rem;padding-top:.7rem;border-top:1px solid {HAIR};"
            f"font-size:.74rem;color:{MUTED}'>{stamp}</div>")
