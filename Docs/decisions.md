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
