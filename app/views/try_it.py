"""Try it — paste a post and watch the pipeline find, confirm and code the
retrieval story in it ([CTX] §15.6). Or pick a story from the corpus and see its
stored coding, which costs nothing. Every quote shown was found verbatim in the
text; nothing is written back.
"""


import streamlit as st

from lib import caps, db, tryit, ui, words
from lib.evidence import share

SAMPLE = ("I remember a pic of a small café in Goa from a trip, no idea which year. Searched "
          "'cafe goa' and it showed nothing, then 'goa restaurant' and got hundreds of beach "
          "photos. Ended up scrolling 2019 and 2020 for half an hour and gave up.")

st.title("Try it")
st.html(f"<div style='color:{ui.MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;max-width:72ch;"
        f"line-height:1.55'>Paste a post about trying to find a photo, and the same pipeline "
        f"that coded the corpus runs on it: one model finds the story, a stronger one checks "
        f"it against the definitions, and a third pass codes it against the 60 questions — "
        f"every quote located in your text or thrown away.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

# =========================================================== live
ui.section(1, "Run it on a post", "Paste the text itself. Links are not fetched: most of the "
           "platforms involved disallow automated access (see the Data Bank).", ui.BLUE,
           slug="live")
key = caps.api_key()
text = st.text_area("Post text", value=st.session_state.get("tryit_text", ""), height=140,
                    max_chars=tryit.MAX_CHARS, placeholder=SAMPLE)
c1, c2 = st.columns([1, 3])
if c2.button("Use the sample"):
    st.session_state["tryit_text"] = SAMPLE
    st.rerun()
go = c1.button("Run the pipeline", type="primary", disabled=not key)
if not key:
    ui.note("The live run is not switched on for this deployment (no API key). Part 2 below "
            "works without it.")
if go:
    why = (None if len(text.strip()) >= 30 else "Paste at least a sentence or two.") \
        or caps.blocked("try")
    if why:
        st.info(why)
    else:
        caps.record("try")
        from openai import OpenAI
        with st.spinner("Finding, confirming and coding — about half a minute…"):
            st.session_state["trace"] = tryit.run(OpenAI(api_key=key, timeout=120,
                                                         max_retries=1), text.strip())

tr = st.session_state.get("trace")
if tr:
    if tr.error:
        st.error(caps.explain(tr.error))
    for i, s in enumerate(tr.stories, 1):
        verdict = ("kept" if s["is_story"] else "rejected by the checking model")
        st.html(ui.card(
            f"<div style='font-size:.7rem;font-weight:700;letter-spacing:.08em;color:{ui.MUTED}'>"
            f"STEP 1–2 · STORY {i} · {ui.esc(verdict.upper())}</div>"
            f"<div style='font-size:.9rem;margin:.3rem 0'>“{ui.esc(s['text'])}”</div>"
            f"<div style='font-size:.82rem'>Bucket <b>{ui.esc(s['bucket'])}</b> · reaches stage "
            f"{s['reaches_stage']} · finder's confidence {s['confidence']:.2f}</div>"
            f"<div style='font-size:.8rem;color:{ui.MUTED}'>Finder: {ui.esc(s['finder_reason'])}"
            f" · Checker: {ui.esc(s['confirm_reason'])}</div>",
            ui.GREEN if s["is_story"] else ui.GREY, dim=not s["is_story"]))
    for n in tr.notes:
        ui.note(ui.esc(n))
    if tr.coded:
        c, sp = tr.coded, tr.coded["spine"]
        st.html(ui.card(
            f"<div style='font-size:.7rem;font-weight:700;letter-spacing:.08em;color:{ui.MUTED}'>"
            f"STEP 3 · CODED AGAINST {c['asked']} QUESTIONS (BLOCKS {'+'.join(c['blocks'])})</div>"
            f"<div style='font-size:1rem;font-weight:700;margin:.3rem 0'>First went wrong at "
            f"Stage {sp['primary_stage']} — {ui.esc(words.stage_title(sp['primary_stage']))}</div>"
            f"<div style='font-size:.85rem'>{ui.esc(words.owner(sp['failure_owner']))} · photo: "
            f"{ui.esc(sp['photo_class'])}, {ui.esc(sp['media_type'])} · outcome: "
            f"{ui.esc(sp['outcome'])} · severity {sp['severity']}</div>"
            f"<div style='font-size:.82rem;color:{ui.MUTED};margin-top:.2rem'>Why: "
            f"{ui.esc(sp['why'])}</div>"
            + "".join(ui.quote(v, f"evidence for {k}") for k, v in c["evidence"].items()),
            ui.BLUE))
        rows = "".join(f"<tr><td style='padding:.15rem .6rem .15rem 0;color:{ui.MUTED}'>{q}</td>"
                       f"<td style='padding:.15rem 0'>{ui.esc(', '.join(v))}</td></tr>"
                       for q, v in c["codes"].items())
        st.html(f"<table style='font-size:.84rem'>{rows}</table>")
        ui.note(f"Questions the story does not speak to are coded 'not stated' and not shown. "
                f"{c['dropped_quotes']} quote(s) the coder offered could not be found in the text "
                f"and were dropped, as in the corpus. Stage 5 answers are inferred from what the "
                f"person says.")
        ui.verdict(f"In the corpus this story would join <b>Analysis Part 1</b> at Stage "
                   f"{sp['primary_stage']}, <b>Part 2</b> under {ui.esc(sp['photo_class'])} "
                   f"photos, and the <b>Stage {sp['primary_stage']} opportunity card</b>.",
                   ui.BLUE)
    ui.note(f"This run: {tr.seconds:.0f}s. {caps.left('try')} runs left in this visit.")

# =========================================================== stored
ui.section(2, "Or read a story the engine already coded", "Free, and exactly what the corpus "
           "holds: the story, its coding, and the quote behind each code.", ui.GREEN,
           slug="stored")
pick = db.query("SELECT p.story_id, p.primary_stage, p.photo_class, substr(s.text,1,80) AS head"
                " FROM story_spine p JOIN stories s USING (story_id) WHERE s.bucket='core'"
                " AND s.story_id NOT IN (SELECT story_id FROM exclusions WHERE story_id IS NOT"
                " NULL) ORDER BY p.coding_conf DESC, p.story_id LIMIT 40")
if not pick.empty:
    sid = st.selectbox("Story", pick["story_id"].tolist(),
                       format_func=lambda x: (lambda r: f"Stage {r['primary_stage']} · "
                                              f"{r['photo_class']} · {r['head']}…")(
                           pick[pick["story_id"] == x].iloc[0]))
    s = db.query("SELECT s.text, r.source, p.* FROM stories s JOIN records r USING (record_id)"
                 " JOIN story_spine p USING (story_id) WHERE s.story_id=?", (sid,)).iloc[0]
    ev = db.query("SELECT field, span FROM evidence WHERE story_id=?", (sid,))
    cd = db.query("SELECT question, group_concat(value, ', ') AS v FROM story_codes WHERE"
                  " story_id=? AND value<>'not_stated' AND question<>'10.3' GROUP BY question",
                  (sid,))
    st.html(ui.card(
        f"<div style='font-size:.9rem;margin-bottom:.4rem'>“{ui.esc(s['text'][:900])}”</div>"
        f"<div style='font-size:.8rem;color:{ui.MUTED}'>{ui.esc(words.source(s['source']))}"
        f"</div><div style='font-size:.95rem;font-weight:700;margin:.4rem 0 .2rem'>Stage "
        f"{s['primary_stage']} — {ui.esc(words.stage_title(s['primary_stage']))}</div>"
        f"<div style='font-size:.84rem'>{ui.esc(words.owner(s['failure_owner']))} · "
        f"{ui.esc(s['photo_class'])} · outcome {ui.esc(s['outcome'])} · coding confidence "
        f"{s['coding_conf']:.1f}</div><div style='font-size:.8rem;color:{ui.MUTED}'>Why: "
        f"{ui.esc(s['why'])}</div>"
        + "".join(ui.quote(sp_, f"evidence for {f}") for f, sp_ in zip(ev["field"], ev["span"],
                                                                         strict=True)),
        ui.GREEN))
    st.html("<table style='font-size:.84rem'>" + "".join(
        f"<tr><td style='padding:.15rem .6rem .15rem 0;color:{ui.MUTED}'>{q}</td><td>"
        f"{ui.esc(v)}</td></tr>" for q, v in zip(cd["question"], cd["v"], strict=True))
        + "</table>")
    n_core = int(db.query("SELECT n FROM analysis_funnel WHERE source='_all' AND"
                          " step='stories:core'").iloc[0]["n"])
    ui.note(f"One of {n_core} core stories; {share(len(cd), 60).text} of the codebook's questions "
            f"have an answer for it.")
