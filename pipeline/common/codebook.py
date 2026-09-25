"""Codebook loading, validation, and the FREEZE (implementationplan.md task 0.7).

The codebook is what every number in the engine is counted against. `load()`
refuses to return one whose content hash differs from the frozen hash, which
turns EC-CODE-13 ("codebook edited mid-run") from a policy into an exception:
half the corpus coded on v1 and half on v2 cannot happen silently.

What is hashed: the three files the CODING reads — journey, severity, metric
nodes. Not the lexicon (it is meant to grow during P1) and not the plain
language (display copy). Scoring is pre-registered separately by timestamp.

    python -m pipeline.common.codebook            # validate + print summary
    python -m pipeline.common.codebook freeze "note"   # record the hash (once)
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CODEBOOK_DIR = ROOT / "codebook"
FREEZE_FILE = CODEBOOK_DIR / "FROZEN.json"
FROZEN_FILES = ("journey_v1.yaml", "severity_v1.yaml", "metric_nodes_v1.yaml")

EXPECTED_N_QUESTIONS = 60
# From the per-question table in architecture.md §3.3. (Its prose total line,
# "A 14 · B 14 · C 16 · D 12 · R 9", sums to 66 and is a typo; the table is
# authoritative and reconciles to 60.)
EXPECTED_PER_BLOCK = {"A": 11, "B": 13, "C": 16, "D": 11, "R": 8, "S": 1}
BLOCKS = set(EXPECTED_PER_BLOCK)
SELECTS = {"single", "multi"}
# The six danger questions (implementationplan.md task 0.5): the 5.2/5.3/5.4
# triple, and the Stage 2 / Stage 4 pair on both sides of the line.
DANGER_QUESTIONS = ("5.2", "5.3", "5.4", "2.4", "4.2", "4.3")
MIN_BOUNDARY_NOTE = 80
OTHER_PREFIX = "other:"


class CodebookError(RuntimeError):
    """A structural violation, or a broken freeze."""


@dataclass(frozen=True)
class Codebook:
    version: str
    content_hash: str
    questions: dict[str, dict[str, Any]]   # "5.3" -> question dict, bank order
    stages: dict[str, dict[str, Any]]      # "5" -> stage dict (without questions)
    spine: dict[str, Any]
    metric_nodes: dict[str, Any]
    severity: dict[str, Any]
    frozen: dict[str, Any] | None

    @property
    def version_string(self) -> str:
        """Stamped on every run: v1:ab12cd34 (EC-CODE-13)."""
        return f"{self.version}:{self.content_hash[:8]}"

    def stage_of(self, qid: str) -> str:
        return self.questions[qid]["stage"]

    def block_of(self, qid: str) -> str:
        """The STARTING block. The effective disposition after the pilot is in
        analysis_coverage (arch §3.4), not here."""
        return self.questions[qid]["block"]

    def by_block(self, block: str) -> list[str]:
        return [q for q, d in self.questions.items() if d["block"] == block]

    def is_inferred(self, qid: str) -> bool:
        return bool(self.stages[self.stage_of(qid)].get("inferred"))

    def is_valid_value(self, qid: str, value: str) -> bool:
        """P3-INV-5: a listed value, not_stated, or other:<free text>."""
        if value.startswith(OTHER_PREFIX):
            return len(value) > len(OTHER_PREFIX)
        return value in self.questions[qid]["values"]

    def failure_owner(self, primary_stage: str) -> str:
        return self.spine["failure_owner"]["from_stage"][str(primary_stage)]


def _content_hash() -> str:
    h = hashlib.sha256()
    for name in FROZEN_FILES:
        h.update(name.encode())
        h.update((CODEBOOK_DIR / name).read_bytes())
    return h.hexdigest()


def _validate(raw: dict[str, Any], nodes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every P0-INV that can be checked on the YAML alone. Returns the flat
    question map with `stage` attached."""
    questions: dict[str, dict[str, Any]] = {}
    stage_ids = [s["id"] for s in raw["stages"]]
    if stage_ids != [str(i) for i in range(11)]:
        raise CodebookError(f"stages must be 0..10 in order, got {stage_ids}")

    for stage in raw["stages"]:
        for q in stage["questions"]:
            qid = q["id"]
            if qid in questions:
                raise CodebookError(f"duplicate question id {qid} (P0-INV-1)")
            if qid.split(".")[0] != stage["id"]:
                raise CodebookError(f"{qid} sits under stage {stage['id']} (P0-INV-3)")
            for key in ("block", "select", "text", "plain", "values", "metric_node"):
                if not q.get(key):
                    raise CodebookError(f"{qid}: missing `{key}`")
            if q["block"] not in BLOCKS:
                raise CodebookError(f"{qid}: block {q['block']!r} not in {sorted(BLOCKS)} (P0-INV-3)")
            if q["select"] not in SELECTS:
                raise CodebookError(f"{qid}: select must be single|multi")
            vals = q["values"]
            if "not_stated" not in vals or "other" not in vals:
                raise CodebookError(f"{qid}: needs both not_stated and other (P0-INV-2)")
            if len(vals) - 2 < 2:
                raise CodebookError(f"{qid}: fewer than two substantive values (P0-INV-2)")
            if len(set(vals)) != len(vals):
                raise CodebookError(f"{qid}: duplicate values")
            if q["metric_node"] not in nodes:
                raise CodebookError(f"{qid}: unknown metric_node {q['metric_node']!r}")
            questions[qid] = {**q, "stage": stage["id"]}

    if len(questions) != EXPECTED_N_QUESTIONS:
        raise CodebookError(
            f"expected {EXPECTED_N_QUESTIONS} questions, found {len(questions)} (P0-INV-1)")

    per_block: dict[str, int] = {}
    for q in questions.values():
        per_block[q["block"]] = per_block.get(q["block"], 0) + 1
    if per_block != EXPECTED_PER_BLOCK:
        raise CodebookError(f"block totals {per_block} != {EXPECTED_PER_BLOCK} (arch §3.3)")

    for qid in DANGER_QUESTIONS:
        note = " ".join(str(questions[qid].get("boundary_note") or "").split())
        if len(note) < MIN_BOUNDARY_NOTE:
            raise CodebookError(f"{qid}: boundary_note missing or too thin (P0-INV-4)")

    stage5 = next(s for s in raw["stages"] if s["id"] == "5")
    if stage5.get("inferred") is not True:
        raise CodebookError("stage 5 must be inferred: true (EC-CODE-15)")

    owners = raw["spine"]["failure_owner"]["from_stage"]
    if sorted(owners, key=int) != stage_ids:
        raise CodebookError("failure_owner.from_stage must map every stage 0..10")
    return questions


def load(*, enforce_freeze: bool = True) -> Codebook:
    raw = yaml.safe_load((CODEBOOK_DIR / "journey_v1.yaml").read_text())
    nodes = yaml.safe_load((CODEBOOK_DIR / "metric_nodes_v1.yaml").read_text())["nodes"]
    severity = yaml.safe_load((CODEBOOK_DIR / "severity_v1.yaml").read_text())

    questions = _validate(raw, nodes)
    digest = _content_hash()

    frozen = json.loads(FREEZE_FILE.read_text()) if FREEZE_FILE.exists() else None
    if enforce_freeze:
        if frozen is None:
            raise CodebookError(
                "codebook is not frozen (P0-INV-5). Run "
                "`python -m pipeline.common.codebook freeze` before any coding run.")
        if frozen["content_hash"] != digest:
            raise CodebookError(
                "CODEBOOK CHANGED AFTER FREEZE (EC-CODE-13).\n"
                f"  frozen: {frozen['content_hash'][:16]}  ({frozen['frozen_at']})\n"
                f"  now:    {digest[:16]}\n"
                "A change needs an explicit version bump and a re-freeze, and every\n"
                "story coded on the old version must be re-coded. Half the corpus on\n"
                "one version and half on another is a hard error, not a warning.")

    stages = {s["id"]: {k: v for k, v in s.items() if k != "questions"} for s in raw["stages"]}
    return Codebook(version=raw["version"], content_hash=digest, questions=questions,
                    stages=stages, spine=raw["spine"], metric_nodes=nodes,
                    severity=severity, frozen=frozen)


def freeze(note: str = "") -> dict[str, Any]:
    """Record the content hash. Called once at the P0 gate, and again only on
    an explicit version bump."""
    cb = load(enforce_freeze=False)
    payload = {
        "version": cb.version,
        "content_hash": cb.content_hash,
        "version_string": cb.version_string,
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": list(FROZEN_FILES),
        "n_questions": len(cb.questions),
        "note": note,
    }
    FREEZE_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "freeze":
        print(json.dumps(freeze(" ".join(sys.argv[2:])), indent=2))
    else:
        cb = load()
        print(f"{cb.version_string}  |  {len(cb.questions)} questions")
        for b in EXPECTED_PER_BLOCK:
            print(f"  {b} ({len(cb.by_block(b)):>2}): {' '.join(cb.by_block(b))}")
