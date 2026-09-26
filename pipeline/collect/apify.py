"""Apify actor runner — shared by the Reddit, X and Quora collectors (D-1).

Ported from Myntra's `reddit_apify.py`. Plain urllib, no client library. A run
that ends in anything but SUCCEEDED keeps its partial results and says so
(EC-COL-2); a failed query is recorded as failed, never as a zero yield.

Every raw dataset is saved to `data/raw/` (gitignored — it is unscrubbed), so
a mapping bug found later is fixed by re-mapping, not by paying for the run
again (EC-COL-13).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.apify.com/v2"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


def _call(method: str, url: str, token: str, payload: dict | None = None) -> Any:
    req = urllib.request.Request(
        url, method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def settled_usage(run_id: str, token: str, info: dict, *, tries: int = 6,
                  wait_s: int = 5) -> dict:
    """Re-read the run until its cost stops changing. Apify bills a run for a
    while after it reports SUCCEEDED: read at that moment, `usageTotalUsd`
    came back as $0.012 for a run that settled at $0.242 (2026-09-26), and
    every collect run's recorded cost was low."""
    last = info.get("usageTotalUsd")
    for _ in range(tries):
        time.sleep(wait_s)
        info = _call("GET", f"{API}/actor-runs/{run_id}", token)["data"]
        now = info.get("usageTotalUsd")
        if now == last and now is not None:
            break
        last = now
    return info


def run_actor(actor: str, payload: dict, token: str, *, label: str, poll_s: int = 10,
              timeout_s: int = 3600) -> tuple[list[dict], dict]:
    """Start, poll, fetch. Returns (items, meta) with meta = status, run id and
    the run's USD cost as Apify reports it."""
    run = _call("POST", f"{API}/acts/{actor}/runs", token, payload)["data"]
    run_id, ds = run["id"], run["defaultDatasetId"]
    print(f"    apify {actor} run {run_id} started", flush=True)
    waited, status, info = 0, "RUNNING", run
    while waited < timeout_s:
        time.sleep(poll_s)
        waited += poll_s
        info = _call("GET", f"{API}/actor-runs/{run_id}", token)["data"]
        status = info["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    else:
        _call("POST", f"{API}/actor-runs/{run_id}/abort", token)
        status = "TIMED-OUT (aborted by collector)"
    info = settled_usage(run_id, token, info)
    items = _call("GET", f"{API}/datasets/{ds}/items?clean=true&format=json", token)
    meta = {"actor": actor, "apify_run_id": run_id, "status": status, "items": len(items),
            "usd": info.get("usageTotalUsd"), "waited_s": waited}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{label}-{run_id}.json").write_text(json.dumps({"payload": payload, "meta": meta,
                                                            "items": items}))
    print(f"    {status} after {waited}s — {len(items)} items, ${meta['usd'] or 0:.3f}",
          flush=True)
    if status != "SUCCEEDED":
        print("    WARNING: non-success status; partial results kept and flagged", flush=True)
    return items, meta


def log_says_limited(apify_run_id: str, token: str) -> str | None:
    """A run can report SUCCEEDED and still have refused the work — the X actor
    hit a per-user monthly cap and returned placeholders (2026-09-26). Read the
    run log and return the offending line if it mentions a limit or a plan."""
    try:
        req = urllib.request.Request(f"{API}/actor-runs/{apify_run_id}/log",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            log = r.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    for line in log.splitlines():
        low = line.lower()
        if ("limit" in low and ("exceed" in low or "reached" in low)) or "paid plan" in low:
            return line.strip()[:200]
    return None


def safe_run(actor: str, payload: dict, token: str, *, label: str) -> tuple[list[dict], dict]:
    """run_actor that never lets a failure read as an empty result."""
    try:
        return run_actor(actor, payload, token, label=label)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError) as e:
        print(f"    ERROR {type(e).__name__}: {e}", flush=True)
        return [], {"actor": actor, "status": f"ERROR {type(e).__name__}: {e}", "items": 0,
                    "usd": 0}
