"""Spend caps for the public URL (EC-OPS-4, P5-OPS-1/2). The URL is public and
the key is the PM's; a crawler is enough to drain a balance mid-evaluation.

Two lines of defence here — a per-session cap and a process-wide daily cap —
and one outside: the OpenAI balance itself. The daily counter lives in
`st.cache_resource`, shared by every session in one container, so it is a
GLOBAL cap; it resets when the container restarts. That is stated rather than
papered over: the balance is the real limit.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

LIMITS = {"ask": {"session": 6, "day": 25}, "try": {"session": 2, "day": 8}}


@st.cache_resource(show_spinner=False)
def _global() -> dict:
    return {}


def _today(kind: str) -> dict:
    g = _global()
    c = g.setdefault(kind, {"day": date.today().isoformat(), "n": 0})
    if c["day"] != date.today().isoformat():
        c.update(day=date.today().isoformat(), n=0)
    return c


def blocked(kind: str) -> str | None:
    lim = LIMITS[kind]
    used = int(st.session_state.get(f"cap_{kind}", 0))
    if used >= lim["session"]:
        return (f"That is the limit of {lim['session']} for one visit — this public page runs "
                f"on a personal API budget. Reload to start a new visit.")
    if _today(kind)["n"] >= lim["day"]:
        return (f"The page has reached today's limit of {lim['day']}. Everything else on the "
                f"site — the Data Bank, Analysis and Opportunities — stays available.")
    return None


def record(kind: str) -> None:
    st.session_state[f"cap_{kind}"] = int(st.session_state.get(f"cap_{kind}", 0)) + 1
    _today(kind)["n"] += 1


def left(kind: str) -> int:
    return LIMITS[kind]["session"] - int(st.session_state.get(f"cap_{kind}", 0))


def api_key() -> str | None:
    """Streamlit secrets on Cloud; the laptop's .env locally. Never displayed."""
    try:
        k = st.secrets.get("OPENAI_API_KEY")
    except Exception:                                            # noqa: BLE001 — no secrets file
        k = None
    if not k:
        import os
        k = os.environ.get("OPENAI_API_KEY")
        if not k:
            try:
                from pipeline.common import env
                k = env.load(export=False).get("OPENAI_API_KEY")
            except Exception:                                    # noqa: BLE001
                k = None
    return k or None


def explain(error: str) -> str:
    """What a reader sees when a call fails. An empty API balance (a 429
    `insufficient_quota`, seen 2026-09-26) is the budget, not a bug, and the
    raw error names a billing URL — say it plainly instead."""
    e = (error or "").lower()
    if "insufficient_quota" in e or "no credits" in e or "billing" in e:
        return ("This part of the demo is paused: its API budget has run out. Everything else "
                "on the site — the Data Bank, Analysis and Opportunities — still works.")
    return error
