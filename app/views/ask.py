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

When a question is asked the page makes one scroll, bringing it to the top, and
then only the reader moves it (`_scroll_guard`, `_bring_into_view`).

NO JUMP WHEN IT LANDS (ask_v3, the PM: "there is a huge jerk post an answer
completion"). The answer used to be streamed into one layout and then the page
was re-run and redrawn from the transcript in another — a status box vanished,
the "Understood as" line appeared above the words, superscripts re-flowed them,
and a scroll script fired. Now the live answer is drawn in the SAME slots the
transcript uses, filled in place: the restatement first, the words as they
stream, the evidence and footer below them when checked. And the question is
taken in on one instant run and answered on the next (`_accept`), so no element
of the previous screen is left to be removed when the answer finishes.

NO SUPERSCRIPTS (ask_v3). The answer reads as prose; what it rests on is in the
evidence panel under it — the exact figures, each post in full, the limits — so
the panel adds what the answer does not repeat.

Everything on this page is in plain words: the evidence reaches the writer
through the translation layer (plain.py), and the references, warnings and
header here use the same words — nothing needs the project's vocabulary.

User text is shown with `st.text` (never parsed); the answer is Markdown with
HTML OFF and `$` escaped; its citations are removed before it is shown.
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
TYPICAL = "about 10 seconds"   # the PM, 2026-09-27; measured mean 7.6 s, max 9.1 s

# (chip, question): the chip fits under the input; the question is what is sent,
# each one from the golden set the engine is graded on.
SUGGESTED = [
    ("Which photos are hardest to find?", "What kinds of old photos do people struggle to find?"),
    ("What do people remember?",
     "What do people remember about the photo they want — and what have they forgotten?"),
    ("How do people search?", "How do people search when their memory is incomplete?"),
    ("Do their clues find the photo?",
     "When people type a clue they remember, does Google Photos bring up the photo?"),
    ("What should be fixed first?", "Which opportunity does the engine recommend, and why?"),
    ("How big is the evidence?",
     "How many cases is this based on, and from how many different people?"),
]

# The stage names the status line shows (analyst.ask calls progress(stage)).
STAGE = {"plan": "Reading your question…", "retrieve": "Finding the evidence…",
         "write": "Writing — every figure and quote is checked next…",
         "check": "Checking every figure and quote…"}

# The evidence panel's three groups, by where a citation points.
GROUP = {"story": "What people wrote", "analysis_method_flags": "Limits to keep in mind",
         "site": "About the study"}
FIGURES = "What the figures say"
# Only findings that bear on whether the answer can be TRUSTED reach the screen;
# a missing closing question or a long answer is the writing, not the evidence.
# Each in plain words: the reader sees what to be careful of, not the checker's rule name.
EVIDENCE = {"directional": "a figure from a small group is not marked as a rough guide",
            "comparison between kinds": "it compares kinds of photo that have too few cases "
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
# The intro line under the heading was removed (the PM, 2026-09-27).


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
    """Everything the evidence panel can show, resolved once, as plain strings."""
    out = {}
    if not a.retrieved:
        return out
    for s in a.retrieved.records():
        text = s["text"].replace(" …[cut]", "…")
        url = str(s.get("source_url") or "")
        out[f"story|{s['story_id']}"] = {
            "group": GROUP["story"],
            "detail": f"A post on {P.SOURCE.get(s['source'], s['source'])}",
            "quote": text[:420] + ("…" if len(text) > 420 else ""),
            # Where it was posted, as the Data Bank links it (the PM, 2026-09-27: "where
            # there is a quote, mention the link to the actual quote in the evidence box").
            "url": url if re.match(r"https?://", url) else ""}
    for r in a.retrieved.rows():
        c = r.get("_cite")
        if c:
            # The exact figure, as the translation layer states it — the answer said
            # it in words; here is the count behind it.
            out[f"{c['table']}|{c['key']}"] = {
                "group": GROUP.get(c["table"], FIGURES),
                "detail": P.reader_words(P.sentence(r)
                                         or P.scrub(r.get("text") or r.get("label") or ""))}
    return out


def _prose(text: str) -> str:
    """The answer as a reader sees it: no citation marks (they live in the panel)."""
    t = V.CITATION.sub("", text or "")
    t = re.sub(r"[ \t]+([.,;:!?])", r"\1", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def _evidence(msg: dict) -> None:
    """The panel under an answer: every source it cites, grouped, in full."""
    keys = list(dict.fromkeys(f"{t}|{k.strip()}" for t, k in V.CITATION.findall(msg["text"])))
    refs = [msg["refs"][k] for k in keys if k in msg.get("refs", {})]
    if not refs:
        return
    with st.expander(f"The evidence behind this answer · {len(refs)} "
                     f"source{'s' if len(refs) != 1 else ''}"):
        html = [f"<div style='color:{MUTED};font-size:.76rem;margin:0 0 .5rem'>A <i>case</i> is "
                "one person's account, in a public post, of hunting for one photo. Figures "
                "count cases — not users, not searches.</div>"]
        for head in (GROUP["site"], FIGURES, GROUP["story"], GROUP["analysis_method_flags"]):
            items = [r for r in refs if r.get("group", FIGURES) == head]
            if not items:
                continue
            html.append(f"<div style='font-size:.68rem;font-weight:800;letter-spacing:.12em;"
                        f"color:{MUTED};margin:.8rem 0 .3rem'>{head.upper()}</div>")
            for r in items:
                body = "<div style='font-size:.86rem;line-height:1.5;margin:.3rem 0'>"
                if r.get("quote"):
                    link = (f" · <a href='{ui.esc(r['url'])}' target='_blank' "
                            f"rel='noopener noreferrer'>Open the post ↗</a>"
                            if r.get("url") else "")
                    body += (f"<div style='border-left:3px solid {ACCENT};padding-left:.7rem'>"
                             f"“{ui.esc(r['quote'])}”<div style='color:{MUTED};font-size:.74rem;"
                             f"margin-top:.15rem'>{ui.esc(r['detail'])}{link}</div></div>")
                else:
                    body += f"• {ui.esc(r['detail'])}"
                html.append(body + "</div>")
        st.html("".join(html))


def _restated_html(text: str) -> str:
    return (f"<div style='color:{MUTED};font-size:.78rem;margin-bottom:.4rem'>"
            f"{text}</div>")


def _below(msg: dict) -> None:
    """What sits under the words: why a draft was replaced (below, so nothing above
    the words moves when it lands), the evidence, any warning, the footer."""
    if msg.get("replaced") is not None:
        st.caption(REPLACED[bool(msg["replaced"])])
    _evidence(msg)
    said = list(dict.fromkeys(plain for p in msg.get("problems", [])
                              for k, plain in EVIDENCE.items() if p.startswith(k)))
    if said:
        st.warning(VERIFY_WARNING + "; ".join(said) + ".", icon="⚠️")
    st.caption(msg.get("foot", ""))


def _render_answer(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])
        return
    # The same order the live answer fills: restatement, words, below.
    if msg.get("restated"):
        st.html(_restated_html(f"Understood as: {ui.esc(msg['restated'])}"))
    st.markdown(_escape_md(_prose(msg["text"])), unsafe_allow_html=False)
    _below(msg)


def _scroll_guard() -> None:
    """On this page only the reader, and `_bring_into_view`, move the page (the PM:
    "fast up and down oscillations, about 5-6 in under a sec").

    Why, read from Streamlit 1.64's own code: when a chat input is on the page, its
    scroll container checks every 17 ms whether the view has left the bottom and,
    34 ms later, animates it back down (`scrollTop = …` each frame) — always, on a
    first answer, because a page shorter than the window counts as "at the bottom".
    Every scroll made to keep an answer in place was undone 34 ms later, and re-made:
    the oscillation. Winning that fight is impossible; this ends it. The container's
    `scrollTop` setter ignores scripted scrolls while this page is open, so Streamlit's
    pull does nothing; the reader's own scrolling (wheel, touch, keys, the bar) does
    not go through that setter and is untouched. Leaving the page restores it."""
    components.html(r"""<script>
    const doc = window.parent.document, win = window.parent;
    // Ask AI is the front door (2026-09-27): it is also served at the app's root.
    const onAsk = () => /\/ask\/?$|^\/(?:~\/\+\/?)?$/.test(win.location.pathname);
    const guard = () => {
      const el = doc.querySelector('[data-testid="stAppScrollToBottomContainer"]');
      if (!el) { setTimeout(guard, 100); return; }
      if (el.__askGuard) return;
      const d = Object.getOwnPropertyDescriptor(Element.prototype, "scrollTop");
      Object.defineProperty(el, "scrollTop", {configurable: true,
        get() { return d.get.call(this); },
        set(v) { if (!onAsk() || win.__askOwnScroll) d.set.call(this, v); }});
      el.__askGuard = true;
    };
    guard();
    </script>""", height=0)


def _bring_into_view(margin: int = 72) -> None:
    """One scroll, when a new answer starts: the question just asked to the top of
    the window, so the answer is read from its first line as it streams. Then
    nothing moves until the reader scrolls."""
    components.html(f"""<script>
    const doc = window.parent.document, win = window.parent;
    const go = (tries) => {{
      const m = doc.querySelectorAll(".ask-a");
      const el = doc.querySelector('[data-testid="stAppScrollToBottomContainer"]');
      if (!m.length || !el) {{ if (tries < 30) setTimeout(() => go(tries + 1), 50); return; }}
      const msgs = [...doc.querySelectorAll('[data-testid="stChatMessage"]')];
      const ans = m[m.length - 1].closest('[data-testid="stChatMessage"]');
      const q = msgs[msgs.indexOf(ans) - 1] || ans;
      const dy = q.getBoundingClientRect().top - el.getBoundingClientRect().top - {margin};
      if (Math.abs(dy) < 4) return;
      win.__askOwnScroll = true;
      el.scrollTop = el.scrollTop + dy;
      win.__askOwnScroll = false;
    }};
    go(0);
    </script>""", height=0)


_scroll_guard()
thread = _active()


_YES = re.compile(r"^\s*(?:yes|yeah|yep|yup|sure|ok|okay|please|go ahead|do it|go on|y|yes please|"
                  r"sure thing|absolutely|of course)[\s.!,]*(?:please|thanks)?[\s.!]*$", re.I)
_OFFER = re.compile(r"^\s*(?:would you like|do you want|want|shall i|should i|can i)\s+(?:me\s+)?"
                    r"(?:to\s+)?", re.I)


def _take_up(q: str, messages: list) -> str:
    """"yes" to an answer's closing offer is that offer, asked (the PM, 2026-09-27: the
    answer ended "Want to see which words people tried first?", "yes" was sent, and the
    next answer did not show any words — "yes" had been read as a question of its own).
    "Want to see which words people tried first?" → "Show which words people tried first.";
    "Would you like me to list them by kind?" → "List them by kind."."""
    if not _YES.match(q or "") or not messages or messages[-1].get("role") != "assistant":
        return q
    lines = [ln.strip() for ln in str(messages[-1].get("text") or "").strip().splitlines()
             if ln.strip()]
    last = lines[-1].strip("*_ ") if lines else ""
    if not last.endswith("?"):
        return q
    rest = _OFFER.sub("", last).rstrip("?").strip()
    shown = re.sub(r"^(?:see|know|look at|show you|pull|pull together|get)\s+", "", rest,
                   flags=re.I)
    if not rest:
        return q
    return f"Show {shown}." if shown != rest else f"{rest[:1].upper()}{rest[1:]}."


def _accept(q: str) -> None:
    """A question is taken in on one run and answered on the NEXT (ask_v3). That
    instant run redraws the page in its final shape — the conversation with the
    question in it — before any word arrives. Answered on the same run, the words
    streamed in while the previous screen's leftover elements (the welcome block)
    were still on the page, and when the run ended Streamlit removed them all at
    once: the page shrank and the answer jumped (measured 95 px → 263 px)."""
    q = _take_up(q, thread["messages"])
    why = A.screen(q) or caps.blocked("ask")
    thread["messages"].append({"role": "user", "content": q})
    if thread["title"] == "New chat":
        thread["title"] = _title(q)
    if why:
        # A declined question is a turn like any other and stays in the thread.
        thread["messages"].append({"role": "assistant", "text": why, "restated": "",
                                   "refs": {}, "problems": [], "foot": ""})
    else:
        caps.record("ask")
        st.session_state["answering"] = thread["id"]
    st.rerun()


# ------------------------------------------------------------- transcript
if thread["messages"]:
    st.html(f"<div style='display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;"
            f"border-bottom:1px solid {HAIR};padding-bottom:.55rem;margin:0 0 1.1rem'>"
            f"<span style='font-size:.68rem;font-weight:800;letter-spacing:.18em;"
            f"color:{MUTED}'>ASK AI</span><span style='font-size:.78rem;color:{MUTED};"
            f"line-height:1.5'>based on <b>{CORE}</b> cases people described in public posts · "
            "the evidence sits under each answer · figures count <b>public posts</b>, not "
            "users or searches</span></div>")

for msg in thread["messages"]:
    with st.chat_message(msg["role"], avatar=AVATAR[msg["role"]]):
        if msg["role"] == "user":
            st.html(QUESTION_MARK)
            st.text(msg["content"])
        else:
            st.html(ANSWER_MARK)
            _render_answer(msg)

# ------------------------------------------------------------ the input, or the welcome
# Before the answer is written: the input is pinned to the window's bottom wherever it
# is drawn, and drawn AFTER a streamed answer it was the last thing the run added.
if thread["messages"]:
    typed = st.chat_input("Ask a follow-up…", key="ask_more")
    if typed:
        _accept(typed)
else:
    st.html("<div style='height:6vh'></div>")
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        st.html(f"<div style='text-align:center;margin:0 0 1.1rem'>"
                f"<div style='font-size:.68rem;font-weight:800;letter-spacing:.18em;"
                f"color:{MUTED}'>ASK AI</div>"
                f"<div style='font-size:1.9rem;font-weight:750;line-height:1.25;"
                f"margin-top:.3rem'>What can I help you with?</div></div>")
        with st.container():
            typed = st.chat_input("Ask anything about how people search for old photos…",
                                  key="ask_first")
        if typed:
            _accept(typed)
        st.html(f"<div style='color:{MUTED};font-size:.76rem;text-align:center;"
                f"margin:.9rem 0 .3rem'>or start with one of these</div>")
        for row in (SUGGESTED[:3], SUGGESTED[3:]):
            for col, (chip, q) in zip(st.columns(len(row)), row, strict=True):
                if col.button(chip, key=f"sugg{q[:18]}"):
                    _accept(q)


# ------------------------------------------------------------- a new answer
# Drawn where the next message goes, in the transcript's own slots, filled in place.
if st.session_state.get("answering") == thread["id"] and thread["messages"] \
        and thread["messages"][-1]["role"] == "user":
    st.session_state.pop("answering")          # never asked twice, even if this run fails
    question = thread["messages"][-1]["content"]
    msgs = thread["messages"][:-1]
    hist = [{"question": q["content"], "answer": a.get("text", "")}
            for q, a in zip(msgs[::2], msgs[1::2], strict=False)]
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        st.html(ANSWER_MARK)
        top, words, under = st.empty(), st.empty(), st.empty()
        top.html(_restated_html(f"{STAGE['plan']} · usually {TYPICAL}"))
        under.caption(STAGE["retrieve"])
        _bring_into_view()

        def show(so_far: str) -> None:
            words.markdown(_escape_md(P.reader_words(so_far)) + " ▌", unsafe_allow_html=False)

        a = A.ask(_client(key), db.connection(), question, history=hist, on_text=show,
                  on_restated=lambda r: top.html(_restated_html(f"Understood as: {ui.esc(r)}")),
                  progress=lambda s: under.caption(f"{STAGE[s]} · usually {TYPICAL}"))
        route = {"FULL": "full answer", "PARTIAL": "partial answer — it says what the evidence "
                 "cannot settle", "NONE": "outside what this study covers"}.get(a.route, a.route)
        msg = {"role": "assistant", "error": caps.explain(a.error) if a.error else "",
               "text": a.text, "restated": a.restated, "refs": _refs(a),
               "replaced": (a.withheld[0].startswith("the draft did not finish")
                            if a.withheld else None),
               "problems": a.report.problems() if a.report else [],
               "foot": (f"{'✓ checked' if a.verified else '⚠ not fully checked'} · {route} · "
                        f"{a.seconds:.0f}s")}
        if msg["error"]:
            top.empty()
            words.error(msg["error"])
            under.empty()
        else:
            words.markdown(_escape_md(_prose(msg["text"])), unsafe_allow_html=False)
            with under.container():
                _below(msg)
                st.html("<span class='ask-done' style='display:none'></span>")
    thread["messages"].append(msg)


# ---------------------------------------------------------------- sidebar
# Drawn LAST, so a chat started on this run is already in the list (no re-run
# after an answer, ask_v3); the sidebar's place on screen does not depend on order.
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
