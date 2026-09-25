"""Write evals/reports/gate_P<n>_<date>.md for a gate (implementationplan.md §0.2).

The report carries: the eval table with pass/fail per row, the run_id it was
taken against, actual spend vs estimate and the running total against $15, and
a one-line verdict. A gate signed off against a run_id that is not the deployed
run_id is not signed off (EC-OPS-11, X-3). It renders inside the app on the
How it works page (evals.md §4).

`manual` checks are INCLUDED here (they are excluded from CI only), so a gate
cannot read as passed while a PM-only step is outstanding. A skipped check is
reported as skipped, never as passed.

    python evals/report.py p0
    python evals/report.py p3 --run-id <run_id>
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))   # deadlines are IST; so are report dates

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evals" / "reports"
JUNIT = ROOT / ".pytest_junit.xml"
DB = ROOT / "data" / "corpus.db"
CEILING = 15.00

TITLES = {"p0": "P0 — Foundation & freeze", "p1": "P1 — Data Bank", "p2": "P2 — Segmentation",
          "p3": "P3 — Coding & reliability", "p4": "P4 — Analysis & opportunities",
          "p5": "P5 — Ask AI", "p6": "P6 — Release"}


def run_gate(marker: str) -> int:
    cmd = [sys.executable, "-m", "pytest", "evals/", "-m", marker, "-q", "--tb=line",
           "-p", "no:cacheprovider", f"--junit-xml={JUNIT}"]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).returncode


def parse_junit() -> list[dict]:
    if not JUNIT.exists():
        return []
    cases = []
    for tc in ET.parse(JUNIT).getroot().iter("testcase"):
        fail = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        status = ("SKIP" if tc.find("skipped") is not None
                  else "FAIL" if fail is not None else "PASS")
        msg = (fail.get("message", "") if fail is not None else
               tc.find("skipped").get("message", "") if status == "SKIP" else "")
        cases.append({"name": tc.get("name", ""), "status": status, "message": msg})
    return cases


def spend() -> tuple[list[sqlite3.Row], float]:
    if not DB.exists():
        return [], 0.0
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT run_id, stage, status, model, batch, estimate_usd, cost_usd"
                       " FROM runs ORDER BY started_at").fetchall()
    return rows, sum(r["cost_usd"] or 0 for r in rows)


def write(marker: str, cases: list[dict], rc: int, run_id: str | None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).astimezone(IST)
    n = {s: sum(c["status"] == s for c in cases) for s in ("PASS", "FAIL", "SKIP")}
    passed = rc == 0 and n["FAIL"] == 0 and n["SKIP"] == 0 and cases
    runs, total = spend()

    lines = [f"# Gate report — {TITLES[marker]}", "",
             f"**Generated:** {now.isoformat(timespec='seconds')}",
             f"**Run id:** `{run_id or 'n/a — no pipeline run in this phase'}`",
             f"**Checks:** {n['PASS']} passed · {n['FAIL']} failed · {n['SKIP']} skipped",
             f"**Spend to date:** ${total:.2f} of ${CEILING:.2f} "
             f"(${CEILING - total:.2f} headroom)", "",
             "| Check | Status | Detail |", "|---|---|---|"]
    for c in sorted(cases, key=lambda c: ({"FAIL": 0, "SKIP": 1, "PASS": 2}[c["status"]],
                                          c["name"])):
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[c["status"]]
        detail = c["message"].replace("|", "\\|").splitlines()[0][:160] if c["message"] else ""
        lines.append(f"| `{c['name']}` | {icon} {c['status']} | {detail} |")

    lines += ["", "## Spend by pass (T-19, X-1)", ""]
    if runs:
        lines += ["| Run | Stage | Model | Batch | Estimate | Actual | × est | Status |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in runs:
            est, act = r["estimate_usd"], r["cost_usd"] or 0
            ratio = f"{act / est:.2f}×" if est else "—"
            lines.append(f"| `{r['run_id']}` | {r['stage']} | {r['model'] or '—'} | "
                         f"{'yes' if r['batch'] else 'no'} | "
                         f"{f'${est:.2f}' if est is not None else '—'} | ${act:.4f} | "
                         f"{ratio} | {r['status']} |")
    else:
        lines.append("No paid pass has run yet.")

    verdict = ("**GATE PASSED.**" if passed else
               "**GATE NOT PASSED** — skipped checks are not passes." if n["FAIL"] == 0 else
               "**GATE FAILED.**")
    lines += ["", "---", "", f"**Verdict:** {verdict}", ""]
    path = REPORTS / f"gate_{marker.upper()}_{now:%Y%m%d}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("marker", choices=sorted(TITLES))
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    rc = run_gate(args.marker)
    cases = parse_junit()
    JUNIT.unlink(missing_ok=True)
    path = write(args.marker, cases, rc, args.run_id)
    print(f"{path.relative_to(ROOT)}  —  "
          f"{sum(c['status'] == 'PASS' for c in cases)}/{len(cases)} passed")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
