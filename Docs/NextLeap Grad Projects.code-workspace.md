# context.md — AI-Powered Discovery Engine (Functional Context)

> **Audience:** Claude Code, as the starting context for producing architecture plans, implementation plans and tasks.
> **Nature of this document:** Functional (what the PM needs the engine to do, and why). It deliberately avoids prescribing a technical stack. Where a functional requirement implies a technical constraint, it is stated as a constraint, not a design.
> **Owner:** The PM (me). When in doubt, ask me rather than assume.

---

## 0. Reference documents (read these first)

Do not duplicate their content into plans; reference them by filename and section.

| Ref | File | What it contains | How to use it |
|---|---|---|---|
| **[PS]** | `Sept_Problem.pdf` | The official problem statement: Google Photos, Core Experience PM, goal metric, Parts 1–8, deliverables, deck rules, deadline. | Source of truth for requirements. Part 1 defines this engine. Parts 2–4 consume its output. |
| **[SOL]** | `September_Problem_s_Solution_*.md` | My working solution. | Context and framing. |
| **[SOL-JOURNEY]** | [SOL], section *"Claude's version: User Journey and diving deeper into each component of a user's journey:"* | (1) Critique of the solution, including the vague-retrieval definition, success definition and cleaner metric decomposition. (2) The 11-stage retrieval journey (Stages 0–10). (3) The **question bank** with IDs (0.1 … 10.3) and possible answers for each. (4) How to use it as the engine's codebook. | **This is the engine's codebook and analytical backbone.** Every tag the engine assigns must map to a stage and question ID from here. |
| **[SOL-METRIC]** | [SOL], section *"Business metric decomposition into product outcomes"*, plus the revised decomposition inside [SOL-JOURNEY] | How "successful retrieval of vaguely remembered photos" breaks into funnel factors. | Every opportunity the engine surfaces must be mapped to a node in this decomposition. |

If a file name differs on disk, locate it by content. If [SOL-JOURNEY] and older parts of [SOL] conflict, **[SOL-JOURNEY] wins**.

---

## 1. Why this engine exists

### 1.1 The business goal it serves
From [PS]: *Increase the percentage of users who successfully retrieve a photo they remember but cannot precisely describe when they start searching.* The challenge is **not** to improve search in general.

### 1.2 The engine's job
Analyse public user conversations about photo retrieval **at scale** and turn them into **structured, evidence-backed, comparable retrieval problems and opportunity areas**. It must answer *why* retrieval fails despite users retaining some memory of the photo, and *where in the journey intelligence is actually needed*.

It is **not** a review summariser and **not** a sentiment analyser ([PS], Part 1). Sentiment may appear only as a severity signal.

### 1.3 Where it sits in the case study

```
Business metric ──► Product outcomes (metric decomposition)
                          │
                          ▼
              AI-POWERED DISCOVERY ENGINE   ◄── this document
                          │
      ┌───────────────────┼─────────────────────┐
      ▼                   ▼                     ▼
Ranked opportunity   Hypotheses &          Target-segment
areas (with          interview guide       direction
evidence)            inputs (Part 3)       (Part 4)
      │                   │                     │
      └──────► Problem definition ──► MVP (Part 5) ──► Metrics (Part 7) ──► Risks (Part 8)
```

The engine's output must visibly support the narrative chain required in [PS] Part 4: **Business Metric → Product Outcomes → AI-Powered Discovery → Observed User Behaviour → Problem Definition.**

### 1.4 Deliverable obligations ([PS], Deliverables)
1. **A public link where the workflow can be tested** by an evaluator who is not me.
2. **A one-slide explanation** in the final deck of how the workflow works. The engine must therefore have a pipeline that can be explained in one diagram.
3. Findings good enough to populate the deck's "Discovery-engine findings" slide, with numbers and representative quotes.

---

## 2. Users of the engine and their jobs

| User | Job to be done | What they need from the engine |
|---|---|---|
| **The PM (primary)** | Decide which retrieval problem to solve and for whom, with defensible evidence. | Ranked opportunities, cross-tabs, drill-down to quotes, hypotheses for interviews, exportable charts for the deck. |
| **Evaluator / mentor (secondary)** | Verify the engine is real, works, and goes beyond summarisation. | A public link; an overview they understand in under 2 minutes; the ability to ask a question and get a grounded, cited answer; the ability to run the pipeline on a small sample or a pasted post. |
| **Future me (interview prep)** | Reuse the engine as a portfolio artefact and interview story. | A clean, explainable pipeline and a reproducible methodology note. |

---

## 3. Questions the engine must be able to answer

### 3.1 The three big questions ([SOL])
1. **How do people remember old visual information?** (what they recall, what they forget, how accurately)
2. **Where does the existing retrieval experience break down, and why?** (stage × failure owner × root cause)
3. **Which opportunity can most meaningfully improve successful retrieval?** (ranked and compared, with rationale)

### 3.2 The sample questions from [PS] (must each have an explicit answer view)
- What kinds of old photos do users struggle to retrieve?
- What information do people actually remember about a photo?
- What information have they forgotten?
- How do users formulate searches when their memory is incomplete?
- Is the user unable to express what they remember? *(Part 2)*
- Does Google Photos fail to understand the clues they provide? *(Part 2)*
- Are potentially relevant results difficult to evaluate? *(Part 2)*
- Does the user struggle to refine an unsuccessful search? *(Part 2)*

### 3.3 The full question bank
Every question in [SOL-JOURNEY] (IDs 0.1 through 10.3) is an analytical question the engine should try to answer. Where public data cannot answer one (for example the exact attempt counts in 8.1), the engine must **say so explicitly** and flag it as an interview/usability-test question for Part 3. That list of "unanswerable from public data" questions is itself a required output (see §9.5).

---

## 4. Scope

### 4.1 In scope
- **Retrieval of known items**: the user believes a specific photo (or photo from a specific moment) exists and is trying to find it.
- **Vague retrieval**: the user's starting cues are partial, fuzzy, relational or possibly wrong. Definition in [SOL-JOURNEY], critique point 3.
- Media: photos, **screenshots and document photos** (explicitly named in [PS]). Videos are captured and tagged but analysed separately; the PM will decide whether they are in or out.
- Both **sentimental** (Goa café) and **utility** (medicine, receipt, ID, whiteboard) retrieval. Keep them separable throughout; this is expected to be a key segmentation axis.
- Google Photos primarily, including its search, Ask Photos, People/Places/Things, Map, timeline scrolling and albums.
- **Comparative and workaround evidence** from other products (Apple Photos, OEM galleries such as Samsung Gallery, Amazon Photos, WhatsApp media search), used only to understand behaviours, expectations and workarounds.
- Mobile context by default (per [SOL] scope); desktop evidence is kept but tagged.

### 4.2 Out of scope (collect only if needed for filtering, never analyse as findings)
- Storage pricing, quota and subscription complaints.
- Backup/sync failures, **unless** they explain why a photo could not be found (Stage 0.1).
- Editing tools, sharing bugs, general app crashes.
- General search quality where the user knew exactly what to type and it worked or failed for non-memory reasons. (Kept in an "adjacent" bucket, see §6.3.)
- Browsing for pleasure with no target photo in mind.

### 4.3 Explicit non-goals
- No sentiment dashboard as a headline output.
- No generic "top complaints about Google Photos" list.
- No solution design. The engine may generate *hypotheses* about where intelligence is needed, but not feature specs.

---

## 5. Key definitions (the engine must apply these consistently)

| Term | Functional definition |
|---|---|
| **Retrieval story** | The unit of analysis. One user's account of one attempt (or pattern of attempts) to find a specific photo or set. A single post may contain zero, one or several stories; a thread may contain several users' stories. |
| **Vague retrieval** | Known-item retrieval where the user's starting cues are partial, fuzzy, relational, or possibly wrong, so no single precise filter reaches the target. See [SOL-JOURNEY]. |
| **Precise retrieval** | The user knew exactly what to type or where to go. Tagged as *adjacent*, not core. |
| **Cue** | Any piece of information the user remembers about the target. Taxonomy in [SOL-JOURNEY] question 2.1 (Who / What / Where / When / Event / Perceptual / Meaning / Capture context / Source / Library position). |
| **Cue accuracy** | Certain-correct, certain-wrong, range, relative, inferred ([SOL-JOURNEY] 2.2). Often only inferable when the story reveals the truth later ("turns out it was 2019"). |
| **Journey stage** | Stages 0–10 in [SOL-JOURNEY]. |
| **Failure owner** | Where the breakdown sits: **Library/data** (Stage 0), **Memory** (Stage 2), **Strategy** (Stage 3), **Expression** (Stage 4), **System understanding & matching** (Stage 5), **Presentation & recognition** (Stage 6), **Recovery** (Stage 7), **Persistence** (Stage 8). |
| **Outcome** | Found; found after struggle; substitute accepted; abandoned with fallback; abandoned without fallback; false positive; found later by accident; unknown. ([SOL-JOURNEY] Stage 9.) |
| **Workaround** | Any behaviour outside the intended retrieval path used to get the photo or the information in it ([SOL-JOURNEY] 9.4, 10.2). |
| **Opportunity area** | A combination of **journey stage × failure mode × segment** that, if solved, would move a node of the metric decomposition. |

---

## 6. Data sources and collection (functional requirements)

### 6.1 Sources, what each is good for, and known biases

| Source ([PS] list) | Why it's valuable | Known bias / limitation | Priority |
|---|---|---|---|
| **Reddit** (r/googlephotos, r/GooglePixel, r/Android, r/iphone, r/india, r/DataHoarder, r/applephotos, tech-help subs) | Longest, most narrative retrieval stories; shows cues, tactics and workarounds in the user's own words. | Tech-savvy, Western-skewed, English. | **P0** |
| **Google Photos Help Community / support forums** | Explicit "I can't find my photo" threads; often include what the user tried. | Skews to failures and to Stage 0 (backup/account) issues. | **P0** |
| **Google Play Store reviews** (Google Photos) | Volume; India-heavy; short complaints about search. | Very short, low context; rating-driven. | **P0** |
| **Apple App Store reviews** (Google Photos) | Cross-platform users, Apple-vs-Google comparisons. | Short; smaller volume. | P1 |
| **YouTube comments** (Google Photos search / Ask Photos tutorials and reviews) | Reactions to features, especially Ask Photos; "tried this, didn't work" stories. | Noisy; many off-topic comments. | P1 |
| **Social media** (X/Twitter, public posts) | Real-time frustrations, including Ask Photos reactions. | Short; access limits. | P2 |
| **Other forums** (XDA, Quora, Stack Exchange, tech blog comment sections) | Long-tail detailed stories; Indian users on Quora. | Scattered. | P2 |
| **Competitor/alternative evidence** (Apple Photos search, Samsung Gallery, WhatsApp media search threads) | Behaviour, expectations and workarounds. | Must be tagged as non-GP. | P2 |

**Functional constraints on collection**
- Public data only. Respect each platform's terms. No login-walled or private content.
  > **Amended 26 Sep 2026 (PM decision):** Reddit, X and Quora are collected through Apify although their robots.txt disallows all agents, because Reddit's API is closed to new developers and Reddit carries most of the long-form stories. The method is disclosed on every record and in Methodology. See `Docs/decisions.md` D-1.
- Store the minimum needed; strip personal identifiers (usernames, emails, phone numbers, faces in linked images) before analysis. Quotes shown in outputs must be anonymised.
- Time window: prioritise the most recent 24–36 months (post–Ask Photos era), keeping older data tagged by date so "before vs after Ask Photos" can be compared.
- Language: English, Hinglish/code-mixed and Hindi (translated for analysis, original retained). Other languages are tagged and counted, not necessarily analysed.
- Geography: capture any available region signal. India is a region of interest (the PM's likely interview pool), but not the only one.

### 6.2 Seed search lexicon (to be expanded by the engine)
The engine should start from a seed list and **expand it iteratively** using vocabulary found in relevant posts.

- **Direct:** "can't find photo", "cannot find a picture", "lost photo in google photos", "find old photo", "search not working", "search doesn't find", "ask photos", "photos search useless", "how to find a photo I don't remember when", "find photo without date".
- **Cue-shaped:** "photo from years ago", "picture of a receipt", "medicine photo", "screenshot I took", "photo someone sent me on whatsapp", "photo of a document", "that photo of", "remember taking a photo".
- **Workaround-shaped:** "scrolled for hours", "had to scroll", "asked my friend to send again", "searched whatsapp instead", "found it by accident".
- **Hinglish/Hindi examples:** "photo nahi mil rahi", "purani photo kaise dhoondhe", "google photos me photo search".

The final lexicon, with hit counts per term, is a required output for reproducibility.

### 6.3 Record content to capture per item (functional fields)
Source, platform, URL/permalink, date, the text (and title for threads), parent/thread context for replies, rating (for store reviews), engagement signals (upvotes, likes, "helpful" count), app version or device if stated, language, and any region signal. Replies that answer the question ("try searching X") are valuable: they reveal **known workarounds and tactics** and whether they worked.

### 6.4 Target volumes (guidance, not hard limits)
- Raw collected: ~5,000–15,000 items.
- After relevance filtering: ~500–1,500 retrieval stories, of which core vague-retrieval stories are hopefully 300+.
- Enough per major segment (sentimental vs utility; Android vs iOS) to compare, or the engine must flag that a comparison is under-powered.

---

## 7. Data refinement (functional requirements)

Refinement must be **transparent and countable**. The funnel from raw to analysed data is itself a deck-worthy output.

### 7.1 Steps
1. **De-duplication.** Exact and near-duplicate text; cross-posted threads; review spam.
2. **Language handling.** Detect language; translate non-English for analysis; keep the original.
3. **Unit segmentation.** Split posts and threads into **retrieval stories** (§5). Keep a link to the parent item.
4. **Relevance classification.** Each story is put into exactly one bucket:
   - **Core:** known-item retrieval with vague, partial or wrong cues.
   - **Adjacent:** retrieval with precise cues, general search quality, or Stage 0 issues (backup/account) that affected retrieval.
   - **Irrelevant:** everything else (pricing, editing, crashes, and so on).
   Each classification carries a short reason and a confidence. Adjacent stories are kept because they help explain Stage 0 and Stage 5 failures.
5. **Quality filtering.** Remove stories with too little content to code at least the stage and outcome (for example "search sucks" with nothing else). Keep a count of what was dropped so frequency bias from short reviews is visible.
6. **Anonymisation.** As in §6.1.

### 7.2 Inclusion and exclusion examples (for calibrating the relevance classifier)
| Example | Bucket | Why |
|---|---|---|
| "I remember a pic of a small café in Goa from a trip, no idea which year, search for 'cafe goa' shows nothing." | Core | Known item, partial cues, search failure. |
| "Needed the photo of my prescription, took ages scrolling, finally found by searching 'tablet'." | Core | Utility, vocabulary barrier, eventual success. |
| "Searching my wife's name shows nothing even though face grouping is on." | Adjacent | Precise cue; system/data failure. |
| "My WhatsApp photos never got backed up so I couldn't find the one from my brother's wedding." | Adjacent (Stage 0) | Explains a retrieval failure via library state. |
| "Storage is full, stop asking me to pay." | Irrelevant | Out of scope. |

### 7.3 Validation of classification and coding

**Superseded by §15.7.** The PM is not available to review a coding sample, so reliability is established without a human gold standard: deterministic evidence-span verification, dual-model coding with per-field agreement, and an adjudicator pass. See §15.7 for the full protocol and for what must be disclosed in the Methodology view.

Disagreements still feed back into classifier instructions and examples, and a changelog of those revisions is still kept.

---

## 8. Analysis: coding every retrieval story

### 8.1 The codebook
The codebook is derived from **[SOL-JOURNEY]**. Each story is tagged with the fields below. Allowed values come from the "possible answers" under each question ID in [SOL-JOURNEY], **plus an "other/emergent" value with free text** for everything that doesn't fit. Values not stated in the story are marked **"not stated"**; the engine must not guess.

| Field | Maps to [SOL-JOURNEY] | Notes |
|---|---|---|
| Photo/media type | 0.3, 2.1 (What) | Sentimental vs utility is a mandatory top-level split; plus subtype (screenshot, document, selfie, group, received/forwarded, etc.). |
| Library/data state | 0.1–0.5 | Only when stated or clearly implied. |
| Trigger | 1.1 | |
| Goal after retrieval | 1.2 | |
| Target specificity | 1.3 | |
| Urgency & stakes | 1.4, 1.5 | |
| Cues remembered (multi-select) | 2.1 | Using the cue taxonomy. |
| Cue accuracy | 2.2 | Especially flag certain-but-wrong cues. |
| Cues forgotten (multi-select) | 2.4 | |
| Reason for forgetting | 2.5 | |
| Existence/location belief | 2.6 | |
| Mental model of the system | 2.7 | |
| External cue-gathering | 2.8 | |
| Channel & mode used | 3.1, 3.2, 3.5 | |
| Search avoided and why | 3.4 | |
| Query shape & example query text | 4.1 | Store the literal query where given (anonymised). |
| Cues omitted from query and why | 4.2 | |
| Expression barriers | 4.3 | |
| System failure type | 5.1–5.6 | Inferred from user evidence; mark as inferred. |
| Results experience | 6.1–6.4 | |
| Results-as-cues (memory triggered by results) | 6.5 | Key hypothesis area; tag carefully. |
| Near-hit behaviour (anchor & pivot) | 6.7 | |
| Failure interpretation | 7.1 | |
| Refinement tactics (ordered sequence if available) | 7.2 | |
| Emotional state | 7.4 | Used as severity input, not a headline. |
| Persistence signals (time, attempts, quit reason) | 8.1–8.4 | |
| Outcome | 9.1–9.6 | |
| Workaround / fallback | 9.4, 10.2 | |
| Aftermath (trust, habits) | 10.1–10.2 | |
| **Primary breakdown stage** | Stages 0–10 | Single value: the stage where the story first went wrong. |
| **Failure owner** | §5 | Derived from primary breakdown stage. |
| **Metric node affected** | [SOL-METRIC] | Which factor in the decomposition this story drags down. |
| **Severity** | — | Scale defined in §8.2. |
| **Evidence quote(s)** | — | Short anonymised span(s) that justify the key tags. Mandatory for primary stage and failure owner. |
| **Coding confidence** | — | Low / medium / high per story. |

### 8.2 Severity (functional definition)
A per-story judgement combining: **stakes** (sentimental loss, money, health, legal), **outcome** (abandoned > substitute > found after struggle > found), **effort spent** (time, attempts), and **emotional intensity**. The rubric must be written down, shown in the methodology view, and applied consistently.

### 8.3 Emergent themes
Periodically cluster the "other/emergent" values and uncoded patterns. Propose new codes to the PM with example stories. The PM approves or rejects; approved codes get applied retroactively. This protects against the codebook blinding the engine to things [SOL-JOURNEY] missed.

### 8.4 Aggregate analyses (required views)
1. **Relevance funnel:** raw → deduped → stories → core/adjacent/irrelevant, per source.
2. **Journey breakdown heatmap:** count and share of core stories by primary breakdown stage, split by sentimental vs utility.
3. **Failure-owner distribution:** with metric-node mapping, i.e. which decomposition factors are losing the most users.
4. **Cue matrix:** for each cue type, % of stories where it was remembered, forgotten, or wrong. This directly answers "what do people remember / forget".
5. **Cue → query translation:** which remembered cues make it into queries vs get dropped, and why (4.2, 4.3). Answers "how do users formulate searches".
6. **Query pattern library:** clustered example queries by shape (keyword, natural language, relative time, code-mixed…) with outcome rates.
7. **Photo-type breakdown:** which kinds of photos are hardest to retrieve (by frequency and by severity).
8. **Tactics and recovery:** refinement tactics used and how often each leads to success; prevalence of anchor-and-pivot and results-as-cues.
9. **Workaround map:** what people do instead, and which workarounds reveal an unmet need GP could own.
10. **Outcome by mode:** success/abandon rates by retrieval mode (keyword search, Ask Photos, scroll, People, Map…), with the caveat that public data over-represents failures.
11. **Segment cross-tabs:** at minimum photo type × failure owner, urgency × outcome, platform × failure owner, library-state issues × outcome; plus library topology (hoarder/curator/passive) where inferable.
12. **Before vs after Ask Photos:** how failure modes shift over time, where date data allows.
13. **Source comparison:** does the pattern hold across sources, or is it one community's artefact?

Every aggregate number must be drill-down-able to the underlying stories and quotes.

---

## 9. Opportunity identification, comparison and recommendation

### 9.1 Forming opportunity areas
An opportunity area = **primary breakdown stage × specific failure mode × segment**, for example "Stage 5.3: wrong or fuzzy time cues applied as hard filters × sentimental trip photos × heavy users". The engine proposes candidate areas by grouping stories; the PM can merge, split, rename or add.

Each opportunity card contains:
- a plain-language problem statement, framed as *why* retrieval fails despite partial memory (not "search is hard");
- the journey stage(s), failure owner and metric node affected;
- segment(s) most affected;
- evidence: story count, share of core stories, source spread, severity distribution, 3–5 representative anonymised quotes;
- current workarounds;
- where intelligence would be needed (which stage and what kind of inference, e.g. interpreting relative time, treating cues as soft, using results to prompt recall) — stated as a hypothesis;
- open questions for interviews.

### 9.2 Scoring criteria
| Criterion | Question it answers | Source |
|---|---|---|
| **Frequency** | How often does this appear among core stories? | Engine counts |
| **Severity** | How bad is it when it happens? | §8.2 |
| **Reach proxy** | How broad is the affected segment (e.g. utility photos vs niche)? | Segment tags + PM judgement |
| **Metric leverage** | How much would fixing it move the goal metric, given its place in [SOL-METRIC]? | Metric-node mapping |
| **Addressability by Google Photos** | Can GP fix it, or does it lie outside (e.g. the photo was never backed up)? | Failure owner + PM judgement |
| **AI necessity** | Does solving it need intelligence, or would a simple UI fix do? ([PS]: "where intelligence is actually needed") | PM judgement, engine hypothesis |
| **Evidence strength** | Is it consistent across sources and coded with high confidence? | Source spread + confidence |

Requirements:
- Weights are **visible and adjustable** by the PM, and the ranking updates when they change.
- The engine shows a **sensitivity check**: does the top opportunity stay on top under reasonable weight changes?
- Each score has a one-line justification.

### 9.3 Comparison views
- A ranked table of opportunities with all criterion scores.
- A 2×2 view (for example frequency × severity, or metric leverage × AI necessity), with the axes selectable. The PM's segmentation plan in [SOL] explicitly calls for a 2×2.
- Side-by-side comparison of any two or three opportunity cards.

### 9.4 Recommendation output
The engine must produce a clear recommendation, explicitly labelled as **a hypothesis to be validated in Part 3**, containing:
1. The top opportunity (and the runner-up), with the reasoning chain: metric node → evidence → stage → root-cause hypothesis.
2. The recommended **target segment direction** (e.g. utility vs sentimental; library topology; urgency).
3. The **root-cause hypothesis**: why retrieval fails despite partial memory.
4. Where in the journey intelligence is most likely needed.
5. What would falsify the recommendation.

### 9.5 Handoff to user research (Part 3)
The engine produces:
- **Hypotheses to test**, each linked to the evidence that raised it.
- **Screening criteria** for recruiting interviewees in the recommended segment.
- **Interview guide inputs:** question prompts per journey stage, prioritising the questions public data could not answer (§3.3), plus a suggested observed retrieval task ("find that photo now, thinking aloud").
- **Representative retrieval tasks** drawn from real stories, usable later for MVP testing in Part 6.

After interviews, the PM will want to add interview notes as a separate, clearly labelled source and see which engine findings were confirmed, contradicted or refined. Design with this in mind (should-have, see §12).

---

## 10. "Ask AI": conversational access to the evidence

A chat interface over the processed dataset, for the PM and evaluators.

Functional requirements:
- Answers are **grounded only** in the collected and coded data. It must say when the data doesn't contain the answer, rather than falling back on general knowledge.
- Every answer **cites** the stories it draws on (anonymised quotes with source and date) and gives **counts** where relevant ("37 of 412 core stories…").
- It can answer both qualitative questions ("How do people describe medicine photos they're searching for?") and quantitative ones ("What share of utility-photo stories end in abandonment?").
- It understands the codebook vocabulary (stage IDs, failure owners, cue types) so the PM can ask "show me Stage 6.5 stories".
- It flags low-confidence or small-sample answers.
- Suggested starter questions include the [PS] sample questions.

---

## 11. Outputs and experience (what the public link must offer)

| Output | Purpose | Audience |
|---|---|---|
| **Overview** | One-screen summary: data funnel, top findings, top opportunities, recommendation. Understandable in under 2 minutes. | Evaluator, PM |
| **Journey view** | Breakdown heatmap across Stages 0–10, clickable to stories. | PM, evaluator |
| **Memory view** | Cue matrix (remembered / forgotten / wrong) and cue → query translation. | PM |
| **Opportunity board** | Ranked cards, scoring weights, 2×2, comparison. | PM, evaluator |
| **Evidence explorer** | Filter stories by any codebook field and read them with their tags and quotes. | PM, evaluator |
| **Ask AI** | §10. | PM, evaluator |
| **Try it** | Paste a post or review (or pick a sample) and watch the engine classify and code it end to end. Shows the workflow is real and testable. | Evaluator |
| **Methodology** | Sources, lexicon, funnel, codebook, severity rubric, scoring weights, validation results, limitations. Also the basis for the one-slide explanation. | Evaluator |
| **Exports** | Charts and tables sized for slides; the opportunity table; interview hypotheses and guide inputs. | PM |

Deck constraints from [PS] that affect exported charts: readable in a 10-slide PDF, **minimum font size rules**, and **colour-blind-safe palettes** (never encode meaning by colour alone).

---

## 12. Prioritisation (time-boxed)

**Hard deadline:** 7 October 2026, 3:59 PM IST ([PS]). Build so that a usable, testable version exists early and improves afterwards.

| Priority | Capabilities |
|---|---|
| **Must have** | P0 sources collected; dedup, story segmentation, relevance buckets with a visible funnel; coding on the core fields (photo type, cues remembered/forgotten, query shape, mode, primary breakdown stage, failure owner, metric node, outcome, workaround, severity, evidence quote); aggregate views 1–5, 7 and 9; opportunity cards with scoring and ranking; recommendation; interview handoff; evidence explorer; public link; methodology page. |
| **Should have** | P1 sources; full codebook coverage; Ask AI with citations; "Try it"; adjustable weights with sensitivity check; 2×2; PM validation sample with agreement rate; emergent-theme review. |
| **Could have** | P2 sources; before/after Ask Photos; source comparison; adding interview notes as a source; lexicon auto-expansion loop; slide-ready exports. |
| **Won't have (now)** | Real-time monitoring; sentiment dashboards; non-English deep analysis beyond Hindi/Hinglish; solution design. |

---

## 13. Quality, bias and limitations (must be surfaced in the product, not hidden)

- **Selection bias:** public posts over-represent painful failures and technical users; quiet successes and people who never search are under-represented. Present frequencies as *directional*, and use rates cautiously.
- **Short-text bias:** store reviews are too short to code most fields; report coverage per field (% of stories where a field is "not stated").
- **Inference risk:** system-side failures (Stage 5) are inferred from user accounts. Label them as inferred.
- **LLM coding error:** mitigated by evidence quotes, confidence levels, PM validation sampling and agreement rates.
- **Codebook blindness:** mitigated by emergent-theme review (§8.3).
- **Ethics and privacy:** public data only, anonymised quotes, no attempt to identify individuals, respect for platform terms.
- **Cost awareness:** the engine should process at a scale and cost appropriate for a student project; prefer re-using processed results over re-processing.

---

## 14. Definition of done

The engine is done when:
1. An evaluator can open a public link, understand the overview within 2 minutes, drill into evidence, ask a grounded question and get a cited answer, and run the workflow on a sample post.
2. Each [PS] sample question (§3.2) has an explicit, evidence-backed answer view.
3. At least ~300 core vague-retrieval stories are coded, from at least 3 source types, with a visible funnel.
4. Opportunity areas are ranked with transparent, adjustable scoring and a sensitivity check.
5. A recommendation exists, stating the top opportunity, target-segment direction, root-cause hypothesis and where intelligence is needed, framed as hypotheses for Part 3.
6. Interview handoff materials exist (hypotheses, screener criteria, guide inputs, representative retrieval tasks).
7. The methodology can be explained on one slide.
8. Coding reliability is established per §15.7 (evidence-span pass rate, per-field inter-model agreement, low-reliability fields flagged) and reported in the Methodology view, with the absence of a human gold standard stated plainly.

---

## 15. Decisions (resolved 25 September 2026)

These were open questions for the PM. They are now **decided and binding**. Claude Code should build to them. If evidence during the build contradicts one, raise it explicitly rather than silently deviating.

### 15.1 Videos — excluded from core analysis, tagged and counted

**Decision:** Video-only retrieval stories are **out of the core analysis**. Screenshots and document photos remain **in** (named explicitly in [PS]). Every story still carries a `media_type` tag, and video stories are counted and reported.

**Rationale:** The goal metric says "a photo they remember." Video also has a materially different Stage 6 — a video cannot be recognised from a grid thumbnail, it must be opened and scrubbed — so pooling it would confound recognition failure with a media-format problem outside this scope.

**Build implication:** One enum field, not a pipeline branch. The relevance classifier routes video-only stories to `adjacent` with reason `video_out_of_scope`. The funnel view (§8.4 view 1) shows the count. If video-involving stories exceed 15% of otherwise-core stories, surface that as a stated limitation, not a re-scoping.

### 15.2 Opportunity scoring — two gates, then five weights

**Decision:** Of the seven criteria in §9.2, **Addressability by Google Photos** and **AI necessity** act as **gates**, not weights. The remaining five are weighted:

| Criterion | Role | Default weight |
|---|---|---|
| Addressability by GP | Gate — must score ≥3/5 | — |
| AI necessity | Gate — must score ≥3/5 | — |
| Metric leverage | Weighted | 30 |
| Severity | Weighted | 25 |
| Frequency | Weighted | 20 |
| Evidence strength | Weighted | 15 |
| Reach proxy | Weighted | 10 |

All criteria scored 1–5 with a one-line justification (§9.2). Weights remain PM-adjustable in the UI as §9.2 requires; the table above is the default and the pre-registered setting.

**Rationale:** Addressability and AI necessity are pass/fail questions. Weighting them would let a frequent but unfixable problem rank highly on volume, and would let a problem needing only a UI tweak survive — which fails [PS]'s "where intelligence is actually needed" test. Frequency is held at 20 because §13 concedes public-data frequency is directional; letting it dominate would contradict the product's own limitations disclosure. Reach is weighted low because it correlates with frequency in this corpus, and is defined as *estimated share of the GP user base affected* (PM judgement), not story count.

**Build implication:**
- Gated-out candidates are **shown, not hidden**, greyed with the failing gate and its reason. The funnel from candidate areas to gated to ranked is itself a deck slide.
- **Weights are pre-registered before the ranking is first run.** Record the timestamp. Tuning weights after seeing results invalidates the sensitivity check.
- **Sensitivity protocol (§9.2):** perturb all five weights randomly within ±10 absolute, 1,000 runs, report the percentage of runs in which the top-ranked area stays top. ≥80% = robust. <60% = present the top two as co-leaders and say so.

### 15.3 India — a recruiting constraint, not an analytical filter

**Decision:** Analyse the corpus **globally**. Region is a **cross-tab dimension** (§8.4 view 11), never a filter on the whole analysis. India is the **interview and MVP-testing** recruiting pool (Parts 3 and 6). India-specific claims are made **only where the cross-tab shows a real difference** at the thresholds in §15.5.

**Rationale:** Filtering the corpus to India would gut the sample — English-language Reddit is Western-skewed by §6.1's own bias table, leaving mostly Play Store reviews, which are too short to code most fields. It would trade the highest-quality evidence for geographic purity the brief does not ask for. If the top opportunity proves universal, that is a stronger business case for Google than an India-only one.

**Build implication:** Three India-flavoured **hypotheses to test, not assume**, each a taggable code:
1. WhatsApp as both primary photo source and primary workaround — forwarded images carry received-date rather than capture-date and have EXIF stripped (Stage 0.2 directly).
2. Hinglish / code-mixed queries failing at Stage 5.1 parsing.
3. Uneven Ask Photos availability changing which failure modes are reachable at all.

The Methodology view must state that interviews are drawn from a single region and that the engine's findings are global-directional.

### 15.4 Sentimental vs utility — two parallel analyses, one MVP

**Decision:** **One** corpus, **one** codebook, **one** pipeline, with a mandatory `photo_class` field (`sentimental | utility | both | unclear`). **Every** aggregate view in §8.4 splits on it. The opportunity ranking then **converges on one** class for the Part 5 MVP.

**Rationale:** The two populations differ at nearly every stage. Utility photos are poorly encoded (snapped without attention), remembered by content and purpose, OCR-dependent, high-urgency, and rarely substitutable — the user needs *that* prescription. Sentimental photos are better encoded, remembered by who/where/when, lower-urgency, and often substitutable — any photo from the trip may do. Pooling them averages away the single most informative contrast in the dataset. But two pipelines would double the build cost for no analytical gain, and [PS] Part 5 requires exactly one MVP.

**Build implication:** One enum field, one split applied at the view layer. This field is also the default axis of the §9.3 2×2 and the basis of the segmentation slide. The deck uses the split to **justify** the chosen segment, not merely to describe it.

### 15.5 Insufficient evidence — n < 30 per cell

**Decision:** Three tiers, applied everywhere a proportion is displayed:

| Cell size | Treatment |
|---|---|
| **n < 30** | "Insufficient evidence." Raw count only. No percentage, no comparison drawn. |
| **30 ≤ n < 80** | Directional. Percentage shown with count and a widened confidence interval, labelled *directional*. |
| **n ≥ 80** | Comparable. A difference is claimed only if 95% CIs do not overlap, or Fisher's exact test gives p < 0.05. |

**Hard rule:** no percentage is ever displayed without its denominator — in the product or in the deck.

**Rationale:** Below n=30 a single story moves the share by more than 3pp, so any comparison reads noise. Checked against the §6.4 target of 300+ core stories: a 2-way split yields ~150 per cell (comparable), a 2×2 yields ~75 (directional), and a 3-dimension cross-tab breaches the floor immediately.

**Build implication:** **Headline claims are capped at two cross-tab dimensions.** Any three-dimension cell is illustrative only, explicitly labelled, and may never support the recommendation. Implement the tiering as a single shared display helper so no view can bypass it.

### 15.6 Evaluator access — frozen corpus plus live single-item "Try it"

**Decision:** Evaluators explore a **frozen, version-stamped dataset** and can run the **full pipeline live on one pasted post or URL at a time**. No evaluator-triggered bulk collection.

**Rationale:** An open collection trigger on a public link is an unbounded cost and a platform-terms exposure. More importantly, a corpus that shifts mid-evaluation would stop matching the numbers printed in the deck — far worse than appearing static. [PS] asks only for "a link where the workflow can be tested," which single-item "Try it" satisfies precisely, and more convincingly, since the evaluator watches classification and coding happen on their own input.

**Build implication:**
- Stamp the corpus visibly: *"Corpus v1.0 — N core stories, collected <date range>."*
- "Try it" accepts pasted text **or** a URL; rate-limited.
- "Try it" shows the full trace: relevance bucket + reason + confidence → codebook tags with evidence spans → which aggregate views this story would join.
- Optional, near-zero cost: a "run on 10 held-out stories" control backed by pre-computed results.

### 15.7 Coding validation — no human gold standard (supersedes §7.3)

**Decision:** The PM will **not** review a coding sample. Reliability is established by automated means and **disclosed honestly** rather than overstated.

**Protocol:**
1. **Deterministic evidence-span verification (highest value, lowest cost).** §8.1 already mandates a verbatim quote for primary stage and failure owner. Add a non-LLM check that each quote is a literal substring of the source text after normalisation. Any story failing is automatically re-coded once, then dropped and counted. This catches fabricated evidence cheaply and with certainty.
2. **Dual-model coding on a held-out sample of 80–100 stories.** Code twice — primary coder, then a second pass with a different model or a materially different prompt framing. Compute per-field agreement: Cohen's κ for single-select fields, Jaccard for multi-select.
3. **Per-field reliability gate.** Any field with κ < 0.6 is flagged **low-reliability** in the Methodology view and **barred from headline claims and from the recommendation**.
4. **Adjudicator pass.** A third call sees the story and both codings, selects or writes the correct value with a rationale, producing a silver-standard set without PM time.
5. **Evaluator-facing sanity strip.** The Methodology view displays 10 randomly chosen coded stories with their source text, tags and evidence spans side by side, so an evaluator can judge coding quality themselves in under a minute. This relocates human validation from the PM to the reader and is a credibility asset rather than a gap.

**Disclosure requirement:** the Methodology view must state plainly that there is **no human-adjudicated gold standard**, that reliability figures are **inter-model agreement plus deterministic evidence verification**, and that inter-model agreement measures consistency rather than correctness — two models can agree and both be wrong.

**Rationale:** Losing PM review removes §14's original point 8. Rather than drop the claim, replace it with checks that are automatable, cheap and honestly bounded. The evidence-span check in particular is deterministic and catches the failure mode that most threatens the analysis — hallucinated quotes backing a tag.

---

## 16. Constraints on the build itself

Added 25 September 2026, alongside §15.

- **Minimum time to build.** Prefer the shortest path that satisfies §14. Reach for an existing pattern before designing a new one.
- **Minimum complexity.** Fewer moving parts beats elegance. Reuse one pipeline with a field over branching into two. Reuse one display helper over per-view logic. No infrastructure that the deliverables in §1.4 do not require.
- **Efficiency.** Cache and re-use processed results; never re-process an unchanged story (§13, cost awareness). Batch model calls. Store coded output so every view reads from one processed dataset rather than recomputing.
- **Front-end.** UI and UX are ported from the PM's existing Myntra discovery engine (`github.com/Arvind710/myntra-discovery-engine`). Content, structure and data are new; the visual system, layout language and Ask AI interaction pattern are reused. Do not redesign what already works.
