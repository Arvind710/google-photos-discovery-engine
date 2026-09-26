# Implementation Plan — AI-Powered Discovery Engine (Google Photos Vague Retrieval)

**Status:** v1
**Reads with:** `NextLeap Grad Projects.code-workspace.md` (**[CTX]**) · `architecture.md` · `edgecase.md` (EC-*) · `evals.md` (P0–P6, T-1…T-20)
**Written:** 2026-09-26 · **Engine deadline:** 2026-09-30 · **Submission:** 2026-10-07, 15:59 IST
**Purpose:** the build sequence. Seven phases, each with a mechanical exit gate already defined in `evals.md`. No phase starts until the previous one is built, deployed and signed off.

---

## 0. Gate discipline

### 0.1 What "built" means

A phase is built when **all five** are true. Four of five is not four-fifths built.

| # | Condition |
|---|---|
| B-1 | Code committed and pushed to `main` |
| B-2 | The pass has **actually run** end to end on real data and written a `runs` row |
| B-3 | Artifacts frozen and committed (`corpus.db`) |
| B-4 | The corresponding page is **live on the public URL**, reading from the frozen artifacts |
| B-5 | `pytest evals/ -m p<n>` green, **and** the Claude-in-Chrome checks for that page pass against the live URL |

B-5 has two halves deliberately. Per `architecture.md` §10, `AppTest` cannot see `st.html` at all, so a green pytest run says nothing about what a reader sees. **Python tests the data and the logic; Chrome tests the product.** Both, every phase.

### 0.2 Sign-off

Each gate produces `evals/reports/gate_P<n>_<date>.md`: the eval table with pass/fail per row, the `run_id` it was taken against, **actual spend vs estimate and the running total against $15**, and a one-line verdict. A gate signed off against a `run_id` that is not the deployed `run_id` is not signed off (EC-OPS-11, X-3).

### 0.3 What a failed gate means

| Failure class | Response |
|---|---|
| **Invariant (INV)** | Hard stop. Logic error, no threshold to negotiate. Fix, re-run the phase |
| **Metric below threshold (MET)** | Enter that metric's named remediation loop, capped at three iterations. On cap, the shortfall is **reported as a stated limitation in the app and the deck** and the phase passes carrying it. Never silently dropped |
| **Absolute (T-1, T-2, T-14, T-15, T-16, T-18)** | Build failure. No limitation clause exists. Do not proceed |
| **Browser (BR)** | Fix before the deploy is called done. A green CI build is not a verified deploy |
| **Budget (T-19)** | Halt the pipeline and take a decision from the descope ladder (Appendix B). Do not "just continue and watch it" |

### 0.4 The one permitted loop-back

P3's pilot measures true story yield and core share. If the projection lands below **300 core stories** ([CTX] §14.3, T-20), the plan re-enters **P1-F, top-up collection** — the only backward edge. It is pre-authorised, scoped to collection only (no schema change, no codebook change), and must re-pass the P1 gate before P3 resumes. Every other backward movement is a re-plan, not a loop.

### 0.5 App structure — pinned now

Build order is nav order; each phase ships its own page.

| Nav | File | Phase | Notes |
|---|---|---|---|
| How it works | `views/home.py` | **P6** | Method, funnel, the one-slide diagram, full Methodology incl. the 60-question coverage register and reliability table. Written last because only then is it true |
| Data Bank | `views/data_bank.py` | P1 | Sources, funnel, exclusions, evidence explorer |
| Analysis | `views/analysis.py` | P4 | Stages 0–10, failure owners, cue matrix, cue→query |
| Opportunities | `views/opportunities.py` | P4 | Cards, gates, weights, sensitivity, recommendation, handoff |
| Ask AI | `views/ask.py` | P5 | |
| Try it | `views/try_it.py` | P5 | |

---

## 1. Timeline

**Eleven days to submission. The engine gets five.**

| Phase | Duration | Dates | Ships | Gate |
|---|---|---|---|---|
| **P0 — Foundation & freeze** | 0.5d | Sep 26 AM | Repo, schema + deltas, frozen codebook, fixtures, harness, **blank app live** | P0-* |
| **P1 — Data Bank** | 1d | Sep 26 PM – Sep 27 AM | Nine collectors (D-1), cleaning, pilot + full collection, Data Bank page | P1-*, T-4 |
| **P2 — Segmentation** | 0.5d | Sep 27 PM | Record → stories, buckets, `reaches_stage` | P2-*, T-1, T-5, T-6, T-9 |
| **P3 — Coding & reliability** | 1.5d | Sep 28 – Sep 29 AM | Pilot on all 60 · coverage register · **batch all four blocks** · dual-coding, κ, blind-read | P3-*, T-2, T-7, T-8, T-10…T-12, T-20 |
| **P4 — Analysis & opportunities** | 1d | Sep 29 | Cross-tabs, scoring, sensitivity, recommendation, Part 3 handoff, two pages | P4-* |
| **P5 — Ask AI** | 1d | Sep 30 AM | Planner, 4 channels, gate, synthesis, checker, Ask AI + Try it | P5-*, T-13…T-17 |
| **P6 — Release** | 0.5d | Sep 30 PM | How it works, Methodology, run pin, full browser sweep | P6-*, X-* |
| — | | **Oct 1 – Oct 7** | *Parts 3–8. Engine frozen.* | — |

### 1.0 Budget, as a schedule constraint

Phase budgets reconcile to `architecture.md` §8 and separate **committed** spend from **reserve**:

| | Amount |
|---|---|
| Committed base path, P0 → P6 | **~$12.35** |
| Block A re-run reserve, held in P3 | ~$2.40 |
| **Ceiling if the reserve is spent** | **~$14.75** |
| Console hard cap | **$15.00** |

**Actual, 2026-09-26 (end of P3):** $12.89 spent of $15 — P0–P2 $4.88 (3.md), P3 $8.01: coding $3.53 (the corpus batch $2.80 + the Stage 0 re-code $0.73), synchronous re-codes $0.32, three fixture runs and a token probe $3.11, dual coding, adjudication, blind read, residual and themes $1.04. **$2.11 remains** for P4 (~$0.60) and P5 (~$2.80 planned), so P5 is cut to fit: the golden set drops to 24 questions (Appendix B), and live Ask AI testing is rationed. See `Docs/decisions.md` D-9, D-10 and `Docs/4.md`.

Two consequences. The reserve funds **one** codebook repair and re-run, not two — if a second is needed, Appendix B decides what goes. And the base path leaves ~$2.65 of headroom under the cap, which is the only thing standing between a surprise and a halted project. **Spend is checked against estimate after every pass (T-19); 1.5× halts the pipeline for a decision rather than quietly continuing.**

### 1.1 Critical path

```
P0 ──▶ P1A pilot collect ──▶ P2 segment ──▶ P3A pilot code (all 60, sync)
                │                                     │
                └──▶ P1E full collect (parallel) ──────┤
                                                       ▼
                                        COVERAGE REGISTER DECISION
                                                       │
                                  P3B submit ALL FOUR BLOCKS as one batch
                                          (evening Sep 28 ──▶ morning Sep 29)
                                                       │
                                        P3C reliability ──▶ P4 ──▶ P5 ──▶ P6
```

Two items are not controllable by writing code:

- **Batch turnaround.** Up to 24h. Submit **the evening of the day P3A passes**, so the wait overlaps sleep rather than working hours. Missing that evening window costs a whole day, and there is no whole day to spend. This is the hardest deadline in the plan.
- **Streamlit Cloud first deploy.** Dependency resolution, cold starts, secrets propagation. Done on day 1 with a blank page (§2.2).

**Nothing waits on PM time.** Unlike the Myntra build, there is no labelling step on the critical path — the §15.7 consequence that happens to help.

### 1.2 Deliberate parallelism

| While waiting on… | Do this |
|---|---|
| Full collection (P1E, ~2h of scraping) | Author the fixture sets; write the segmentation prompt; write the eval harness |
| The overnight batch (P3B) | Nothing — it is night. That is the point of submitting in the evening |
| Pilot coding (P3A, ~20 min) | Write `crosstabs.py` against the schema, not against data |
| Any phase | Ask AI's **deterministic** parts — `retrieval.py`, `verify.py`, the query registry — depend on the schema, not the corpus. They can be written from P1 onward and should be, because P5 is the thinnest phase in the plan |

### 1.3 Blocked on you — resolve **Sep 26 morning**

| Item | Consequence if late | Status (2026-09-26) |
|---|---|---|
| **OpenAI API key + hard usage cap set to $15** | No pass can run. EC-OPS-1 says the cap precedes the first call, not the public URL | ✅ Key in `.env`; $15 cap recorded in `evals/manual_checks.yaml` |
| ~~**Reddit app credentials** (PRAW client id + secret)~~ → **Apify token** | The richest source is unavailable. Reddit carries blocks C and D almost single-handed; without it the corpus is Play Store reviews and the analysis loses its narrative depth | ✅ Reddit's API is closed to new developers; Reddit, X and Quora come through Apify instead (D-1). Token in `.env`, account upgraded to a $10/month limit |
| **YouTube Data API key** (added by D-1) | YouTube comments unavailable | ✅ In `.env`, verified |
| **Public GitHub repo created, Streamlit Cloud linked to it** | No deploy path. P0 cannot close | ✅ Live since P0 |
| **Author-dedupe salt** as an env var, not a file | EC-OPS-7. Committing it beside the hashes makes them reversible | ✅ Generated into `.env`; never change it |

All resolved. Everything else is mine.

---

## 2. Phase 0 — Foundation & freeze

**Objective:** make every later phase mechanically checkable. Nothing here produces a finding; everything here is what stops a later finding from being wrong.
**Duration:** 0.5 day · **Budget:** < $0.30 (smoke calls only) · **Committed to date:** ~$0.30

### 2.1 Build tasks

| # | Task | Output |
|---|---|---|
| 0.1 | Repo, venv, `requirements.txt` (app only: streamlit, pandas, plotly, rank-bm25, openai, pyyaml) and `requirements-pipeline.txt` (praw, httpx, selectolax, google-play-scraper, app-store-scraper, datasketch — revised in P1 by D-1: praw and app-store-scraper out, playwright in) | Two files, **never merged** |
| 0.2 | Directory tree per `architecture.md` §3 | Skeleton with `__init__.py` |
| 0.3 | `pipeline/schema.sql` — arch §4 **plus all five Appendix A deltas** | `corpus.db` created empty; every invariant query runs against it |
| 0.4 | `codebook/journey_v1.yaml` — **all 60 questions**, each with values, `not_stated`, `other`, stage, block, metric node | Loads; P0-INV-1 passes at 60 of 60 |
| 0.5 | `boundary_note` written for the six danger questions: 5.2, 5.3, 5.4, and the Stage 2 / Stage 4 pair | P0-INV-4 |
| 0.6 | `severity_v1.yaml`, `metric_nodes_v1.yaml`, `lexicon_v1.yaml`, `plain_language.yaml`, `scoring_v1.yaml` with `pre_registered_at` set | Load; P0-INV-7 |
| 0.7 | **Freeze:** sha256 of the codebook recorded as `codebook_version = v1:<hash8>`; a loader that refuses to run if the hash differs without an explicit bump | EC-CODE-13 enforced in code, not prose |
| 0.8 | `pipeline/common/runs.py` — token and cost logger writing a `runs` row per pass, with **actual model rates confirmed at build time**, and a halt at 1.5× estimate | T-19, X-1 |
| 0.9 | `app/lib/evidence.py` — the `share()` helper (arch §4). Written before any view exists, so no view can be written without it | [CTX] §15.5 |
| 0.10 | Eval harness: `conftest.py`, markers `p0…p6`, `report.py` | `pytest evals/ -m p0` green |
| 0.11 | **Fixtures authored by hand, now** — `stories_authored.jsonl` (~40, composition per `evals.md` §4), `segmentation_counts.jsonl` (~20), `dedupe_consensus.jsonl` (40 distinct-author + 5 same-author), `bucket_boundary.jsonl`, `injection_stories.jsonl` | Five files, committed |
| 0.12 | `app/Home.py` + `lib/nav.py` — placeholder. **Deploy today** | Public URL live on day 1 |
| 0.13 | Credentials in Streamlit secrets; `secrets.toml.example` committed; `.gitignore`; **CI workflow with ruff + pytest + secret scan** | P0-OPS-1, P0-OPS-3 |

### 2.2 Why the blank app deploys on day 1

The deploy path is the most common late-stage surprise in a Streamlit project: dependency resolution, cold-start timeouts, secrets not propagating. Discovering that on Sep 30 with Ask AI to ship is project-ending. Discovering it on Sep 26 with a blank page is twenty minutes. **Every phase after this deploys to a URL already known to work.**

### 2.3 Exit gate

P0-INV-1…7 green · P0-OPS-1…3 green · blank app live · all five fixture files committed · CI passing → **P1 starts.**

---

## 3. Phase 1 — Data Bank

**Objective:** a clean, auditable corpus with a visible funnel.
**Duration:** 1 day · **Budget:** ~$0.05 OpenAI (the lexicon probe) · **plus Apify, billed separately:** ~$2–4 of a $10/month limit, planned from Reddit ≈ $0.38 per 1,000 records measured on Myntra, X ≈ $0.40 and Quora ≈ $0.99 per 1,000 listed · **Actual:** OpenAI $0.09 (two probe rounds); Apify $6.06 at the P1 gate, $7.94 after the D-6 Reddit top-up. Myntra's Reddit figure counted each comment as a record. Whole threads measured **~$6.70 per 1,000 threads, ~$0.27 per search term** (D-4, D-5) · **Committed to date:** ~$0.35

### 3.1 Build tasks

Sources and methods per `Docs/decisions.md` D-1 (revised 2026-09-26). Every collector stamps `collect_method` and `collect_query` on every row (A.10).

| # | Task | Notes |
|---|---|---|
| 1.1 | `collect/apify_sources.py` (Reddit, X, Quora) + `collect/apify.py` (actor runner) | Ported from Myntra's `reddit_apify.py`: flatten nested comments, key on the platform's own id (not Apify's per-run id), drop bots and log it, report per-query yield with failures marked. Subreddits from [CTX] §6.1 (arch §5.1 never listed them), recorded in the run params. Apify runs outside the OpenAI budget but are still logged in `runs` |
| 1.2 | `collect/gp_help.py` | Playwright renders thread pages; threads discovered from the listing pages (`/search` and `/api` are robots-disallowed). Thread + replies, per-post author; replies carry the workarounds. **Fallback:** Apify `burbn~google-forums-search`; if both fail, stop and tell the PM |
| 1.3 | `collect/stores.py` (Play, App Store) | Play via `google-play-scraper`; App Store via Apple's review RSS across several countries (~500 per country cap). Expect low yield and **report the ratio** — that ratio is [CTX] §13's short-text bias, made visible |
| 1.3a | `collect/official_apis.py` (YouTube, Stack Exchange, Hacker News) | Official APIs. YouTube: search is 100 of 10,000 daily units, comments 1 — few searches, many comments per video |
| 1.4 | `clean/dedupe.py` | Exact hash across sources; near-dupe **only** within `(source, author_key)`. Jaccard > 0.85 |
| 1.5 | `clean/language.py` | Detect; translate non-English into `text_en`. **`text_clean` stays canonical** — EC-CLEAN-4 |
| 1.6 | `clean/scrub.py` | Typed placeholders. Assert zero email/phone/handle patterns survive |
| 1.7 | **P1A — pilot collect**, ~600 raw, stratified across all nine sources | Feeds P2 and P3A. Also measures Apify cost per record and GP Help render throughput before the full collect |
| 1.8 | **P1E — full collect**, ~11,000 raw | Runs in background; write fixtures while it does |
| 1.9 | `views/data_bank.py` — funnel, source composition, exclusion log, evidence explorer shell | Deploy |
| 1.10 | `evals/test_p1_databank.py` | Written before 1.7 runs |

### 3.2 Exit gate

P1-INV-1…6 green (accounting identity, `source_url`, idempotence, **zero PII**, exclusion reasons, no silent truncation) · every configured source non-zero (nine, D-1) · **T-4 lexicon recall ≤ 5%** · **P1-PROBE-1 consensus preservation green** · Data Bank page live and browser-checked → **P2 starts.**

> **On P1-MET-3.** Sample 200 lexicon-*rejected* records, run the relevance pass over them on `gpt-5-mini`, measure the relevant share. Above 5%, add the terms that surfaced and re-probe. ~$0.05, no labelling. This is the substitute for the gold-set recall measurement §15.7 took away, and it guards EC-PRE — a record the lexicon rejects never reaches a model and leaves no trace anywhere.

---

## 4. Phase 2 — Segmentation

**Objective:** turn records into the unit of analysis. The pass with no precedent, carrying the worst silent failure in the system.
**Duration:** 0.5 day · **Budget:** ~$1.25 (Pass 1 relevance + segmentation, one call over ~5,500 records, plus the dual-model probe) · **Committed to date:** ~$1.60

### 4.1 Build tasks

| # | Task | Notes |
|---|---|---|
| 2.1 | `prompts/segment_v1.md` | [CTX] §7.2's calibration table **verbatim**. Returns stories with spans, bucket, reason, confidence, `reaches_stage`, per-story author |
| 2.2 | `segment/stories.py` on `gpt-5-mini` | Long records chunked on comment boundaries (EC-COL-4); chunk results merged under one `record_id` |
| 2.3 | **`reaches_stage` set generously** | On doubt, go higher. Over-gating costs cents in `not_stated`; under-gating loses the data silently. The asymmetry is the main defence against EC-SEG-5 |
| 2.4 | Write-time asserts: spans are substrings, non-overlapping, union ≤ record length | T-1 |
| 2.5 | Dual-model run on 60 records for T-5 and T-6 | Disagreements on `reaches_stage` **resolve upward** |
| 2.6 | `evals/test_p2_segmentation.py` | |

### 4.2 Exit gate

**T-1 at 100%** · P2-INV-1…6 green (incl. per-story authorship) · **T-5 ≥ 80%**, **T-6 ≥ 75%**, **T-9 ≥ 90%** · zero-story rate ≤ 25% of lexicon hits → **P3 starts.**

---

## 5. Phase 3 — Coding & reliability

The heaviest phase, and the one with the immovable deadline inside it.
**Duration:** 1.5 days · **Budget:** ~$7.25 committed, **plus a $2.40 re-run reserve** · **Committed to date:** ~$8.85
**Actual (2026-09-26, one day early):** $8.01 · gate **passed 49/49** (`evals/reports/gate_P3_20260926.md`) · 331 live stories coded (115 core) · carries stated limitations T-20 and T-7 (B, C, D). How it was actually run differs from §5.1–5.2 in the ways below; `Docs/decisions.md` D-9 and D-10 give the reasoning.

### 5.1 Sub-phase order — not negotiable

```
3A  pilot: code ALL 60 questions on ~70 pilot stories, synchronous      (~20 min, ~$0.80)
     ↓
3B  coverage register: measure not_stated per question, set dispositions
     ↓   ← the decision point. Also projects core count for T-20
3C  fixture run: primary_stage, 5.2/5.3/5.4, Stage 2 vs 4               (~cents, loop here)
     ↓
3D  SUBMIT ALL FOUR BLOCKS AS ONE BATCH — evening of Sep 28
     ↓   ← up to 24h. Overlaps sleep or it costs a day
3E  reliability: dual-code 100, κ, adjudicate, blind-read audit
```

**3A before 3D is the whole point.** Discovering a broken boundary note after coding 1,000 stories means paying twice, and the re-run reserve funds exactly one repair. The pilot costs under a dollar and the fixture loop in 3C costs cents — iteration happens there, never against the paid corpus.

**Blocks B, C and D do not wait for Block A.** They gate on `reaches_stage` and `bucket`, both set in P2. All four submit together. One overnight.

**As run (D-9).** With 115 core stories, 3A's "~70-story pilot" would have been most of the core, so 3A and 3D became one step: every core story was asked all 59 bank questions (the coverage register and the pilot at once), every adjacent story Block A plus C/D by `reaches_stage`. The order was 3C (fixture loop, three runs) → 3D (one Batch job, 334 stories, ~40 minutes, not overnight) → 3B (coverage register) → a corpus-found repair (the Stage 0 re-code, D-9) → 3E. Pass 1's gpt-5 confirmation (D-8) had already moved the core-count decision (T-20) before P3.

### 5.2 Build tasks

| # | Task | Notes |
|---|---|---|
| 3.1 | `prompts/block_{a,b,c,d}_v1.md` | Codebook slice in a **cached prefix**, story in the fresh suffix. `strict: true` structured output. **As built:** ONE prompt, `prompts/code_v1.md` + the whole codebook rendered from `journey_v1.yaml`, one request per story; the blocks choose the questions (D-9). 86% of input tokens were cache hits |
| 3.2 | `classify/blocks.py` | `why` is **one clause, ~15 words** — the direct concession to the ceiling |
| 3.3 | `validate/spans.py` | Exact substring against **`text_clean`**, min 15 chars. Re-code once, then drop and count |
| 3.4 | `analyse/coverage.py` | All 60 questions, pooled and per source; disposition at 85% |
| 3.5 | `classify/batch.py` | Checkpoint by `run_id`; resume diffs `stories` against the block's output. Never re-submit a completed slice. **As built:** inside `classify/blocks.py` (`submit` skips coded or marked stories; `collect` writes what succeeded; `recode` re-codes a named set) |
| 3.6 | `validate/agreement.py` | κ + raw agreement + marginals. **Verdict reads all three** — `degenerate` ≠ `low_reliability` (EC-VAL-2) |
| 3.7 | `validate/adjudicate.py`, `analyse/blind_read.py` | Blind-read is the only independent view of the coding. **As built:** adjudication is `validate/agreement.py adjudicate` |
| 3.8 | `synthesise/residual.py` | Emergent themes from `other:` values. **Added:** `synthesise/themes.py` tags the four themes the PM approved (D-10) into `story_themes` |
| 3.9 | `evals/test_p3_coding.py` | |

### 5.3 The remediation loop

On T-8 or a fixture group failing: read the failures → sharpen the offending `boundary_note` → bump `prompt_version` → re-run **fixtures only** → re-score. **Max three iterations**, then report as a stated limitation. The loop runs on 40 authored stories, so three iterations cost under a dollar. That is deliberate: it is cheap precisely so that iteration happens before the batch, not after.

### 5.4 Exit gate

**T-2 at 100%** (spans against `text_clean`) · T-3, T-7, T-8, T-11, T-12 met · P3-INV-1…10 green · κ computed with a verdict for every spine field · **coverage register complete, all 60 rows** · **T-20 ≥ 300 core stories** → **P4 starts.**

If T-20 fails at 3B's projection, trigger the §0.4 loop-back to P1-F before submitting the batch — not after.

**Result (2026-09-26).** T-2 and T-3 100% (3,261 verified spans) · T-8 90%, P3-MET-2 89% (question level, D-9), P3-MET-3 100% on fixtures v1.2 · T-11 60/60 (32 coded, 28 to the interview register) · T-12: worst `other:` rate 5% · κ with verdicts on every spine field (primary_stage 0.63; outcome 0.51 and severity 0.33 `low_reliability`) · blind read 60 stories, 77% · **T-7 below 25% for B, C, D and T-20 at 115: stated limitations** (`evals/limitations.yaml`). The T-20 loop-back could not run: paid collection is exhausted (D-8).

---

## 6. Phase 4 — Analysis & opportunities

**Duration:** 1 day · **Budget:** ~$0.60 · **Committed to date:** ~$9.45

| # | Task | Notes |
|---|---|---|
| 4.1 | `analyse/crosstabs.py` | All tables in arch §4.2. One generic `analysis_crosstab` |
| 4.2 | `analyse/derived.py` | Cue matrix, cue→query attrition, certain-but-wrong rate, results-as-cues, anchor-and-pivot, workaround intensity, JS divergence |
| 4.3 | `analyse/opportunity.py` | Two gates, five weights. Gated-out candidates **kept and shown** with the failing gate named |
| 4.4 | Sensitivity: 1,000 draws, ±10 absolute, precomputed | Moving a slider is a lookup |
| 4.5 | `synthesise/recommendation.py`, `synthesise/handoff.py` | Handoff prompts built **from the coverage register** |
| 4.6 | `views/analysis.py`, `views/opportunities.py` | Numbered parts, one visual each, one-sentence verdicts |
| 4.7 | `evals/test_p4_analysis.py` | |

**As run (2026-09-26, D-11).** Candidates are primary stages (every failure-mode cell is under ten stories); only Stage 5 (31 core) clears the floor of 30 and is ranked; Stages 2, 3, 6 pass the gates below the floor; Stage 0 is gated out. The gates, reach and node leverage were proposed by Claude and approved by the PM (`codebook/opportunity_inputs_v1.yaml`); severity is out of the headline (κ 0.33) and shown as a sensitivity row. Building the recommendation found quiet successes still coded Stage 2/5; 13 were re-coded ($0.18) and reliability recomputed (metric_node became `low_reliability`). Recommendation and handoff: gpt-5 from a 44-fact pack, checked in code (`synthesise/recommendation.py`, `handoff.py`), $0.16 in all. Tasks 4.1–4.6 are built as listed; `ui.py` holds the page furniture.

**Gate:** P4-INV-1…8 green — especially **INV-3 (no `low_reliability` field feeds a score)** and **INV-4 (`pre_registered_at` precedes the first ranking run)** · sensitivity reported · handoff generated · both pages live and browser-checked → **P5 starts.**

---

## 7. Phase 5 — Ask AI

**Duration:** 1 day · **Budget:** ~$2.80 · **Committed to date:** ~$12.25
**Re-planned 2026-09-26:** about $1.50 is left for this phase after P4. Golden set 40 → 24 (Appendix B's reduced form, every category kept); the per-session and daily caps are set before the URL is shared; the deterministic half (retrieval, gate, verify) is written first as §7.1 already says.
**The thinnest phase against its scope.** Mitigation: its deterministic half is written earlier (§1.2).

### 7.1 Build order — deterministic first

```
retrieval.py (4 channels, query registry) ──▶ gate() ──▶ verify.py ──▶ analyst.py (2 calls) ──▶ views
        written from P1 onward                                        needs the corpus
```

| # | Task | Notes |
|---|---|---|
| 5.1 | `lib/retrieval.py` | Whitelisted parameterised queries; BM25; disconfirming channel; method+reliability channel carrying κ **and coverage** |
| 5.2 | `gate()` | Deterministic FULL / PARTIAL / NONE with the §15.5 floor applied |
| 5.3 | `lib/verify.py` | Numbers, quotes, citations, uncited claims, **proxy discipline**, **`check_label_colon` from day one** |
| 5.4 | `lib/analyst.py` | Planner on `gpt-5-mini`, synthesis on `gpt-5`. Restatement displayed |
| 5.5 | `prompts/synthesis_v1.md` | The proxy rule rewritten for this domain — *a share of coded public stories, never a retrieval success rate* |
| 5.6 | `views/ask.py`, `views/try_it.py` | Per-session cap; Try it accepts text or URL, rate-limited, full trace |
| 5.7 | `golden_questions.yaml` (~40) + the sweep | |

**Gate:** **T-14, T-15, T-16, T-17 absolute** · T-13 ≥ 90% · P5-INV-1…10 green · caps live · both pages browser-checked incl. the refusal path → **P6 starts.**

**As run (2026-09-26, D-12).** Tasks 5.1–5.7 are built: `lib/retrieval.py` (a registry of 18 queries, four channels, the gate), `lib/verify.py`, `lib/analyst.py` (the synthesis prompt lives in it, not in `prompts/`), `lib/tryit.py`, `lib/caps.py`, both pages, a 24-question golden set and `evals/golden_sweep.py`. Seven sweeps took route correctness from 13/24 to 24/24 (`ask_v1.5`). Reading the answers — not only the checks — found the misattributed number, engine text quoted as testimony, the fallback that misled, and the fallback that quoted an injected story; each is fixed and pinned. Try it runs live ($0.066 a post) on text only; URL fetching was dropped with the PM's agreement. **Not yet done: the gate.** Sweep 8 (`ask_v1.6`) ran out of API credit on 13 of 24 questions, so no full sweep exists at the current prompt (`ask_v1.7`); T-13 and T-14…T-17 wait on the PM adding credit, then one sweep (≈ $0.33), the live Ask AI browser check and the gate report.

---

## 8. Phase 6 — Release

**Duration:** 0.5 day · **Budget:** ~$0.10 · **Final committed:** ~$12.35 · **Ceiling if the reserve is spent:** ~$14.75

| # | Task |
|---|---|
| 6.1 | `views/home.py` — method, funnel, the one-slide diagram, and full Methodology: sources, lexicon, codebook, severity rubric, weights, **the 60-question coverage register**, reliability table, **the 10-story sanity strip**, limitations |
| 6.2 | **The no-gold-standard disclosure, unhedged** — P6-BR-12. No human adjudication; figures are inter-model agreement; agreement measures consistency, not correctness |
| 6.3 | Pin the published `run_id`; corpus version stamp in the footer |
| 6.4 | Warm the app; measure cold-start latency (the Myntra app took 78s against a stated 15) |
| 6.5 | Full P6 browser sweep, all six pages |
| 6.6 | `evals/reports/` published in-app and committed |

**Gate:** P6-BR-1…12 green · X-1…X-6 green · final spend reported against $15 · every [CTX] §14 criterion mapped to a passing eval → **engine frozen. Parts 3–8 begin.**

**As run (2026-09-26, D-13).** 6.1–6.3 and 6.5–6.6 done: How it works with the full Methodology, the unhedged disclosure, `pipeline/analyse/publish.py` pinning `publish-20260926-173336-c13120` with a manifest, the corpus stamp in the footer, gate reports rendered in the app, the P6 browser sweep (11 of 12). **6.4 is open: cold start after the app has slept (P6-BR-10)** — the gate reads 14/15 until it is measured. Spend $16.34 recorded of $17.

---

## Appendix A — Schema deltas found while sequencing

All five land in P0. Changing the schema after data is in it costs a re-run the budget cannot fund. A.6–A.10 were found later and are listed below the table.

| # | Delta | Why |
|---|---|---|
| A.1 | **`exclusions` marks, it does not remove.** Every collected record stays in `records`; `exclusions` is a marking table | P1-MET-3 samples lexicon-*rejected* records and re-runs relevance on them. If rejection deleted the row there would be nothing to sample, and EC-PRE would be unmeasurable |
| A.2 | **`stories.author_key`** — authorship moves to the story, not just the record | EC-COL-12: a GP Help thread holds several users' stories. Attributing all of them to the thread starter corrupts the distinct-author count that EC-COL-6 exists to protect |
| A.3 | **`analysis_coverage` PK becomes `(question, source)`**, with `source = '_all'` for the pooled row | P3-MET-11 requires coverage per source as well as pooled. The current PK of `question` alone cannot hold both |
| A.4 | **`runs.estimate_usd`** alongside `cost_usd` | T-19 compares actual against estimate after every pass and halts at 1.5×. Without the estimate stored beside the actual, the check needs a human to remember the number |
| A.5 | **Chunking is transient, not stored.** A long record stays one row; segmentation runs per chunk in memory and merges the stories | EC-COL-4 says chunks share one `record_id` — but `record_id` is the primary key, so chunks cannot be rows. Resolving it in the schema would break idempotence; resolving it in the segmenter costs nothing |

Found later, all applied before any record existed, so none cost a re-run. Each is also described in the header of `pipeline/schema.sql`.

| # | Delta | Found | Why |
|---|---|---|---|
| A.6 | **`stories.char_start`, `char_end`** — offsets into `records.text_clean`, with `char_end − char_start = length(text)` | P0 | P2-INV-2 (spans do not overlap) is uncheckable without offsets, and EC-ASK-6 wants them for exact rendering |
| A.7 | **`analysis_reliability` carries raw agreement, κ, top-value share and marginals**; `degenerate` is a verdict | P0 | EC-VAL-2: κ alone bars correct but skewed fields |
| A.8 | **`published`** — a singleton row pinning the run the app serves | P0 | EC-OPS-11, X-3: the app reads a pinned run, never "latest" |
| A.9 | **`records.source` gains `youtube`, `stackexchange`, `hackernews`, `x`, `quora`** | P1 | The PM's source decision, `Docs/decisions.md` D-1 |
| A.10 | **`records.collect_method`**, NOT NULL: `official_api`, `public_feed`, `public_scraper_lib`, `headless_render`, `apify` | P1 | D-1: three sources come through a third-party scraper against their robots policy, so how each record was obtained is disclosed per row, not only in prose |
| A.12 | **`story_themes`** — emergent themes the PM approved after the freeze, one row per (story, theme) with a verified span | P3 | D-10: adding them to the frozen codebook would re-code every story. A table beside it re-codes nothing |
| A.11 | **`records.posts_json`** — for a thread stored as one record, each post's `author_key` and its offsets in `text_clean` | P1 | EC-COL-4 and the segmentation fixtures treat a thread as one record holding several people's stories. A story's author is then the author of the post its span starts in — looked up, not guessed by a model (A.2, EC-COL-12). Nullable and last, so it was added to the empty file in place |

---

## Appendix B — Descope ladder

If the schedule slips, cut in this order.

**Never cut, in any circumstance** — each guards a failure that would reach the deck looking correct:

P3-INV-2 (spans against `text_clean`) · P2-INV-1 (story spans) · **P2-MET-2 (`reaches_stage` agreement)** · **P3-MET-9 (block yield)** · P1-PROBE-1 (consensus) · P1-MET-3 (lexicon recall) · P5-INV-2 (numeric verification) · P5-INV-4 (proxy discipline) · injection probes · P0-OPS-1 (secret scan) · **P0-OPS-2 and P5-OPS-3 (the $15 console cap, set before the first call and live before the URL is shared)**

**Reduce rather than cut:**

| Item | Reduced form |
|---|---|
| Corpus | 1,000 stories → 700. Report thinner cells honestly; the `share()` helper already handles it. **Floor is 300 core — below that [CTX] §14.3 fails** |
| Golden questions | 40 → 24, every category still represented |
| Authored fixtures | 40 → 24, keeping all nine 5.2/5.3/5.4 minimal pairs and all six Stage 2/4 cases |
| Coverage | Pooled only, drop per-source |

**Cut first if forced:**

Block D (aftermath and persistence detail, −$0.75) · weight sensitivity (report a single ranking, state robustness untested) · phone-width browser check · the LLM-as-judge advisory pass

**Cut last, and only with the consequence written into the deck:**

The **blind-read audit**. It costs about a dollar and it is the only genuinely independent view of the coding. Cutting it means [CTX] §8.3's emergent-theme requirement has nowhere to come from, and the honest report becomes *"we could not have discovered a failure mode outside our own question bank."* With §15.7 already removing human review, this is the last independent check standing.

---

## Appendix C — What the engine hands to Parts 3–8

The engine is not the deliverable; it is Part 1. On 30 September it must hand over:

| To | Artefact | From |
|---|---|---|
| Part 2 metric decomposition | Failure-owner and metric-node distributions | `analysis_metric_node` |
| **Part 3 interviews** | Hypotheses with evidence, screener criteria, per-stage prompts, representative retrieval tasks — **and the coverage register's interview questions** | `synthesise/handoff.py` |
| Part 4 problem definition | Recommendation with the chain and its falsifier | `views/opportunities.py` |
| Part 5 MVP | Where intelligence is needed, as a stage-level hypothesis | Recommendation |
| Part 6 MVP testing | Representative retrieval tasks drawn from real stories | Handoff |
| Deck | The public link, the one-slide diagram, findings with numbers and quotes | `views/home.py` |

The coverage register is the highest-leverage handoff. It is the only artefact that turns *"public data cannot answer this"* from a limitation into a research instrument — which is exactly what [CTX] §3.3 and §9.5 ask for.
