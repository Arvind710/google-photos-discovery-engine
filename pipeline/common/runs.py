"""Per-pass provenance and cost accounting — T-19, X-1, EC-OPS-1.

Every pipeline pass opens a `Run`, records real token counts, and closes it.
Two budget guards live here, in code, because at $15 with ~$2.65 of headroom
money is a correctness constraint (edgecase.md §2 #6):

1. **1.5× halt (T-19).** A pass carries its estimate from architecture.md §8.
   The moment accumulated cost exceeds 1.5× that estimate, `add_usage` raises
   `BudgetHalt`. The pass stops mid-flight for a decision (Appendix B) rather
   than "continue and watch it".
2. **Ceiling.** A pass may not start if committed spend plus its estimate
   would cross the $15 ceiling.

    with Run(con, "pass1_segment", model="gpt-5-mini", batch=True,
             estimate_usd=1.20, prompt_version="segment_v1",
             codebook_version=cb.version_string) as run:
        ...
        run.add_usage(input_tokens=..., output_tokens=..., cached_tokens=...)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

# USD per 1M tokens, standard tier. CONFIRMED 2026-09-26 against
# developers.openai.com/api/docs/pricing. The Batch API bills exactly half of
# every line (also confirmed on that page) — applied in cost_usd(), not
# duplicated here. Re-confirm before P3's batch submission.
MODEL_RATES: dict[str, dict[str, float]] = {
    "gpt-5":      {"in": 1.25, "cached_in": 0.125, "out": 10.00},
    "gpt-5-mini": {"in": 0.25, "cached_in": 0.025, "out": 2.00},
    "gpt-5-nano": {"in": 0.05, "cached_in": 0.005, "out": 0.40},
}
RATES_CONFIRMED_AT = "2026-09-26"
BATCH_DISCOUNT = 0.5

CEILING_USD = 15.00          # the console hard cap (P0-OPS-2); this is the in-code mirror
HALT_MULTIPLE = 1.5          # T-19


class BudgetHalt(RuntimeError):
    """A pass exceeded 1.5× its estimate, or would cross the ceiling. Stop and
    decide from the descope ladder (implementationplan.md Appendix B)."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def cost(model: str, *, input_tokens: int, output_tokens: int, cached_tokens: int = 0,
         batch: bool = False) -> float:
    """USD for one bundle of usage. Unknown model → KeyError, never a silent 0."""
    r = MODEL_RATES[model]
    fresh = max(input_tokens - cached_tokens, 0)
    usd = (fresh * r["in"] + cached_tokens * r["cached_in"] + output_tokens * r["out"]) / 1e6
    return usd * (BATCH_DISCOUNT if batch else 1.0)


def committed_spend(con: sqlite3.Connection) -> float:
    """Total actual spend across every recorded run (X-2)."""
    return float(con.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM runs").fetchone()[0])


class Run:
    def __init__(self, con: sqlite3.Connection, stage: str, *, model: str | None,
                 estimate_usd: float, batch: bool = False, **params: Any) -> None:
        if model is not None and model not in MODEL_RATES:
            raise KeyError(f"no confirmed rate for model {model!r} — add it to MODEL_RATES")
        if estimate_usd is None or estimate_usd < 0:
            raise ValueError("every pass declares its estimate (A.4); T-19 needs it")
        self.con = con
        self.stage = stage
        self.model = model
        self.batch = batch
        self.estimate_usd = float(estimate_usd)
        self.params = params
        self.run_id = f"{stage}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.input_tokens = self.output_tokens = self.cached_tokens = 0
        self.n_input = self.n_output = 0

    # -- budget --------------------------------------------------------------
    def cost_usd(self) -> float:
        if self.model is None:
            return 0.0
        return round(cost(self.model, input_tokens=self.input_tokens,
                          output_tokens=self.output_tokens,
                          cached_tokens=self.cached_tokens, batch=self.batch), 6)

    def _check(self) -> None:
        spent = self.cost_usd()
        if self.estimate_usd > 0 and spent > HALT_MULTIPLE * self.estimate_usd:
            raise BudgetHalt(
                f"{self.stage}: ${spent:.4f} spent against a ${self.estimate_usd:.2f} "
                f"estimate (>{HALT_MULTIPLE}×). Halted for a decision (T-19).")

    def add_usage(self, *, input_tokens: int = 0, output_tokens: int = 0,
                  cached_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens
        self._check()

    # -- lifecycle -------------------------------------------------------------
    def __enter__(self) -> Run:
        already = committed_spend(self.con)
        if already + self.estimate_usd > CEILING_USD:
            raise BudgetHalt(
                f"{self.stage}: ${already:.2f} committed + ${self.estimate_usd:.2f} estimate "
                f"would cross the ${CEILING_USD:.2f} ceiling.")
        self.con.execute(
            "INSERT INTO runs (run_id, stage, started_at, status, model, batch, prompt_version,"
            " codebook_version, estimate_usd, params_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self.run_id, self.stage, _now(), "running", self.model, int(self.batch),
             self.params.get("prompt_version"), self.params.get("codebook_version"),
             self.estimate_usd, json.dumps(self.params, default=str)))
        self.con.commit()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        status = ("ok" if exc_type is None
                  else "halted_budget" if exc_type is BudgetHalt else "failed")
        # Recorded even on failure: money spent on a failed pass is still spent.
        self.con.execute(
            "UPDATE runs SET finished_at=?, status=?, n_input=?, n_output=?, input_tokens=?,"
            " cached_tokens=?, output_tokens=?, cost_usd=? WHERE run_id=?",
            (_now(), status, self.n_input, self.n_output, self.input_tokens,
             self.cached_tokens, self.output_tokens, self.cost_usd(), self.run_id))
        self.con.commit()
