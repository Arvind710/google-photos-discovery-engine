"""The ONE way a share reaches the screen — [CTX] §15.5, architecture.md §4.

Written before any view exists (implementationplan.md task 0.9), so no view can
be written without it. "Never a percentage without its denominator" is then
structurally true rather than remembered, and P4-INV-1 is a grep: no view
formats a share itself.

Three tiers, applied everywhere a proportion is displayed, charts and Ask AI
alike (EC-ASK-5):

    n < 30        insufficient  raw count only; no percentage, no comparison
    30 ≤ n < 80   directional   share + count + widened (Wilson 95%) interval
    n ≥ 80        comparable    share + count; a difference is claimed only
                                if the 95% intervals do not overlap

`n` in the tiers is the DENOMINATOR — the cell size ([CTX] §15.5).

Deliberately free of Streamlit imports, so the pipeline, Ask AI's verifier and
the tests can all use the same function.
"""

from __future__ import annotations

import math
from typing import NamedTuple

FLOOR = 30          # below this: count only
COMPARABLE = 80     # at or above this: comparable

# Okabe-Ito, matching the carried-over design language (§2).
GREY = "#BBBBBB"    # exists, cannot be ranked
WARN = "#E69F00"    # directional
BLUE = "#0072B2"    # comparable


class Share(NamedTuple):
    text: str
    tier: str          # insufficient | directional | comparable
    colour: str
    n: int
    denom: int
    pct: float | None  # None below the floor — callers cannot chart what is not there


def wilson(n: int, denom: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval, as proportions. Well-behaved at small n and
    at 0/1, unlike the normal approximation."""
    if denom <= 0:
        return (0.0, 0.0)
    p = n / denom
    centre = (p + z * z / (2 * denom)) / (1 + z * z / denom)
    half = (z / (1 + z * z / denom)) * math.sqrt(p * (1 - p) / denom + z * z / (4 * denom * denom))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def share(n: int, denom: int) -> Share:
    """(text, tier, colour, n, denom, pct). No caller formats a share itself."""
    if n < 0 or denom < 0 or n > denom:
        raise ValueError(f"impossible share {n} of {denom}")
    if denom < FLOOR:
        return Share(f"{n} of {denom}", "insufficient", GREY, n, denom, None)
    p = n / denom
    if denom < COMPARABLE:
        lo, hi = wilson(n, denom)
        # Said plainly (2026-09-27): "directional" and a bare interval meant nothing to a
        # reader; the tier keeps its internal name.
        return Share(f"{_pct(p)} ({n} of {denom}) · rough guide, likely {_pct(lo)}–{_pct(hi)}",
                     "directional", WARN, n, denom, p)
    return Share(f"{_pct(p)} ({n} of {denom})", "comparable", BLUE, n, denom, p)


def fisher_p(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Two-sided Fisher's exact test on the 2×2 table [[na, da-na], [nb, db-nb]]."""
    (na, da), (nb, db) = a, b
    row1, col1, total = da, na + nb, da + db

    def prob(x: int) -> float:
        return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)

    observed = prob(na)
    lo, hi = max(0, row1 + col1 - total), min(row1, col1)
    return min(1.0, sum(p for x in range(lo, hi + 1)
                        if (p := prob(x)) <= observed * (1 + 1e-9)))


def differs(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """May a difference between two shares be CLAIMED? Only when both cells are
    comparable AND either their 95% intervals do not overlap or Fisher's exact
    test gives p < 0.05 ([CTX] §15.5)."""
    (na, da), (nb, db) = a, b
    if da < COMPARABLE or db < COMPARABLE:
        return False
    lo_a, hi_a = wilson(na, da)
    lo_b, hi_b = wilson(nb, db)
    return hi_a < lo_b or hi_b < lo_a or fisher_p(a, b) < 0.05
