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
# P0 ships only the front door. Data Bank lands in P1, Analysis and
# Opportunities in P4, Ask AI and Try it in P5, the full How it works in P6.
PAGES: list[tuple[str, str, str, str, list[tuple[str, str]]]] = [
    ("home.py", "How it works", "🔎", "", []),
    ("data_bank.py", "Data Bank", "🗂️", "data_bank", [
        ("what-was-read", "What was read"),
        ("how-obtained", "How each source was obtained"),
        ("set-aside", "What was set aside"),
        ("thinnest", "Where it is thinnest"),
        ("browse", "Read the records"),
    ]),
]

# Pinned in implementationplan.md §0.5 — shown on the front door as "coming",
# never as nav links, until each is built.
PLANNED: list[tuple[str, str]] = [
    ("Analysis", "Where retrieval breaks across the eleven stages, and what people remember"),
    ("Opportunities", "Ranked opportunity areas, the scoring behind them, and the recommendation"),
    ("Ask AI", "Questions answered only from the coded stories, with citations"),
    ("Try it", "Paste a post and watch the pipeline classify and code it"),
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


def footer() -> None:
    """The corpus stamp on every page (EC-OPS-11, P6-BR-9). Reads the PINNED
    run; says so plainly when nothing has been published yet."""
    pub = db.published()
    stamp = (pub["corpus_version"] if pub
             else "Corpus not yet published — the engine is being built")
    st.html(f"<div style='margin-top:3rem;padding-top:.7rem;border-top:1px solid {HAIR};"
            f"font-size:.74rem;color:{MUTED}'>{stamp}</div>")
