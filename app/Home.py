"""Entrypoint and router — the Myntra engine's pattern ([CTX] §16).

Navigation is declared explicitly with `st.navigation` so "which sections does
the app have?" is answered by reading the source (and by a test), not by
Streamlit's implicit `pages/` discovery. Paths are built from `__file__`:
Streamlit Cloud runs from the repo root while this script lives in `app/`, so
a relative path would resolve against the wrong directory — the mismatch that
took the Myntra app down once, and did not reproduce locally.
"""

import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
VIEWS = HERE / "views"

# Views import `lib.*` by that name, so `app/` must be importable wherever the
# process started — Cloud starts at the repo root, a local run often in `app/`.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
# Try it runs the pipeline's own find / confirm / code modules (P5), so the repo
# root must be importable too; appended, so `lib` still resolves to app/lib.
if str(HERE.parent) not in sys.path:
    sys.path.append(str(HERE.parent))

from lib import nav  # noqa: E402  (must follow the sys.path line above)

st.set_page_config(page_title="Google Photos Discovery Engine", page_icon="🔎",
                   layout="wide", initial_sidebar_state="expanded")

FRONT = "ask"          # the app opens on Ask AI (the PM, 2026-09-27)
SECTIONS = [st.Page(VIEWS / f, title=t, icon=i, url_path=u or None, default=(u == FRONT))
            for f, t, i, u, _ in nav.PAGES]

# The built-in nav is hidden so lib/nav.py can draw a pinned one. The front door is
# served at "/" (its url_path then reads "").
page = st.navigation(SECTIONS, position="hidden")
nav.render(page.url_path or FRONT, VIEWS)
page.run()
nav.footer(plain=True)   # every page: no project words (D-14; all pages since 2026-09-27)
