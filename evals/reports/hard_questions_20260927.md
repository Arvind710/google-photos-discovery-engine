# Hard questions — Ask AI, 2026-09-27

The PM: "ask a complex, nuanced set of questions to test it and evaluate the answer."
Fourteen questions (`evals/fixtures/hard_questions.yaml`): multi-part, causal, a what-if,
a request for real examples, a sceptic, the method, a recommendation, a trap comparison,
feelings, a false premise, an ambiguous follow-up, an off-topic request, a numbers question,
and a synthesis. Not a gate: every answer read and graded by hand. Run with
`evals/golden_sweep.py --file evals/fixtures/hard_questions.yaml --name hard`.

## What the first run (v3.12) exposed, and what changed

| Q | First run | Cause | Fix |
|---|---|---|---|
| H10 "Since Ask Photos made things worse for everyone…" | Recommended rollbacks on the false premise | A plan from rules had no premise detection | "Since/because X, …" flags the premise; the writer must correct it first |
| H9 feelings, H11 giving up, H13 how they found it | Generic first-failure figures | No rule routed them to their codebook questions | Rules for 7.4, 9.4, 9.1 — with the posts' own words |
| H6 "how often did readers disagree?" | Answer's second half dropped | The writer subtracted 100 − 69 (no arithmetic allowed) | Reliability lines state agreed AND disagreed |
| H8 screenshots vs people | Claimed the study did not split by kind | Invented method claim | Never say the study did not measure something unless a note says so |
| H12 poem | Offered to write the poem | Offer outside the study | No offers outside the study |
| H4 "give real examples" | Examples in one run, none in the next | Prompt compliance | A final reminder: quote two or three exact phrases when asked for words |
| H14 three takeaways | Repair left two of three | A dropped list item | Dropping an item of a list sends the answer to the fallback |

## Final run (`ask_v3.17`, `ask-hard-synth-20260926-223013-071c8a`, $0.036)

All 14 routed as expected; none late (max 9.5 s); 2 fell back.

| Grade | Questions | Note |
|---|---|---|
| A / A− | H1, H3, H7, H11, H12 | Steps ranked with counts; the what-if names what would remain, each with its count; a reasoned build priority; "four of 115 said they gave up", honestly bounded; a polite decline that turns to the study |
| B | H2, H4, H5, H6, H13 | Mostly right; H6 calls 69 of 100 agreement "a sizable minority" (it is a majority); H4 counts a filename and "recently added" as scene words |
| C | H8, H9, H10, H14 | H8: "search interpretation matters more for memory-photos" — a kinds comparison the check missed; H9: says feelings shorten later attempts — no evidence; H10, H14: correct but thin fallbacks |

## Still open

- Comparisons phrased without a kind word the check knows ("matters more for memory-photos"),
  and wrong glosses of a correct figure ("a sizable minority" for 69 of 100), are not caught.
- A fraction is checked against any share its sentence cites, not the one it describes.
- The "few posts say anything about this — N of 331 do" lines come from coverage over all cases.
