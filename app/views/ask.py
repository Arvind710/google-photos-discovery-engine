"""Ask AI — a conversation with the stories ([CTX] §10, architecture.md §7).

THE LOOK IS THE MYNTRA ENGINE'S ([CTX] §16), PORTED ON THE PM'S REQUEST
------------------------------------------------------------------------
`myntra-discovery-engine/app/views/ask.py`, read in full: a chat window and
nothing else. Threads on the left; on an empty thread a centred "What can I
help you with?" with the input under it and six short prompts below; the
question left and narrow, the answer right and wide, each with a face; one
muted "Understood as" line above the answer; references folded into an
expander; a named status line while it works; and only EVIDENCE problems on
screen — a writing nit shown under a warning teaches readers to distrust an
answer that was fine. Every rule behind the glass is unchanged: plan →
retrieve → gate → write → check, one repair, withhold on an absolute failure.

STREAMING, THEN THE CHECK (D-14). The words appear as they are written
(`analyst.ask(on_text=…)`), as in Myntra, and the whole answer lands inside 10
seconds. The checker runs when the draft is complete; a draft it withholds (a
made-up number or quote, an injected instruction, an internal word) is replaced
on screen by the fallback, with a line saying so. The draft is visible for the
second or two it takes to check — the PM's trade for words that appear as they
are written, and why the status line reads "checking" until the check is done.

When an answer lands the page scrolls to the START of it and stays there
(`_scroll_to_answer`), not to its end.

Everything on this page is in plain words: the evidence reaches the writer
through the translation layer (plain.py), and the references, warnings and
header here use the same words — nothing needs the project's vocabulary.

User text is shown with `st.text` (never parsed); the answer is Markdown with
HTML OFF and `$` escaped; citation numbers are Unicode superscripts, because a
tag inside HTML-off Markdown prints as text.
"""

import re
import uuid

import streamlit as st
import streamlit.components.v1 as components

from lib import analyst as A
from lib import caps, db, ui
from lib import plain as P
from lib import verify as V

MUTED, HAIR, ACCENT, WARN = ui.MUTED, ui.HAIR, ui.BLUE, ui.ORANGE
AVATAR = {"user": "🙋", "assistant": "🔎"}
TYPICAL = "about 15 seconds"
_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

# (chip, question): the chip fits under the input; the question is what is sent,
# each one from the golden set the engine is graded on.
SUGGESTED = [
    ("Which photos are hardest to find?", "What kinds of old photos do people struggle to find?"),
    ("What do people remember?",
     "What do people remember about the photo they want — and what have they forgotten?"),
    ("How do people search?", "How do people search when their memory is incomplete?"),
    ("Does search understand them?",
     "Does Google Photos fail to understand the clues people give it?"),
    ("What should be fixed first?", "Which opportunity does the engine recommend, and why?"),
    ("How big is the evidence?",
     "How many stories is this based on, and from how many different people?"),
]

# The stage names the status line shows (analyst.ask calls progress(stage)).
STAGE = {"plan": "Reading your question…", "retrieve": "Finding the stories and figures…",
         "write": "Writing — checking follows…", "check": "Checking every number and quote…"}

# A citation reads as evidence, not as a schema.
TABLE_LABEL = {"analysis_crosstab": "A count from the stories",
               "analysis_derived": "A count from the stories",
               "analysis_coverage": "How many posts mention this",
               "analysis_reliability": "How consistently the stories were read",
               "analysis_method_flags": "A limit of this evidence",
               "analysis_funnel": "The size of the evidence",
               "analysis_sources": "Where the posts came from",
               "analysis_opportunity": "A problem worth fixing",
               "analysis_weight_sensitivity": "How stable the ranking is",
               "analysis_synthesis": "The engine's suggestion",
               "story_themes": "A pattern noticed later", "story": "What someone wrote"}

# Only findings that bear on whether the answer can be TRUSTED reach the screen;
# a missing closing question or a long answer is the writing, not the evidence.
# Each in plain words: the reader sees what to be careful of, not the checker's rule name.
EVIDENCE = {"uncited claim": "a sentence is not tied to a source",
            "directional": "a figure from a small group is not marked as a rough guide",
            "comparison between kinds": "it compares kinds of photo that have too few stories "
                                        "to compare",
            "evidence": "it rests on fewer sources than a full answer should"}
VERIFY_WARNING = "**Read this answer with care:** "
REPLACED = {True: "The first draft took too long, so this answer was built straight from the "
                  "evidence.",
            False: "The first draft did not pass the fact check, so it was replaced by this "
                   "answer, built straight from the evidence."}

# Every selector checked against the rendered DOM (the Myntra notes): the stable
# hooks are data-testid and .stButton; questions are told from answers by a
# marker this page renders inside the message, never by Streamlit's own classes.
# Never write an HTML tag inside a comment here: st.html drops the whole block.
CSS = f"""
<style>
[data-testid="stChatMessage"] {{
  border: 1px solid {HAIR}; border-radius: 14px; padding: .9rem 1.1rem;
  margin: .55rem 0 .9rem; background: rgba(128,128,128,.045);
}}
[data-testid="stChatMessage"]:has(.ask-q) {{
  background: transparent; border-radius: 14px 14px 14px 4px; padding: .6rem .95rem;
  width: 76%; max-width: 100%; margin: 1.5rem auto .2rem 0;
}}
[data-testid="stChatMessage"]:has(.ask-a) {{
  border-radius: 14px 14px 4px 14px; width: 92%; max-width: 100%; margin: .5rem 0 1.1rem auto;
}}
@media (max-width: 800px) {{
  [data-testid="stChatMessage"]:has(.ask-q),
  [data-testid="stChatMessage"]:has(.ask-a) {{ width: 100%; margin-left: 0; }}
}}
[data-testid="stChatMessage"]:has(.ask-q) [data-testid="stVerticalBlock"] {{ gap: 0; }}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
[data-testid="stChatMessage"]:has(.ask-q) [data-testid="stText"] {{
  font-size: 1.02rem; font-weight: 620; line-height: 1.45; font-family: inherit;
}}
[data-testid="stChatMessage"]:has(.ask-a) p:last-child em {{
  color: {ACCENT}; font-style: normal; font-weight: 600;
}}
.stMain .stButton button {{
  text-align: left; justify-content: flex-start; white-space: normal; line-height: 1.35;
  min-height: 0; padding: .42rem .8rem; border-radius: 999px; border: 1px solid {HAIR};
  font-size: .84rem; font-weight: 500; transition: border-color .13s ease, transform .13s ease;
}}
.stMain .stButton button:hover {{ border-color: {ACCENT}; transform: translateY(-1px); }}
.stMain .stButton button > div {{ justify-content: flex-start; width: 100%; }}
.stMain .stButton {{ display: flex; justify-content: center; }}
[data-testid="stSidebar"] .stButton button {{
  min-height: 0; padding: .34rem .6rem; font-size: .86rem; border-radius: 8px;
}}
[data-testid="stChatInput"] {{ border-radius: 12px; }}
</style>
"""
QUESTION_MARK = "<span class='ask-q' style='display:none'></span>"
ANSWER_MARK = "<span class='ask-a' style='display:none'></span>"

st.html(CSS)

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()
key = caps.api_key()
if not key:
    st.info("Ask AI is not switched on for this deployment yet (no API key is configured). "
            "Every other page works without it.")
    st.stop()

fun = db.query("SELECT n, n_authors FROM analysis_funnel WHERE source='_all'"
               " AND step='stories:core'")
CORE = int(fun.iloc[0]["n"]) if not fun.empty else 0
PEOPLE = int(fun.iloc[0]["n_authors"]) if not fun.empty else 0
IDENTITY = (f"Answers come only from <b>{CORE} stories</b> that {PEOPLE} people posted about "
            "a photo they only vaguely remembered. Every claim shows its source, every number "
            "and quote is checked, and the answer says plainly when the stories cannot tell.")


@st.cache_resource(show_spinner=False)
def _client(k: str):
    from openai import OpenAI
    return OpenAI(api_key=k, timeout=A.TIMEOUT_S, max_retries=1)


def _escape_md(text: str) -> str:
    return re.sub(r"(?<!\\)\$", r"\\$", text or "")


# ---------------------------------------------------------------- threads
# In st.session_state: they last as long as the browser tab. The URL is public,
# so nothing a visitor asks is kept on the server for the next one to see.
def _threads() -> dict:
    st.session_state.setdefault("threads", {})
    st.session_state.setdefault("order", [])
    return st.session_state["threads"]


def _new_thread() -> str:
    tid = uuid.uuid4().hex[:8]
    _threads()[tid] = {"id": tid, "title": "New chat", "messages": []}
    st.session_state["order"].insert(0, tid)
    st.session_state["active"] = tid
    return tid


def _active() -> dict:
    tid = st.session_state.get("active")
    return _threads()[tid if tid in _threads() else _new_thread()]


def _title(q: str) -> str:
    q = " ".join(str(q).split())
    return q[:38] + ("…" if len(q) > 38 else "")


# ------------------------------------------------------------- one answer
def _refs(a: A.Answer) -> dict[str, dict]:
    """Everything a reference can show, resolved once, as plain strings."""
    out = {}
    if not a.retrieved:
        return out
    for s in a.retrieved.records():
        text = s["text"].replace(" …[cut]", "…")
        out[f"story|{s['story_id']}"] = {
            "label": TABLE_LABEL["story"],
            "detail": f"a post on {P.SOURCE.get(s['source'], s['source'])}",
            "quote": text[:320] + ("…" if len(text) > 320 else "")}
    for r in a.retrieved.rows():
        c = r.get("_cite")
        if c:
            # The same plain sentence the writer was given (plain.py).
            out[f"{c['table']}|{c['key']}"] = {
                "label": TABLE_LABEL.get(c["table"], "A figure from the stories"),
                "detail": P.sentence(r) or P.scrub(r.get("text") or r.get("label") or "")}
    return out


def _scroll_to_answer(follow_s: float = 2.0) -> None:
    """Bring the START of the newest answer to the top of the screen and hold it
    there for `follow_s` seconds — Streamlit's chat keeps the page pinned to the
    bottom as content grows, which left readers at the END of a long answer
    (the PM, 2026-09-27). A reader who scrolls or taps stops the hold at once."""
    components.html(f"""<script>
    const doc = window.parent.document;
    let stop = false;
    ["wheel", "touchstart", "keydown", "mousedown"].forEach(e =>
        doc.addEventListener(e, () => {{ stop = true; }}, {{once: true, passive: true}}));
    const go = () => {{
      const m = doc.querySelectorAll(".ask-a");
      if (!m.length) return;
      const msg = m[m.length - 1].closest('[data-testid="stChatMessage"]') || m[m.length - 1];
      msg.scrollIntoView({{block: "start"}});
    }};
    const t0 = Date.now();
    const iv = setInterval(() => {{
      if (stop || Date.now() - t0 > {int(follow_s * 1000)}) {{ clearInterval(iv); return; }}
      go();
    }}, 100);
    </script>""", height=0)


def _render_answer(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])
        return
    if msg.get("replaced") is not None:
        st.caption(REPLACED[bool(msg["replaced"])])
    if msg.get("restated"):
        st.html(f"<div style='color:{MUTED};font-size:.78rem;margin-bottom:.4rem'>Understood "
                f"as: {ui.esc(msg['restated'])}</div>")
    order: list[tuple[str, str]] = []

    def num(m):
        k = (m.group(1), m.group(2).strip())
        if k not in order:
            order.append(k)
        return str(order.index(k) + 1).translate(_SUP)

    st.markdown(V.CITATION.sub(num, _escape_md(msg["text"])), unsafe_allow_html=False)
    if order:
        with st.expander(f"Where this came from — {len(order)} references"):
            st.caption("Every numbered claim above, traced to the figure or the story it "
                       "rests on.")
            lines = []
            for i, (t, k) in enumerate(order, 1):
                ref = msg["refs"].get(f"{t}|{k}", {"label": t, "detail": k})
                body = (f"<div style='font-size:.84rem;margin:.35rem 0'><b>[{i}]</b> "
                        f"{ui.esc(ref['label'])} — {ui.esc(ref['detail'])}")
                if ref.get("quote"):
                    body += (f"<div style='border-left:2px solid {HAIR};padding-left:.6rem;"
                             f"margin-top:.2rem;color:{MUTED}'>“{ui.esc(ref['quote'])}”</div>")
                lines.append(body + "</div>")
            st.html("".join(lines))
    said = list(dict.fromkeys(plain for p in msg.get("problems", [])
                              for k, plain in EVIDENCE.items() if p.startswith(k)))
    if said:
        st.warning(VERIFY_WARNING + "; ".join(said) + ".", icon="⚠️")
    st.caption(msg.get("foot", ""))


# ---------------------------------------------------------------- sidebar
thread = _active()
with st.sidebar:
    st.html(f"<div style='margin-top:.4rem;padding-top:.7rem;border-top:1px solid {HAIR}'>"
            "</div>")
    if st.button("✚  New chat", width="stretch", key="newchat"):
        _new_thread()
        st.rerun()
    started = [t for t in st.session_state["order"]
               if t in _threads() and _threads()[t]["messages"]]
    if started:
        st.html(f"<div style='font-size:.66rem;font-weight:800;letter-spacing:.14em;"
                f"color:{MUTED};margin:.9rem 0 .3rem'>THIS SESSION</div>")
        for tid in started:
            cur = tid == thread["id"]
            if st.button(("▸ " if cur else "  ") + _threads()[tid]["title"], key=f"th{tid}",
                         width="stretch", disabled=cur):
                st.session_state["active"] = tid
                st.rerun()
        st.html(f"<div style='font-size:.7rem;color:{MUTED};line-height:1.45;margin-top:.5rem'>"
                "Chats live in this browser tab only — the URL is public, so nothing is kept "
                "on the server.</div>")
    st.html(f"<div style='font-size:.7rem;color:{MUTED};line-height:1.45;margin-top:.8rem'>"
            f"{caps.left('ask')} questions left in this visit · a public page on a personal "
            "API budget.</div>")

# ------------------------------------------------------------- transcript
if thread["messages"]:
    st.html(f"<div style='display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;"
            f"border-bottom:1px solid {HAIR};padding-bottom:.55rem;margin:0 0 1.1rem'>"
            f"<span style='font-size:.68rem;font-weight:800;letter-spacing:.18em;"
            f"color:{MUTED}'>ASK AI</span><span style='font-size:.78rem;color:{MUTED};"
            f"line-height:1.5'>based on <b>{CORE}</b> stories people posted · every claim "
            "shows its source · figures count <b>public posts</b>, not users or searches"
            "</span></div>")

for msg in thread["messages"]:
    with st.chat_message(msg["role"], avatar=AVATAR[msg["role"]]):
        if msg["role"] == "user":
            st.html(QUESTION_MARK)
            st.text(msg["content"])
        else:
            st.html(ANSWER_MARK)
            _render_answer(msg)

# ----------------------------------------------------- the empty-thread state
# On the run that answers the first question the thread is still empty, so the
# hero must step aside when a question is already in flight (Myntra, checked).
in_flight = bool(st.session_state.get("pending") or st.session_state.get("ask_first"))
typed = None
if thread["messages"]:
    typed = st.chat_input("Ask a follow-up…", key="ask_more")
elif in_flight:
    typed = st.session_state.get("ask_first")
else:
    st.html("<div style='height:6vh'></div>")
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        st.html(f"<div style='text-align:center;margin:0 0 1.1rem'>"
                f"<div style='font-size:.68rem;font-weight:800;letter-spacing:.18em;"
                f"color:{MUTED}'>ASK AI</div>"
                f"<div style='font-size:1.9rem;font-weight:750;line-height:1.25;"
                f"margin-top:.3rem'>What can I help you with?</div>"
                f"<div style='color:{MUTED};font-size:.9rem;line-height:1.55;margin:.5rem auto 0;"
                f"max-width:56ch'>{IDENTITY} Most land in {TYPICAL}.</div></div>")
        with st.container():
            st.chat_input("Ask anything about the stories…", key="ask_first")
        st.html(f"<div style='color:{MUTED};font-size:.76rem;text-align:center;"
                f"margin:.9rem 0 .3rem'>or start with one of these</div>")
        for row in (SUGGESTED[:3], SUGGESTED[3:]):
            for col, (chip, q) in zip(st.columns(len(row)), row, strict=True):
                if col.button(chip, key=f"sugg{q[:18]}"):
                    st.session_state["pending"] = q
                    st.rerun()
        st.html(f"<div style='text-align:center;margin:1.4rem 0 .2rem'><span style='font-size:"
                f".75rem;color:{MUTED};border:1px solid {HAIR};border-radius:999px;padding:.2rem"
                f" .55rem'><span style='display:inline-block;width:.45rem;height:.45rem;"
                f"border-radius:50%;background:{WARN};margin-right:.4rem;vertical-align:middle'>"
                "</span>every figure counts <b>public posts</b> — not users, not searches, "
                "not a success rate</span></div>")

question = typed or st.session_state.pop("pending", None)

# ------------------------------------------------------------- a new answer
if question:
    why = A.screen(question) or caps.blocked("ask")
    thread["messages"].append({"role": "user", "content": question})
    if thread["title"] == "New chat":
        thread["title"] = _title(question)
    if why:
        # A declined question is a turn like any other and stays in the thread.
        thread["messages"].append({"role": "assistant", "text": why, "restated": "",
                                   "refs": {}, "problems": [], "foot": ""})
        st.rerun()
    caps.record("ask")
    with st.chat_message("user", avatar=AVATAR["user"]):
        st.html(QUESTION_MARK)
        st.text(question)
    msgs = thread["messages"][:-1]
    hist = [{"question": q["content"], "answer": a.get("text", "")}
            for q, a in zip(msgs[::2], msgs[1::2], strict=False)]
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        st.html(ANSWER_MARK)
        stage = st.status(f"{STAGE['plan']} · usually {TYPICAL}", expanded=False)
        words = st.empty()
        _scroll_to_answer(follow_s=12.0)

        def show(so_far: str) -> None:
            words.markdown(_escape_md(so_far) + " ▌", unsafe_allow_html=False)

        a = A.ask(_client(key), db.connection(), question, history=hist, on_text=show,
                  progress=lambda s: stage.update(label=f"{STAGE[s]} · usually {TYPICAL}"))
        stage.update(label=("Could not answer" if a.error else f"Answered in {a.seconds:.0f}s"),
                     state="error" if a.error else "complete")
    route = {"FULL": "full answer", "PARTIAL": "partial answer — it names what the stories "
             "cannot support", "NONE": "outside what these stories hold"}.get(a.route, a.route)
    thread["messages"].append(
        {"role": "assistant", "error": caps.explain(a.error) if a.error else "",
         "text": a.text, "restated": a.restated, "refs": _refs(a),
         "replaced": (a.withheld[0].startswith("the draft did not finish")
                      if a.withheld else None),
         "problems": a.report.problems() if a.report else [],
         "foot": (f"{'✓ checked' if a.verified else '⚠ not fully checked'} · {route} · "
                  f"{a.seconds:.0f}s")})
    st.session_state["scroll_to_answer"] = True
    st.rerun()

if st.session_state.pop("scroll_to_answer", False):
    _scroll_to_answer()
