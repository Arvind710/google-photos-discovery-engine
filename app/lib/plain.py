"""The translation layer: the engine's evidence in plain words, BEFORE any model
sees it (the PM, 2026-09-27: answers must be "extremely simple, precise and
unambiguous", with no internal words, and "nothing on the answer page should be
such that whose understanding depends on knowing the internal data").

Deterministic — no model call. Every retrieved row becomes ONE plain sentence
with a short tag: [F3] a fact, [S2] a post, [N1] a note on what the evidence
cannot show. The writer sees only these sentences and cites only these tags, so
it never meets a stage number, a question id, a table name or a codebook value
it could repeat. `Tags.expand()` turns tags back into the internal citations
the checker verifies and the page resolves into references.

Every number a sentence states is one its row holds — or is added to the row
here, under a plain key — so the per-paragraph number check still binds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from lib.evidence import COMPARABLE, FLOOR

ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ vocabulary
# Where a story first went wrong, as a clause after "the first thing that went wrong was that".
STAGE = {
    "0": "the photo was already gone — deleted, never backed up, or kept somewhere else",
    "1": "the post only says why they were looking",
    "2": "they could not remember enough about the photo to search for it",
    "3": "they never used the search box — they scrolled, or looked somewhere else",
    "4": "they remembered the photo but could not put it into words the search understood",
    "5": "the search did not understand what they typed, or showed the wrong photos",
    "6": "the photo was in the results, but hard to spot among similar ones",
    "7": "after a failed search, they could not find another way to it",
    "8": "they gave up",
    "9": "nothing went wrong — they found the photo",
    "10": "they changed how they keep photos afterwards",
}
KIND = {"sentimental": "photos kept as memories (people, trips, events)",
        "utility": "photos kept for the information in them (receipts, documents, notes)",
        "unclear": "photos whose post does not say why they were kept",
        "both": "photos kept both as memories and for the information in them"}
OUTCOME = {"found": "they found it straight away",
           "found_after_struggle": "they found it after a struggle",
           "substitute_accepted": "they settled for a similar photo",
           "abandoned_with_fallback": "they gave up and got it another way",
           "abandoned_without_fallback": "they gave up",
           "false_positive": "they picked the wrong photo",
           "found_later_by_accident": "they found it later by accident",
           "not_stated": "the post does not say how it ended"}
# Answer values whose code name does not read as English once "_" is a space.
VALUE = {
    "hard_filter_single_cue": "one wrong detail hid the photo",
    "and_logic_shrinks_recall": "adding more words made the photo disappear",
    "soft_ok": "a small mistake in a detail did not matter",
    "concept_not_modelled": "search does not know the idea they typed",
    "entities_misparsed": "search misread a name or thing they typed",
    "object_unrecognised": "search did not recognise the object",
    "text_not_ocrd": "search could not read the text in the photo",
    "unnamed_face": "the person's face had no name",
    "missing_location": "the photo had no location",
    "wrong_date": "the photo had the wrong date",
    "buried_below_fold": "the photo was far down the results",
    "crowded_by_near_duplicates": "near-identical photos crowded it out",
    "recency_bias": "newer photos were shown first",
    "clutter_ranked_above": "clutter was shown above it",
    "confident_wrong_ask_photos_answer": "Ask Photos confidently gave a wrong answer",
    "cant_find_it_message": "a message saying it could not find anything",
    "cross_cue_inference_needed_and_absent": "search could not link one clue to another",
    "cross_cue_inference_worked": "search linked one clue to another",
    "relative_time_unresolved": "search did not understand a time like last summer",
    "personal_reference_unresolved": "search did not understand a word like my mum",
    "place_name_misparsed": "search misread a place name",
    "negation_ignored": "search ignored a not or a without",
    "code_mixed_language_failed": "search failed on words from two languages",
    "parsed_ok": "search understood what they typed",
    "one_generic_cue_weak": "one common clue, too weak on its own",
    "several_weak_cues_combine": "several weak clues together",
    "one_highly_distinctive_cue": "one very distinctive clue",
    "false_negative_abandoned_reachable": "they gave up on a photo that was there to find",
    "false_positive_wrong_photo": "they settled on the wrong photo",
    "anchor_and_pivot": "they used a nearly-right photo to reach the right one",
    "meaning_not_visual": "what matters about it cannot be seen in the image",
    "text_heavy_ocr_dependent": "it is mostly text",
    "single_noun": "a single word", "named_entity": "a name",
    "code_mixed_misspelt_or_synonym": "mixed languages, a misspelling, or a different word",
    "first_screen_only": "only the first screen", "exhaustive": "all the way down",
    "yes_backed_up": "yes, it was backed up",
    "device_only_backup_off_or_folder_excluded": "only on the phone — backup was off, or the "
                                                 "folder was left out",
    "never_encoded": "they never took it in properly",
    "one_attempt": "one try", "few_attempts_minutes": "a few tries over some minutes",
    "many_attempts_under_hour": "many tries, under an hour", "hour_or_more": "an hour or more",
    "not_stated": "not said",
}
PREFIX = {"path": "found by", "decisive_cue": "the clue that found it", "why": "why they gave up",
          "fallback": "what they did instead", "aftermath": "afterwards",
          "urgency": "how urgent", "setting": "where they were", "date": "the date",
          "location": "the location", "faces": "faces", "organisation": "how it was kept"}
MEDIA = {"photo": "a photo", "screenshot": "a screenshot", "document": "a photo of a document",
         "video": "a video", "mixed": "photos and videos"}
FAMILY = {"who": "who was in it", "what": "what was in it", "where": "where it was taken",
          "when": "when it was taken", "event": "the event", "perceptual": "how it looked",
          "meaning": "what it meant to them", "capture": "why it was taken",
          "source": "where it came from", "library_position": "where it sat in their library",
          "_all": "a detail"}
# "In 31 of 115 stories (27%) ABOUT …"
POP = {"core": "about a photo the person only vaguely remembered",
       "adjacent": "about a photo the person knew exactly, or one already gone"}
SOURCE = {"x": "X (Twitter)", "youtube": "YouTube comments", "reddit": "Reddit",
          "hackernews": "Hacker News", "quora": "Quora",
          "gp_help": "the Google Photos help forum", "appstore": "App Store reviews",
          "play": "Google Play reviews", "stackexchange": "Stack Exchange"}
THEME = {"search_refuses_sensitive_terms": "the search refused a word it treated as sensitive",
         "auto_creation_lost": "a collage or memory video the app made could not be found again",
         "no_album_scoped_search": "they could not search inside one album",
         "looked_in_other_photo_app": "they looked in another photo app or service"}
FIELD = {"primary_stage": "where a story first went wrong",
         "photo_class": "why the photo was kept", "media_type": "what kind of image it was",
         "outcome": "how the search ended", "failure_owner": "what caused the problem",
         "metric_node": "which part of finding a photo broke",
         "severity": "how serious the problem was"}
# The registered method flags, in plain words. A number is never written here:
# `{0}`, `{1}`… are the numbers of the flag's own stored text, in order, filled by
# `flag()` — so a re-published corpus cannot leave a stale count in an answer,
# and the number check (which reads that row) always holds.
FLAG = {
    "proxy_not_success_rate": "Every figure counts stories people chose to post in public. It "
                              "is not a success rate, and not a share of Google Photos users "
                              "or of searches.",
    "public_selection_bias": "People mostly post when something goes wrong, so quiet successes "
                             "are missing from these stories.",
    "thin_core": "There are {0} stories about a vaguely remembered photo, fewer than the {1} "
                 "planned. A figure about fewer than {2} stories is given as a count only; one "
                 "about {3} to {4} stories is marked as only a rough guide.",
    "stage5_inferred": "What the search did is worked out from what people wrote. Nobody "
                       "outside Google can see why a search missed.",
    "no_gold_standard": "No person checked how the stories were read. Two AI models read them "
                        "separately; their agreeing shows they were consistent, not that they "
                        "were right.",
    "low_reliability_fields": "On some details — how a search ended, how serious it was, how "
                              "many tries people made, and several more — the two AI readers "
                              "agreed too rarely to rely on them.",
    "interview_register": "{0} of the {1} questions asked of every story are answered by too "
                          "few posts, so they are left for interviews with real users.",
    "adjacent_apart": "{0} other stories — where the person knew exactly which photo they "
                      "wanted, or it was already gone — are counted separately.",
    "missing_cuts": "The posts say nothing reliable about age, gender, country, phone type or "
                    "dates, and do not compare other photo apps, so no split by any of these "
                    "is possible.",
    "emerging_themes": "Four patterns noticed after the study was designed are only counted, "
                       "never ranked.",
}


def flag(key: str, stored: str = "") -> str | None:
    """A method flag in plain words, its numbers taken in order from the flag's
    stored text. None when the stored text no longer carries the numbers the
    template needs — the flag is then left out rather than shown wrong."""
    t = FLAG.get(key)
    if t is None:
        return None
    try:
        return t.format(*re.findall(r"\d+(?:\.\d+)?", stored or ""))
    except IndexError:
        return None


@cache
def _questions() -> dict[str, str]:
    cb = yaml.safe_load((ROOT / "codebook" / "journey_v1.yaml").read_text())
    return {q["id"]: q["plain"] for s in cb["stages"] for q in s["questions"]}


_ASKING = ("what", "why", "whether", "how", "which", "whose", "when", "where", "who")


def question(qid) -> str:
    """A codebook question's meaning, lower-case (a name keeps its capital) and
    without its full stop. Three meanings are statements ("The system discarded
    the photo because one detail was wrong"); they read as "whether …", or "say
    anything about the system discarded the photo" is not a sentence (v2.7: R2)."""
    q = _questions().get(str(qid), "").rstrip(". ")
    if not q.startswith("Google"):
        q = q[:1].lower() + q[1:]
    if q and q.split()[0].lower() not in _ASKING:
        q = f"whether {q}"
    return q


def words(slug) -> str:
    """A codebook value in words: "when:year" → "when it was taken (year)"."""
    s = str(slug)
    if s.startswith("other:"):
        return s[6:].replace("_", " ")
    if s in VALUE:
        return VALUE[s]
    fam, _, rest = s.partition(":")
    if rest and fam in FAMILY:
        return f"{FAMILY[fam]} ({VALUE.get(rest, rest.replace('_', ' '))})"
    if rest and fam in PREFIX:
        return f"{PREFIX[fam]} — {VALUE.get(rest, rest.replace('_', ' '))}"
    return s.replace("_", " ").replace(":", " — ")


def kind(group) -> str:
    return KIND.get(str(group), f"{words(group)} photos")


def among(by: str, group) -> str:
    """A cross-tab's group in words, by what it groups on: a source split read
    "among x photos" when every group was taken for a kind of photo (v2.7: P3)."""
    if by == "source":
        return f"among posts on {SOURCE.get(str(group), words(group))}"
    if by == "outcome":
        return f"among stories where {OUTCOME.get(str(group), 'the end was: ' + words(group))}"
    return f"among {kind(group)}"


def about(group) -> str:
    """"about photos kept as memories", or "from posts on Hacker News" for a
    source group — never "about hackernews photos"."""
    g = str(group)
    return f"from posts on {SOURCE[g]}" if g in SOURCE else f"about {kind(g)}"


def count(n: int, d: int, unit: str = "stories") -> str:
    """[CTX] §15.5 in plain words: "6 of 21 stories" below 30; "13 of 48 stories
    (27%)" at 30 and above. The percentage is the one share() prints."""
    if d < FLOOR:
        return f"{n} of {d} {unit}"
    return f"{n} of {d} {unit} ({round(100 * n / d)}%)"


ROUGH = "rough guide"


def rough(d: int) -> str:
    """The 30–79 label, said plainly — the checker accepts it in place of
    "directional" when it sits in the same sentence as the share."""
    return f" — a small group, so only a {ROUGH}" if FLOOR <= d < COMPARABLE else ""


# ------------------------------------------------------------- one row → words
def _crosstab(key: str, r: dict) -> str | None:
    m = re.fullmatch(r"(core|adjacent)\.([^=]+)=(.+)@([^:]+):(.+)", key)
    if not m:
        return None
    pop, dim, val, by, group = m.groups()
    n, d = int(r.get("stories", 0)), int(r.get("of", 0))
    about = POP[pop] if group == "_all" else f"{POP[pop]}, {among(by, group)}"
    head = f"In {count(n, d)} {about}"
    tail = rough(d) + "."
    if dim == "primary_stage" and val == "9":
        return f"{head}, nothing went wrong — they found the photo{tail}"
    if dim == "primary_stage" and val == "1":
        return f"{head}, the post only says why they were looking, not what went wrong{tail}"
    if dim == "primary_stage":
        return f"{head}, the first thing that went wrong was that {STAGE.get(val, val)}{tail}"
    if dim == "photo_class":
        return f"{head}, the photo was one of the {kind(val)}{tail}"
    if dim == "outcome":
        return f"{head}, {OUTCOME.get(val, 'the end was: ' + words(val))}{tail}"
    if dim == "media_type":
        return f"{head}, what they wanted was {MEDIA.get(val, words(val))}{tail}"
    if dim == "source":
        return f"{head}, the post was on {SOURCE.get(val, val)}{tail}"
    if dim == "failure_owner":
        from lib import words as W
        return f"{head}, the cause was this: {W.owner(val).lower()}{tail}"
    if dim.startswith("q:"):
        return f"{head}, on {question(dim[2:])}, the post says: {words(val)}{tail}"
    return None                           # metric_node: low reliability, and no plain idea


def _derived(key: str, r: dict) -> str | None:
    metric, which, pop = (key.split(":") + ["", ""])[:3]
    if metric == "js_divergence":
        return None
    n, d = int(r.get("stories", 0)), int(r.get("of", 0))
    if n == 0:
        return None                       # "0 of 115" answers nothing and crowds the brief
    head = f"In {count(n, d)} {POP.get(pop, '')}".rstrip()
    fam = FAMILY.get(which, words(which))
    body = {"cue_remembered": f"they remembered {fam}",
            "cue_forgotten": f"they had forgotten {fam}",
            "cue_wrong": f"they were sure of {fam} and turned out to be wrong",
            "certain_wrong": "they were sure of a detail that turned out to be wrong",
            "results_as_cues": "the search results reminded them of something new",
            "anchor_and_pivot": "they used a nearly-right photo to reach the right one",
            "workaround": "they got the photo, or what was in it, some other way",
            "fallback": f"after giving up, they turned to {which.replace('_', ' ')}",
            "preventive_habit": "they changed how they keep photos afterwards",
            }.get(metric)
    return f"{head}, {body}{rough(d)}." if body else None


def sentence(r: dict) -> str | None:
    """One plain sentence for one retrieved row, or None when the row has no
    plain form (it is then not shown to the writer at all)."""
    c = r.get("_cite") or {}
    t, k = c.get("table"), str(c.get("key", ""))
    if t == "analysis_crosstab":
        return _crosstab(k, r)
    if t == "analysis_derived":
        return _derived(k, r)
    if t == "analysis_funnel":
        n, a = int(r.get("n") or 0), int(r.get("n_authors") or 0)
        return {"collected": f"{n:,} public posts, reviews and comments were read, written by "
                             f"{a:,} people.",
                "kept": f"{n:,} of those posts were about trying to find a photo.",
                "stories": f"They hold {n} stories of someone trying to find a photo, told by "
                           f"{a} people.",
                "stories:core": f"{n} of those stories, told by {a} people, are about a photo "
                                "the person only vaguely remembered — the stories most answers "
                                "here rest on.",
                "stories:adjacent": f"{n} stories are about a photo the person knew exactly, "
                                    "or one already gone; they are counted separately."
                }.get(str(r.get("step")))
    if t == "analysis_sources":
        return (f"{int(r.get('n_records') or 0):,} posts came from "
                f"{SOURCE.get(r.get('source'), r.get('source'))}.")
    if t == "analysis_coverage":
        r["stories_asked"] = int(r.get("n_coded") or 0) + int(r.get("n_not_stated") or 0)
        few = "Only " if r.get("disposition") == "register" else ""
        return (f"{few}{r.get('n_coded')} of {r['stories_asked']} stories say anything about "
                f"{question(r.get('question'))}.")
    if t == "analysis_reliability":
        f = str(r.get("field", ""))
        what = FIELD.get(f) or question(f[2:])
        n = int(r.get("n") or 0)
        r["stories_agreed"] = round(float(r.get("raw_agreement") or 0) * n)
        tail = (" — too rarely to rely on it." if r.get("verdict") == "low_reliability"
                else ".")
        return (f"Two AI readers went through {n} stories separately and agreed on {what} in "
                f"{r['stories_agreed']} of them{tail}")
    if t == "analysis_method_flags":
        return flag(k, r.get("text", ""))
    if t == "analysis_opportunity":
        d, n = int(r.get("of") or 0), int(r.get("core_stories") or 0)
        if d >= FLOOR:
            r["percent"] = round(100 * n / d)                    # the one count() prints
        label = str(r.get("label", "")).rstrip(".")
        status = {"ranked": " It is the one problem with enough stories to rank.",
                  "below_floor": " Too few stories to rank it.",
                  "gated_out": " Better search could not fix it."}.get(r.get("status"), "")
        return (f"The problem — {label[:1].lower() + label[1:]} — comes up in "
                f"{count(n, d)} about a vaguely remembered photo, "
                f"from {r.get('people')} people{rough(d)}.{status}")
    if t == "analysis_weight_sensitivity":
        draws = int(r.get("draws") or 0)
        r["times_first"] = round(float(r.get("top_share") or 0) * draws)
        cand = str(r.get("candidate_id", ""))
        what = STAGE.get(cand.removeprefix("stage"), words(cand))
        return (f"When the problems were re-scored {draws:,} times with different weights, "
                f"the problem where {what} came first {r['times_first']:,} times.")
    if t == "analysis_synthesis":
        return "The engine's suggestion, an idea to test in interviews: " + desnake(r.get("text"))
    if t == "story_themes":
        return (f"{r.get('stories')} stories say that "
                f"{THEME.get(str(r.get('theme')), words(r.get('theme')))} (a pattern noticed "
                "after the study was designed, so only counted).")
    return None


# ------------------------------------------------------------------- jargon
# Words a reader who knows nothing of the project cannot read. The translation
# layer never shows them to the writer; `check_jargon` catches any that come
# back (absolute: the draft is replaced), and `scrub` rewrites stored text that
# has a plain equivalent.
JARGON = re.compile(
    r"\b(?:[Ss]tages?\s+\d+|[Cc]ore|[Aa]djacent|[Cc]orpus|[Cc]oded|[Cc]odebook|[Cc]oders?|"
    r"[Cc]ohort|[Dd]ataset|[Dd]irectional|[Kk]appa|[Mm]etric nodes?|[Pp]roxy|[Gg]ated|[Cc]rosstab|"
    r"[Rr]etrieval stor(?:y|ies)|[Uu]tility (?:photos?|stories)|"
    r"(?:[Qq]uestion|[Qq])\s*\d+\.\d+|FULL|PARTIAL|NONE)\b|κ|\[\s*[FSN]\d+\b(?:\s*\])?")


def check_jargon(text: str) -> list[str]:
    """Internal words in the answer's own words. A quote is the poster's, and a
    citation is machinery the page turns into a number; an unexpanded tag
    ("[F9]", never retrieved) is caught here too."""
    from lib.verify import CITATION, QUOTE
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    return sorted({m.group(0) if m.group(0).isupper() else m.group(0).lower()
                   for m in JARGON.finditer(t)})


_SCRUB = [(re.compile(r"\s*\((?:[Ss]tages?|[Qq]uestions?) [\d.,–and ]+\)"), ""),
          (re.compile(r"\b[Ss]tage (\d+)\b"),
           lambda m: f"the step where {STAGE.get(m.group(1), 'it went wrong')}"),
          (re.compile(r"\bcore stories\b", re.I), "stories about a vaguely remembered photo"),
          (re.compile(r"\bcoded (?:public )?stories\b", re.I), "stories people posted"),
          (re.compile(r"\bthe corpus\b", re.I), "the stories"),
          (re.compile(r"\bcorpus\b", re.I), "stories"),
          (re.compile(r"\bcoders\b", re.I), "readers"),
          (re.compile(r"\bstage(\d+)\b"), lambda m: STAGE.get(m.group(1), "that step")),
          (re.compile(r"\butility\b", re.I), "practical"),
          (re.compile(r"\bcore\b", re.I), "main"),
          (re.compile(r"\bdirectional\b", re.I), "only a rough guide"),
          (re.compile(r"\bfailure modes?\b", re.I), "way it goes wrong"),
          (re.compile(r"\bretrieval\b", re.I), "finding the photo"),
          (re.compile(r"\bstages\b", re.I), "steps"),
          (re.compile(r"\bstage\b", re.I), "step")]


def scrub(text) -> str:
    """Stored text (a recommendation, the planner's restatement) in plain words."""
    text = str(text or "")
    for pat, rep in _SCRUB:
        text = pat.sub(rep, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_CODE_WORDS = {"below_floor": "too few stories to rank", "not_a_failure": "not a failure",
               "gated_out": "not something better search could fix"}


def desnake(text) -> str:
    """Model-written stored text (the recommendation) in plain words: its code
    names spelled out, its labels and brackets dropped."""
    t = scrub(re.sub(r"(?:^|(?<=[.;—]\s))[Mm]etric node:\s*[a-z_]+\s*—\s*", "", str(text or "")))
    t = re.sub(r"\b[a-z]+(?:_[a-z]+)+\b",
               lambda m: _CODE_WORDS.get(m.group(0), m.group(0).replace("_", " ")), t)
    t = re.sub(r"\[([^\]]+)\]", r"\1", t)
    return re.sub(r"\bmetric\b", "measure", t)


# ------------------------------------------------------------ reader words
# "Stories" is the study's word for one person's account of hunting for one
# photo; a reader does not know it (the PM, 2026-09-27: "do you think people
# would understand it?"). Everything a reader sees says "cases" instead.
_STORY_WORD = [(re.compile(r"\bStories\b"), "Cases"), (re.compile(r"\bstories\b"), "cases"),
               (re.compile(r"\bStory\b"), "Case"), (re.compile(r"\bstory\b"), "case"),
               # v3.0's writer said "the dataset" in 13 of 24 drafts; to a reader it is
               # the evidence (and "dataset" is an internal word to the checker).
               (re.compile(r"\bThe data ?set\b"), "The evidence"),
               (re.compile(r"\bthe data ?set\b"), "the evidence"),
               (re.compile(r"\b(?:This|Our) data ?set\b"), "This evidence"),
               (re.compile(r"\b(?:this|our) data ?set\b"), "this evidence"),
               (re.compile(r"\bdata ?sets?\b"), "evidence"),
               (re.compile(r"\b[Cc]oded (cases|posts)\b"), r"\1"),
               (re.compile(r"\bcoded\b"), "read"), (re.compile(r"\bCoded\b"), "Read"),
               (re.compile(r"\bcoders\b"), "readers"), (re.compile(r"\bcoder\b"), "reader"),
               (re.compile(r"\b(?:as |only )?directional\b"), "only a rough guide")]


def reader_words(text: str) -> str:
    """"stories" → "cases" in the text's own words — never inside a quotation (a
    poster's words) or a citation (machinery)."""
    from lib.verify import CITATION, QUOTE
    t = text or ""
    keep: list[str] = []

    def hide(m):
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"
    t = QUOTE.sub(hide, CITATION.sub(hide, t))
    for pat, rep in _STORY_WORD:
        t = pat.sub(rep, t)
    while "\x00" in t:
        t = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], t)
    return t


def unquote_terms(text: str, records: list[dict], rows: list[dict]) -> str:
    """Formatting only (ask_v3): quotation marks around one of the study's own
    category names — "adding more words made the photo disappear" — make it read
    as someone's words. They are removed, unless a retrieved post really says it."""
    from lib.verify import QUOTE, _norm
    names = {_norm(v) for d in (STAGE, VALUE, OUTCOME, FAMILY) for v in d.values()}
    for r in rows or []:
        k = str((r.get("_cite") or {}).get("key", ""))
        m = re.fullmatch(r"(?:core|adjacent)\.[^=]+=(.+)@.+", k)
        if m:
            names.add(_norm(words(m.group(1))))
    said = " ".join(_norm(x.get("text", "")) for x in records or [])

    def fix(m):
        q = _norm(m.group(1)).strip(" .,;:!?…")
        # Whole or in part ("did not understand what they typed, or showed the wrong
        # photos" is the end of a category name, v3.1 P2).
        hit = q in names or (len(q.split()) >= 4 and any(q in n for n in names))
        return m.group(1) if hit and q not in said else m.group(0)
    return QUOTE.sub(fix, text or "")


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven "
                                    "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
                                    "nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty "
                                         "ninety".split()) if w != "_"}
_NUMBER_WORD = re.compile(
    r"\b((?:" + "|".join(_TENS) + r")(?:[-\s](?:" + "|".join(list(_UNITS)[1:10]) + r"))?|"
    r"(?:" + "|".join(list(_UNITS)[6:]) + r"))\b(?=\s+(?:of|cases?|people|posts?|stories|reports?|"
    r"said|say|describe))", re.I)


def number_words(text: str) -> str:
    """"Thirty-one of the 115 cases" → "31 of the 115 cases" (v3.7, N2), so a count
    written in words is checked like any number. Only counts of 6 and up — 1 to 5
    are small quantifiers the checker lets pass anyway — and never a proportion
    ("one in six" is left alone: "six" there is followed by "cases" only after "in")."""
    from lib.verify import QUOTE

    def val(w: str) -> int:
        parts = re.split(r"[-\s]", w.lower())
        return sum(_TENS.get(x, _UNITS.get(x, 0)) for x in parts)

    def fix(m):
        if re.search(r"\bin\s+$", m.string[max(0, m.start() - 4):m.start()], re.I):
            return m.group(0)                                 # "one in six cases"
        return str(val(m.group(1)))
    keep: list[str] = []

    def hide(m):
        keep.append(m.group(0))
        return f"\x01{len(keep) - 1}\x01"
    t = _NUMBER_WORD.sub(fix, QUOTE.sub(hide, text or ""))
    return re.sub(r"\x01(\d+)\x01", lambda m: keep[int(m.group(1))], t)


# A share in words: what the writer says instead of "31 of 115 stories (27%)"
# (the PM, 2026-09-27: "constantly quoting the number of stories would make a bad
# impression"). The checker holds every such phrase to the share it cites
# (verify.check_proportions), with PROPORTION_TOLERANCE either side.
PROPORTIONS = [(0.05, "one in twenty"), (0.10, "one in ten"), (0.125, "one in eight"),
               (1 / 6, "one in six"), (0.20, "one in five"), (0.25, "a quarter"),
               (1 / 3, "a third"), (0.40, "two in five"), (0.50, "half"),
               (0.60, "three in five"), (2 / 3, "two-thirds"), (0.75, "three-quarters"),
               (0.80, "four in five"), (0.90, "nine in ten")]
PROPORTION_TOLERANCE = 0.05


def in_words(n: int, d: int) -> str | None:
    """"about a quarter" for 31 of 115; None below the floor, where a share is not
    given at all ([CTX] §15.5), or when nothing is near enough."""
    if not d or d < FLOOR:
        return None
    v = n / d
    if v < 0.03:
        return "only a handful"
    best = min(PROPORTIONS, key=lambda x: abs(x[0] - v))
    return f"about {best[1]}" if abs(best[0] - v) <= PROPORTION_TOLERANCE else None


def _share_of(r: dict) -> tuple[int, int] | None:
    n = r.get("stories", r.get("core_stories"))
    d = r.get("of")
    return (int(n), int(d)) if isinstance(n, int) and isinstance(d, int) and d else None


# ------------------------------------------------------------------- tags
_TAG = re.compile(r"\[\s*([FSN]\d+(?:\s*(?:,|;|/|&|and)\s*[FSN]?\d+)*)\s*\]")
_ONE = re.compile(r"([FSN])?(\d+)")
_PARTIAL = re.compile(r"\[[FSN]?[\d,\s FSN]{0,12}$")          # a tag still arriving
# A quote written INSIDE the tag ("[S1 “returned way too many images”]", v2.8: L1)
# is the quote followed by its tag; the quote is then checked like any other.
_LOOSE_TAG = re.compile(r"\[\s*[FSN]\d+[^\[\]\n]{0,40}\]")
_QUOTED_TAG = re.compile(r"\[\s*([FSN]\d+)\s*[:,—–-]?\s*(“[^”\]]*”|\"[^\"\]]*\")\s*\]")


def untangle(text: str) -> str:
    return _QUOTED_TAG.sub(r"\2 [\1]", text or "")


@dataclass
class Tags:
    """[F3] / [S2] / [N1] ↔ the internal citation, for one answer."""
    to_cite: dict[str, str] = field(default_factory=dict)       # "F3" → "[[table|key]]"
    lines: dict[str, list[str]] = field(default_factory=lambda: {"F": [], "S": [], "N": []})

    def add(self, kind_: str, cite: str, line: str) -> str:
        tag = f"{kind_}{len(self.lines[kind_]) + 1}"
        self.to_cite[tag] = cite
        self.lines[kind_].append(f"[{tag}] {line}")
        return tag

    def expand(self, text: str) -> str:
        """[F3] and [F3, S1] → [[table|key]]… for the checker and the page. A tag
        that was never given ("[F34]" with 30 facts, v3.2 R1), or a bracket of tags
        in a form the pattern does not know ("[F1–F14]"), is dropped: citations are
        not shown to the reader any more (ask_v3), and every number in that paragraph
        is still held to the rows its other tags name — or to every retrieved row."""
        def one(m):
            out, last = [], "F"
            for k, n in _ONE.findall(m.group(1)):
                last = k or last
                out.append(self.to_cite.get(f"{last}{n}", ""))
            return "".join(out)
        t = _TAG.sub(one, untangle(text))
        return _LOOSE_TAG.sub(lambda m: "".join(
            self.to_cite.get(f"{k}{n}", "") for k, n in re.findall(r"([FSN])(\d+)", m.group(0))), t)


def visible(text: str) -> str:
    """What the page shows WHILE the draft streams: the words, without tags."""
    t = _PARTIAL.sub("", _TAG.sub("", untangle(text)))
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"[ \t]+([.,;:!?])", r"\1", t))


def build(got, *, story_chars: int = 600, max_facts: int = 30) -> Tags:
    """Every retrieved row and post, tagged, in plain words."""
    from lib import verify as V
    tags = Tags()
    seen: set[str] = set()
    method = got.method
    for r in (got.facts[:max_facts] + got.counter.get("rivals", []) + method.get("coverage", [])
              + method.get("reliability", []) + method.get("totals", [])):
        c = r.get("_cite") or {}
        cite = f"[[{c.get('table')}|{c.get('key')}]]"
        s = sentence(r)
        if s and cite not in seen:
            seen.add(cite)
            nd = _share_of(r)
            if nd and nd[1] < FLOOR:
                s += " (≈ counts only)"
            elif nd and in_words(*nd):
                s += f" (≈ {in_words(*nd)})"
            tags.add("F", cite, reader_words(s))
    for r in method.get("flags", []):
        s = sentence(r)
        if s:
            tags.add("N", f"[[{r['_cite']['table']}|{r['_cite']['key']}]]", reader_words(s))
    for s in got.records():
        where = SOURCE.get(s.get("source"), s.get("source"))
        body = s["text"].replace(" …[cut]", "")
        body = body if len(body) <= story_chars else body[:story_chars] + " …"
        tags.add("S", f"[[story|{s['story_id']}]]",
                 f"A post on {where}:\n{V.FENCE_OPEN} >>>\n{V.fence(body)}\n{V.FENCE_CLOSE}")
    return tags
