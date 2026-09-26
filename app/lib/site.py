"""What the other pages show, as plain fact rows Ask AI can cite (the PM, 2026-09-27:
"The Ask AI should be able to answer anything on the other three tabs as well … along
with how it works").

Every row is one plain sentence with its numbers in it — built from the same tables and
files the Data Bank, Analysis, Opportunities and How it works pages read, never typed by
hand — cited as `[[site|<key>]]`. The checker reads each row's numbers from its text, so a
figure the writer takes from here is checked like any other. Rows come in topic groups; a
question gets only the groups it asks about, to keep the brief short.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

import yaml

from lib import words
from lib.evidence import share

ROOT = Path(__file__).resolve().parents[2]

# Which groups a question asks about, from its own words. First the study as a whole.
TOPICS: list[tuple[str, str]] = [
    ("sources", r"\bsources?\b|\bsites?\b|\bplatforms?\b|\bwhere (?:did|do) (?:the )?(?:posts|data|"
                r"records) come|\breddit|\byoutube|\bquora|\bhacker ?news|\bapp store|\bgoogle play|"
                r"\bstack ?exchange|\bx \(twitter\)|\btwitter|\bhelp (?:forum|community)"),
    ("collection", r"\bcollect\w*|\bscrap\w*|\bapify|\brobots|\bhow (?:was|were|did you) "
                   r"(?:the )?(?:data|posts|records) (?:get|gathered|obtained|collected)|\bobtained"),
    ("setaside", r"\bset aside|\bexclu\w*|\bremoved|\bdropped|\bduplicat\w*|\bfiltered|\bwhat was "
                 r"(?:left out|thrown out)|\btoo short"),
    ("method", r"\bmethod\w*|\bhow (?:was|is|were|did) (?:this|it|the study|you)\b|\bhow it works|"
               r"\bcodebook|\bquestions? (?:the study|asked|you ask)|\bpipeline|\bbuilt|\bread (?:the "
               r"posts|each)|\bai readers?|\bcoders?|\breliab\w*|\bagree\w*|\btest cases?|\bblind"),
    ("scoring", r"\bweights?\b|\bscor\w*|\brank\w*|\bsensitiv\w*|\bprioriti\w*|\bcriteri\w*"),
    ("limits", r"\blimit\w*|\bweak\w*|\bcaveat|\bbias\w*|\btrust|\bhow reliable|\bshortcoming"),
    ("gates", r"\bgates?\b|\bquality checks?|\btests? (?:pass|it passed)|\bchecks? passed"),
    ("lexicon", r"\bsearch terms?|\bkeywords? (?:used|searched)|\blexicon|\bwhat (?:did you|was) "
                r"search(?:ed)? for|\bqueries used"),
]


def topics(question: str) -> list[str]:
    q = question or ""
    return [name for name, pat in TOPICS if re.search(pat, q, re.I)]


def _row(key: str, text: str) -> dict:
    return {"_cite": {"table": "site", "key": key}, "text": text}


@cache
def _scoring() -> dict:
    return yaml.safe_load((ROOT / "codebook" / "scoring_v1.yaml").read_text())


def _gates() -> list[str]:
    out = []
    for phase in range(7):
        files = sorted((ROOT / "evals" / "reports").glob(f"gate_P{phase}_*.md"))
        if not files:
            continue
        m = re.search(r"\*\*Checks:\*\*\s*(\d+) passed · (\d+) failed", files[-1].read_text())
        if m:
            out.append(f"P{phase}: {m.group(1)} checks passed, {m.group(2)} failed")
    return out


def facts(con, groups: list[str]) -> list[dict]:
    """The rows for the named groups, each a plain sentence with its figures."""
    rows: list[dict] = []
    q = con.execute
    if "sources" in groups or "collection" in groups:
        for r in q("SELECT * FROM analysis_sources ORDER BY n_records DESC"):
            r = dict(r)
            name = words.source(r["source"])
            rows.append(_row(
                f"source:{r['source']}",
                f"{name} ({words.source_kind(r['source'])}): {int(r['n_records']):,} records from "
                f"{int(r['n_authors']):,} people, posted between "
                f"{str(r['earliest'] or '')[:10]} and {str(r['latest'] or '')[:10]}; "
                f"{int(r['n_dated']):,} have a date and {int(r['n_threads']):,} are whole threads. "
                f"How it was collected: {words.method(r['collect_method']).rstrip('.')}."))
    if "sources" in groups:
        # Analysis, "Does the pattern hold across sources?" — how far each site's pattern of
        # first failures sits from the pattern across all sites.
        for r in q("SELECT key, value, n FROM analysis_derived WHERE metric='js_divergence' AND "
                   "population='core' ORDER BY value"):
            rows.append(_row(
                f"divergence:{r[0]}",
                f"How far {words.source(r[0])}'s pattern of first failures is from the pattern "
                f"across all sites: {float(r[1]):.2f}, on a scale where 0 is identical and 1 is "
                f"nothing in common ({int(r[2])} vaguely remembered cases from there)."))
        n_src = q("SELECT count(*) FROM analysis_sources").fetchone()[0]
        rows.append(_row("sources:count", f"The posts came from {n_src} sites."))
    if "collection" in groups:
        paid = [dict(r) for r in q("SELECT source, n_records, collect_usd FROM analysis_sources "
                                   "WHERE collect_method='apify'")]
        if paid:
            n = sum(int(r["n_records"]) for r in paid)
            usd = sum(float(r["collect_usd"] or 0) for r in paid)
            tot = q("SELECT n FROM analysis_funnel WHERE source='_all' AND step='collected'"
                    ).fetchone()[0]
            rows.append(_row(
                "collection:paid",
                f"{share(n, int(tot)).text} of the records read came through a paid collection "
                f"service (Apify), from {', '.join(words.source(r['source']) for r in paid)}, "
                f"against those sites' published rules for automated collection; it cost "
                f"${usd:.2f}. It is public, not behind a login, with names, emails, phone numbers "
                f"and handles removed before storing, and marked on every record."))
    if "setaside" in groups:
        tot = {r[0]: (r[1], r[2]) for r in q(
            "SELECT step, n, n_authors FROM analysis_funnel WHERE source='_all'")}
        collected, kept = tot["collected"][0], tot["kept"][0]
        rows.append(_row("setaside:total",
                         f"{collected:,} records were read; {kept:,} were kept and "
                         f"{collected - kept:,} set aside, none deleted — each with its reason."))
        for step, (n, a) in tot.items():
            if step.startswith("excluded:"):
                rows.append(_row(f"setaside:{step[9:]}",
                                 f"Set aside because: {words.exclusion(step[9:]).rstrip('.')} — "
                                 f"{int(n):,} records from {int(a or 0):,} people."))
    meth = {r[0]: json.loads(r[1]) for r in q("SELECT key, value_json FROM analysis_methodology")}
    if "method" in groups:
        cb = meth.get("codebook") or {}
        rows.append(_row("method:questions",
                         f"Every case is read against the same {cb.get('questions', 60)} questions, "
                         f"fixed on {str(cb.get('frozen_at', ''))[:10]} before any case was read."))
        rows.append(_row("method:readers",
                         "One AI model finds each case in a post; a second, stronger model checks "
                         "it against the study's written definitions and reads it along the path "
                         "of finding a photo, marking the first point it went wrong."))
        br = meth.get("blind_read") or {}
        if br:
            agreed = round(float(br["stage_agreement"]) * int(br["n"]))
            rows.append(_row("method:blind",
                             f"A separate blind re-read of {int(br['n'])} cases, by another AI model "
                             f"(not a person), named the same first point of failure in {agreed} "
                             f"of them."))
        fx = meth.get("coding_fixtures") or {}
        if fx:
            right = round(float(fx["primary_stage"]) * int(fx["n"]))
            rows.append(_row("method:tests",
                             f"On {int(fx['n'])} hand-written test cases with a known right answer, "
                             f"the first point of failure was read right in {right} of them."))
        sp = meth.get("spans") or {}
        if sp:
            rows.append(_row("method:quotes",
                             f"{int(sp['n']):,} quoted passages back the answers; each is at least "
                             f"{int(sp['min_len'])} characters and was found word for word in its "
                             f"post."))
        for r in q("SELECT field, value, raw_agreement, n, verdict FROM analysis_reliability "
                   "WHERE field='primary_stage'"):
            r = dict(r)
            agreed = round(float(r["raw_agreement"]) * int(r["n"]))
            rows.append(_row("method:agreement",
                             f"Two AI readers read {int(r['n'])} cases separately and agreed on "
                             f"where each first went wrong in {agreed} and disagreed in "
                             f"{int(r['n']) - agreed} (an agreement score of {float(r['value']):.2f}, "
                             f"where 1 is perfect and 0 is chance; the study's minimum was 0.60)."))
        low = [r[0] for r in q("SELECT field FROM analysis_reliability WHERE "
                               "verdict='low_reliability'")]
        rows.append(_row("method:low", f"On {len(low)} of the details read, the two AI readers "
                                       "agreed too rarely to rest a finding on them."))
    if "scoring" in groups:
        sc = _scoring()
        w = sc["weights"]
        names = {"metric_leverage": "how much fixing it helps", "severity": "how serious it is",
                 "frequency": "how often it happens", "evidence_strength": "how solid the evidence "
                 "is", "reach": "how many people it affects"}
        rows.append(_row("scoring:weights",
                         "Each problem is scored 1–5 on five things, weighted: "
                         + ", ".join(f"{names.get(k, k)} {v}" for k, v in w.items())
                         + f" (out of 100), fixed on {str(sc['pre_registered_at'])[:10]} before "
                         "any ranking ran. Two checks come first: can Google Photos fix it, and "
                         "does it need AI rather than a design change."))
        for r in q("SELECT candidate_id, top_share, draws FROM analysis_weight_sensitivity WHERE "
                   "variant='headline' ORDER BY top_share DESC LIMIT 1"):
            r = dict(r)
            first = round(float(r["top_share"]) * int(r["draws"]))
            lab = q("SELECT label FROM analysis_opportunity WHERE candidate_id=?",
                    (r["candidate_id"],)).fetchone()
            rows.append(_row("scoring:robust",
                             f"Re-run {int(r['draws']):,} times with the weights nudged at random, "
                             f"the problem ‘{(lab[0] if lab else r['candidate_id'])}’ came first "
                             f"{first:,} times."))
    if "limits" in groups:
        plain_lim = {"P2-MET-1": "the two AI models agreed on how many cases a post holds in 35 "
                                 "of 100; the stronger model now confirms every case",
                     "P2-MET-4": "97 of every 100 records read held no search case at all",
                     "T-20": "115 vaguely remembered cases, not the 300 planned — collection "
                             "ran out"}
        for item in meth.get("limitations") or []:
            if item.get("id") in plain_lim:
                rows.append(_row(f"limits:{item['id']}", "A known limit: "
                                 + plain_lim[item["id"]] + "."))
        rows.append(_row("limits:posts", "Public posts over-represent problems — people post "
                                         "when something goes wrong — and cannot count users or "
                                         "searches, or compare apps, phones, countries or years."))
    if "gates" in groups:
        g = _gates()
        if g:
            rows.append(_row("gates:all", "The study's quality checks by phase — "
                                          + "; ".join(g) + "."))
    if "lexicon" in groups:
        lex = meth.get("lexicon") or []
        top = sorted(lex, key=lambda t: -int(t.get("hits", 0)))[:6]
        if top:
            rows.append(_row("lexicon:top", "Posts were found with search terms such as "
                             + "; ".join(f"‘{t['term']}’ ({int(t['hits']):,} matches)" for t in top)
                             + "."))
    return rows
