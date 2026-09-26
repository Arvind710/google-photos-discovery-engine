# Decisions — Google Photos Discovery Engine

Decisions taken during the build that change or extend the design docs. Each
records what was decided, who decided it, the evidence, and what it costs.
Where a decision departs from [CTX], `architecture.md` or the Myntra precedent,
that is stated rather than smoothed over.

---

## D-1 — Sources and how each is collected (2026-09-26, decided by the PM)

### What changed

`architecture.md` §5.1 planned four sources: Reddit via `praw`, GP Help via
`httpx` + `selectolax`, Play Store, and App Store via `app-store-scraper`.
Tested on 2026-09-26, two of those four routes do not work, and the PM widened
the source list to cover everything [PS] names: "Google Photos
community/support discussions, social media conversations, forums and other
relevant public discussions".

| Source | Method (`records.collect_method`) | Evidence, 2026-09-26 |
|---|---|---|
| Reddit | `apify` — `webdatalabs~reddit-scraper-pro` | Reddit's self-serve API is closed to new developers (Myntra, `Docs/DECISIONS.md` 2026-08-19). Same actor Myntra used: 10 runs, $1.80, 4,750 records ≈ $0.38 per 1,000. **Those were comment-level records; whole threads cost ~$6.70 per 1,000 (D-4)** |
| GP Help Community | `headless_render` — Playwright renders thread pages | Thread HTML carries no post text; the page loads it from `support.google.com/*/api`. Rendered, a thread yields the original post, its author and every reply. Fallback if rendering fails at scale: `apify` via `burbn~google-forums-search`; if that fails too, the PM is told |
| Play Store | `public_scraper_lib` — `google-play-scraper` | Myntra's route, 3,200 reviews collected |
| App Store | `public_feed` — Apple's customer-review RSS | 50 reviews per page in US and IN; capped near 500 per country, so several countries. `app-store-scraper` dropped: unmaintained, pins `requests<2.24` (broke the Myntra environment) |
| YouTube | `official_api` — YouTube Data API v3 | Key verified. Search costs 100 of 10,000 daily units, comments 1 — few searches, many comments |
| Stack Exchange | `official_api` — api.stackexchange.com | ~250 matching questions across Web Apps, Android and Ask Different for one query |
| Hacker News | `official_api` — HN Algolia search | 547 comments for "google photos" search |
| X / Twitter | `apify` — `apidojo~tweet-scraper` **(replaced in the pilot by `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`, D-4)** | ~$0.40 per 1,000 tweets |
| Quora | `apify` — `fatihtahta~quora-scraper` | ~$0.99 per 1,000 records |

Schema deltas **A.9** (the five new `source` values) and **A.10**
(`records.collect_method`, NOT NULL) implement this. Both land before any
record exists.

### What this departs from, stated plainly

**Reddit, X and Quora publish `Disallow: /` for all agents in robots.txt**, and
Apify's actors work by getting past that. [CTX] §6.1 says "Respect each
platform's terms" and `architecture.md` §11 rests the public corpus's
defensibility on it.

The Myntra project reached the opposite decision in writing — its
`Docs/DECISIONS.md` (2026-08-19) declines Apify on exactly these grounds — and
then collected Reddit through Apify anyway without recording the reversal. This
project records it instead: **the PM decided on 2026-09-26 to use Apify for
Reddit, X and Quora**, because Reddit carries nearly all the long-form stories
that blocks C and D need, and the ≥300 core-story floor (T-20) is at risk
without it.

For the GP Help Community, the thread pages themselves are allowed by
`support.google.com/robots.txt`, but the page's own JavaScript fetches post
content from `/*/api`, which is disallowed, and the forum search (`/*/search`)
is disallowed too. Threads are discovered from the listing pages, not search.

### How it is disclosed

- `collect_method` on every record; the Data Bank shows source × method.
- Methodology (P6) states the method per source, including that three sources
  were collected through a third-party scraper against the platforms' stated
  robots policy.
- The corpus is still public data only: no login-walled content, PII scrubbed,
  authors pseudonymised with an env-only salt (EC-OPS-7, EC-OPS-8).

### Budget

Apify is billed separately from the $15 OpenAI ceiling. The PM upgraded the
Apify account; the monthly limit is **$10** (cycle 2026-09-19 → 10-18, $0.00
used at the time of writing). The P1A pilot measures the real cost per record
before the full collect.

---

## D-2 — GP Help threads are screened on their listing text before rendering (2026-09-26, Claude, disclosed)

Rendering a thread takes 2–3 seconds, and the forum's search is disallowed, so
threads are found from the listing page (`/photos/threads?max_results=N`,
which returns up to N threads with title and first line in one load).
Of 1,999 listed on 2026-09-26, **52 (2.6%)** mentioned finding or searching;
the rest were deletion, backup, sync and account problems.

*Update after the collect runs:* the listing honours larger N. It returned
1,998 of 2,000 in the pilot and **4,998 of 5,000** in the full collect. The
`SCREEN` pattern used in those runs is broader than the probe above: it matched
119 and 328 threads respectively (`runs.params_json.render`).

So `pipeline/collect/gp_help.py` renders only threads whose title or first
line matches a deliberately broad retrieval pattern (`SCREEN`). This is a
recall-first gate in front of the model's relevance pass, and it has the same
blind spot as the lexicon (EC-PRE): a thread that never says "find", "search",
"looking for" and the like in its opening line is not collected. The counts —
listed, matched, rendered, render failures — are stored in each run's params
and shown on the Data Bank.

## D-3 — Exact duplicates across different authors are kept when short (2026-09-26, Claude)

Myntra's dedupe (ported) removed exact duplicates across authors as well as
within one. For short text that is the EC-CLEAN-1 failure in another form: two
different people writing the identical line "search can't find old photos"
are two voices. The rule now removes an exact duplicate only when it shares an
author with the kept copy, or when the text is ≥ 25 words, where identical
wording means a quote or cross-post rather than coincidence. Near-duplicates
remain same-author only. Pinned by
`test_exact_duplicate_short_text_from_different_authors_is_consensus`.

## D-4 — What the P1A pilot found in the collectors (2026-09-26, Claude)

The pilot (981 records, all nine sources) surfaced four collector defects. Each
was silent — records kept arriving and looked fine — and each is now pinned by
a test.

1. **The X actor refused work while reporting SUCCEEDED.** `apidojo~tweet-scraper`
   caps runs per month for accounts on Apify's free plan; past the cap it
   returns `{"noResults": true}` placeholders. Replaced by the pay-per-result
   `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest` (search
   field `twitterContent`). `apify.log_says_limited()` now reads the run log
   whenever a run returns only placeholders, and records the query as
   **refused**, not as a zero yield (EC-COL-13).
2. **Long X posts were clipped at 280 characters.** The mapper preferred
   `fullText`, which in apidojo's output is the clipped field; `text` held the
   whole post (up to 23,778 characters). Caught by P1-INV-6. The mapper now
   takes the longer field, and the 18 affected records were re-mapped from the
   saved raw payloads (run `repair-x-truncation`) rather than re-bought.
3. **Permalinks carried usernames.** X URLs are `x.com/<handle>/status/<id>` and
   Quora answer URLs end `/answer/<Author-Name>` — PII in a public corpus, and
   outside the text the scrubber sees. Rewritten to `x.com/i/status/<id>` and to
   the question page with `#answer-<id>` (run `repair-permalink-pii`, 205
   records); P1-INV-4 now checks permalinks too.
4. **Play's country parameter is not a region.** `en-IN` and `en-US` returned
   the same reviews, so Play records carry no `region_hint`. App Store feeds are
   per storefront and keep theirs.

**Measured Reddit cost.** Whole threads (post + every comment) cost about
**$6.70 per 1,000 threads** — Myntra's $0.38 per 1,000 counted each comment as a
record. The full Reddit collect is sized to that figure, inside the $10 Apify
limit.

## D-5 — The full collect (P1E), the lexicon gate's two rounds, and a Reddit budget stop (2026-09-26, Claude)

**Collected.** 11,366 records from 10,956 people, all nine sources: YouTube 3,845 ·
App Store 2,500 · Play 2,000 · X 1,139 · Hacker News 577 · Stack Exchange 351 ·
GP Help 328 · Quora 320 · Reddit 306 (threads, each with its comments). After
cleaning and the gate, **5,291 are kept for segmentation** — close to the ~5,500
`architecture.md` §8 costs Pass 1 at, so the $1.20 estimate stands.

**The lexicon gate failed its first recall probe, and was widened.** Round 1
passed a record only if it named a photo-like thing AND a retrieval act; the
probe found 13 of 199 rejected records were core (6.5% > T-4's 5%) — Hinglish
("kaise ayenge", "dikh rahe"), Devanagari ("मेरी पुरानी फोटो…"), deleted and
hidden photos. Round 2 passes any record that mentions a photo-like thing in any
script; it rejects 2,468 records that never mention one (YouTube 1,237, App
Store 672, X 284, Play 249) and **passed at 2.5% (5 of 200)**. The round-1 judge
also called some plainly non-retrieval text "core" at minimal reasoning effort;
its prompt was NOT changed to pass the test — a generous judge overstates
misses, which is the safe direction. Two probes, $0.088.

**Reddit was stopped at 1.5× its estimate.** Whole threads cost ~$0.27 per
search term (27 threads × comments), against the $0.18 planned from the pilot.
Continuing all 26 terms would have run into the $10 Apify limit mid-run, so the
run was interrupted after three terms (recorded `failed`, its 44 threads kept;
the in-flight Apify run was aborted on Apify's side too), and re-run on ten
chosen terms. **Reddit ends at 306 threads, not the ~4,500 records
`architecture.md` §5.1 planned** — that figure assumed Myntra's comment-level
records and PRAW's zero cost. Each thread carries its full comment tree
(264 hold more than one post), so this is fewer, richer records, and it is the
first place to add volume if Phase 3's pilot projects fewer than 300 core
stories (the §0.4 loop-back). Apify this cycle: $6.06 of $10. *(Topped up to
448 threads before P2 — see D-6.)*

**YouTube over-delivered.** 3,845 comment threads against ~800 planned: the same
popular videos answer many terms. 91% of YouTube text never mentions a photo and
is set aside by the gate; 1,086 YouTube records go forward.

## D-6 — Reddit top-up on the terms the budget stop skipped, and Apify costs re-read (2026-09-26, decided by the PM)

**Why.** D-5's budget stop meant Reddit was searched on only 15 of the 26
lexicon terms. The 11 never run included **every utility-shaped term**
("picture of a receipt", "medicine photo", "photo of a document", "photo someone
sent me on whatsapp"). Sentimental vs utility is the axis every view splits on
([CTX] §15.4), and Reddit is the richest source, so its coverage was lopsided
before any story was counted. This is the §0.4 P1-F top-up, taken before P2
rather than after P3's pilot. It is collection only, with no schema or codebook
change, and the P1 gate was re-passed afterwards (60/60).

**What ran.** Seven terms: the four utility terms above, plus "found it by
accident", "how to find a photo I don't remember when" and "purani photo kaise
dhoondhe". Each ran as its own collect run at `-n 3` (9 subreddits × 3 threads).
A guard refused to start a term that could take the top-up past $2.85.
**142 new threads** (48 already held); Reddit is now **448 threads holding 5,493
posts**. The ~4,500 in `architecture.md` §5.1 counted posts, so that target is now met. Kept for
segmentation: 5,420 (was 5,291).

**Cost.** $1.88 on the Apify account ($6.06 → $7.94 of $10); ~$0.27 per term, as
D-5 measured. **$2.06 remains** for the cycle, which ends after submission.

**A collector bug this found.** `apify.run_actor` read a run's cost the moment
the run reported SUCCEEDED, but Apify keeps billing it for a short while after.
One run recorded $0.012 and settled at $0.242, and every earlier collect was
under-recorded ($3.90 recorded against $6.06 spent). The runner now re-reads
until the cost stops changing (`settled_usage`, pinned by a test). Every
recorded run was re-read from Apify's own records (run `repair-apify-usage`,
$5.52 → $6.99 recorded; the rest of the account total is the refused X actor,
the aborted Reddit run and the shape probes).

## D-7 — How Pass 1 (segmentation) is run, and what T-6 measures (2026-09-26, Claude, disclosed)

**Anchors, not copies.** The model returns each story's post number and its
first and last 5–12 words. Code locates both with an exact search inside that
post, and the stored story is the text between them (`pipeline/segment/stories.py`).
Every story is therefore verbatim by construction (T-1). Output tokens, 75% of
the bill (architecture.md §8), fall to a fraction of what a copied span costs.
Matching tolerates only whitespace runs and straight vs curly quotes; case,
spelling and punctuation must match. Unfound anchors and overlapping spans are
discarded AND counted.

**Packing.** The prompt is ~1,700 tokens and most records are short reviews, so
one request carries up to 12 records or 10,000 characters. Records longer than
10,000 characters are split on post boundaries (EC-COL-4, A.5); a single longer
post is sent whole, never cut. The fixtures are run shuffled and packed the same
way, so they test the conditions the corpus meets.

**The prompt as drafted disagreed with the fixtures in five places, and was
corrected before any run.** A follow-up post by the same author counts toward
`reaches_stage` but does not move the span (seg-07, seg-20). A story told about
someone else belongs to the post's author (seg-16). A quiet success is a story
(seg-11). A question to others or a general habit is not (seg-19). A record with
no story scores as `irrelevant` on the bucket fixtures.

**Two remediation iterations on the fixtures** (evals.md §8 loop, max three):
1. "Precise" is about what the person REMEMBERS, not the words they typed. A
   wrong or hedged cue is vague. A known item wanted before any search is a
   story. A new habit afterwards reaches 10.
2. `reaches_stage` is how far a story is TOLD, not where it first went wrong. A
   changed query is "trying something else" (≥ 7). One specific photo inside a
   person or category search is core when the rest is fuzzy.

Result on gpt-5-mini at `low` effort: story counts 95% exact (P2-MET-3 ≥ 85%),
T-9 92.9% (≥ 90%), `reaches_stage` at or above the fixture floor 94%, authored-story
buckets 90%, every anchor located. Stopped at two iterations, so as not to tune
toward these particular fixtures. Two known misses: seg-17 (a feature request
that mentions a red photo gets no story) and bb-12, which flips between runs.

**Effort.** `minimal` reasoning cost a third as much but failed story counts (75%)
and T-9 (85.7%), so the batch runs at `low`. The projection at `low` is $1.64
against architecture.md §8's $1.20. The recorded estimate stays $1.20, so
T-19 still halts at $1.80. The submit refuses only a projection that would cross
that halt. The submit's own recorded projection ($0.82) was taken from the
`minimal` fixture run by mistake. It is annotated in the run's params, and
the lookup now matches on effort.

**What T-6 measures.** evals.md sets T-6 at "≥ 75% agreement" on `reaches_stage`
without defining agreement. What `reaches_stage` decides is which coding blocks
run (C at ≥ 5, D at ≥ 7). So T-6 is agreement on that GATING BAND
(< 5 · 5–6 · ≥ 7), with exact and within-one agreement reported beside it. The
second coder is gpt-5 with the same prompt. Disagreements resolve upward
(EC-SEG-5), and every raised story is listed in the artifact.

## D-8 — gpt-5 confirms every story; two top-ups; 115 core stories and why (2026-09-26, decided by the PM)

**The dual check failed, in one direction.** On 60 story-bearing records,
gpt-5-mini and gpt-5 agreed on the story count in 25% (T-5 ≥ 80%) after the
second prompt iteration, and in 35% after the third. gpt-5 found fewer stories
in 39 of 60 records and more in none. Read one by one, the disputed candidates
were general deletion-recovery requests, device and export problems, and questions
about photos on the web: complaints with no particular photo sought. gpt-5-mini
kept calling them stories even after the prompt excluded them by name.

**Decision (PM): gpt-5 confirms every candidate** (`pipeline/segment/confirm.py`).
- gpt-5-mini stays the recall-first finder over every record.
- gpt-5 judges each candidate against the same definitions, reused verbatim
  from `segment_v1.md`, plus a short header of its own (`confirm_v1.md`).
- A rejected story is MARKED `no_story` with its story_id (A.1); a record whose
  every story is rejected is marked too.
- gpt-5's bucket is kept.
- `reaches_stage` takes the higher of the two, which resolves T-6 upward across
  the whole corpus.

The confirmation header needed one fix: gpt-5 first rejected [CTX]'s own
"searching my wife's name shows nothing" (a set defined by a precise cue IS a
target) and short, vague wanted-photo stories. On the fixtures, the two-stage
pipeline gives story counts 90% exact and T-9 92.9%.

**Two top-ups (the §0.4 loop-back), because core fell below 300:**
- **Free sources:** YouTube +14,817 comment threads, Hacker News +740, Stack
  Exchange +267. GP Help's 10,000-thread listing returned nothing.
- **X via Apify:** +3,903 posts for $1.58, all 26 terms at 250 posts each.
  Apify is now $9.52 of $10.

The recall probe was re-run after each top-up (T-4 4.0%, passed both times).

**Result:** 31,235 records, 11,794 read by Pass 1, **334 confirmed stories:
115 core (109 people), 219 adjacent.** Core by source: X 49, YouTube 30,
Hacker News 11, Quora 8, Reddit 8, GP Help 7, App Store 2. Play and Stack
Exchange have none. 71 of the first 88 core stories run to stage 7 or beyond,
so they are rich.

**Why so few, stated as a finding.** gpt-5 rejected 1,348 of the first 1,643
candidates, and a sample from every source bears it out. Public talk about
not finding a photo is overwhelmingly about photos that are GONE:
- deleted-photo recovery (thousands of YouTube comments under recovery
  tutorials, largely in Hinglish);
- backup and sync;
- dead phones and exports.

It is rarely about photos remembered only vaguely. That is EC-ANL-3's case
("much 'can't find it' is 'was never there'"), and it is a result for the deck,
not a defect to hide.

**What passes as a stated limitation** (`evals/limitations.yaml`,
implementationplan.md §0.3): T-5 (0.35, gpt-5-mini alone), T-6 (0.55,
mitigated upward), the zero-story rate (0.973), and T-20 (115 against 300).
**The PM chose to proceed** with the thin core:
- every share goes through `share()`, so thin cells show counts only;
- headline claims stay at one dimension;
- the Part 3 interviews carry more of the weight.

**Spend.** OpenAI $4.88 of $15 to date, against ~$1.60 planned by the end of
P2. Coding is priced per story, so coding 334 stories, not ~1,000, should
bring P3 in far under its $7.25.
