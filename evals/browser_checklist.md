# Browser checklist — Claude in Chrome against the LIVE URL

`architecture.md` §10: `AppTest` cannot see `st.html`, CSS fails silently, and the
stale-module trap only reproduces on Cloud. **Python tests the data and the logic;
Chrome tests the product.** Run this after every deploy; a green CI build is not a
verified deploy (`implementationplan.md` §0.3, class BR).

## Every deploy (from P0)

| ID | Check | How |
|---|---|---|
| BR-1 | Every page in the nav renders content, not an exception | Navigate each; screenshot |
| BR-2 | Console clean, no failed requests | `read_console_messages`, `read_network_requests` after load |
| BR-3 | Stylesheet applied | `getComputedStyle` on the pinned sidebar (`[data-testid=stSidebar]` min-width = 16.5rem at ≥900px) and on one card's `border-top` |
| BR-4 | Phone width + both themes readable | Resize to 390px; toggle light/dark |
| BR-9 | Corpus stamp present in the footer | Text search on each page |
| BR-10 | Cold start after sleep | Time the first load after the app has slept (Myntra: 78s against a stated 15) |

## Added by phase

- **P1** Data Bank funnel renders; every share goes through `share()` (no `%` without "of N").
- **P4** Analysis + Opportunities; gated-out candidates visible and greyed.
- **P5** Ask AI end to end (restatement, citations, caveat, closing question, run-meta);
  refusal on an out-of-scope question; Try it trace renders.
- **P6** Full sweep P6-BR-1…12 (`evals.md` §11), incl. the unhedged no-gold-standard disclosure.
