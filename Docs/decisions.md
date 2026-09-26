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
| Reddit | `apify` — `webdatalabs~reddit-scraper-pro` | Reddit's self-serve API is closed to new developers (Myntra, `Docs/DECISIONS.md` 2026-08-19). Same actor Myntra used: 10 runs, $1.80, 4,750 records ≈ $0.38 per 1,000 |
| GP Help Community | `headless_render` — Playwright renders thread pages | Thread HTML carries no post text; the page loads it from `support.google.com/*/api`. Rendered, a thread yields the original post, its author and every reply. Fallback if rendering fails at scale: `apify` via `burbn~google-forums-search`; if that fails too, the PM is told |
| Play Store | `public_scraper_lib` — `google-play-scraper` | Myntra's route, 3,200 reviews collected |
| App Store | `public_feed` — Apple's customer-review RSS | 50 reviews per page in US and IN; capped near 500 per country, so several countries. `app-store-scraper` dropped: unmaintained, pins `requests<2.24` (broke the Myntra environment) |
| YouTube | `official_api` — YouTube Data API v3 | Key verified. Search costs 100 of 10,000 daily units, comments 1 — few searches, many comments |
| Stack Exchange | `official_api` — api.stackexchange.com | ~250 matching questions across Web Apps, Android and Ask Different for one query |
| Hacker News | `official_api` — HN Algolia search | 547 comments for "google photos" search |
| X / Twitter | `apify` — `apidojo~tweet-scraper` | ~$0.40 per 1,000 tweets |
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
which returns up to ~2,000 threads with title and first line in one load).
Of 1,999 listed on 2026-09-26, **52 (2.6%)** mentioned finding or searching;
the rest were deletion, backup, sync and account problems.

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
stories (the §0.4 loop-back). Apify this cycle: $6.06 of $10.

**YouTube over-delivered.** 3,845 comment threads against ~800 planned: the same
popular videos answer many terms. 91% of YouTube text never mentions a photo and
is set aside by the gate; 1,086 YouTube records go forward.
