"""Ask AI, step 5 — the checker. Post-generation checks in Python, not requests
in a prompt: "rules backed by the checker hold; rules living only in the prompt
drift" (architecture.md §7, AR-9). Ported from the Myntra engine's verifier, with
this project's rules added:

    numbers        every number the answer asserts appears in a retrieved row
                   (T-14, absolute). Stage numbers, question ids and years are
                   structure, not claims.
    percentages    a % sits beside its "n of N" ([CTX] §15.5: never a percentage
                   without its denominator)
    quotes         every quotation of 3+ words is found in a retrieved story or row
    citations      every [[table|key]] was actually retrieved
    uncited        every claim carries a citation or opens `Interpretation:`
    proxy          no share of stories stated as a success rate, a share of users or
                   of searches (T-16 = 0)
    label-colon    no sentence opens with a short label and a colon, except
                   `Interpretation:` (T-17 = 0, EC-ASK-8 — shipped from day one)
    closing        a non-refusal ends with one italic question
    refusal        a NONE answer states no number, quotes nothing and cites nothing
    evidence       FULL cites ≥ 1 story and ≥ 1 analysis row; a counted answer
                   cites a method flag (P5-INV-7, P5-INV-9)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lib.evidence import COMPARABLE, FLOOR

CITATION = re.compile(r"\[\[([a-z_]+)\|([^\]]+)\]\]")
QUOTE = re.compile(r"[\"“]([^\"“”]{3,400})[\"”]")
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(%)?")
TOLERANCE = 0.011
STRUCTURAL = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0,          # ordinals and small quantifiers
              30.0, 80.0,                            # the two reporting floors
              60.0, 300.0, 0.6, 1000.0}              # questions, design target, κ bar, draws
FENCE_OPEN, FENCE_CLOSE = "<<<UNTRUSTED_STORY", ">>>END_UNTRUSTED_STORY<<<"

PROXY = re.compile(
    r"\b(success rate|failure rate|retrieval rate|fail(?:ure)? rate|"
    r"of (?:all )?(?:google photos )?users|of (?:all )?searches|of people who search|"
    r"of (?:all )?attempts|users (?:fail|succeed)|searches (?:fail|succeed))\b", re.I)
_NEGATION = re.compile(r"\b(not|never|no|cannot|can't|isn't|aren't|rather than|instead of|"
                       r"does not|do not|is not|are not|without)\b", re.I)
LABEL_COLON = re.compile(r"(?:^|(?<=[.!?]\s)|(?<=\n))\s*[*_]*([A-Z][A-Za-z' ]{0,28}?)[*_]*:\s")


def fence(text: str) -> str:
    """Neutralise anything in a story that imitates the prompt's delimiters, so
    a story cannot close its own wrapper and speak as the system (EC-ASK-2).
    Lives beside the quote check because the two must agree on what the model saw."""
    s = str(text or "")
    for marker in (FENCE_OPEN, FENCE_CLOSE, "<<<", ">>>"):
        s = s.replace(marker, "[")
    return re.sub(r"</?\s*(story|record|system|instructions?|developer)\s*>", "[tag]", s,
                  flags=re.I)


def citations(text: str) -> list[dict]:
    return [{"table": t, "key": k.strip()} for t, k in CITATION.findall(text or "")]


def _strip(text: str) -> str:
    """Citations and quotations are not the answer's own claims: ids are hex,
    and a number inside a quote is someone else's (it is checked as a quote)."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    # "Stage 5", "question 5.3", "(5.6)", "Stages 2 and 4": structure, not claims.
    t = re.sub(r"\b[Ss]tages?\s+\d+(?:\s*(?:,|and|or|–|-|to)\s*\d+)*", " ", t)
    t = re.sub(r"\b(?:[Qq]uestions?\s+)?\(?\b(?:10|[0-9])\.\d\b\)?", " ", t)
    return t


def numerals(text: str) -> list[tuple[float, str, int]]:
    out = []
    for m in _NUM.finditer(text):
        try:
            out.append((float(m.group(1).replace(",", "")), m.group(2) or "", m.start()))
        except ValueError:
            continue
    return out


def _candidates(rows: list[dict]) -> set[float]:
    vals: set[float] = set()

    def add(v):
        vals.update({v, round(v, 1), round(v, 2)})
        if 0 <= v <= 1:
            vals.update({v * 100, round(v * 100), round(v * 100, 1)})

    for row in rows or []:
        for k, v in row.items():
            if str(k).startswith("_") or v is None or isinstance(v, bool):
                continue
            if isinstance(v, int | float):
                add(float(v))
            elif isinstance(v, dict):
                for x in v.values():
                    if isinstance(x, int | float):
                        add(float(x))
            else:
                for n, _, _ in numerals(str(v)):
                    add(n)
    return vals


def check_numbers(text: str, rows: list[dict], gap: str = "") -> list[str]:
    """Per PARAGRAPH: a number must appear in a row that paragraph CITES. A number
    that exists somewhere in the brief but is pinned to an unrelated row ("31 of
    115" cited to a coverage row) is a misattribution, and the reader follows the
    citation. A paragraph that cites no row is held to every retrieved row."""
    by_key = {(r["_cite"]["table"], str(r["_cite"]["key"])): r for r in rows or []
              if r.get("_cite")}
    everything = _candidates(rows)
    # The gate's gap sentence is handed to the model to state ("22 of 290 stories
    # do"), so its numbers are supported wherever they appear.
    stated = _candidates([{"gap": gap}]) if gap else set()
    bad = []
    for para in re.split(r"\n\s*\n", text or ""):
        cited = [by_key[(c["table"], c["key"])] for c in citations(para)
                 if (c["table"], c["key"]) in by_key]
        bad += _numbers_in(para, (_candidates(cited) if cited else everything) | stated)
    return bad


def _numbers_in(text: str, cands: set[float]) -> list[str]:
    bad = []
    for v, pct, _ in numerals(_strip(text)):
        if not pct and v in STRUCTURAL:
            continue
        if not pct and 1900 <= v <= 2100 and v == int(v):
            continue                                                 # a year
        if any(abs(v - c) <= TOLERANCE for c in cands):
            continue
        bad.append(f"{v:g}{pct}")
    return bad


def check_percentages(text: str) -> list[str]:
    """A percentage needs its count: "27% (31 of 115)" or "31 of 115 (27%)"."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    bad = []
    for m in re.finditer(r"\d+(?:\.\d+)?%", t):
        around = t[max(0, m.start() - 45):m.end() + 30]
        if not re.search(r"\b\d[\d,]* of \d[\d,]*\b", around):
            bad.append(m.group(0))
    return bad


_SHARE_N = re.compile(r"(\d+(?:\.\d+)?)%\s*\((\d[\d,]*) of (\d[\d,]*)"
                      r"|(\d[\d,]*) of (\d[\d,]*)\s*\((\d+(?:\.\d+)?)%\)")


def check_directional(text: str) -> list[str]:
    return [b for kind, b in _directional(text) if kind == "unlabelled"]


def check_directional_claimed(text: str) -> list[str]:
    """"directional" on a share of a group of 80 or more — the label says the
    figure is weaker than it is (sweep 11, F2)."""
    return [b for kind, b in _directional(text) if kind == "claimed"]


def _directional(text: str) -> list[tuple[str, str]]:
    """[CTX] §15.5: a share over a group of 30–79 is shown AND labelled
    directional. share() writes "27% (13 of 48; 17%–41%) · directional"; an
    answer that keeps "27% (13 of 48)" and drops the label reads as settled
    (sweep 9: S1, F1, U2). Not absolute: it triggers the repair."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    bad = []
    for m in _SHARE_N.finditer(t):
        n = int((m.group(3) or m.group(5)).replace(",", ""))
        if FLOOR <= n < COMPARABLE and "directional" not in t[m.start():m.end() + 70].lower():
            bad.append(("unlabelled", m.group(0)))
        # The mirror slip (sweep 10, U2; live on the first starter): "27% (31 of 115)
        # · directional". Only the text right after THIS share is read, so the next
        # share's own label does not count.
        tail = t[m.end():m.end() + 25].lower()
        if n >= COMPARABLE and re.match(r"[^.;%]*?·?\s*directional", tail):
            bad.append(("claimed", m.group(0)))
    return bad


_KIND = r"(?:sentimental|utility|practical|unclear)"
_MORE = (r"(?:most|more|less|least|fewer|harder|hardest|easier|easiest|higher|highest|lower|"
         r"lowest|mainly|mostly|skews?|skewed|bigger|biggest|larger|largest|dominat\w*|than)")
_KIND_COMPARE = re.compile(rf"\b{_KIND}\b[^.;\n]{{0,40}}\b{_MORE}\b|\b{_MORE}\b[^.;\n]{{0,40}}"
                           rf"\b{_KIND}\b", re.I)


def check_comparison(text: str) -> list[str]:
    """No kind of photo can be claimed to differ from another: every kind has
    fewer than 80 core stories, below the floor where [CTX] §15.5 allows a
    difference to be claimed (the Analysis page says so). Sweep 9's first
    starter answered "people most often struggle with sentimental photos".
    Flags a comparative word within a few words of a kind of photo, in the
    answer's own words. Not absolute: it triggers the repair."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    return [m.group(0)[:80] for m in _KIND_COMPARE.finditer(t)]


def _norm(s: str) -> str:
    s = re.sub(r"[\"'‘’“”`´]", "'", str(s))
    s = re.sub(r"\s*'\s*", "'", s)       # a space added or lost at a quote mark is typography
    return re.sub(r"\s+", " ", s).strip().lower()


LABEL_WORDS = 6


def check_quotes(text: str, records: list[dict], rows: list[dict],
                 question: str = "") -> list[str]:
    # Testimony comes from STORIES (and the asker's own words, quoted back). The
    # engine's own rows are never quotable: a sentence of the recommendation was
    # once presented as what "one person summed up".
    hay = [_norm(question)] if question else []
    for r in records or []:
        hay += [_norm(r.get("text", "")), _norm(fence(r.get("text", "")))]
    # A category's own NAME, quoted as a term ("a few scrolls", "Is the photo there to
    # find?"), is not testimony. Sweep 10 withheld three drafts for it once rows
    # carried plain-word labels. Only row LABELS (a cross-tab row's `about`, a derived
    # row's measure and value) and only up to LABEL_WORDS words — never an engine
    # sentence, so the quoted-recommendation case above stays closed.
    labels = [_norm(" ".join(str(r.get(k, "")) for k in ("measure", "which")).replace("_", " "))
              for r in rows or [] if r.get("measure")]
    labels += [_norm(str(r["about"]).replace("_", " ")) for r in rows or [] if r.get("about")]
    bad = []
    for m in QUOTE.finditer(text or ""):
        # Punctuation the writer adds at the quote's edge ("…where," for "…where.")
        # is typography, not a change of words.
        q = _norm(m.group(1)).strip(" .,;:!?…")
        if len(q.split()) < 3:
            continue                                          # a term, not testimony
        if len(q.split()) <= LABEL_WORDS and any(q in lab for lab in labels):
            continue                                          # a category's name
        parts = [p for p in re.split(r"\s*(?:…|\.\.\.)\s*", q) if len(p.split()) >= 3] or [q]
        if not all(any(p in h for h in hay) for p in parts):
            bad.append(m.group(1)[:80])
    return bad


def check_citations(text: str, rows: list[dict], records: list[dict]) -> list[str]:
    have = {(r["_cite"]["table"], str(r["_cite"]["key"])) for r in rows if r.get("_cite")}
    have |= {("story", str(r["story_id"])) for r in records}
    return [f"{c['table']}[{c['key']}] was not retrieved" for c in citations(text)
            if (c["table"], c["key"]) not in have]


def _negated(text: str, start: int, window: int = 70) -> bool:
    before = text[max(0, start - window):start]
    cut = max(before.rfind("."), before.rfind("\n"), before.rfind(";"), before.rfind("?"))
    return bool(_NEGATION.search(before[cut + 1:] if cut >= 0 else before))


def check_proxy(text: str) -> list[str]:
    t = QUOTE.sub(" ", text or "")
    return [m.group(0) for m in PROXY.finditer(t) if not _negated(t, m.start())]


def check_label_colon(text: str) -> list[str]:
    """EC-ASK-8: "Caveat:", "Answer:", "The numbers:" — a form, not an answer."""
    t = CITATION.sub(" ", text or "")
    return [m.group(1).strip() + ":" for m in LABEL_COLON.finditer(t)
            if m.group(1).strip().lower() != "interpretation"
            and len(m.group(1).split()) <= 4
            and not _SPEECH.search(m.group(1))]


# "One poster wrote:" introduces a quote with a subject and a verb — a sentence,
# not a label. "Caveat:" and "The numbers:" have no verb.
_SPEECH = re.compile(r"\b(wrote|writes|said|says|put it|posted|asked|asks|explained|"
                     r"complained|added|recalled|described|admitted)\s*$", re.I)


_CODE = re.compile(r"(?<![\w:/.\-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def check_codes(text: str) -> list[str]:
    """Plain words, not codes: a snake_case slug ("irrelevant_results",
    "below_floor") in the answer's own words is a code name the reader never
    learned. Citations and quotes are not the answer's words. Not absolute:
    it triggers the repair, and a survivor is served with the warning."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    return sorted(set(_CODE.findall(t)))


def italicise_closing(text: str) -> str:
    """Formatting only, never content: a final line that is already a question
    is wrapped in *…* so it renders as the contract's italic closing line."""
    lines = (text or "").rstrip().split("\n")
    last = lines[-1].strip() if lines else ""
    if last.endswith("?") and not re.fullmatch(r"[*_].*[*_]", last) and len(last.split()) <= 16:
        lines[-1] = f"*{last.strip('*_ ')}*"
    return "\n".join(lines)


def _units(text: str) -> list[str]:
    units = []
    for block in re.split(r"\n\s*\n", text or ""):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        bullets = [ln for ln in lines if re.match(r"(?:[-*•]|\d+\.)\s+", ln)]
        rest = [ln for ln in lines if ln not in bullets]
        units += bullets + ([" ".join(rest)] if rest else [])
    return units


def _is_structural(unit: str) -> bool:
    bare = re.sub(r"[*_`>#\-•]", "", unit).strip()
    return (not bare or bare.endswith(":") or len(bare.split()) <= 3
            or (bare.endswith("?") and len(bare.split()) <= 14))


def check_uncited(text: str) -> list[str]:
    return [u[:100] for u in _units(text) if not _is_structural(u)
            and "interpretation:" not in u.lower() and not CITATION.search(u)]


def check_closing(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    ok = re.fullmatch(r"[*_][^*_]{3,120}\?[*_]", last) is not None
    return [] if ok else ["the answer does not end with one italic closing question"]


@dataclass
class Report:
    numbers: list[str] = field(default_factory=list)       # T-14
    percentages: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)        # P5-INV-3
    citations: list[str] = field(default_factory=list)
    uncited: list[str] = field(default_factory=list)       # P5-INV-6
    proxy: list[str] = field(default_factory=list)         # T-16
    label_colon: list[str] = field(default_factory=list)   # T-17
    closing: list[str] = field(default_factory=list)
    refusal: list[str] = field(default_factory=list)       # P5-INV-8
    evidence: list[str] = field(default_factory=list)      # P5-INV-7, -9
    length: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)         # plain words, not slugs
    directional: list[str] = field(default_factory=list)   # [CTX] §15.5 label
    directional_claimed: list[str] = field(default_factory=list)
    comparison: list[str] = field(default_factory=list)    # no kind of photo differs

    def problems(self) -> list[str]:
        out = []
        for label, items in (("unsupported number", self.numbers),
                             ("percentage without its count", self.percentages),
                             ("unverifiable quote", self.quotes),
                             ("citation not retrieved", self.citations),
                             ("uncited claim", self.uncited),
                             ("share stated as a rate of users or searches", self.proxy),
                             ("label-and-colon opening", self.label_colon),
                             ("closing", self.closing), ("refusal", self.refusal),
                             ("evidence", self.evidence), ("length", self.length),
                             ("code name instead of plain words", self.codes),
                             ("directional share not labelled", self.directional),
                             ("directional label on a comparable share",
                              self.directional_claimed),
                             ("comparison between kinds of photo", self.comparison)):
            out += [f"{label}: {x}" for x in items]
        return out

    @property
    def ok(self) -> bool:
        return not self.problems()


def canonical_citations(text: str, rows: list[dict], records: list[dict]) -> str:
    """Formatting, not content: a citation that is not retrieved as written is
    rewritten ONLY when exactly one retrieved key matches it — the key with its
    spaces restored to underscores ("missing cuts" → "missing_cuts", the brief
    shows plain words), or the same key under another table ("stories:core"
    cited as a cross-tab when it is the funnel's). Never invents a source."""
    have = {(r["_cite"]["table"], str(r["_cite"]["key"])) for r in rows or [] if r.get("_cite")}
    have |= {("story", str(r["story_id"])) for r in records or []}

    def fix(m):
        t, k = m.group(1), m.group(2).strip()
        if (t, k) in have:
            return m.group(0)
        for cand in (k.replace(" ", "_"),):
            if (t, cand) in have:
                return f"[[{t}|{cand}]]"
        other = [(tt, kk) for tt, kk in have if kk in (k, k.replace(" ", "_"))]
        return f"[[{other[0][0]}|{other[0][1]}]]" if len(other) == 1 else m.group(0)
    return CITATION.sub(fix, text or "")


def canonical_story_citations(text: str, records: list[dict]) -> str:
    """Formatting, not content: [[story|abc…]] written without the retrieved id's
    ':0' suffix is completed when exactly one retrieved story matches."""
    ids = [str(r["story_id"]) for r in records or []]

    def fix(m):
        if m.group(1) != "story" or m.group(2) in ids:
            return m.group(0)
        hits = [i for i in ids if i.startswith(m.group(2).strip())]
        return f"[[story|{hits[0]}]]" if len(hits) == 1 else m.group(0)
    return CITATION.sub(fix, text or "")


def check(answer: str, route: str, rows: list[dict], records: list[dict], *,
          question: str = "", gap: str = "") -> Report:
    rep = Report()
    text = answer or ""
    rep.numbers = check_numbers(text, rows, gap)
    rep.percentages = check_percentages(text)
    rep.quotes = check_quotes(text, records, rows, question)
    rep.citations = check_citations(text, rows, records)
    rep.proxy = check_proxy(text)
    rep.label_colon = check_label_colon(text)
    rep.codes = check_codes(text)
    rep.directional = check_directional(text)
    rep.directional_claimed = check_directional_claimed(text)
    rep.comparison = check_comparison(text)
    words = len(CITATION.sub(" ", text).split())
    if words > 200:
        rep.length = [f"{words} words, over the 200 limit"]
    if route == "NONE":
        if citations(text):
            rep.refusal.append("a refusal cites evidence")
        if _numbers_in(_strip(text), set()):
            rep.refusal.append("a refusal states a number")
        if any(len(m.group(1).split()) >= 3 for m in QUOTE.finditer(text)):
            rep.refusal.append("a refusal quotes")        # a quoted 2-word term is not testimony
        return rep
    rep.uncited = check_uncited(text)
    rep.closing = check_closing(text)
    cited = citations(text)
    if route == "FULL":
        if not any(c["table"] == "story" for c in cited):
            rep.evidence.append("a FULL answer quotes no story")
        if not any(c["table"].startswith("analysis_") for c in cited):
            rep.evidence.append("a FULL answer cites no counted row")
    counted = any(c["table"].startswith("analysis_") and c["table"] != "analysis_method_flags"
                  for c in cited)
    if counted and not any(c["table"] == "analysis_method_flags" for c in cited):
        rep.evidence.append("a counted answer cites no method flag in its caveat")
    return rep
