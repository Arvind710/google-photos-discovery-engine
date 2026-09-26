"""Ask AI — questions answered only from the coded stories, with citations
([CTX] §10, architecture.md §7). The loop is lib.analyst.ask: plan → retrieve →
gate → write under contract → check, one bounded repair. This page shows what
the reader needs to judge an answer: how the question was understood, the
answer with numbered references, what each reference is, and whether every
number, quote and citation passed the checker.
"""

import re

import streamlit as st

from lib import analyst as A
from lib import caps, db, ui
from lib import verify as V

STARTERS = ["What kinds of old photos do people struggle to find?",
            "What do people remember about the photo they want — and what have they forgotten?",
            "How do people search when their memory is incomplete?",
            "Does Google Photos fail to understand the clues people give it?",
            "Which opportunity does the engine recommend, and why?"]

st.title("Ask AI")
st.html(f"<div style='color:{ui.MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>Ask about the stories. Every answer is written only from the "
        f"engine's own tables and the stories themselves, cites them, and is checked in code "
        f"before you see it: each number against the rows it came from, each quote against the "
        f"story it came from.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()
key = caps.api_key()
if not key:
    st.info("Ask AI is not switched on for this deployment yet (no API key is configured). "
            "Every other page works without it.")
    st.stop()


@st.cache_resource(show_spinner=False)
def _client(k: str):
    from openai import OpenAI
    return OpenAI(api_key=k, timeout=A.TIMEOUT_S, max_retries=1)


def _escape_md(text: str) -> str:
    return re.sub(r"(?<!\\)\$", r"\\$", text or "")


_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _render(answer: dict) -> None:
    """Citations become numbered superscripts; the references are listed under
    the answer with what each one is. The answer is Markdown with HTML OFF, so
    an HTML superscript tag would print as text: the numbers are Unicode superscripts."""
    refs: list[tuple[str, str]] = []

    def num(m):
        k = (m.group(1), m.group(2).strip())
        if k not in refs:
            refs.append(k)
        return str(refs.index(k) + 1).translate(_SUP)
    body = V.CITATION.sub(num, _escape_md(answer["text"]))
    if answer.get("restated"):
        st.html(f"<div style='color:{ui.MUTED};font-size:.8rem;margin-bottom:.3rem'>Understood "
                f"as: {ui.esc(answer['restated'])}</div>")
    st.markdown(body, unsafe_allow_html=False)
    if refs:
        lines = []
        for i, (t, k) in enumerate(refs, 1):
            desc = answer["refs"].get(f"{t}|{k}", k)
            lines.append(f"<div style='font-size:.78rem;color:{ui.MUTED};margin:.15rem 0'>"
                         f"[{i}] {ui.esc(desc)}</div>")
        st.html("".join(lines))
    route = {"FULL": "full answer", "PARTIAL": "partial answer — see the gap it names",
             "NONE": "outside what these stories hold"}.get(answer["route"], answer["route"])
    meta = (f"{'✓ checked' if answer['verified'] else '⚠ not fully verified'} · "
            f"{route} · {answer['seconds']:.0f}s")
    st.html(f"<div style='font-size:.72rem;color:{ui.MUTED};margin-top:.3rem'>{meta}</div>")
    if not answer["verified"]:
        st.warning("The checker could not confirm everything in this answer: "
                   + "; ".join(answer["problems"][:3]) + ". Treat it with care.")


def _ref_text(a: A.Answer) -> dict[str, str]:
    out = {}
    if not a.retrieved:
        return out
    for s in a.retrieved.records():
        out[f"story|{s['story_id']}"] = (f"A story from {s['source']} (stage {s['primary_stage']}"
                                         f", {s['photo_class']}): “{s['text'][:160]}…”")
    for r in a.retrieved.rows():
        c = r.get("_cite")
        if c:
            desc = (r.get("about") or r.get("text") or r.get("label") or r.get("measure")
                    or r.get("step") or r.get("field") or r.get("question") or c["key"])
            extra = r.get("share") or ""
            desc = str(desc).replace("_", " ")                  # plain words, not code names
            out[f"{c['table']}|{c['key']}"] = f"{desc}{' — ' + extra if extra else ''}"
    return out


st.session_state.setdefault("chat", [])
for turn in st.session_state["chat"]:
    with st.chat_message("user"):
        st.text(turn["question"])
    with st.chat_message("assistant"):
        _render(turn)

if not st.session_state["chat"]:
    st.html(f"<div style='font-size:.8rem;color:{ui.MUTED};margin:.6rem 0 .3rem'>Try one of "
            f"these</div>")
    for q in STARTERS:
        if st.button(q, key=f"starter_{q}"):
            st.session_state["pending"] = q
            st.rerun()

ui.note(f"Every share is a share of coded public stories — never a retrieval success rate, a "
        f"share of users, or a share of searches. {caps.left('ask')} questions left in this "
        f"visit.")
typed = st.chat_input("Ask about the stories…")
question = typed or st.session_state.pop("pending", None)
if question:
    why = A.screen(question) or caps.blocked("ask")
    if why:
        st.info(why)
        st.stop()
    caps.record("ask")
    with st.chat_message("user"):
        st.text(question)
    with st.chat_message("assistant"), st.spinner("Planning, retrieving, writing, checking…"):
        con = db.connection()
        hist = [{"question": t["question"], "answer": t["text"]}
                for t in st.session_state["chat"]]
        a = A.ask(_client(key), con, question, history=hist)
    if a.error:
        st.error(caps.explain(a.error))
        st.stop()
    st.session_state["chat"].append({
        "question": question, "restated": a.restated, "text": a.text, "route": a.route,
        "verified": a.verified, "problems": a.report.problems() if a.report else [],
        "seconds": a.seconds, "refs": _ref_text(a)})
    st.rerun()
