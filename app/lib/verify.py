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
_NEGATION = re.compile(r"\b(not|never|no|none|nor|neither|cannot|can't|isn't|aren't|"
                       r"rather than|instead of|does not|do not|is not|are not|without)\b", re.I)
# Also right after a sentence's citations ("…idea. [[x|y]] This fits a simple idea: …",
# v3.3 S4): the checker sees it once citations are blanked, so the rewrite must too.
LABEL_COLON = re.compile(r"(?:^|(?<=[.!?]\s)|(?<=\]\]\s)|(?<=\n))\s*[*_]*([A-Z][A-Za-z' ]{0,28}?)"
                         r"[*_]*:\s")


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
    # The size of the evidence ("the 115 cases", "331 cases from 316 people") is
    # context an answer may state anywhere (v3.4: "of the 115 cases" in a paragraph
    # citing only a split withheld N2 and U1).
    stated |= _candidates([r for r in rows or []
                           if (r.get("_cite") or {}).get("table") == "analysis_funnel"])
    bad = []
    for para in re.split(r"\n\s*\n", text or ""):
        cited = [by_key[(c["table"], c["key"])] for c in citations(para)
                 if (c["table"], c["key"]) in by_key]
        bad += _numbers_in(para, (_candidates(cited) if cited else everything) | stated)
    return bad


# "over 31,000 public posts" for 31,235 (v3.1, N1): a round number of a thousand or
# more, said as approximate, matches a figure within 5% on the right side.
_APPROX = re.compile(r"\b(about|around|roughly|nearly|almost|over|more than|some|close to|"
                     r"just over|just under|under)\s+$", re.I)


def _approx_ok(v: float, before: str, cands: set[float]) -> bool:
    m = _APPROX.search(before)
    if not m or v < 1000 or v % 100:
        return False
    word = m.group(1).lower()
    for c in cands:
        if abs(c - v) <= 0.05 * c:
            if word in ("over", "more than", "just over") and c < v:
                continue
            if word in ("nearly", "almost", "under", "just under") and c > v:
                continue
            return True
    return False


def _numbers_in(text: str, cands: set[float]) -> list[str]:
    bad = []
    t = _strip(text)
    for v, pct, at in numerals(t):
        if not pct and v in STRUCTURAL:
            continue
        if not pct and _approx_ok(v, t[max(0, at - 14):at], cands):
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


# "27% (13 of 48", "13 of 48 (27%)", and the plain layer's "13 of 48 stories (27%)".
_SHARE_N = re.compile(r"(\d+(?:\.\d+)?)%\s*\((\d[\d,]*) of (\d[\d,]*)"
                      r"|(\d[\d,]*) of (\d[\d,]*)(?:\s+[a-z]+){0,2}\s*\((\d+(?:\.\d+)?)%\)")
# The label, as share() writes it or as the plain layer says it (plain.rough).
_LABEL = re.compile(r"directional|rough guide", re.I)


def check_share_arithmetic(text: str) -> list[str]:
    """A percentage must be the one its own count gives: "1 of 175 (9%)" passed
    every number check (1 is structural, 9% was another row's) and was served
    (v2.2, R2). Rounding tolerance: 1 point."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    bad = []
    for m in _SHARE_N.finditer(t):
        pct = float(m.group(1) or m.group(6))
        n = int((m.group(2) or m.group(4)).replace(",", ""))
        d = int((m.group(3) or m.group(5)).replace(",", ""))
        if d == 0 or n > d or abs(100 * n / d - pct) > 1.0:
            bad.append(m.group(0))
    return bad


# Up to 140 characters ("32 stories are about photos kept for the information in
# them (receipts, documents, notes) — too few", v2.9), but never across another count.
_FLOOR_CLAIM = re.compile(r"(\d[\d,]*)\s+(?:stories|posts|cases)\b(?:(?!\d[\d,]*\s+(?:stories|posts|cases)\b)"
                          r"[^.\n]){0,140}?too few \(under (\d+)\)", re.I)


def check_floor_claim(text: str) -> list[str]:
    """"Only 32 stories … too few (under 30)" is false on its face: the gate said 21
    and the writer swapped in another group's count (v2.5, U2). A count called too
    few for a percentage must be below the floor it names."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    return [m.group(0)[:80] for m in _FLOOR_CLAIM.finditer(t)
            if int(m.group(1).replace(",", "")) >= int(m.group(2))]


# A share said in words (ask_v3, the PM: "constantly quoting the number of stories
# would make a bad impression"). Each phrase is held to the shares the sentence
# cites — and, when the sentence cites none, its paragraph's — like a number.
_FRACTION = {"one in twenty": 0.05, "one in ten": 0.10, "one in eight": 0.125,
             "one in seven": 1 / 7, "one in six": 1 / 6, "one in five": 0.20, "a fifth": 0.20,
             "one in four": 0.25, "a quarter": 0.25, "one in three": 1 / 3, "a third": 1 / 3,
             "two in five": 0.40, "half": 0.50, "three in five": 0.60, "two-thirds": 2 / 3,
             "two thirds": 2 / 3, "three-quarters": 0.75, "three quarters": 0.75,
             "four in five": 0.80, "nine in ten": 0.90}
_FRACTION_RE = re.compile(
    r"\b(?:(about|around|roughly|nearly|almost|over|more than|under|less than|just over|"
    r"just under|close to|some)\s+)?(" + "|".join(sorted(map(re.escape, _FRACTION), key=len,
                                                     reverse=True)) + r")\b", re.I)
_MAJORITY = re.compile(r"\b(?:the majority|most (?:people|of them|of these|cases|posts|searchers|"
                       r"of the (?:people|cases|posts)))\b", re.I)
_SENT_CITED = re.compile(r"[^.!?\n]+(?:[.!?]+|$)(?:\s*\[\[[a-z_]+\|[^\]]+\]\])*")


_PAIRS = (("stories", "of"), ("core_stories", "of"), ("n_coded", "stories_asked"))


def _shares(rows: list[dict]) -> list[float]:
    """Every share a row can state — a count of cases, an opportunity's cases, or
    how many cases say anything at all (coverage: "about a quarter say how long
    they kept trying", v3.0 R3)."""
    out = []
    for r in rows:
        for a, b in _PAIRS:
            n, d = r.get(a), r.get(b)
            if isinstance(n, int) and isinstance(d, int) and d:
                out.append(n / d)
    return out


def check_proportions(text: str, rows: list[dict]) -> list[str]:
    """"about a quarter", "roughly one in five", "most people": each must fit a
    share the sentence rests on, within PROPORTION_TOLERANCE (5 points; "over" /
    "nearly" also on the right side). A group under 30 gets no share at all, so
    no fraction may rest on it alone. Absolute, like a made-up number."""
    from lib.plain import PROPORTION_TOLERANCE as TOL
    by_key = {(r["_cite"]["table"], str(r["_cite"]["key"])): r for r in rows or []
              if r.get("_cite")}
    bad = []
    for para in re.split(r"\n\s*\n", text or ""):
        para_rows = [by_key[(c["table"], c["key"])] for c in citations(para)
                     if (c["table"], c["key"]) in by_key]
        for m in _SENT_CITED.finditer(para):
            sent = m.group(0)
            cited = [by_key[(c["table"], c["key"])] for c in citations(sent)
                     if (c["table"], c["key"]) in by_key] or para_rows or list(by_key.values())
            bare = QUOTE.sub(" ", CITATION.sub(" ", sent))
            floor_ok = [r for r in cited if max((v for v in (r.get("of"), r.get("stories_asked"))
                                                 if isinstance(v, int)), default=0) >= FLOOR]
            vals = _shares(floor_ok)
            for f in _FRACTION_RE.finditer(bare):
                mod, v = (f.group(1) or "").lower(), _FRACTION[f.group(2).lower()]
                if f.group(2).lower() == "half" and re.search(
                        r"\bhalf(?:[\-\u2010\u2011\u2012\u2013]\w|[\s]+(?:remembered|forgotten|"
                        r"recalled|formed|memor))", bare[f.start():],
                        re.I):
                    continue                              # "a half-remembered photo"
                if mod in ("over", "more than", "just over"):
                    ok = any(v <= x <= v + 2 * TOL for x in vals)
                elif mod in ("nearly", "almost", "under", "less than", "just under", "close to"):
                    ok = any(v - 2 * TOL <= x <= v + 0.01 for x in vals)
                else:
                    ok = any(abs(x - v) <= TOL for x in vals)
                if not ok:
                    bad.append(f.group(0))
            for f in _MAJORITY.finditer(bare):
                if not any(x > 0.5 for x in vals):
                    bad.append(f.group(0))
    return bad


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
        # Anywhere in the SAME sentence, before or after: the plain layer ends its
        # sentence with the label, and a writer may lead with it ("… — a small
        # group, so only a rough guide: 11 of 48 stories (23%)", v2.1, S4).
        sent = _sentence_of(t, m.start(), m.end())
        if FLOOR <= n < COMPARABLE and not _LABEL.search(sent):
            bad.append(("unlabelled", m.group(0)))
        # The mirror slip (sweep 10, U2): "27% (31 of 115) · directional". Right
        # after THIS share, so the next share's own label does not count…
        tail = t[m.end():m.end() + 25].lower()
        if n >= COMPARABLE and re.match(r"[^.;%]*?·?\s*(?:directional|— a small group)", tail):
            bad.append(("claimed", m.group(0)))
        # … or anywhere in a sentence whose every share is of 80 or more ("This 31
        # of 115 stories (27%) is a small group, so only a rough guide", v2.1, N2).
        elif (n >= COMPARABLE and _LABEL.search(sent)
              and all(int((x.group(3) or x.group(5)).replace(",", "")) >= COMPARABLE
                      for x in _SHARE_N.finditer(sent))):
            bad.append(("claimed", m.group(0)))
    return bad


_BOUND = re.compile(r"[.!?](?=\s|$)|\n")


def _sentence_of(t: str, a: int, b: int, cap: int = 300) -> str:
    """The sentence holding t[a:b] (at most `cap` characters either side)."""
    start = 0
    for m in _BOUND.finditer(t, max(0, a - cap), a):
        start = m.end()
    start = max(start, a - cap)
    end = _BOUND.search(t, b)
    return t[start:min(end.start() if end else len(t), b + cap)]


# "practical" only as a kind ("practical photos"): "the biggest practical gain" is not
# one (v3.0, F1). A comparative followed by "to <verb>" is about an action — "easier
# to back up or mark utility photos" (v3.0, L1) — not a kind of photo.
_KIND = (r"(?:sentimental|utility|practical (?:photos?|ones|images)|unclear|kept as memories|"
         r"memory photos|information photos|photos kept for (?:their )?information|"
         r"for the information in them|why (?:it|the photo|the photos|they) (?:was|were) kept)")
# A comparative near a kind of photo compares kinds ("information photos more often
# fail", "behave differently"). A superlative ranks — kinds when it is said of one
# ("people struggle most with sentimental photos"), problems within one when the kind
# is the scope ("For photos kept as memories, the largest problem was…", v3.4 U1/U2).
_COMPARATIVE = (r"(?:more|less|fewer|harder(?!\s+to\b)|easier(?!\s+to\b)|higher|lower|bigger|"
                r"larger|skews?|skewed|than|differently|different|unlike|whereas)")
_SUPERLATIVE = r"(?:most|least|hardest|easiest|highest|lowest|mainly|mostly|biggest|largest|dominat\w*)"
_KIND_COMPARE = re.compile(rf"\b{_KIND}\b[^.;\n]{{0,60}}?\b{_COMPARATIVE}\b|\b{_COMPARATIVE}\b"
                           rf"[^.;\n]{{0,40}}?\b{_KIND}\b", re.I)
_KIND_SUPER = re.compile(rf"(?P<pre>[^.;\n]{{0,24}})\b{_KIND}\b[^.;\n]{{0,40}}\b{_SUPERLATIVE}\b|"
                         rf"\b{_SUPERLATIVE}\b[^.;\n]{{0,40}}\b{_KIND}\b", re.I)
_SCOPE = re.compile(r"\b(?:for|among|within|in|about)\b", re.I)

_KIND_WORDS = r"(?:kinds? of photos?|types? of photos?|photo(?:'s)? (?:kind|type)s?)"
_KIND_DIFFER = re.compile(rf"\b(?:differ\w*|depends? on)\b[^.;\n]{{0,40}}\b(?:{_KIND_WORDS}|{_KIND})\b|"
                          rf"\b{_KIND_WORDS}\b[^.;\n]{{0,40}}\bdiffer\w*\b", re.I)


def check_comparison(text: str) -> list[str]:
    """No kind of photo can be claimed to differ from another: every kind has
    fewer than 80 core stories, below the floor where [CTX] §15.5 allows a
    difference to be claimed (the Analysis page says so). Sweep 9's first
    starter answered "people most often struggle with sentimental photos".
    Flags a comparative word within a few words of a kind of photo, in the
    answer's own words. Not absolute: it triggers the repair."""
    t = QUOTE.sub(" ", CITATION.sub(" ", text or ""))
    bad = []
    for m in _KIND_COMPARE.finditer(t):
        sent = _sentence_of(t, m.start(), m.end())
        # Denied only when the denial is right before THIS comparison: "We can't say
        # whether … — but the cases show a different pattern" asserts one (v3.7, U2).
        just_before = t[max(0, m.start() - 50):m.start()]
        if not (sent.rstrip(" *_").endswith("?") or re.search(
                r"\b(?:whether|cannot|can.t|not|no)\b[^—;]*$", just_before, re.I)):
            bad.append(m.group(0)[:80])
    for m in _KIND_SUPER.finditer(t):
        if m.group("pre") is not None and _SCOPE.search(m.group("pre")):
            continue                         # "for photos kept as memories, the largest…"
        bad.append(m.group(0).strip()[:80])
    # "By kind of photo, the first misstep differs." / "Search goes wrong in
    # different ways by kind of photo." (U1, v2.7 and v2.8) — a claim of difference
    # with no comparative word. Not when denied ("cannot say whether it differs by
    # kind of photo") nor in the closing offer ("Want to see how this differs…?").
    for m in _KIND_DIFFER.finditer(t):
        sent = _sentence_of(t, m.start(), m.end())
        if sent.rstrip(" *_").endswith("?") or _NEGATION.search(sent) or re.search(
                r"\bwhether\b", sent, re.I):
            continue
        bad.append(m.group(0)[:80])
    return bad


def _norm(s: str) -> str:
    s = re.sub(r"[\"'‘’“”`´]", "'", str(s))
    s = re.sub(r"\s*'\s*", "'", s)       # a space added or lost at a quote mark is typography
    return re.sub(r"\s+", " ", s).strip().lower()


LABEL_WORDS = 6
_SAID = re.compile(r"\b(wrote|writes|said|says|say|posted|asked|asks|complained|told|put it|"
                   r"one person|someone|a poster|a user|people typed|typed|searched for)\b", re.I)


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
        # Four words or fewer with no one said to have said them — a "did you mean"
        # prompt, a label — is a term too (v3.1, S4). Attributed, it is testimony.
        sent = _sentence_of(text, m.start(), m.end())
        if len(q.split()) <= 4 and not _SAID.search(sent):
            continue
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


# Back to the start of the clause, up to this far: a refusal's list — "cannot tell
# us monthly active users of Ask Photos, any rate of success or failure, or any
# count of users" — puts its negation ~95 characters before "of users" (v2.1, O2).
def _negated(text: str, start: int, window: int = 160) -> bool:
    before = text[max(0, start - window):start]
    cut = max(before.rfind("."), before.rfind("\n"), before.rfind(";"), before.rfind("?"))
    return bool(_NEGATION.search(before[cut + 1:] if cut >= 0 else before))


def check_proxy(text: str) -> list[str]:
    t = QUOTE.sub(" ", text or "")
    return [m.group(0) for m in PROXY.finditer(t) if not _negated(t, m.start())]


def dash_figure_labels(text: str) -> str:
    """Formatting only: "Some found the photo anyway: 38 of 115 stories (33%)." →
    "Some found the photo anyway — 38 of 115 stories (33%)." Every label-colon the
    v2.9 sweep withheld (5 of 24 drafts) was this shape — a clause, a colon, then
    a figure — and the fallback that replaced it lost the answer (P1). A colon
    before anything else ("Caveat: these are…") is untouched, and still absolute."""
    t = text or ""
    for m in reversed(list(LABEL_COLON.finditer(t))):
        if re.match(r"\s*(?:in\s+|about\s+|just\s+|only\s+)?\d", t[m.end():]):
            c = t.rindex(":", m.start(), m.end())
            t = t[:c] + " —" + t[c + 1:]
    return t


# Openers that only announce what follows: dropped, the sentence kept.
_HEADING = re.compile(r"(?:the )?(?:short answer|answer|in short|bottom line|the bottom line|"
                      r"takeaway|the takeaway|note|caveat|caveats|limits?|a limit|why|"
                      r"what this means|where the evidence runs out|what we can say|"
                      r"what the posts do show|what the evidence shows|partial answer|"
                      r"my read|in brief|summary)", re.I)


def unlabel(text: str) -> str:
    """Formatting only (ask_v3): a "Label:" opening becomes prose. A heading-like
    opener ("Short answer:", "Where the evidence runs out:") is dropped and the
    sentence after it kept; any other short clause before a colon ("This suggests
    product fixes:") gets a dash instead. v3.0's writer (gpt-5-mini) opened 13 of 24
    drafts this way and each was withheld. A colon that introduces a quote, or
    follows "wrote"/"said", is untouched."""
    t = text or ""
    for m in reversed(list(LABEL_COLON.finditer(t))):
        label = m.group(1).strip()
        after = t[m.end():]
        if (len(label.split()) > 5 or _SPEECH.search(label)
                or re.match(r"\s*[*_]*[\"“‘']", after)):
            continue
        c = t.rindex(":", m.start(), m.end())
        if _HEADING.fullmatch(label):
            nxt = re.match(r"(\s*[*_]*)(\S)", after)
            rest = (nxt.group(1).lstrip() + nxt.group(2).upper() + after[nxt.end():]) if nxt \
                else after
            t = t[:m.start(1)] + t[c + 1:m.end()].replace(" ", "") + rest
        else:
            t = t[:c] + " —" + t[c + 1:]
    return t


def check_label_colon(text: str) -> list[str]:
    """EC-ASK-8: "Caveat:", "Answer:", "The numbers:" — a form, not an answer."""
    t = CITATION.sub(" ", text or "")
    return [m.group(1).strip() + ":" for m in LABEL_COLON.finditer(t)
            if m.group(1).strip().lower() != "interpretation"
            and len(m.group(1).split()) <= 5          # "What we can say instead:" (v2.2, L2)
            and not _SPEECH.search(m.group(1))
            # A colon that opens a quotation introduces someone's words — "One post
            # fits the point: “it says no results”" — it is not a label (v2.3: four
            # such drafts were withheld once labels of five words were caught).
            and not re.match(r"\s*[*_]*[\"“‘']", t[m.end():])]


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
    is wrapped in *…* so it renders as the contract's italic closing line. A
    closing question written at the end of a paragraph (v3.4: P1, L2, I1) is
    moved to a line of its own first."""
    t = (text or "").rstrip()
    m = re.search(r"(?<=[.!)”\]])\s+(\*?[A-Z][^.!?\n*]{3,200}\?\*?)$", t)
    if m and "\n" not in m.group(1):
        t = t[:m.start()].rstrip() + "\n\n" + m.group(1)
    lines = t.split("\n")
    last = lines[-1].strip() if lines else ""
    if last.endswith("?") and not re.fullmatch(r"[*_].*[*_]", last) and len(last.split()) <= 30:
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
    # The closing question is an offer, not a claim — in italics it may run a little
    # longer (a 15-word one was flagged "uncited" in v2.1, P2).
    italic_q = re.fullmatch(r"[*_][^*_]+\?[*_]", unit.strip()) is not None
    return (not bare or bare.endswith(":") or len(bare.split()) <= 3
            or (bare.endswith("?") and len(bare.split()) <= (25 if italic_q else 14)))


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
    arithmetic: list[str] = field(default_factory=list)    # T-14: % disagrees with its count
    floor_claim: list[str] = field(default_factory=list)   # T-14: "32 … too few (under 30)"
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
    jargon: list[str] = field(default_factory=list)        # plain words (D-14)
    proportions: list[str] = field(default_factory=list)   # a share in words must fit (v3)

    def problems(self) -> list[str]:
        out = []
        for label, items in (("unsupported number", self.numbers),
                             ("unsupported number (the % does not match its count)",
                              self.arithmetic),
                             ("unsupported number (a count called too few is not)",
                              self.floor_claim),
                             ("unsupported number (a share in words does not fit)",
                              self.proportions),
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
                             ("comparison between kinds of photo", self.comparison),
                             ("internal word a reader cannot know", self.jargon)):
            out += [f"{label}: {x}" for x in items]
        return out

    @property
    def ok(self) -> bool:
        return not self.problems()


_FALSE_LABEL = re.compile(r"(?:\s*[,—–-]|\s+is)?\s*(?:this is\s+)?a small group, so only a rough "
                          r"guide|\s*·\s*directional", re.I)


_N_OF_M = re.compile(r"(\d[\d,]*) of (\d[\d,]*)")
_LEAD_LABEL = re.compile(r"^(\s*)a small group, so only a rough guide\s*[:,—–-]\s*(\S)", re.I)
_ONLY_LABEL = re.compile(r"\s*(?:this is\s+|that is\s+)?(?:a small group,?\s*)?(?:so\s+)?only a "
                         r"rough guide\.?\s*$", re.I)
_LABEL_SENTENCE = re.compile(r"\s*(?:this|that|the|these)\s+(?:figure|number|count|share|"
                             r"percentage)s?\b[^.!?\n]*\brough guide", re.I)


def drop_unfounded_rough_guide(text: str) -> str:
    """Remove the "rough guide" label from a sentence whose EVERY share is of 80 or
    more stories: the label is false there (it says the figure is weaker than it
    is), and the writer added it despite the prompt (v2.4: S1, P3, R2, F1). No number
    or word of evidence changes; a sentence with any share under 80 keeps it."""
    out, last, dropped, prev = [], 0, False, []
    for end in [m.end() for m in _BOUND.finditer(text or "")] + [len(text or "")]:
        seg = text[last:end]
        if dropped:                        # the dropped sentence's own citations
            seg = re.sub(r"^[ \t]*" + CITATION.pattern + r"(?:\s*" + CITATION.pattern + r")*",
                         "", seg)
            if not seg.strip() and "".join(out).endswith("\n"):
                seg = ""                   # the dropped line's own line break
            dropped = False
        # Every "N of M" counts, with or without its %: "A small group, so only a
        # rough guide: 30 of 115 stories say anything about…" (v2.8: R3).
        ns = [int(m.group(2).replace(",", "")) for m in _N_OF_M.finditer(
            QUOTE.sub(" ", CITATION.sub(" ", seg)))]
        bare = CITATION.sub(" ", seg)
        if not ns and prev and all(n >= COMPARABLE for n in prev) and _ONLY_LABEL.match(bare):
            # "…2 of 115 stories (2%). A small group, so only a rough guide." (v2.9: R2)
            lead = re.match(r"(?:\s*" + CITATION.pattern + r")*", seg).group(0)
            seg, dropped, ns = lead, True, prev
        elif ns and all(n >= COMPARABLE for n in ns):
            seg = _LEAD_LABEL.sub(lambda m: m.group(1) + m.group(2).upper(), seg)
            seg = _FALSE_LABEL.sub("", seg)
            # A sentence that exists only to say it ("This figure is only a rough
            # guide, because it comes from 31 of 115 stories (27%).", v2.7: N2)
            # goes whole: nothing in it is new, and what it claims is false.
            if _LABEL_SENTENCE.match(CITATION.sub(" ", seg)):
                # Citations that open the segment close the sentence before it.
                lead = re.match(r"(?:\s*" + CITATION.pattern + r")*", seg).group(0)
                seg, dropped = lead + ("\n" if seg.endswith("\n") else ""), True
        out.append(seg)
        if ns:
            prev = ns
        elif bare.strip():
            prev = []
        last = end
    return "".join(out)


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


MAX_WORDS = 260          # ask_v3: as long as the question needs, never an essay


def check(answer: str, route: str, rows: list[dict], records: list[dict], *,
          question: str = "", gap: str = "") -> Report:
    rep = Report()
    text = answer or ""
    rep.numbers = check_numbers(text, rows, gap)
    rep.arithmetic = check_share_arithmetic(text)
    rep.floor_claim = check_floor_claim(text)
    rep.proportions = check_proportions(text, rows) if route != "NONE" else []
    rep.percentages = check_percentages(text)
    rep.quotes = check_quotes(text, records, rows, question)
    rep.citations = check_citations(text, rows, records)
    rep.proxy = check_proxy(text)
    rep.label_colon = check_label_colon(text)
    rep.codes = check_codes(text)
    rep.directional = check_directional(text)
    rep.directional_claimed = check_directional_claimed(text)
    rep.comparison = check_comparison(text)
    from lib.plain import check_jargon
    # A word the asker typed is one they know ("How many core stories…?"), however
    # they hyphenated or pluralised it ("utility-photo" → "utility photos", v2.2 L1).
    asked = re.sub(r"[-_]", " ", (question or "").lower())
    rep.jargon = [w for w in check_jargon(text)
                  if not all(x.rstrip("s") in asked for x in w.lower().split())]
    words = len(CITATION.sub(" ", text).split())
    if words > MAX_WORDS:
        rep.length = [f"{words} words, over the {MAX_WORDS} limit"]
    if route == "NONE":
        if citations(text):
            rep.refusal.append("a refusal cites evidence")
        if _numbers_in(_strip(text), set()):
            rep.refusal.append("a refusal states a number")
        if any(len(m.group(1).split()) >= 3 for m in QUOTE.finditer(text)):
            rep.refusal.append("a refusal quotes")        # a quoted 2-word term is not testimony
        return rep
    # ask_v3 (the PM, 2026-09-27): an answer argues like a researcher — its own
    # reasoning needs no source (numbers, fractions and quotes in it are still
    # checked), a post is quoted only when it bears on the point, and a limit is
    # said only where it changes how a claim reads — so neither an uncited
    # sentence, a missing quote nor a missing caveat line is a problem any more.
    rep.closing = check_closing(text)
    cited = citations(text)
    if route == "FULL" and not any(c["table"].startswith("analysis_") for c in cited):
        rep.evidence.append("a FULL answer cites no counted row")
    return rep
