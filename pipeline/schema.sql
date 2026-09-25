-- corpus.db — architecture.md §4, plus implementationplan.md Appendix A deltas.
--
-- Idempotent: every statement is IF NOT EXISTS, so `pipeline.common.db.init()`
-- is safe on an existing file. The schema is frozen at P0 — changing it after
-- data is in costs a re-run the $15 budget cannot fund (Appendix A).
--
-- Deltas applied here, each marked inline:
--   A.1  exclusions MARKS, it does not remove. Every collected record stays in
--        `records`; the accounting identity becomes
--        records = kept + excluded, each record exactly one of the two at the
--        record level (P1-INV-1). P1-MET-3 samples lexicon-rejected rows, so
--        rejection must not delete them.
--   A.2  stories.author_key — authorship per story, not per record (EC-COL-12).
--   A.3  analysis_coverage PK is (question, source); source '_all' = pooled.
--   A.4  runs.estimate_usd beside cost_usd, so T-19 (halt at 1.5×) is mechanical.
--   A.5  chunking is transient: a long record stays ONE row; the segmenter
--        chunks in memory and merges. No chunk table, by design.
--   A.6  (found in P0) stories.char_start/char_end — offsets into
--        records.text_clean. P2-INV-2 (spans do not overlap) is uncheckable
--        without them, and EC-ASK-6 wants offsets for exact rendering.
--   A.7  (found in P0) analysis_reliability carries raw agreement, κ and the
--        top-value share together, and `degenerate` is a verdict (EC-VAL-2).
--   A.8  (found in P0) `published` pins the run the app serves (EC-OPS-11, X-3).
--   A.9  (P1, 2026-09-26) five more sources, per the PM's source decision
--        (Docs/decisions.md D-1): youtube, stackexchange, hackernews, x, quora.
--        Applied before any record existed, so it cost nothing.
--   A.10 (P1, 2026-09-26) records.collect_method on every row, so HOW a record
--        was obtained is disclosed per record, not only in prose (D-1).
--   A.11 (P1, 2026-09-26) records.posts_json — for a thread stored as ONE
--        record (EC-COL-4), the post boundaries inside text_clean:
--        [{"author_key": …, "start": …, "end": …}, …], end exclusive. A
--        story's author is the author of the post its span starts in, so
--        per-story authorship (A.2, EC-COL-12) is looked up, not guessed by a
--        model. NULL for single-post records. Last column, so an in-place
--        ALTER TABLE on an existing file matches a fresh build.

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------ collect
CREATE TABLE IF NOT EXISTS records (         -- raw collected material, immutable
  record_id      TEXT PRIMARY KEY,           -- sha1(source || native_id): re-ingest is idempotent (EC-CLEAN-7)
  source         TEXT NOT NULL CHECK (source IN (                                 -- A.9
                   'reddit','gp_help','play','appstore',
                   'youtube','stackexchange','hackernews','x','quora')),
  collect_method TEXT NOT NULL CHECK (collect_method IN (                         -- A.10
                   'official_api',       -- YouTube Data API, Stack Exchange API, HN Algolia
                   'public_feed',        -- Apple's customer-review RSS feed
                   'public_scraper_lib', -- google-play-scraper
                   'headless_render',    -- GP Help Community thread pages (Playwright)
                   'apify')),            -- Reddit, X, Quora (and GP Help fallback)
  source_url     TEXT NOT NULL CHECK (length(source_url) > 0),   -- no record without a permalink
  native_id      TEXT,
  author_key     TEXT,                       -- salted hash; salt is env-only (EC-OPS-7)
  created_at     TEXT,                       -- nullable: some sources give none (EC-COL-9)
  text_raw       TEXT NOT NULL CHECK (length(text_raw) > 0),
  text_clean     TEXT NOT NULL,              -- CANONICAL text: coding, quoting, verification (EC-CLEAN-4)
  text_en        TEXT,                       -- translation, an AID in the prompt only; never a span source
  lang           TEXT,                       -- metadata; 'unknown' is valid, never a drop reason (EC-CLEAN-5)
  rating         INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
  engagement     INTEGER,
  thread_context TEXT,                       -- may be read, never quoted (EC-SEG-9)
  platform_hint  TEXT CHECK (platform_hint IS NULL OR platform_hint IN ('android','ios','desktop','unknown')),
  region_hint    TEXT,                       -- a cross-tab dimension, never a filter ([CTX] §15.3)
  collect_query  TEXT,                       -- which lexicon term surfaced it — bias audit
  collected_at   TEXT NOT NULL,
  ingest_run_id  TEXT NOT NULL,
  posts_json     TEXT                        -- A.11: post boundaries + per-post author_key
);

-- A.1: a marking table. `record_id` references a row that still exists.
CREATE TABLE IF NOT EXISTS exclusions (
  exclusion_id INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id    TEXT NOT NULL REFERENCES records(record_id),
  story_id     TEXT,                         -- set when a single story, not the record, is dropped
  source       TEXT,
  stage        TEXT NOT NULL CHECK (stage IN ('collect','clean','prefilter','segment','code','validate')),
  reason       TEXT NOT NULL CHECK (reason IN (          -- P1-INV-5: the allowed enum
                 'deleted',                    -- [deleted]/[removed] body (EC-COL-3)
                 'too_short',                  -- length floor (EC-COL-5)
                 'low_quality',                -- template / nothing codeable (EC-COL-8, [CTX] §7.1 step 5)
                 'exact_duplicate',            -- exact hash, any source (EC-CLEAN-2)
                 'near_duplicate_same_author', -- Jaccard > 0.85 within (source, author_key) ONLY (EC-CLEAN-1)
                 'lexicon_rejected',           -- free prefilter gate; sampled by P1-MET-3
                 'out_of_window',              -- outside the collection time window
                 'no_story',                   -- relevant, zero retrieval stories (EC-SEG-7)
                 'span_unverified',            -- evidence failed substring check twice (EC-CODE-5)
                 'coding_failed',              -- malformed output after one retry (EC-CODE-11)
                 'model_refusal'               -- content-policy refusal (EC-CODE-12)
               )),
  detail       TEXT,
  run_id       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_exclusions_once
  ON exclusions (record_id, COALESCE(story_id, ''), stage);

-- ------------------------------------------------------------------ segment
CREATE TABLE IF NOT EXISTS stories (         -- the unit of analysis ([CTX] §5)
  story_id      TEXT PRIMARY KEY,
  record_id     TEXT NOT NULL REFERENCES records(record_id),
  ordinal       INTEGER NOT NULL CHECK (ordinal >= 0),
  text          TEXT NOT NULL CHECK (length(text) > 0),    -- exact substring of records.text_clean (T-1)
  char_start    INTEGER NOT NULL CHECK (char_start >= 0),  -- A.6
  char_end      INTEGER NOT NULL,                          -- A.6, exclusive
  author_key    TEXT,                                      -- A.2
  bucket        TEXT NOT NULL CHECK (bucket IN ('core','adjacent','irrelevant')),
  bucket_reason TEXT NOT NULL CHECK (length(bucket_reason) > 0),
  bucket_conf   REAL NOT NULL CHECK (bucket_conf BETWEEN 0 AND 1),
  reaches_stage INTEGER NOT NULL CHECK (reaches_stage BETWEEN 0 AND 10),  -- gates blocks C/D; set GENEROUSLY (EC-SEG-5)
  run_id        TEXT NOT NULL,
  CHECK (char_end > char_start),
  CHECK (char_end - char_start = length(text)),
  UNIQUE (record_id, ordinal)
);

-- -------------------------------------------------------------------- code
CREATE TABLE IF NOT EXISTS story_spine (     -- block A, one row per story
  story_id      TEXT PRIMARY KEY REFERENCES stories(story_id),
  photo_class   TEXT NOT NULL CHECK (photo_class IN ('sentimental','utility','both','unclear')),  -- [CTX] §15.4
  media_type    TEXT NOT NULL CHECK (media_type IN ('photo','screenshot','document','video','mixed')), -- §15.1
  photo_subtype TEXT,
  primary_stage TEXT NOT NULL CHECK (primary_stage IN ('0','1','2','3','4','5','6','7','8','9','10')),
  failure_owner TEXT NOT NULL CHECK (failure_owner IN (
                  'library_data','memory','strategy','expression','system',
                  'presentation','recovery','persistence','none')),
  metric_node   TEXT,
  outcome       TEXT NOT NULL CHECK (outcome IN (          -- [CTX] §5; 'not_stated' is its "unknown"
                  'found','found_after_struggle','substitute_accepted',
                  'abandoned_with_fallback','abandoned_without_fallback',
                  'false_positive','found_later_by_accident','not_stated')),
  mode_used     TEXT,
  severity      INTEGER CHECK (severity IS NULL OR severity BETWEEN 1 AND 5),
  urgency       TEXT,
  workaround    INTEGER CHECK (workaround IS NULL OR workaround IN (0,1)),
  workaround_text TEXT,
  coding_conf   REAL NOT NULL CHECK (coding_conf BETWEEN 0 AND 1),
  why           TEXT NOT NULL,               -- ONE clause, ~15 words (§8 cost)
  run_id        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_codes (     -- blocks B/C/D: long and narrow
  story_id   TEXT NOT NULL REFERENCES stories(story_id),
  question   TEXT NOT NULL,                  -- "0.1" … "10.3"
  value      TEXT NOT NULL,                  -- listed value, not_stated, or other:<free text>
  accuracy   TEXT CHECK (accuracy IS NULL OR accuracy IN (
               'certain_correct','certain_wrong','range','relative_only','inferred')),  -- 2.2 only
  seq        INTEGER,                        -- ordered tactics (7.2) keep their order
  inferred   INTEGER NOT NULL DEFAULT 0 CHECK (inferred IN (0,1)),   -- every Stage 5 row = 1 (EC-CODE-15)
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  run_id     TEXT NOT NULL,
  PRIMARY KEY (story_id, question, value, run_id),
  CHECK (substr(question, 1, 2) <> '5.' OR inferred = 1)
);

CREATE TABLE IF NOT EXISTS evidence (        -- substring-verified against text_clean BEFORE write
  story_id TEXT NOT NULL REFERENCES stories(story_id),
  field    TEXT NOT NULL,
  span     TEXT NOT NULL CHECK (length(span) >= 15),   -- T-3 (EC-VAL-5)
  verified INTEGER NOT NULL CHECK (verified IN (0,1)),
  run_id   TEXT NOT NULL,
  PRIMARY KEY (story_id, field, run_id)
);

CREATE TABLE IF NOT EXISTS queries (         -- literal queries users reported typing (4.1)
  story_id   TEXT NOT NULL REFERENCES stories(story_id),
  query_text TEXT NOT NULL,
  shape      TEXT,
  attempt_no INTEGER,
  worked     INTEGER CHECK (worked IS NULL OR worked IN (0,1)),
  run_id     TEXT NOT NULL
);

-- --------------------------------------------------------------- validate
CREATE TABLE IF NOT EXISTS double_coding (
  story_id TEXT NOT NULL REFERENCES stories(story_id),
  field    TEXT NOT NULL,
  coder    TEXT NOT NULL,                    -- primary | secondary | adjudicator
  value    TEXT,
  run_id   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_reliability (   -- A.7
  field         TEXT PRIMARY KEY,
  metric        TEXT NOT NULL CHECK (metric IN ('kappa','jaccard')),
  value         REAL,                        -- κ (single-select) or mean Jaccard (multi-select)
  raw_agreement REAL,
  top_share     REAL,                        -- share of the most common value — the κ-paradox guard
  marginals_json TEXT,
  n             INTEGER NOT NULL,
  verdict       TEXT NOT NULL CHECK (verdict IN ('ok','low_reliability','degenerate')),
  run_id        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_coverage (      -- §3.4 register — all 60 questions, published
  question     TEXT NOT NULL,
  source       TEXT NOT NULL,                -- A.3: '_all' for the pooled row
  stage        TEXT NOT NULL,
  block        TEXT NOT NULL,
  n_coded      INTEGER NOT NULL,
  n_not_stated INTEGER NOT NULL,
  coverage     REAL,
  disposition  TEXT NOT NULL CHECK (disposition IN ('coded','register')),
  run_id       TEXT NOT NULL,
  PRIMARY KEY (question, source)
);

-- ---------------------------------------------------------------- analyse
-- The generic cross-tab (arch §4). The remaining analysis_* tables are
-- derived, recomputable for free, and land with the phase that fills them
-- (P1 funnel, P4 the rest). Every one carries n, denominator and run_id
-- (P3-INV-10).
-- P1: the Data Bank's two tables. Derived, rebuilt whole by
-- `python -m pipeline.analyse.funnel` after every collect or clean run.
CREATE TABLE IF NOT EXISTS analysis_funnel (          -- [CTX] §8.4 view 1
  step       TEXT NOT NULL,                  -- collected | excluded:<reason> | kept (P2 adds story steps)
  step_order INTEGER NOT NULL,
  source     TEXT NOT NULL,                  -- a source, or '_all'
  n          INTEGER NOT NULL,
  denom      INTEGER NOT NULL,               -- records collected from that source
  n_authors  INTEGER,                        -- EC-COL-6
  run_id     TEXT NOT NULL,
  PRIMARY KEY (step, source)
);

CREATE TABLE IF NOT EXISTS analysis_sources (         -- source × method, D-1 disclosure
  source         TEXT PRIMARY KEY,
  collect_method TEXT NOT NULL,
  n_records      INTEGER NOT NULL,
  n_authors      INTEGER NOT NULL,
  n_threads      INTEGER NOT NULL,           -- records holding more than one post (A.11)
  n_dated        INTEGER NOT NULL,
  earliest       TEXT, latest TEXT,
  n_kept         INTEGER NOT NULL,
  collect_usd    REAL,                       -- third-party spend (Apify); OpenAI is in runs.cost_usd
  run_id         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_crosstab (
  dim_a  TEXT NOT NULL, val_a TEXT NOT NULL,
  dim_b  TEXT NOT NULL, val_b TEXT NOT NULL,
  n      INTEGER NOT NULL, denom INTEGER NOT NULL,
  n_authors INTEGER,                         -- distinct authors beside every count (EC-COL-6)
  run_id TEXT NOT NULL,
  PRIMARY KEY (dim_a, val_a, dim_b, val_b, run_id)
);

-- -------------------------------------------------------------- provenance
CREATE TABLE IF NOT EXISTS runs (
  run_id           TEXT PRIMARY KEY,
  stage            TEXT NOT NULL,
  started_at       TEXT NOT NULL,
  finished_at      TEXT,
  status           TEXT NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running','ok','failed','halted_budget')),
  model            TEXT,
  batch            INTEGER NOT NULL DEFAULT 0 CHECK (batch IN (0,1)),
  prompt_version   TEXT,
  codebook_version TEXT,
  n_input          INTEGER, n_output INTEGER,
  input_tokens     INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  estimate_usd     REAL,                     -- A.4
  cost_usd         REAL,
  params_json      TEXT
);

CREATE TABLE IF NOT EXISTS published (       -- A.8: the app reads THIS run, never "latest"
  singleton      INTEGER PRIMARY KEY CHECK (singleton = 1),
  run_id         TEXT NOT NULL,
  corpus_version TEXT NOT NULL,              -- "Corpus v1.0 — N core stories, collected <range>"
  published_at   TEXT NOT NULL
);
