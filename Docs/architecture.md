# Architecture — AI-Powered Discovery Engine (Google Photos Vague Retrieval)

**Status:** v1 — derived from `NextLeap Grad Projects.code-workspace.md` (**[CTX]**) and its codebook source [SOL-JOURNEY]
**Companion docs:** `edgecase.md` + `evals.md`, then `implementationplan.md`
**Host:** Streamlit Community Cloud, continuously deployed from a **public** GitHub repository
**Models:** `gpt-5` (coding, synthesis, Ask AI) · `gpt-5-mini` (relevance, segmentation, second coder). OpenAI is the only vendor
**Budget:** hard ceiling **$15**, enforced by a console spend limit
**Reference:** `myntra-discovery-engine` — design language and Ask AI answer contract only, per [CTX] §16
**Scope:** how the engine is built. What it must do lives in [CTX]; unprefixed `§n` references point there

---

## 1. The three constraints

**Time.** Deadline 7 Oct 2026, 15:59 IST. Today is 25 Sep. The engine is Part 1 of eight, with interviews, an MVP, user testing and a deck after it. **The engine gets four to five days.**

**Money.** $15 all-in. This is not a rounding constraint — it decides the model on every pass, forces the Batch API, and caps how much prose the coder may emit.

**Completeness.** 60 questions from [SOL-JOURNEY], none of which may be silently dropped.

These pull against each other, and §3.3 is where they are reconciled. [CTX] §16's instruction — minimum time, minimum complexity, reuse before design — produces a system smaller than it first appears it should be. Three components are deleted outright rather than optimised: corpus embeddings, UMAP, HDBSCAN.

| # | Decision | Answer | § |
|---|---|---|---|
| 1 | Unit of analysis | The **retrieval story**, not the post | 3.1 |
| 2 | What a code is, and where codes come from | [SOL-JOURNEY] Part 2, all 60 questions, with dispositions | 3.3 |
| 3 | Corpus | ~11,000 raw → ~1,000 stories → ~450 core | 4.2 |
| 4 | Coding | Four blocks, gated by how far the story goes | 5.3 |
| 5 | Questions public data can't answer | Coverage register → Part 3 interview guide | 3.4 |
| 6 | Emergent themes without clustering | One LLM call over `other:` values + a blind-read audit | 5.5 |
| 7 | Validation without a human gold set | Span verification + dual-model κ + adjudication + sanity strip | 5.6 |
| 8 | Scoring | Two gates, five weights, 1,000-run sensitivity, pre-registered | 6.2 |
| 9 | Verification of the app | Claude in Chrome against the live URL | 10 |
| 10 | Delivery | Continuous deploy, public repo, frozen corpus + live Try it | 9, 11 |

---

## 2. System overview

**The pipeline computes, the app displays.**

```
┌────────────────────── OFFLINE (laptop, a handful of runs) ────────────────┐
│  COLLECT        CLEAN         SEGMENT          CODE (4 blocks)            │
│  ┌───────┐    ┌────────┐    ┌──────────┐   ┌──────────────────────┐     │
│  │Reddit │    │dedupe  │    │post →    │   │A spine   (all 1,000) │     │
│  │GP Help│───▶│lang    │───▶│stories + │──▶│B memory  (core 450)  │     │
│  │Stores │    │PII     │    │bucket    │   │C system  (reach 5–6) │     │
│  │+5 more│    └────────┘    └──────────┘   │D outcome (reach 7–10)│     │
│  └───────┘                   gpt-5-mini    └──────────────────────┘     │
│                                                  gpt-5    │               │
│                    ┌──────────────────────┐              │               │
│                    │ EMERGENT THEMES      │◀─────────────┤               │
│                    │ + BLIND-READ AUDIT   │              ▼               │
│                    └──────────────────────┘   ┌──────────────────────┐  │
│                              │                │ VERIFY · ANALYSE     │  │
│                              └───────────────▶│ spans · κ · coverage │  │
│                                               │ crosstabs · scoring  │  │
│                                               └──────────────────────┘  │
│                                        ┌──────────────▼──────────────┐  │
│                                        │ data/corpus.db ◀── frozen   │  │
│                                        └─────────────────────────────┘  │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │ git push → Streamlit auto-redeploy
                                 ▼
┌──────────────── ONLINE (Streamlit Cloud, public URL) ──────────────────────┐
│ How it works · Data Bank · Analysis · Opportunities · Ask AI · Try it      │
│ read-only ────────────────────────────── Ask AI and Try it: the live calls │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why the split.** Community Cloud has ~1GB RAM, no persistent disk and sleeps. Streamlit re-executes the whole script on every widget interaction, so an in-app coding call would re-charge on each click — fatal at a $15 budget. [CTX] §15.6 requires a frozen corpus so the deck's numbers still match the link. And [CTX] §8.4 requires every number to drill through to its stories, which is only true if it is a stored row with a `run_id`.

**No vectors anywhere.** Nothing in [CTX] requires semantic search or corpus-wide clustering. Relevance is an LLM judgement, retrieval is BM25 over an already-coded corpus, emergent themes come from §5.5. The app ships with `streamlit`, `pandas`, `plotly`, `rank-bm25`, `openai`, `PyYAML`.

---

## 3. The codebook

### 3.1 The unit of analysis is the story

[CTX] §5: *"One user's account of one attempt to find a specific photo. A single post may contain zero, one or several stories."* What was **collected** and what is **analysed** are different tables, and the funnel counts both. Conflating them would make every number in [CTX] §8.4 wrong, since all of them are counts of stories.

### 3.2 What a code is

A **code** is a label drawn from a fixed, pre-written list and attached to a span of text. A **codebook** is that list plus the rules for when each label applies. The labels are written *before* the data is read, so the results can be counted.

Three layers, all from [SOL-JOURNEY] Part 2, and they are routinely conflated:

| Layer | Source | Example | Count |
|---|---|---|---|
| **Stage** | Part 2(a), the journey table | Stage 5 — *Interpretation and matching* | 11 (0–10) |
| **Question** — a field to fill | Part 2(b)/(c) IDs | `5.6 What response type does the user see?` | **60** |
| **Value** — the code itself | The bullets under each question | `zero_results` | 399 in v1 (estimated ~340 before sub-fields such as `date:` and `who:` were expanded) |

"Assign a code" means: *for question 5.6, pick one of its listed answers.* This is what [SOL-JOURNEY] Part 3 means by *"Turn the question bank into a codebook."* The question bank is not background reading — it is the literal enum.

**Worked example** ([CTX] §7.2's own):

> *"I remember a pic of a small café in Goa from a trip, no idea which year, search for 'cafe goa' shows nothing."*

| Field | Value | Basis |
|---|---|---|
| bucket | `core` | Known item, partial cues, search failed |
| photo_class | `sentimental` | Trip, café |
| cues recalled (2.1) | `where:place_type`, `where:named_place`, `event:trip` | The 2.1 taxonomy |
| cues forgotten (2.4) | `when:year` | "no idea which year" |
| query shape (4.1) | `several_keywords` | "cafe goa" |
| response type (5.6) | `zero_results` | "shows nothing" |
| **primary_stage** | `5` | She had usable cues and expressed them; the system returned nothing |
| **failure_owner** | `system` | Derived from stage 5 |
| outcome (9.x) | `not_stated` | The post doesn't say |
| evidence span | `"search for 'cafe goa' shows nothing"` | Verbatim, substring-verified |

Three things make this reliable rather than impressionistic: the model may pick **only** listed values or `not_stated` and is forbidden from guessing ([CTX] §8.1); every key choice requires a **verbatim quote**, checked with `str.find`; and the hard calls are settled by **boundary notes** written into the codebook. The hard call above is stage 5 vs stage 2 — she produced two real cues and got nothing back, so it is the system, not her memory. That rule is written down, not left to taste.

No clustering, no training. An LLM reading a rubric and filling a form, 1,000 times, consistently.

### 3.3 All 60 questions, with dispositions

Every question in [SOL-JOURNEY] Part 2 appears below. `Exp` is the expected public-data yield that sets its **starting** block; the pilot replaces it with a measurement (§3.4).

**Stage 0 — Library state (preconditions)**

| ID | Question | Block | Note |
|---|---|---|---|
| 0.1 | Is the target actually in this GP account? | A | Often stated; the whole `adjacent` bucket hinges on it |
| 0.2 | What metadata does it carry, and is it correct? | B | Date / location / faces / organisation — four sub-fields |
| 0.3 | How indexable is the content? | A | Partly inferable from the photo description |
| 0.4 | What is the library's composition? | C | Size, clutter share, duplication |
| 0.5 | What were the capture and organisation habits? | C | |

**Stage 1 — Trigger and intent**

| ID | Question | Block | Note |
|---|---|---|---|
| 1.1 | What triggered the need? | A | 9 value groups; strong signal for the sentimental/utility split |
| 1.2 | What will they do with it once found? | B | Decides what counts as success |
| 1.3 | How specific is the target? | B | Decides whether a substitute is acceptable |
| 1.4 | Urgency and physical context | B | |
| 1.5 | How much does it matter? | A | Feeds the severity rubric |
| 1.6 | Who is searching? | **R** | Rarely stated in public text |

**Stage 2 — Memory reconstruction**

| ID | Question | Block | Note |
|---|---|---|---|
| 2.1 | Which cues do they recall? | A | **The single most important question in the bank.** 10 cue families, multi-select |
| 2.2 | How confident and accurate is each cue? | B | `certain_wrong` is the direct evidence for the 5.3 hypothesis |
| 2.3 | How much do the cues narrow things down? | **R** | Requires judging the library, which the text does not show |
| 2.4 | What is typically missing? | A | Usually stated outright |
| 2.5 | Why is it missing? | B | |
| 2.6 | How sure are they it exists and is in GP? | B | |
| 2.7 | Mental model of how it can be found | B | |
| 2.8 | Do they gather cues from outside first? | B | Under-served behaviour; worth catching |

**Stage 3 — Strategy selection**

| ID | Question | Block | Note |
|---|---|---|---|
| 3.1 | Where do they look first? | B | WhatsApp-first is a §15.3 hypothesis |
| 3.2 | Which mode inside Google Photos? | A | Needed for "outcome by mode" (view 10) |
| 3.3 | Why that mode? | C | |
| 3.4 | If they avoid search, why? | B | The invisible-failure population |
| 3.5 | Single path or a combination? | C | |

**Stage 4 — Cue translation (articulation)**

| ID | Question | Block | Note |
|---|---|---|---|
| 4.1 | What shape does the first query take? | A | Store the literal query where given |
| 4.2 | Which cues make it into the query? | B | Drives the cue→query attrition analysis |
| 4.3 | What blocks expression? | B | The Stage 2 vs Stage 4 distinction lives here |
| 4.4 | How does their mental model shape phrasing? | C | |
| 4.5 | Which structured inputs do they use? | C | |

**Stage 5 — Interpretation and matching** *(system side — every value marked `inferred`)*

| ID | Question | Block | Note |
|---|---|---|---|
| 5.1 | Is the query parsed correctly? | C | |
| 5.2 | Does the index contain the cue at all? | C | Danger pair with 5.3/5.4 |
| 5.3 | Hard filters or soft signals? | C | [SOL-JOURNEY]'s stated headline hypothesis |
| 5.4 | Retrieved but badly ranked? | C | Danger pair with 5.2/5.3 |
| 5.5 | Can it infer across cues? | C | |
| 5.6 | What response type does the user see? | A | "zero results" is the most quotable fact in the corpus |

**Stage 6 — Scanning and recognition**

| ID | Question | Block | Note |
|---|---|---|---|
| 6.1 | What do they face? | C | |
| 6.2 | How do they scan? | **R** | Needs observation, not recollection |
| 6.3 | How do they judge a match? | C | |
| 6.4 | What makes judging hard? | C | |
| 6.5 | What do results teach them? | C | **The other headline hypothesis** — results as memory cues |
| 6.6 | How deep do they scan? | **R** | Needs observation |
| 6.7 | What do they do on a near-hit? | C | Anchor-and-pivot |

**Stage 7 — Diagnosis and adaptation**

| ID | Question | Block | Note |
|---|---|---|---|
| 7.1 | How do they explain the failure? | D | |
| 7.2 | Which tactic do they try next? | D | Ordered sequence where available |
| 7.3 | What new information do they use? | D | |
| 7.4 | Emotional state | D | Severity input only, never a headline ([CTX] §4.3) |
| 7.5 | Does the product help them refine? | D | |

**Stage 8 — Persistence**

| ID | Question | Block | Note |
|---|---|---|---|
| 8.1 | How many attempts, how much time? | **R** | [CTX] §3.3 names this as the example of unanswerable |
| 8.2 | What decides continue vs quit? | D | Sometimes stated ("gave up after 20 minutes") |
| 8.3 | What shape does the path take? | **R** | Needs observation |
| 8.4 | Any sense of warmer or colder? | **R** | Needs think-aloud |

**Stage 9 — Outcome**

| ID | Question | Block | Note |
|---|---|---|---|
| 9.1 | If found, how? | A | Which cue was decisive |
| 9.2 | What do they do after finding it? | D | |
| 9.3 | Did they settle for a substitute? | D | |
| 9.4 | If abandoned, why, and what fallback? | A | Workaround map (view 9) |
| 9.5 | Was the outcome false? | **R** | Mostly invisible by definition |
| 9.6 | Found later by accident? | D | |

**Stage 10 — Aftermath**

| ID | Question | Block | Note |
|---|---|---|---|
| 10.1 | How does trust change? | D | |
| 10.2 | Preventive habits adopted? | D | Reveals unmet need |
| 10.3 | Do they complain publicly? | — | Structurally 100% in this corpus. Coded as a **standing bias flag**, not a variable |

**Totals.** Block A 11 · B 13 · C 16 · D 11 · R (interview register) 8 · structural 1 = **60**, counted from the tables above. (An earlier draft of this line read "A 14 · B 14 · C 16 · D 12 · R 9", which sums to 66; `pipeline/common/codebook.py` pins the table's totals.)

Every question keeps its full value list from [SOL-JOURNEY]. Every question also gets `not_stated` and `other:<free text>`. Values are never invented.

### 3.4 The coverage register — nothing is dropped, some is reassigned

`R` above is a *starting* disposition, not a verdict. [CTX] §3.3 requires that questions public data cannot answer be **named explicitly and handed to Part 3**, and §9.5 makes that list a deliverable.

So:

1. **The pilot codes all 60 questions** on ~70 stories, regardless of block.
2. `pipeline/analyse/coverage.py` measures the `not_stated` rate per question.
3. Questions above **85% not_stated** move to the register. Questions below it move into the block their yield justifies — *including ones I marked `R`*. If 8.2 turns out to be stated 40% of the time, it gets coded.
4. `analysis_coverage` is published on the Methodology page: all 60 rows, each with its coverage rate and disposition.
5. The register generates Part 3 interview questions automatically, per stage.

This is what makes "we did not miss anything" a claim the document can defend. A question is either coded with a measured coverage rate, or named as an interview question with the measurement that justified it. Nothing is unaccounted for.

It also protects against my guesses being wrong in the expensive direction: I have marked 8 questions `R` on judgement, and the pilot costs under a dollar to check all of them.

### 3.5 The codebook is data

`codebook/journey_v1.yaml` is the single source of truth — consumed by the coding prompts, the evidence explorer's filters, the analytics and the app's labels. Frozen before the full run; a version bump forces re-coding.

```yaml
version: v1
frozen_at: null
stages:
  - id: "5"
    name: Interpretation and matching
    owner: system
    inferred: true        # renders as "inferred from user evidence", never as fact
    questions:
      - id: "5.3"
        block: C
        text: Are cues treated as hard filters or soft signals?
        plain: The system discarded the photo because one detail was wrong
        voice: "I said 2019 and got nothing — turns out it was 2020"
        values: [hard_filter_single_cue, and_logic_shrinks_recall, soft_ok, not_stated, other]
        metric_node: query_captures_usable_cue
        boundary_note: >
          5.3 is the system DISCARDING a correct target because a cue was wrong or
          over-strict. If the cue was never indexed at all that is 5.2; if the target
          came back but buried, 5.4. One data problem, one logic problem, one ranking
          problem — different owners, different solves. Do not collapse them.
```

`boundary_note` is the load-bearing field, and only about six questions need a real one: the **5.2 / 5.3 / 5.4** triple, and **Stage 2 vs Stage 4** (couldn't remember it vs remembered but couldn't say it). Getting the second wrong would misattribute the entire problem between the user's memory and the product's language understanding — which is the recommendation.

Alongside: `severity_v1.yaml` ([CTX] §8.2's rubric as data), `metric_nodes_v1.yaml`, `scoring_v1.yaml`, `lexicon_v1.yaml`, `plain_language.yaml`.

---

## 4. Data model

SQLite (`data/corpus.db`) — one file, zero config, queryable, git-committable, read directly by Streamlit.

```sql
CREATE TABLE records (               -- raw collected material, immutable
  record_id TEXT PRIMARY KEY,        -- sha1(source || native_id)
  source TEXT NOT NULL,              -- reddit|gp_help|play|appstore|youtube|stackexchange|hackernews|x|quora (A.9)
  collect_method TEXT NOT NULL,      -- official_api|public_feed|public_scraper_lib|headless_render|apify (A.10, D-1)
  source_url TEXT NOT NULL,          -- permalink — no record without one
  native_id TEXT,
  author_key TEXT,                   -- salted hash; salt is env-only, never committed (§11)
  created_at TEXT,
  text_raw TEXT NOT NULL, text_clean TEXT NOT NULL, text_en TEXT,
  lang TEXT, rating INTEGER, engagement INTEGER, thread_context TEXT,
  platform_hint TEXT,                -- android|ios|desktop|unknown
  region_hint TEXT,                  -- §15.3: cross-tab dimension, never a filter
  collect_query TEXT,                -- which lexicon term surfaced it — bias audit
  collected_at TEXT NOT NULL, ingest_run_id TEXT NOT NULL
);

CREATE TABLE exclusions (            -- what was dropped and why — a finding in itself
  record_id TEXT, source TEXT, stage TEXT, reason TEXT, detail TEXT, run_id TEXT
);

CREATE TABLE stories (               -- the unit of analysis
  story_id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(record_id),
  ordinal INTEGER NOT NULL, text TEXT NOT NULL,
  bucket TEXT NOT NULL,              -- core|adjacent|irrelevant
  bucket_reason TEXT NOT NULL, bucket_conf REAL NOT NULL,
  reaches_stage INTEGER,             -- furthest stage the story narrates — gates blocks C/D
  run_id TEXT NOT NULL
);

CREATE TABLE story_spine (           -- block A, one row per story
  story_id TEXT PRIMARY KEY REFERENCES stories(story_id),
  photo_class TEXT NOT NULL,         -- sentimental|utility|both|unclear   §15.4
  media_type TEXT NOT NULL,          -- photo|screenshot|document|video|mixed §15.1
  photo_subtype TEXT,
  primary_stage TEXT NOT NULL,       -- 0..10 — where it FIRST went wrong
  failure_owner TEXT NOT NULL,
  metric_node TEXT, outcome TEXT NOT NULL, mode_used TEXT,
  severity INTEGER, urgency TEXT,
  workaround INTEGER, workaround_text TEXT,
  coding_conf REAL NOT NULL,
  why TEXT NOT NULL,                 -- ONE clause, ~15 words. Audit trail at minimum cost (§8)
  run_id TEXT NOT NULL
);

CREATE TABLE story_codes (           -- blocks B/C/D — long and narrow, one row per value
  story_id TEXT REFERENCES stories(story_id),
  question TEXT NOT NULL,            -- "2.1" … "10.2"
  value TEXT NOT NULL,               -- listed value, not_stated, or other:<free text>
  accuracy TEXT,                     -- 2.2 only
  seq INTEGER,                       -- ordered tactics (7.2) keep their order
  inferred INTEGER NOT NULL DEFAULT 0,  -- all Stage 5 values carry this
  confidence REAL NOT NULL, run_id TEXT NOT NULL,
  PRIMARY KEY (story_id, question, value, run_id)
);

CREATE TABLE evidence (              -- substring-verified before write (§5.6)
  story_id TEXT, field TEXT NOT NULL, span TEXT NOT NULL,
  verified INTEGER NOT NULL, run_id TEXT,
  PRIMARY KEY (story_id, field, run_id)
);

CREATE TABLE queries (               -- literal queries users reported typing
  story_id TEXT, query_text TEXT NOT NULL, shape TEXT,
  attempt_no INTEGER, worked INTEGER, run_id TEXT
);

CREATE TABLE double_coding (story_id TEXT, field TEXT, coder TEXT, value TEXT, run_id TEXT);
CREATE TABLE analysis_reliability (
  field TEXT PRIMARY KEY, metric TEXT, value REAL, n INTEGER,
  verdict TEXT,                      -- ok|low_reliability
  run_id TEXT
);
CREATE TABLE analysis_coverage (     -- §3.4 — all 60 questions, published
  question TEXT PRIMARY KEY, stage TEXT, block TEXT,
  n_coded INTEGER, n_not_stated INTEGER, coverage REAL,
  disposition TEXT,                  -- coded|register
  run_id TEXT
);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, stage TEXT, started_at TEXT, finished_at TEXT,
  model TEXT, prompt_version TEXT, codebook_version TEXT,
  n_input INTEGER, n_output INTEGER,
  input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  cost_usd REAL, params_json TEXT
);
```

`story_codes` is long and narrow rather than 60 sparse columns: most questions do not apply to most stories, and adding a question becomes a codebook edit rather than a migration.

**Emergent themes (A.12, D-10):** `story_themes (story_id, theme, span, run_id)` — themes the PM approved after the codebook froze, beside it rather than in it, each tag carrying a span verified against `text_clean`.

**Materialised analysis tables**, precomputed once and read by both the app and Ask AI, every one carrying `n`, denominator and `run_id`, mapping to the thirteen views in [CTX] §8.4:

`analysis_funnel` · `analysis_stage_prevalence` · `analysis_failure_owner` · `analysis_metric_node` · `analysis_cue_matrix` · `analysis_cue_to_query` · `analysis_query_shape` · `analysis_photo_type` · `analysis_tactics` · `analysis_workaround` · `analysis_mode_outcome` · `analysis_crosstab` (one generic table: `dim_a, val_a, dim_b, val_b, n, denom`) · `analysis_source_stage` · `analysis_opportunity` · `analysis_weight_sensitivity` · `analysis_method_flags` · `analysis_coverage` · `analysis_reliability`

**Design rule:** the app performs no aggregation over raw stories. Everything displayed is a `SELECT` from a materialised table — which is what guarantees Ask AI and the charts cannot disagree.

**The minimum-n rule is code, not discipline.** [CTX] §15.5's three tiers live in one function, and every view renders shares through it:

```python
def share(n, denom):
    """(text, tier, colour). No caller formats a share itself."""
    if denom < 30:  return (f"{n} of {denom}", "insufficient", GREY)
    if denom < 80:  return (f"{pct(n,denom)} ({n} of {denom}) · directional", "directional", …)
    return (f"{pct(n,denom)} ({n} of {denom})", "comparable", …)
```

One helper makes "never a percentage without its denominator" structurally true rather than remembered.

---

## 5. Collection, coding, validation

### 5.1 Sources

**Revised 2026-09-26 — `Docs/decisions.md` D-1.** The original plan had four sources: Reddit via `praw`, GP Help via `httpx` + `selectolax`, Play, and App Store via `app-store-scraper`. Tested on the day, Reddit's API is closed to new developers, GP Help threads carry no post text in their HTML, and `app-store-scraper` is unmaintained. The PM also widened the list to every source type [PS] names. Raw targets are planning figures; the P1A pilot measures yield and cost per record before the full collect.

| Source | Method (`collect_method`) | Raw target | Why |
|---|---|---|---|
| **Reddit** | `apify` — `webdatalabs~reddit-scraper-pro` | ~4,500 **posts** | Longest narratives, real cue vocabulary, actual tactics. Carries blocks C and D. The target counts posts and comments, the unit Myntra stored as records. Here a whole thread is one record (A.11), so the P1 collect was **306 threads holding 3,751 posts** (D-5), and after the top-up on the terms the budget stop had skipped it is **448 threads holding 5,493 posts** (D-6) |
| **GP Help Community** | `headless_render` — Playwright on thread pages (fallback: `apify`) | ~1,500 | Explicit "can't find my photo" threads; replies carry workarounds |
| **Play Store** | `public_scraper_lib` — `google-play-scraper` | ~2,000 | Volume, India-heavy. Mostly block A only — and that ratio is a reported finding |
| **App Store** | `public_feed` — Apple's customer-review RSS, several countries | ~1,000 | Cross-platform comparison |
| **YouTube** | `official_api` — Data API v3 comment threads | ~800 | Reactions to search and Ask Photos tutorials; "tried this, didn't work" |
| **X** | `apify` — `kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest` (`apidojo~tweet-scraper` refused work on Apify's free plan, D-4) | ~600 | Real-time frustration, Ask Photos reactions |
| **Quora** | `apify` — `fatihtahta~quora-scraper` | ~300 | Long-tail stories, Indian users |
| **Stack Exchange** | `official_api` — Web Apps, Android, Ask Different | ~200 | Detailed, technical retrieval problems |
| **Hacker News** | `official_api` — Algolia search | ~200 | Detailed comparisons with Apple Photos and others |

Public data only — no login-walled content. **Reddit, X and Quora publish `Disallow: /` for all agents in robots.txt, and Apify's actors get past that**; the PM decided to use them anyway, and this is disclosed per record (`collect_method`), on the Data Bank and in Methodology (D-1). Every collector records the `collect_query` that surfaced each item, so collection bias is auditable. The [CTX] §6.2 seed lexicon lives in `lexicon_v1.yaml` with per-term hit counts — a required reproducibility output. Apify is billed separately from the $15 OpenAI ceiling (≤ $10/month).

### 5.2 The pilot decides everything

Run the whole pipeline on ~600 raw records **first**, coding all 60 questions. It measures four things that the rest of the plan depends on: story yield per record, core share, per-question coverage (§3.4), and real cost per story. Under a dollar, and it converts every estimate in §8 into a measurement on day one — while there is still time to change the plan.

**Cleaning:** exact-hash dedupe, then near-dedupe **within a single author only** — cross-author duplication is the finding, not noise. Hindi/Hinglish translated into `text_en`, original always retained. PII scrubbed to typed placeholders before storage, which on a public repo (§11) is a hard requirement.

**Prefilter:** free lexicon gate, then the LLM pass. No embedding gate — `gpt-5-mini` on a short review costs a fraction of a cent, and buying marginal precision with an embeddings API and a vector file is a bad trade. Recall matters more here; the LLM pass is the precision step.

### 5.3 The four coding blocks

| Pass | Model | Runs on | Produces |
|---|---|---|---|
| 1 Relevance + segmentation | gpt-5-mini | ~5,500 records | 0..n stories each, bucketed, with `reaches_stage` |
| 2 Block A — spine | gpt-5 | all ~1,000 stories | `story_spine` + evidence |
| 3 Block B — memory & articulation | gpt-5 | ~450 core | 2.x, 4.x, 1.x, 3.x detail |
| 4 Block C — system & recognition | gpt-5 | stories reaching stage 5–6 (~300) | 5.x, 6.x, 0.4–0.5, 3.3, 3.5, 4.4–4.5 |
| 5 Block D — adaptation to aftermath | gpt-5 | stories reaching stage 7+ (~250) | 7.x, 8.2, 9.x detail, 10.x |

**Blocks are gated by how far the story actually goes.** A story that ends at "search shows nothing" has no Stage 7–10 content, so running block D on it would pay for a page of `not_stated`. `reaches_stage`, set during segmentation, is what makes the budget work — it is the single largest cost saving in the design after Batch.

Pass 1 does segmentation and bucketing in one call: the model must read the post either way, so splitting them would double the call count for nothing. **The boundary that decides it is vague vs precise retrieval** — *"searching my wife's name shows nothing"* is `adjacent` (precise cue, failed), *"that café in Goa, no idea which year"* is `core`. [CTX] §7.2's calibration table goes into the prompt verbatim.

Each coding call carries the relevant codebook slice in a **cached prefix**, stable across every story, with the story in the fresh suffix. Structured outputs with `strict: true` so the schema is enforced rather than hoped for.

**As built (2026-09-26, `Docs/decisions.md` D-9).** One request per story, not one per block: the prefix is the WHOLE codebook (`prompts/code_v1.md` + the codebook rendered from `journey_v1.yaml`), and the story's blocks decide which questions its schema asks. With 334 stories of 200–400 characters, the codebook is the input; the Batch API cached 86% of it. Core stories (115) were asked all 59 bank questions — the pilot and the coverage register in one run; adjacent stories Block A, plus C at `reaches_stage` ≥ 5 and D at ≥ 7. Core ran at `low` reasoning effort, adjacent at `minimal`. `failure_owner`, `metric_node`, `severity` and 10.3 are fixed rules in code, not model answers; 2.2 is stored as cue (`value`) + judgement (`accuracy`). Every quote is located in `text_clean` and stored as the matched slice.

`why` is **one clause of about 15 words**, not a paragraph. It preserves the audit trail [CTX] §8.1 requires and the disagreement analysis §5.6 needs, at roughly a fifth of the output cost of full reasoning. This is a direct concession to the $15 ceiling and it is the right one — the long form buys marginal boundary accuracy at a price the budget cannot pay.

### 5.4 Model assignment, and the experiment hidden inside it

`gpt-5-mini` for pass 1, `gpt-5` for coding. But the §5.6 dual-coding sample runs **mini against gpt-5 on the same 100 stories** — so the reliability check doubles as a model-choice experiment. High κ means the cheap model is good enough and more work can move to it; low κ means we caught it on 100 stories instead of 1,000. Free information from a check we are running anyway.

### 5.5 Emergent themes without clustering

[CTX] §8.3 asks to cluster the *emergent and uncoded values* and propose new codes with example stories. That is what this does:

- **Residual pass.** Collect every `other:<free text>` value plus low-confidence stories; one gpt-5 call groups them, names each group, and proposes candidate codes with exemplar ids.
- **Blind-read audit.** Sample ~60 *confidently* coded stories; ask a model, with no sight of the assigned code, what the story is about; compare. This catches what the residual pass cannot — themes the codebook confidently **mis-codes** rather than leaves as `other`.

**As run (D-9, D-10).** The residual pass read 187 `other:` values, 126 low-confidence stories and 14 blind-read disagreements and proposed 12 groups; six were already counted under listed values. The PM approved four as **emergent themes**, kept beside the frozen codebook (`codebook/emergent_themes_v1.yaml`, table `story_themes`, schema A.12) and tagged across every story — gpt-5-mini proposes with a verbatim quote, gpt-5 confirms. Not pre-registered and each below 30 stories, they are reported as counts only and never ranked. The blind read ran on the 60 most confidently coded stories: 77% stage agreement.

Together these are the guard against codebook blindness ([CTX] §13), and §15.7 makes them more important, not less: with no human reviewing samples, they are the only views of the data the question bank did not shape. Neither needs UMAP. At ~1,000 short stories, density clustering would produce noisy clusters and a large noise bucket anyway.

The two diagnostics clustering *did* provide at Myntra come back free from the dual-coding confusion matrix: systematic disagreement on a field **is** the "boundary is wrong" signal, read directly.

### 5.6 Validation without a human gold set

Per [CTX] §15.7. Five checks, honestly bounded.

1. **Evidence-span verification — deterministic, and the highest-value check in the system.** Every span must be a literal substring of `stories.text` after normalisation. Not a model judging a model: `str.find`. Failures are re-coded once, then dropped and counted. This catches the failure mode that most threatens the analysis — a fabricated quote propping up a tag — with certainty and at zero cost.
2. **Dual-model coding** on a stratified 100 stories. Cohen's κ per single-select field, Jaccard per multi-select.
3. **Per-field reliability gate.** κ < 0.6 flags the field `low_reliability` and **bars it from headline claims and from the recommendation**. Enforced by the app reading the verdict column, not by anyone remembering.
4. **Adjudication.** A third gpt-5 call sees the story and both codings and picks or writes the correct value with a rationale.
5. **Reader-facing sanity strip.** Methodology shows 10 random coded stories with source text, tags and spans side by side — relocating human validation from the PM to the evaluator, which reads as a credibility asset rather than a gap.

**Disclosure is part of the design.** Methodology states that there is no human-adjudicated gold standard, that these are inter-model agreement plus deterministic verification, and that **agreement measures consistency, not correctness — two models can agree and both be wrong.**

### 5.7 Derived analyses that answer [CTX]'s actual questions

| Analysis | From | Answers |
|---|---|---|
| **Cue matrix** | 2.1 × 2.2 × 2.4 | [CTX] §3.2 — what people remember, forget, and get wrong |
| **Cue → query attrition** | 2.1 minus 4.1, by 4.2/4.3 | How users formulate searches with incomplete memory |
| **Certain-but-wrong rate** | 2.2 | Direct evidence for the 5.3 hard-filter hypothesis |
| **Results-as-cues** | 6.5 × outcome | [SOL-JOURNEY]'s headline hypothesis: do results help people remember more? |
| **Anchor-and-pivot** | 6.7 | A tactic that is neither search nor refinement |
| **Workaround intensity** | 9.4 × 10.2 | Effort proves unmet need better than complaint volume |
| **Source divergence** | Jensen–Shannon per source | Separates real signal from one community's artefact |
| **Severity × prevalence** | 2×2 | High-severity, low-prevalence problems are invisible to volume ranking |

---

## 6. Opportunities and recommendation

An opportunity is **primary stage × failure mode × segment** ([CTX] §9.1). Each card carries a plain-language problem statement framed as *why retrieval fails despite partial memory* — never "search is hard" — plus stages, failure owner, metric node, segments, counts and share, source spread, severity, 3–5 anonymised quotes, workarounds, the hypothesised point where intelligence is needed, and open interview questions.

**Scoring — two gates, then five weights**, exactly as [CTX] §15.2 fixes it, in `codebook/scoring_v1.yaml`:

```yaml
pre_registered_at: "<set before the first ranking run>"
gates:
  addressable_by_gp: {min: 3}     # GP cannot fix it → not an opportunity
  ai_necessity:      {min: 3}     # a UI tweak would do → fails the brief's test
weights: {metric_leverage: 30, severity: 25, frequency: 20,
          evidence_strength: 15, reach: 10}
```

Gated-out candidates are **shown, greyed, with the failing gate named** — that funnel is itself a deck slide. Weights are adjustable as [CTX] §9.2 requires, but the pre-registered set produces the headline and its timestamp is displayed. **Sensitivity:** 1,000 runs perturbing all five weights ±10 absolute; ≥80% top-stability is robust, <60% presents the top two as co-leaders. Computed offline, so moving a slider is a lookup.

**Recommendation and Part 3 handoff** are generated from the analysis tables, never from raw stories: top opportunity and runner-up with the chain (metric node → evidence → stage → root cause), target-segment direction, root-cause hypothesis, where intelligence is needed, and **what would falsify it** ([CTX] §9.4) — all labelled hypotheses. The handoff adds screener criteria, per-stage interview prompts **built from the §3.4 register**, and representative retrieval tasks drawn from real stories.

---

## 7. Ask AI

Contract and planner/checker split reused from the Myntra engine per [CTX] §16; corpus vocabulary, query registry and one checker rule are new.

**Two LLM calls, and only two.** Step 1 plans (gpt-5-mini), step 4 writes under contract (gpt-5). Retrieval, the answerability gate and verification are deterministic code in between. That split makes *refuses when it should* and *never invents a number* properties of the program rather than of the prompt. The restatement is shown above every answer — a misread question answered confidently is the worst failure this system can produce.

**Four retrieval channels.** (1) **Structured facts** — whitelisted parameterised queries over `analysis_*`; the planner picks which, never writes SQL, and receives `{stage: 5, stories: 128, denominator: 412}` rather than estimating from passages. (2) **Verbatim evidence** — BM25 over `stories.text`, filtered to the questions or values the plan names; the corpus is already coded, so "show me 6.5 stories" is an exact filter. (3) **Disconfirming evidence** — deliberately retrieves against the emerging answer. (4) **Method and reliability** — source mix, coding confidence, **κ**, **coverage rate**, registered flags. Channel 4 carries real weight here: it is how an answer knows whether the field it is quoting can be trusted, and whether the question was answerable at all.

**The gate** is deterministic comparison of the plan's `evidence_needed` against what returned, with the §4 thresholds applied. FULL / PARTIAL (names the unsupported part in the first two sentences) / NONE. Refusal is an outcome of code, not of prompt compliance.

**The answer contract:** one short sentence carrying a citation → the number that settles it, percentage first with the count beside it → one verbatim quote → a caveat clause citing a method flag → a single italic closing question. 60–120 words. No label-and-colon openings. Plain names in prose, question ids only in citations.

**The proxy-discipline rule is rewritten, and it is the most important line in the prompt.** The Myntra version said a share is a share of discussion, never a conversion rate. Here the trap is sharper because **the goal metric genuinely is a retrieval success rate**. A reader who takes "31% of core stories broke at Stage 5" for "31% of retrieval attempts fail at Stage 5" has misread the engine as measuring the exact thing it cannot. The rule: *every share is a share of coded public stories — never a retrieval success rate, never a share of users, never a share of searches.*

**Verification, plus one rule added from testing.** The checker covers unsupported numbers, unverifiable quotes, citations not retrieved, uncited claims, out-of-scope claims and funnel phrasing; one bounded repair, then an explicit unverified banner rather than a loop. Testing the live Myntra app on 25 Sep 2026, both answers opened their caveat with `Caveat:` — a construction the prompt explicitly forbids, with no checker rule behind it. **Rules backed by the checker hold; rules living only in the prompt drift.** `check_label_colon` ships from day one.

---

## 8. Cost — the $15 ceiling

| Line | Model | Batched |
|---|---|---|
| Pass 1 — relevance + segmentation, ~5,500 records | gpt-5-mini | ~$1.20 |
| Block A — spine, 1,000 stories | gpt-5 | ~$2.40 |
| Block B — memory & articulation, ~450 | gpt-5 | ~$1.30 |
| Block C — system & recognition, ~300 | gpt-5 | ~$0.90 |
| Block D — adaptation to aftermath, ~250 | gpt-5 | ~$0.75 |
| Reliability: dual-code 100 + adjudicate | mini + gpt-5 | ~$0.50 |
| Emergent themes + blind-read audit | gpt-5 | ~$0.60 |
| Recommendation + handoff | gpt-5 | ~$0.60 |
| Pilot — 600 raw, all 60 questions | mixed | ~$0.80 |
| One re-run of Block A after codebook repair | gpt-5 | ~$2.40 |
| Ask AI testing + demo, ~80 questions | mini + gpt-5 | ~$2.80 |
| **Total** | | **~$14.25** |

**The four decisions that made $15 reachable**, in order of size:

1. **Batch API on every pipeline pass** — a straight 50% cut. Mandatory, not optional. The coding job is submitted overnight, so the turnaround costs a night rather than a day.
2. **Block gating by `reaches_stage`** — blocks C and D run on 300 and 250 stories rather than 1,000. Without this the pipeline roughly doubles.
3. **`gpt-5-mini` on pass 1** — the largest record count and the simplest judgement.
4. **`why` as one clause** — output tokens are ~75% of the bill and this was the biggest single line.

**Two honest caveats.** ~$14.25 against a $15 cap leaves no room for a *second* re-run; the first cuts if it comes to that are block D (−$0.75) and Ask AI testing down to 50 questions (−$1.00). And these are estimates against approximate per-token rates — the only *measured* anchors are the Myntra repo's own ($0.0349/question on gpt-5 at low effort, $0.0051 on mini).

**Measured, 2026-09-26 (end of P3).** $12.89 spent, from the `runs` table:

| Line | Plan | Actual | Why it moved |
|---|---|---|---|
| Pass 1 — find (gpt-5-mini) + confirm (gpt-5), incl. two top-ups | ~$1.20 | $4.70 | Re-segmentation, dual checks, and a gpt-5 confirmation of every candidate (D-7, D-8) |
| Coding, blocks A–D + pilot, 334 stories | ~$6.15 | $3.85 | 334 stories, not ~1,000; one call per story with a cached codebook (D-9). Includes the Stage 0 re-code and retries |
| Fixture loop (three runs) + a token probe | cents | $3.11 | Coding fixtures cost ~$1.65 synchronous at `low`; later runs went through Batch |
| Reliability, blind read, residual, themes | ~$1.10 | $1.04 | |
| Probes (P1) | ~$0.05 | $0.18 | Four recall probes across three top-ups |

**$2.11 remains** for recommendation/handoff (~$0.60) and Ask AI (~$2.80 planned), so Ask AI testing is cut to fit (implementationplan.md §7).

**So the ceiling is enforced by a hard spend limit in the OpenAI console, set to $15 before the first call — not by this table being right.** The `runs` table records actual tokens and cost per pass, and the pilot replaces every figure above with a measurement on day one. This excludes the Claude Code budget for building it, which is separate.

**Scale.** At ~450 core stories the [CTX] §15.5 tiers land well: sentimental vs utility ~225/cell (comparable), photo class × platform ~110/cell (comparable), three dimensions breaches the floor. **Headline claims cap at two cross-tab dimensions** — arithmetic, not preference. Below 300 core the corpus fails [CTX] §14.3 and collection must continue.

**Runtime.** Ask AI ~$0.035/question at 9–13s; Try it ~$0.02, rate-limited, with a per-session cap on the public URL. Every other page load is a cached SQLite read.

---

## 9. CI/CD

The repo is public and Streamlit Cloud tracks the default branch, so **every push to `main` is a deploy**.

| Concern | Approach |
|---|---|
| Trigger | Push to `main` → automatic rebuild. No manual deploy step |
| CI | One GitHub Actions workflow: `ruff`, the deterministic tests (schema invariants, span verification, the share helper, every checker rule), and a **secret scan**. Under two minutes — a slow pipeline gets skipped |
| Not in CI | No LLM calls. Model-dependent evals cost money; they run deliberately from the laptop and their reports are committed |
| Artifacts | `corpus.db` committed; ~1,000 stories ≈ 10–18MB. Past ~100MB, a Release asset fetched on boot |
| Stale-module trap | Cloud reruns the entry script **without restarting the process**, so a module already in `sys.modules` keeps old definitions — a view calling a helper added in the same push dies with `AttributeError` on the deployed app while working locally. Editing a requirements file forces a real restart: keep a `rebuild-token:` line and bump it on every push touching `app/lib/`. This cost the Myntra build a broken deploy on 2026-08-22 |
| Verification | Every deploy checked against the live URL by Claude in Chrome (§10), not assumed from a green build |
| Rollback | `git revert` and push |
| Corpus freeze | Footer shows *"Corpus v1.0 — N core stories, collected \<range\>"*. Code deploys continuously; the corpus does not |

Working directly on `main` is right here: a solo four-day build gains nothing from PR ceremony, and Cloud's one-branch model means a feature branch is not deployed anyway.

---

## 10. Verification — Claude in Chrome as source of truth

The app is verified **against the deployed URL in a real browser**. Three reasons make this architectural rather than a preference, and it replaces scaffolding rather than adding to it:

1. **`AppTest` cannot see `st.html` at all** — there is no `at.html`. Since the entire visual system is injected HTML and CSS, a passing `AppTest` proves almost nothing about what a reader sees.
2. **CSS fails silently.** A selector matching nothing raises no error and looks like working code. The only reliable check is `getComputedStyle` in the browser.
3. **Only the deployed app is real.** The stale-module trap reproduces on Cloud and not locally.

| What | How |
|---|---|
| Deploy smoke test | Navigate each page, screenshot, confirm render rather than error |
| Layout and theme | Desktop and phone widths; light and dark |
| CSS applied | `getComputedStyle` on the elements the stylesheet targets |
| Console and network | Read errors and failed requests after each load |
| Ask AI end to end | Live question; confirm restatement, citations, references, caveat, closing question, run-meta |
| Refusal path | Out-of-scope question; confirm it refuses rather than improvising |
| Try it | Paste a known story; confirm the full trace renders |
| Cold start | First-question latency after sleep — the Myntra app took **78s** against a stated 15, which an evaluator reads as broken |

Deterministic Python tests cover what the browser cannot see: schema invariants, span verification, the share helper, κ and coverage computation, every checker rule. **Python tests the data and the logic; Chrome tests the product.**

---

## 11. Public repository

- **No secret is ever committed.** `OPENAI_API_KEY` lives only in Streamlit Cloud's secrets store; `.gitignore` covers `secrets.toml` and `.env`; CI runs a secret scan; `secrets.toml.example` is committed with placeholders.
- **The author salt stays out of the repo.** `author_key` is a salted hash for within-author dedupe; committing the salt beside the hashes would make them reversible for any known handle. Supplied as an environment variable at collection time, never written down.
- **The committed corpus is published data** — public material stored with permalinks, PII-scrubbed, quotes anonymised, no login-walled content. This is what makes committing `corpus.db` publicly defensible, and Methodology says so — including, per D-1, that Reddit, X and Quora were collected through Apify against their robots.txt, with `collect_method` on every record.

The public repo is part of the deliverable: [CTX] §1.4 wants a link where the workflow can be tested, and a readable repo beside a working app is stronger than either alone.

---

## 12. App structure

Six pages. Each section page is a chain of numbered parts — one conclusion, one visual, one verdict sentence per part — per the design language carried over under [CTX] §16.

| Page | Carries |
|---|---|
| **How it works** | Method, funnel, the one-slide pipeline diagram, and full Methodology: sources, lexicon, codebook, severity rubric, scoring weights, **the 60-question coverage register**, reliability results, sanity strip, limitations |
| **Data Bank** | Sources, funnel, exclusions, evidence explorer — filter stories by any coded question, read them with tags and spans |
| **Analysis** | Stages 0–10 heatmap, failure owners, metric nodes, outcome by mode, tactics, workarounds — and the memory half: cue matrix, cue→query attrition, query patterns, photo types |
| **Opportunities** | Cards, gates, adjustable weights, sensitivity, 2×2, comparison, recommendation, Part 3 handoff |
| **Ask AI** | §7 |
| **Try it** | Paste text or a URL; watch the pipeline classify and code it live |

---

## 13. Traceability

| [CTX] | Satisfied by |
|---|---|
| §3.2 sample questions | §5.7 — each has a named view |
| §3.3 full question bank + unanswerable list | **§3.3, §3.4** |
| §6 sources, lexicon, fields | §5.1, `records` |
| §7 refinement funnel | §5.2, `exclusions`, `analysis_funnel` |
| §8.1 codebook, all fields | §3.2–3.5, §5.3 |
| §8.2 severity rubric | `severity_v1.yaml` |
| §8.3 emergent themes | §5.5 |
| §8.4 thirteen views | §4 table list |
| §9 opportunities, scoring, comparison | §6 |
| §9.4 recommendation · §9.5 handoff | §6 |
| §10 Ask AI | §7 |
| §11 output surfaces | §12 |
| §13 bias surfaced in-product | `analysis_method_flags`, `analysis_coverage`, channel 4 |
| §14 definition of done | Exit gates in `implementationplan.md` |
| §15.1–15.7 | `media_type` · §6 · `region_hint` · `photo_class` · §4 helper · §9, §12 · §5.6 |
| §16 | §1, §2, §5.3, §5.5, §8 |

---

## 14. Risks

| # | Risk | Mitigation |
|---|---|---|
| AR-1 | **The timebox** — four days for this scope | Pilot first; three components already deleted; `implementationplan.md` gates each stage |
| AR-2 | **The $15 ceiling breaks on a second re-run** | Console hard cap; pilot measures on day one; named cut order (block D, then Ask AI testing) |
| AR-3 | Story segmentation is the one genuinely new pass | [CTX] §7.2 calibration in the prompt; a pilot gate; fall back to one-story-per-record if κ is poor |
| AR-4 | My `R` dispositions are wrong and a codeable question is skipped | §3.4 — the pilot codes all 60 and measures; dispositions are data, not judgement |
| AR-5 | 60 questions across four blocks degrade coding accuracy | Blocks are small and stage-scoped; κ per field; low-reliability fields barred from headlines |
| AR-6 | Two models agree and are both wrong | Stated in Methodology; blind-read audit is the independent view; sanity strip lets the reader judge |
| AR-7 | Scrapers break or rate-limit | Nine sources across five collection methods (D-1); snapshot early; degrade to smaller-but-cited |
| AR-8 | Cold start reads as broken (observed: 78s) | Minimal deps; warm-up note; ping before the evaluation window |
| AR-9 | Prompt-only rules drift (observed: `Caveat:`) | Anything that matters goes in the checker |
| AR-10 | Push to `main` breaks the live deliverable | Sub-two-minute CI gate; Chrome smoke test after every deploy; `git revert` |
| AR-11 | A secret or the salt reaches the public repo | CI secret scan; salt is env-only |
| AR-12 | Thin cells read as confident findings | The share helper; two-dimension cap on headline claims |

---

## 15. What comes next

| Doc | Purpose |
|---|---|
| `edgecase.md` + `evals.md` | Written as one pass — two lenses on one question (what breaks / how we'd know). Myntra's Stage 2 gate rests on a 108-record human gold set and **cannot be ported**; it is rebuilt on span-verification rate, per-field κ, and coverage |
| `implementationplan.md` | Day-by-day sequence, each stage gated by an eval that already exists |

---

## Appendix — completeness check

This document's central claim is that no item from [SOL-JOURNEY] Part 2 is unaccounted for. That claim is checkable:

```
$ grep -cE '\*\*[0-9]+\.[0-9]+ ' <the Part 2 section of the solution file>
60
```

All 60 appear in §3.3 with a block or register disposition, and the block totals reconcile: A 11 · B 13 · C 16 · D 11 · R 8 · structural 1 = 60. §3.4 then converts every disposition from judgement into measurement at the pilot, so a question is either coded with a measured coverage rate or named as a Part 3 interview question with the measurement that justified it.
