# Edge Cases — AI-Powered Discovery Engine (Google Photos Vague Retrieval)

**Status:** v1
**Reads with:** `NextLeap Grad Projects.code-workspace.md` (**[CTX]**, requirements), `architecture.md` (design)
**Feeds:** `evals.md` — every case marked **[E]** becomes a numbered test there
**Scale assumption:** ~1,000 stories from ~11,000 raw, ~450 core, on a **$15 ceiling**. Several cases below exist *because* of that budget

---

## 1. How to read this

Each case carries what breaks, how it is detected, and what the system does. IDs are `EC-<area>-<n>` so `evals.md` and `implementationplan.md` can reference them.

Two classes, and the distinction matters more than any individual entry:

| Class | Meaning | Priority |
|---|---|---|
| **Loud** | Fails visibly — an exception, an empty chart, a crash | Low. The first run finds these |
| **Silent** | Produces plausible, well-formatted, **wrong** output | **Highest.** These survive review and reach the deck |

§11 is the silent-failure register. If time runs short, build detection for those and let the loud ones surface on their own.

A third class deserves naming because this build has a hard budget: **expensive failures** — cases that do not corrupt the output but consume irreplaceable money. At $15 with roughly $0.75 of slack, a wasted re-run is as damaging as a wrong number.

---

## 2. The six that matter most

Ranked by damage × likelihood, ahead of the enumeration.

| # | Case | Why it tops the list |
|---|---|---|
| 1 | **EC-SEG-5 — `reaches_stage` set too low** | Blocks C and D never run for that story. No error, no exception, no empty chart — the data is simply absent and every downstream share is computed over a smaller, biased denominator. The single worst failure this architecture can produce, and it exists only because block gating is what makes $15 possible |
| 2 | **EC-ASK-1 — a share of stories read as a retrieval success rate** | The goal metric *is* a success rate. "31% of core stories broke at Stage 5" is one careless sentence away from "31% of retrievals fail at Stage 5". That sentence in the deck misrepresents the engine as measuring the exact thing it cannot |
| 3 | **EC-CODE-4 — evidence span verified against the wrong text** | Hinglish stories are translated. If the model quotes from `text_en` and we verify against `text_en`, the span passes — and the quote shown to a reader beside the original does not exist in it. A silent traceability break that looks perfect |
| 4 | **EC-VAL-1 — both coders agree and are both wrong** | `gpt-5` and `gpt-5-mini` share a lineage. κ measures consistency, not correctness. This is [CTX] §15.7's known ceiling and it cannot be fully closed — only disclosed and partially probed |
| 5 | **EC-CLEAN-1 — near-dedupe eats the consensus** | Fifty people independently saying "I can never find old screenshots" *is the finding*. Dedupe cannot distinguish that from spam. Set it wrong and the strongest evidence in the corpus disappears, and the charts look fine |
| 6 | **EC-OPS-1 — the budget is gone before the corpus is coded** | $15 total with ~$0.75 of slack. One un-checkpointed batch failure, one accidental re-run, or one uncapped public Ask AI and the project stops. Money is a correctness constraint here |

---

## 3. Collection — `EC-COL`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-COL-1 | Subreddit private, banned or renamed | Collector returns zero; run looks successful | Assert non-zero per configured source; fail loudly, naming the source. **[E]** |
| EC-COL-2 | Rate limit mid-run | Corpus silently truncated | Checkpoint per source with `ingest_run_id`; resume by diffing `native_id`. Never overwrite a partial run |
| EC-COL-3 | `[deleted]` / `[removed]` bodies | Empty text, valid metadata | Drop at ingest, log `exclusions/deleted` |
| EC-COL-4 | Very long thread (3,000-word post, 200 comments) | Token spike; may legitimately hold several stories | Cap at ~2,500 tokens per segmentation call; longer threads chunk on comment boundaries, each chunk segmented separately, all stories linked to one `record_id`. Never truncate silently **[E]** |
| EC-COL-5 | Emoji-only or ≤20 chars | No signal, still costs a call | Length floor at clean stage, logged `exclusions/length` |
| EC-COL-6 | One user posts 30 comments in a thread | A single voice weighted as 30 | Store `author_key`; report a **distinct-author count** beside every story count. 200 stories from 14 authors is weaker evidence than 200 from 180 **[E]** |
| EC-COL-7 | Play Store review about a crash, not retrieval | Off-topic volume | Out of scope in the relevance rubric. Expect low yield from this source and **report the ratio** — [CTX] §13's short-text bias made visible |
| EC-COL-8 | GP Help thread is a support template with no user story | High apparent relevance, no content | Quality filter; logged `exclusions/quality` |
| EC-COL-9 | No timestamp from source | The before/after Ask Photos cut breaks | `created_at` nullable; time analysis runs only over records that have it, coverage stated |
| EC-COL-10 | Permalink dies after collection | Traceability breaks retroactively | `text_raw` stored verbatim at collect time **is** the evidence; the URL corroborates |
| EC-COL-11 | Scraping blocked outright | Source unavailable | Nine sources across five collection methods (`Docs/decisions.md` D-1); degrade to smaller-but-cited and record the gap in composition rather than hiding it. For GP Help, the fallback order is fixed: Playwright render → Apify → tell the PM |
| EC-COL-12 | A thread where several users each tell a retrieval story | Attribution wrong; one author credited with all | Segmentation carries the comment author per story; `author_key` is per story, not per record **[E]** |
| **EC-COL-13** | **An Apify actor changes its output shape** (a field renamed, comments nested differently, a per-run id where the platform id was) | **Silent.** Records keep arriving, but empty, without authors, without comments, or duplicated on every re-run. Myntra's first probe found comments nested inside posts — treating items as flat would have kept ~5% of the text | Map on named fields and count what each mapping produced; P1-PROBE-2 checks field survival per actor on every run; key on the platform's own id, never the actor's run id **[E]** |
| **EC-COL-14** | **GP Help rendering degrades** — Google changes the page, or the render returns before posts load | **Silent.** Threads collected with a title and no body, or with the original post but no replies (where the workarounds live) | Wait for the post container, not a timer; assert body length and reply count per thread; a run whose body-less share rises is halted, not published. Fallback per EC-COL-11 **[E]** |
| EC-COL-15 | Collection method questioned by an evaluator | Credibility, not correctness | Disclosed rather than defended: `collect_method` on every record, source × method on the Data Bank, and D-1's full reasoning in Methodology |

---

## 4. Cleaning — `EC-CLEAN`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| **EC-CLEAN-1** | **Near-dedupe removes genuine repeated signal** | **Catastrophic and silent.** "Can't find old screenshots", said by 50 people, is the finding; dedupe reads it as duplication | Near-dupe **only** within `(source, author_key)`. Never across authors. Cross-author similarity is measured and *reported* as consensus strength, never removed. Jaccard > 0.85 **and** same author. **[E]** |
| EC-CLEAN-2 | Exact dupe across sources (Reddit post quoted on a forum) | Double counting | Exact-hash dedupe; keep the earliest, log the other. **Across different authors only for text ≥ 25 words** — two people writing the same short line is consensus, not a copy (`Docs/decisions.md` D-3) |
| EC-CLEAN-3 | PII scrub destroys meaning | A name inside a narrative gets masked and the sentence stops parsing | Typed placeholders (`[NAME]`, `[EMAIL]`) rather than deletion; sentence structure preserved |
| **EC-CLEAN-4** | **Translation becomes the canonical text** | Coding and quoting happen on `text_en`; the reader sees the Hinglish original. Spans verify against one and display beside the other | **One canonical text for coding, quoting and verification.** Decision: code on `text_clean` (the original), give `text_en` to the model as an *aid* in the same prompt, and require spans from `text_clean`. See EC-CODE-4. **[E]** |
| EC-CLEAN-5 | Language detection fails on short Hinglish | Misrouted or dropped | Never drop on language. `lang` is metadata; `unknown` is valid |
| EC-CLEAN-6 | Normalisation destroys intensity | ALL CAPS and "!!!" carry the severity signal | Normalise a *copy* for matching; the model reads the unnormalised text |
| EC-CLEAN-7 | Same record ingested twice across runs | Duplicate rows | `record_id = sha1(source ‖ native_id)` is the primary key; re-ingest is idempotent by construction |

---

## 5. Segmentation — `EC-SEG`

**The pass with no precedent.** Myntra classified whole records; we split records into stories first, and every downstream count is a count of stories. Errors here propagate everywhere and mostly do not announce themselves.

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-SEG-1 | Post contains several stories, model returns one | Under-counting; the richest posts contribute least | Fixture set with known story counts; dual-model story-count agreement on a sample. **[E]** |
| EC-SEG-2 | Model splits one story into two | Double counting one person's single attempt | Same detection. Also: two stories from one record with near-identical cues and outcome are flagged for merge review |
| EC-SEG-3 | Span is not a substring of the record | Fabricated or paraphrased story text | Hard assert at write time: every `stories.text` must be an exact substring of `records.text_clean`. **[E]** |
| EC-SEG-4 | Spans overlap or exceed the record | Text double-counted | Assert non-overlapping spans, union ≤ record length. **[E]** |
| **EC-SEG-5** | **`reaches_stage` set too low** | **The worst silent failure in the system.** Blocks C and D never run. No error. The story is coded, looks complete, and contributes nothing to Stage 5–10 analysis. Every downstream share is computed over a biased denominator | Three defences: (a) **block yield check** — if a block runs and returns >90% `not_stated`, the gate was wrong in the other direction, and if a block *never* runs for a whole source that is flagged; (b) dual-model agreement on `reaches_stage` specifically; (c) `reaches_stage` is set **generously** — when in doubt, run the block. Paying for a page of `not_stated` costs cents; missing the data costs the analysis. **[E]** |
| EC-SEG-6 | `reaches_stage` set too high | Blocks run and return all `not_stated` | The cheap direction of the same error. Caught by the block-yield check; acceptable at this cost |
| EC-SEG-7 | Record is relevant but contains zero stories ("search is broken, fix it") | A complaint with no retrieval attempt | Valid outcome: 0 stories, logged `exclusions/no_story`. Not an error — but if it exceeds ~25% of lexicon hits, the lexicon is too broad |
| EC-SEG-8 | Bucket boundary — vague vs precise retrieval | The call that decides the whole `core` denominator. *"Searching my wife's name shows nothing"* is `adjacent`; *"that café in Goa, no idea which year"* is `core` | [CTX] §7.2's calibration table verbatim in the prompt; over-represented in the fixture set; dual-coded. **[E]** |
| EC-SEG-9 | Story text carries the surrounding thread's context | Model quotes another user's words as this user's | Segmentation returns the span only; `thread_context` is a separate field the coder may read but never quote from |

---

## 6. Coding — `EC-CODE`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-CODE-1 | Story receives no `primary_stage` | Orphan — in the denominator, in no numerator | Forbidden state. `primary_stage` is non-null in the schema; a failed call quarantines rather than writes. **[E]** |
| EC-CODE-2 | **`primary_stage` anchors on Stage 5** | Stage 5 is the most *discussed* failure, so the model defaults there. The journey heatmap, the failure-owner split and the recommendation all inherit the bias | Distribution sanity check against expectation; dual-model κ reported for `primary_stage` **specifically**, not just on average; the blind-read audit targets this field. **[E]** |
| EC-CODE-3 | **The 5.2 / 5.3 / 5.4 triple conflated** | Cue absent from the index / cue over-filtered / cue ranked badly. Three different owners, three different solves, one sentence of user text | Explicit contrasting `boundary_note` on all three; over-represented in the fixture set; reported as a named cell in the disagreement matrix. **[E]** |
| EC-CODE-4 | **Evidence span verified against the translation** | Span passes the substring check against `text_en`; the reader sees the Hinglish original and the quote is not in it | Canonical text is `text_clean` (EC-CLEAN-4). Verification runs against `text_clean` only. A span that verifies against `text_en` but not `text_clean` is a **failure**, not a pass. **[E]** |
| EC-CODE-5 | Span is paraphrased | Traceability break; the quote reads naturally and does not exist | Exact-substring assertion, whitespace- and Unicode-normalised. Re-code once, then drop and count. **[E]** |
| EC-CODE-6 | Span is the entire story | Technically valid, useless as evidence | Length cap relative to story length; over-long spans flagged |
| EC-CODE-7 | **Stage 2 vs Stage 4 confusion** | Couldn't remember it vs remembered but couldn't express it. Misattributes the whole problem between the user's memory and the product's language understanding — which *is* the recommendation | Boundary note contrasting them directly; fixture coverage; named cell in the disagreement matrix. **[E]** |
| EC-CODE-8 | Model invents a value outside the enum | Codebook violated | Structured output with `strict: true`; plus a write-time assert that every value exists in the codebook or is prefixed `other:`. **[E]** |
| EC-CODE-9 | **`other:` becomes a dumping ground** | Values that should map to a listed answer land in free text; prevalence of real codes under-reported | Monitor `other:` rate per question. Above 20% on any question, the value list is wrong — fix the codebook, don't absorb it. Feeds §5.5's residual pass |
| EC-CODE-10 | **`not_stated` becomes a dumping ground** | The model, told not to guess, over-uses it. Coverage looks low, questions get wrongly routed to the interview register, real signal is lost | Compare `not_stated` rate between the two coders on the dual-coded sample; a large gap means one is over-abstaining. Blind-read audit spot-checks. **[E]** |
| EC-CODE-11 | Block runs but the JSON is malformed | Parse failure | Retry once, then quarantine with the raw response stored. Never drop silently |
| EC-CODE-12 | Model refuses a story on content policy | No coding returned | Quarantine, log, count in exclusions. Expect a handful — personal photo narratives occasionally involve bereavement, medical or intimate content |
| EC-CODE-13 | Codebook edited mid-run | Half the corpus on v1, half on v2 | `codebook_version` on every row; a mismatch within a `run_id` is a hard error |
| EC-CODE-14 | Blocks A–D partially complete for a story | Story looks coded; block C silently missing | Assert per story: for every block whose gate says it should have run, at least one row exists. **[E]** |
| EC-CODE-15 | Stage 5 values presented as fact | Every Stage 5 value is **inferred** from a user's account of a system they cannot see | `inferred` flag on every Stage 5 row, and the app renders it as "inferred from user evidence" wherever it appears. Never a bare claim about Google Photos' behaviour. **[E]** |
| EC-CODE-16 | Severity is unreliable | A subjective 1–5 scale will have the weakest agreement of any field | Expected. Reported with its κ; if below 0.6, flagged `low_reliability` and barred from headline claims like any other field. Severity feeds scoring, so a low κ here is material and must be visible |
| EC-CODE-17 | Video-involving story routed inconsistently | §15.1 puts video in `adjacent` | `media_type = video` → bucket `adjacent`, reason `video_out_of_scope`. A story covering both photo and video is `mixed` and stays in core. Count both and report |
| **EC-CODE-18** | **A story where nothing went wrong is coded Stage 0** *(found in the corpus, 2026-09-26)* | **Silent.** `primary_stage` is where the story FIRST went wrong, and the codebook has no "nothing went wrong" stage. Faced with a quiet success ("searched 'passport' and found it"), the coder fell back to Stage 0 — failure owner `library_data` — and core Stage 0 read 45%, inflating the headline "much can't-find is was-never-there" finding. The authored fixtures had no quiet successes, so they could not catch it | Prompt rule (code_v1.2): Stage 0 needs the story to say the photo was unreachable; no failure is Stage 9 (owner `none`). `stage0_without_evidence` flags Stage 0 on a story that ends with the photo found and nothing in 0.1/0.2 saying it was unreachable; `blocks recode` re-codes them; a corpus test fails while any remain. A story that says the photo VANISHED, even without saying where, is a correct Stage 0 and is not flagged (D-9) **[E]** |
| EC-CODE-18b | **A quiet success coded as the stage that worked** *(found in P4, 2026-09-26)* | Under code_v1.1 a search that simply worked was coded Stage 5 ("search matched") or Stage 2 ("lacked the date but found it"); D-9's re-code only covered Stage 0. Stage 5 read 36 core, not 31 | `blocks.success_without_failure` flags Stage 2/4/5 ending `found` with no failure stated in 5.1–5.6 or 4.3; `blocks recode` re-codes them; a corpus test pins none remain (D-11). Lesson: read the stories behind every headline cell, not only the one that looked inflated **[E]** |
| EC-CODE-19 | A coder's `other:` text spells a listed value | The value is under-counted and the `other:` rate over-stated | `other:` text equal to a listed value becomes that value at validation; a corpus test pins that none remain (D-10) |

---

## 7. Validation without a gold set — `EC-VAL`

[CTX] §15.7 removed PM sample review. These are the failure modes of what replaced it.

| ID | Case | What breaks | Handling |
|---|---|---|---|
| **EC-VAL-1** | **Correlated error — both coders wrong, agreeing** | κ is high, the field passes, the data is wrong. `gpt-5` and `gpt-5-mini` share a lineage; they fail in the same directions | Cannot be fully closed. Three partial defences: the **blind-read audit** (§5.5) is the only genuinely independent view; the **authored fixture set** has known-correct answers; and Methodology states outright that agreement measures consistency, not correctness. **Disclosure is the primary mitigation and it must not be softened.** **[E]** |
| **EC-VAL-2** | **The κ paradox on skewed fields** | A field where 92% of stories take one value shows high raw agreement and near-zero κ — so a *correct* field gets flagged `low_reliability` and barred from headlines | Report **three numbers together**: raw agreement, κ, and the marginal distribution. The `low_reliability` verdict is set from κ **and** prevalence, not κ alone. A field with >85% single-value concentration is labelled `degenerate` rather than unreliable. **[E]** |
| EC-VAL-3 | Adjudicator is not independent | The third call is the same family as the primary and will tend to side with it | Acknowledged limitation. The adjudicator is used to produce a working silver standard, **not** to claim correctness. Adjudication rates are reported by which coder was upheld — a lopsided split is itself a signal |
| EC-VAL-4 | Dual-coded sample is unrepresentative | Reliability measured on the wrong mix | Stratified across source, `photo_class` and `primary_stage`; strata composition published beside the κ table |
| EC-VAL-5 | Span verification passes on a trivial span | A one-word quote is always a substring | Minimum span length (~15 chars) and a requirement that the span overlap the semantic content, not just any token. **[E]** |
| EC-VAL-6 | Fixture set tests the codebook, not reality | Synthetic stories are cleaner than real ones; passing them proves less than it appears | Stated explicitly in Methodology and in `evals.md`. Fixtures are a **floor**: they prove the boundaries are applied as written. They cannot prove accuracy on messy text, and no claim rests on them alone |
| **EC-VAL-8** | **A cheap first model over-finds, in one direction** *(seen three times, 2026-09-26)* | gpt-5-mini called general loss complaints retrieval stories (D-8), and tagged 62 stories "looked in another photo app" for merely mentioning Google Photos (D-10). Counts from it alone are inflated, and look plausible | The cheap model proposes; gpt-5 confirms every candidate against the written definition; both counts are kept in the artifact. Never trust a mini count alone **[E]** |
| EC-VAL-7 | Blind-read audit needs its own mapping step | Comparing free-text "what is this about" to an assigned code is itself a judgement that can fail | The audit reports *disagreement candidates* for inspection, not a score. It is a discovery tool, not a metric |

---

## 8. Coverage register — `EC-COV`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-COV-1 | A question marked `R` was actually codeable | Real signal skipped on my judgement | This is exactly why the pilot codes all 60 regardless of block. Dispositions are **data, not judgement**. **[E]** |
| EC-COV-2 | High coverage but degenerate | 95% coded, 94% of them the same value. Looks informative, carries no information | Report the value distribution beside the coverage rate; flag `degenerate` above 85% concentration |
| EC-COV-3 | Pilot coverage ≠ full-corpus coverage | Dispositions set on an unrepresentative sample | Pilot spread deliberately across all nine sources; coverage recomputed after the full run and any drift reported. A question that crosses the threshold after the full run is noted, not quietly re-coded |
| EC-COV-4 | Coverage differs sharply by source | A question answerable on Reddit and never on Play Store | Report coverage **per source** as well as pooled. This is a finding about the sources, not a defect |
| EC-COV-5 | The register is generated but never surfaced | [CTX] §9.5 requires it as an output | It is a published table on the Methodology page and the input to the Part 3 interview guide. **[E]** |

---

## 9. Analysis and opportunities — `EC-ANL`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-ANL-1 | Top opportunities score within noise | No defensible winner | Report as a tie with the sensitivity figure. **A tie is a legitimate finding** and makes the interviews the tiebreak rather than a formality |
| EC-ANL-2 | Highest-scoring opportunity fails a gate | e.g. the photo was never backed up — Google Photos cannot fix it | Report honestly, then rank within the gated-in set and say plainly that the largest problem is out of scope. Gated-out candidates stay visible **[E]** |
| EC-ANL-3 | Top result is Stage 0 (library state) | Not a retrieval-intelligence problem at all | Sized, then excluded from the recommendation with the reasoning shown. If Stage 0 dominates, the honest headline is that much "can't find it" is "was never there" — a real and useful finding |
| EC-ANL-4 | A cell below the floor is ranked | Thin evidence reads as a confident finding | The §4 share helper; no view formats a share itself. Assert no opportunity is ranked on n below the floor **[E]** |
| EC-ANL-5 | Three-dimension cross-tab used for a headline | Arithmetic guarantees sparsity at 450 core | Headline claims capped at two dimensions; deeper cuts render as illustrative and labelled **[E]** |
| EC-ANL-6 | Weights tuned after seeing the ranking | The sensitivity check becomes theatre | `pre_registered_at` timestamp stored and displayed; a ranking run before that timestamp is a hard error **[E]** |
| EC-ANL-7 | A low-reliability field drives the recommendation | κ said don't trust it; the scoring used it anyway | Assert: no field with `verdict = low_reliability` contributes to a gated or ranked score **[E]** |
| EC-ANL-8 | Emergent themes merely restate the codebook | The blindness guard is theatre | If the residual pass and blind-read audit produce nothing new, that is a **finding** — the question bank covers the space — and is stated, not hidden |

---

## 10. Ask AI — `EC-ASK`

| ID | Case | What breaks | Handling |
|---|---|---|---|
| **EC-ASK-1** | **A share of stories stated as a retrieval success rate** | The goal metric *is* a rate. "31% of core stories broke at Stage 5" → "31% of retrievals fail at Stage 5" misrepresents the engine entirely | The proxy-discipline rule is the most important line in the synthesis prompt **and** a checker rule with zero tolerance. Charts carry a standing flag. **[E]** |
| EC-ASK-2 | **Prompt injection via story text** | Stories are untrusted public text entering the model's context in a publicly reachable app | Records wrapped in delimited untrusted blocks; the system prompt states record content is evidence to quote, never instruction to follow. Probed adversarially. **[E]** |
| EC-ASK-3 | Answer cites a question ID the corpus never coded | A question in the interview register has no data | Channel 4 carries the coverage rate; the gate routes to PARTIAL/NONE and the answer names the gap **[E]** |
| EC-ASK-4 | False-premise question — "why does Ask Photos fail most often?" | Answering accepts the premise | Planner flags premise assertions; the answer corrects before answering **[E]** |
| EC-ASK-5 | Question about a cell below the floor | Over-reading a tiny count | The §4 helper applies to answers identically to charts. Below floor → states the count and declines the share **[E]** |
| EC-ASK-6 | Quote check fails on whitespace or casing | Valid quote rejected | Normalised comparison; offsets into `text_clean` stored for exact rendering |
| EC-ASK-7 | Verification rejects repeatedly | Infinite loop, unbounded spend | Bounded to one regeneration, then served with an explicit unverified banner. At $15, an unbounded loop is a budget failure as much as a UX one **[E]** |
| EC-ASK-8 | `Caveat:` and other label-colon openings | The prompt forbids them; nothing enforced it, and the live Myntra app drifted into doing it on both answers tested 25 Sep 2026 | `check_label_colon` in the checker from day one. **Rules backed by the checker hold; rules living only in the prompt drift.** **[E]** |
| EC-ASK-9 | Methodological question — "how was this built?" | Not in the corpus | Routed to a static description of the pipeline, not to retrieval |
| EC-ASK-10 | Question in Hindi or Hinglish | Planner misreads | Handled; answers in English per the scope decision, quoting the original verbatim |
| EC-ASK-11 | Follow-up referencing a prior turn | No context | Prior turns given to the planner; the displayed restatement resolves the reference explicitly |
| EC-ASK-12 | Gibberish or empty input | Wasted paid call | Rejected before the planner. At this budget, free rejection matters |

---

## 11. Silent-failure register

Plausible, well-formatted, wrong. **Build detection for these first.**

| ID | Silent failure | Why it survives review | Detection |
|---|---|---|---|
| **EC-SEG-5** | `reaches_stage` too low; blocks never run | The story looks fully coded. Missing data leaves no trace in any denominator | Block-yield check; dual-model agreement on `reaches_stage`; gate set generously |
| **EC-ASK-1** | Share of stories read as a success rate | The sentence is grammatical, the number is real, the inference is wrong | Checker rule, zero tolerance; standing flag on every chart |
| **EC-CODE-4** | Span verified against the translation | The check passes and the quote reads well | Single canonical text; verification against `text_clean` only |
| EC-CODE-2 | `primary_stage` anchors on Stage 5 | The most-discussed stage *should* be common, so the bias looks like the finding | Distribution sanity check; per-field κ; blind-read audit targets it |
| EC-CODE-3 | 5.2 / 5.3 / 5.4 conflated | All three are plausible readings of one sentence | Named cell in the disagreement matrix; fixture coverage |
| EC-CODE-7 | Stage 2 vs Stage 4 conflated | Both are defensible for the same story | Same |
| EC-CLEAN-1 | Cross-author dedupe deletes consensus | Charts look normal; deleted records leave no trace | Author-scoped dedupe only; cross-author similarity reported as consensus |
| EC-VAL-1 | Both coders wrong, agreeing | κ is the headline and it looks good | Blind-read audit; authored fixtures; explicit disclosure |
| EC-VAL-2 | κ paradox bars a correct field | The gate fires and looks principled | Agreement + κ + marginals reported together |
| EC-CODE-10 | `not_stated` over-used | Coverage drops, questions route to the register, nobody notices the signal was there | Cross-coder `not_stated` gap |
| EC-COL-6 | One prolific author dominates | 200 stories sounds like 200 people | Distinct-author count beside every story count |
| EC-COL-13 | An Apify actor's output shape drifts | Records still arrive, so the count looks healthy | Field-survival check per actor (P1-PROBE-2) |
| EC-COL-14 | GP Help renders without post bodies or replies | Threads still arrive, with titles | Body length and reply count asserted per thread |
| EC-CODE-18 | A quiet success coded Stage 0 | Stage 0 is a real, headline-worthy category, so an inflated share reads as a finding | `stage0_without_evidence` + a corpus test; read the Stage 0 stories, not only the share |
| EC-VAL-8 | A cheap model's count taken at face value | The count is plausible and the stories it cites exist | A stronger model confirms every candidate; report candidates → confirmed |
| EC-CODE-15 | Inferred Stage 5 values read as fact | They are phrased like observations | `inferred` flag rendered wherever the value appears |

---

## 12. Operations, budget, repo — `EC-OPS`

| ID | Case | Handling |
|---|---|---|
| **EC-OPS-1** | **Budget exhausted before coding completes** | Hard OpenAI console cap at $15 before the first call. Per-pass cost written to `runs` and compared against estimate after every pass; a pass exceeding 1.5× its estimate halts the pipeline for a decision. Named cut order: block D, then Ask AI test volume **[E]** |
| EC-OPS-2 | Batch job fails after partial spend | Checkpoint by `run_id`; resume by diffing `stories` against the block's output table. Never re-submit a completed slice **[E]** |
| EC-OPS-3 | Accidental full re-run | Re-runs require an explicit flag and print the estimated cost with a confirmation prompt. No re-run is a default code path |
| EC-OPS-4 | **Public Ask AI drains the key** | Per-session question cap, global daily cap, and the console limit. The URL is public and the key is yours **[E]** |
| EC-OPS-5 | Missing API key in secrets | Read-only pages render normally; Ask AI and Try it show a clear configuration message, not a stack trace **[E]** |
| **EC-OPS-6** | **A secret reaches the public repo** | `.gitignore` covers `secrets.toml` and `.env`; `secrets.toml.example` committed with placeholders; **CI secret scan on every push** — a hit fails the build **[E]** |
| **EC-OPS-7** | **The author salt is committed** | Committing it beside the hashes makes them reversible for any known handle. Salt is an environment variable at collection time, never written to a file in the repo. CI scans for it **[E]** |
| EC-OPS-8 | PII survives into the committed corpus | `corpus.db` is public. Scrub assertions run as invariants before commit, not after **[E]** |
| EC-OPS-9 | **Push to `main` breaks the live deliverable** | Every push deploys. CI gate under two minutes; Chrome smoke test after every deploy; `git revert` rollback. Never push during an evaluation window |
| EC-OPS-10 | Stale-module trap on Streamlit Cloud | Cloud reruns the entry script without restarting the process; a module in `sys.modules` keeps old definitions and a view calling a new helper dies with `AttributeError` on the deployed app while working locally. Bump `rebuild-token` in `requirements.txt` on every push touching `app/lib/` **[E]** |
| EC-OPS-11 | `corpus.db` committed mid-pipeline | The app serves half-coded data as if final | The app pins a **published** `run_id`, never "latest". A partial run is never published **[E]** |
| EC-OPS-12 | Cold start reads as broken | Observed on the Myntra app: 78s against a stated 15. An evaluator reads that as a dead app | Minimal `requirements.txt`; a warm-up note in the empty state; ping the app before the evaluation window **[E]** |
| EC-OPS-13 | Malformed row crashes a page | Defensive rendering — skip and log on-page, never a white screen |
| EC-OPS-14 | `corpus.db` exceeds GitHub limits | ~1,000 stories ≈ 10–18MB, well inside. Release-asset fallback documented. *Actual: 60 MB at the end of P3 — the 31,235 raw records dominate, not the stories. GitHub warns above 50 MB on every push and refuses 100 MB* |
| EC-OPS-15 | **The provider's billing limit is hit below the recorded spend** *(2026-09-26)* | OpenAI refused batches ("Billing hard limit has been reached") at $10.35 recorded against a $15 cap. The `runs` table reconciled, so the difference was on the account side. Stop every paid call and ask the PM to check the console; never retry around it |
| EC-OPS-16 | **One request in a batch stalls** *(2026-09-26)* | 83 of 84 done, the last stuck for 20 minutes. Cancel the batch: cancelling itself took ~25 minutes before the partial output appeared. `collect` writes what finished; the rest stays un-coded and a later `submit`/`recode` picks it up by diff (X-6) |

---

## 13. What this changes in the build

Cases that are design requirements, not handling. These carry into `implementationplan.md`:

1. **`reaches_stage` is set generously, and block yield is measured** (EC-SEG-5). The single most consequential line in this document.
2. **One canonical text — `text_clean` — for coding, quoting and verification** (EC-CLEAN-4, EC-CODE-4). The translation is an aid in the prompt, never the source of a span.
3. **Dedupe is author-scoped, never cross-author** (EC-CLEAN-1).
4. **Distinct-author counts wherever a story count appears** (EC-COL-6).
5. **Exact-substring assertion on every span, with a minimum length** (EC-CODE-5, EC-VAL-5) — a build-time invariant, not a review step.
6. **Agreement, κ and marginals reported together; `degenerate` is a distinct verdict from `low_reliability`** (EC-VAL-2).
7. **`inferred` flag on every Stage 5 value, rendered wherever it appears** (EC-CODE-15).
8. **Proxy discipline is a checker rule with zero tolerance, not a prompt instruction** (EC-ASK-1).
9. **`check_label_colon` ships from day one** (EC-ASK-8).
10. **Cost checked against estimate after every pass; 1.5× halts the pipeline** (EC-OPS-1).
11. **CI secret scan, including the author salt, before the repo goes public** (EC-OPS-6, EC-OPS-7).
12. **The app pins a published `run_id`, never "latest"** (EC-OPS-11).
