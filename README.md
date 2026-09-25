# Google Photos Discovery Engine

Part 1 of the NextLeap September problem: an AI-powered discovery engine that reads
public conversations about finding photos in Google Photos, splits them into
individual **retrieval stories**, codes each against an eleven-stage retrieval
journey (60 questions), and ranks where retrieval of *vaguely remembered* photos
breaks — and where intelligence is actually needed.

- **What it must do:** `Docs/NextLeap Grad Projects.code-workspace.md`
- **How it is built:** `Docs/architecture.md` · **What breaks:** `Docs/edgecase.md`
  · **How we'd know:** `Docs/evals.md` · **Build order:** `Docs/implementationplan.md`

## Layout

```
app/            Streamlit app (read-only; every number is a SELECT)
  Home.py       router          lib/  nav, db, evidence (the share() helper)
pipeline/       offline, laptop-only: collect → clean → segment → classify → validate → analyse
  schema.sql    the frozen schema       common/  db, codebook (+freeze), runs (cost), env
codebook/       journey_v1.yaml (THE codebook, frozen) + severity, metric nodes, scoring, lexicon
evals/          pytest gates p0…p6, fixtures, gate reports, browser checklist
data/corpus.db  the frozen corpus the app serves
```

## Run

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/streamlit run app/Home.py
.venv/bin/pytest evals/ -m p0            # a phase gate
.venv/bin/python evals/report.py p0      # the same, written to evals/reports/
```

Pipeline work also needs `pip install -r requirements-pipeline.txt` and a `.env`
(see `.env.example`). Nothing secret is ever committed; CI runs a secret scan.
