"""The free lexicon gate in front of the model (architecture.md §5.2) — and the
record of what it rejects, so P1-MET-3 can measure what it costs.

EC-PRE, from the Myntra build: its lexicon + embedding prefilter kept only
76.6% of the relevant records (DECISIONS.md, 2026-08-19); the rest were
relevant by reasoning, not vocabulary, and would have vanished without trace.
So this gate is RECALL-FIRST. A record passes if it

  - contains any lexicon term (`codebook/lexicon_v1.yaml`), or
  - contains a strong retrieval phrase ("can't find", "scrolled through",
    "what to type", "search karu"), or
  - mentions a photo-like thing at all, in any script (round 2 — see passes()).

Everything else is MARKED `lexicon_rejected` at stage `prefilter` — never
deleted (A.1) — and `pipeline.validate.lexicon_probe` samples those marks and
asks the model how many were relevant after all (T-4 ≤ 5%). If the probe fails,
the gate is widened or dropped; it never silently stands.

    python -m pipeline.clean.prefilter
"""

from __future__ import annotations

import re

from pipeline.collect import config
from pipeline.common import db as dbm
from pipeline.common import runs as rmod

THING = re.compile(
    r"(?i)\b(photos?|pictures?|pics?|images?|screenshots?|screen ?shots?|selfies?|snaps?|"
    r"videos?|receipts?|documents?|scans?|albums?|gallery|memories|foto|tasveer|tasveerein|"
    r"google photos|ask photos|camera roll|whiteboard|prescription|id card|aadhaar|passport)\b"
    r"|(?i:photograph(ed|ing)?|screenshott?ed|snapped|clicked (a|the) (pic|photo)|"
    r"took (a|the|some) (pic|photo|picture|screenshot))")
# Strong retrieval phrases pass on their own: a story can describe the hunt
# without ever naming a photo ("no idea what to type… scrolled through 2022",
# "kya search karu"). Found by the authored-fixture test, 2026-09-26.
# Devanagari photo words — the round-1 probe's misses included "मेरी पुरानी फोटो…".
DEVANAGARI_THING = re.compile(r"(फोटो|फ़ोटो|तस्वीर|पिक्चर|फोटोज|फ़ोटोज़|चित्र|गैलरी|स्क्रीनशॉट)")
STRONG = re.compile(
    r"(?i)(can.?t find|cannot find|could ?n.?t find|unable to find|scroll(ed|ing)? "
    r"(through|back|for|down)|what to (type|search)|search(ed|ing)? for|"
    r"search (karu|kiya|kar|karke|karne)|dhoondh|nahi mil|mil nahi|nahin mil)")


def _lexicon() -> list[re.Pattern]:
    return [re.compile(re.escape(t).replace("\\'", "['’]?").replace("\\ ", r"\s+"), re.I)
            for t in config.lexicon_terms()]


def passes(text: str, lexicon: list[re.Pattern] | None = None) -> tuple[bool, str]:
    """(passes, why). `why` is stored on the mark so the probe can report which
    rule rejected what."""
    for p in lexicon if lexicon is not None else _lexicon():
        if p.search(text):
            return True, f"lexicon:{p.pattern[:40]}"
    if STRONG.search(text):
        return True, "strong retrieval phrase"
    # Round 1 of P1-MET-3 (2026-09-26) failed at 6.5%: requiring a retrieval
    # ACT beside the photo word missed Hinglish ("kaise ayenge", "dikh rahe"),
    # Devanagari and deleted/hidden-photo stories. A photo-like thing alone now
    # passes; only text that never mentions one is rejected.
    if THING.search(text) or DEVANAGARI_THING.search(text):
        return True, "photo-like thing"
    return False, "no photo-like thing"


def main() -> int:
    con = dbm.init()
    lex = _lexicon()
    with rmod.Run(con, "prefilter", model=None, estimate_usd=0,
                  rule="lexicon term, or strong retrieval phrase, or any photo-like thing "
                       "(round 2)") as run:
        # The gate's marks are its CURRENT judgement: a re-run replaces the
        # previous gate's marks (a probe's verdicts on them are kept in
        # data/artifacts/). Records set aside by cleaning are not re-judged.
        replaced = con.execute("DELETE FROM exclusions WHERE stage='prefilter'").rowcount
        rows = con.execute("SELECT record_id, source, text_clean FROM records WHERE record_id"
                           " NOT IN (SELECT record_id FROM exclusions WHERE story_id IS NULL)"
                           ).fetchall()
        rejected: dict[str, int] = {}
        for r in rows:
            ok, why = passes(r["text_clean"], lex)
            if not ok:
                con.execute("INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason,"
                            " detail, run_id) VALUES (?,?,?,?,?,?)",
                            (r["record_id"], r["source"], "prefilter", "lexicon_rejected", why,
                             run.run_id))
                rejected[r["source"]] = rejected.get(r["source"], 0) + 1
        con.commit()
        run.n_input, run.n_output = len(rows), len(rows) - sum(rejected.values())
        con.execute("UPDATE runs SET params_json=json_set(params_json,'$.replaced_marks',?)"
                    " WHERE run_id=?", (replaced, run.run_id))
        con.commit()
    print(f"prefilter: replaced {replaced} earlier marks · {len(rows)} checked · "
          f"{sum(rejected.values())} lexicon_rejected "
          f"· by source {rejected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
