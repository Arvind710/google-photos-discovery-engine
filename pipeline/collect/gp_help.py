"""Google Photos Help Community — thread pages rendered with Playwright (D-1).

Why rendering: a thread's HTML carries no post text; the page's JavaScript
loads it from `support.google.com/*/api`. The thread pages themselves are
allowed by robots.txt; `/*/search` and `/*/api` are not. So threads are
DISCOVERED from the listing page (`/photos/threads?max_results=N`, allowed),
never from the forum search, and each thread is rendered like a browser would.

Two steps, both counted in the run's params:
1. LIST up to N threads with title + first line (one page load).
2. SCREEN those with a broad retrieval pattern and RENDER only the matches —
   rendering is ~2–3 s a thread, and ~97% of listed threads are backup,
   deletion or account problems. Listed-but-not-rendered threads are never
   records; the counts are disclosed, not hidden.

A thread is ONE record: the question, then every answer and comment, each post
with its own author (A.11). The "recommended answer" appears twice on the
page (highlighted, and in the list); identical posts are kept once.

EC-COL-14 guards: wait for the post container, not a timer; a thread that
renders with no body is counted as a render failure, not written as a title.
Fallback if rendering fails at scale: Apify (EC-COL-11), then the PM.

    python -m pipeline.collect.gp_help --list 3000 --max-render 150
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime

from pipeline.collect import base
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod

LISTING = "https://support.google.com/photos/threads?hl=en&max_results={n}"
THREAD = "https://support.google.com/photos/thread/{tid}?hl=en"

# Broad on purpose: this screen decides what is rendered at all, so it favours
# recall (EC-PRE). The relevance pass is the precision step.
SCREEN = re.compile(
    r"(?i)can.?t find|cannot find|could ?n.?t find|unable to find|not able to find|"
    r"can.?t locate|looking for|search(ing|ed)?\b|find (a|an|the|my|old|that|specific|some)|"
    r"where (is|are|did) (my|the)|which (year|month|album)|remember|scroll|"
    r"ask photos|gemini|missing (photo|picture|pic)|lost (photo|picture|pic)|"
    r"old (photo|picture|pic)|screenshot|receipt|document|nahi mil|dhoondh")

EXTRACT = """() => {
  const heads = [...document.querySelectorAll('.scTailwindThreadPostheaderroot')];
  const bodies = [...document.querySelectorAll('.scTailwindThreadPostcontentroot')];
  return {title: document.querySelector('h1')?.innerText || '',
    posts: bodies.map((b, i) => ({
      author: heads[i]?.querySelector('.scTailwindThreadPost_headerUserinfoname')?.innerText || null,
      date: heads[i]?.querySelector('.post-date-tooltip')?.innerText || null,
      text: b.innerText}))};
}"""


def parse_date(s: str | None) -> str | None:
    """Tooltip dates look like '9/21/2026, 2:51:13 AM' (US format, en locale)."""
    if not s:
        return None
    try:
        return base.to_iso(datetime.strptime(s.strip(), "%m/%d/%Y, %I:%M:%S %p"))
    except ValueError:
        return None


def thread_record(tid: str, data: dict, *, run_id: str, query: str,
                  method: str = "headless_render") -> tuple[dict | None, int]:
    seen, posts = set(), []
    for i, p in enumerate(data["posts"]):
        text = (p.get("text") or "").strip()
        if i == 0 and data.get("title") and not text.startswith(data["title"]):
            text = f"{data['title']}\n\n{text}"
        key = (p.get("author"), p.get("date"), text)
        if key in seen:                                   # the promoted duplicate
            continue
        seen.add(key)
        posts.append(base.Post(p.get("author"), text, parse_date(p.get("date"))))
    return base.make_record(
        source="gp_help", native_id=tid, source_url=THREAD.format(tid=tid), posts=posts,
        ingest_run_id=run_id, collect_query=query, created_at=posts[0].created_at if posts else None,
        thread_context=data.get("title"), method=method)


async def _list(page, n: int) -> list[tuple[str, str]]:
    await page.goto(LISTING.format(n=n), wait_until="networkidle", timeout=180_000)
    rows = await page.eval_on_selector_all(
        "a[href*='/photos/thread/']",
        "els => els.map(e => [e.getAttribute('href'), e.innerText.trim()])")
    out, seen = [], set()
    for href, text in rows:
        m = re.search(r"/photos/thread/(\d+)", href)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), text))
    return out


async def _render(page, tid: str, *, settle_ms: int) -> dict | None:
    await page.goto(THREAD.format(tid=tid), wait_until="domcontentloaded", timeout=60_000)
    try:
        await page.wait_for_selector(".scTailwindThreadPostcontentroot", timeout=20_000)
    except Exception:                                       # noqa: BLE001
        return None
    await page.wait_for_timeout(settle_ms)                  # replies render just after the question
    data = await page.evaluate(EXTRACT)
    if not data["posts"] or not any((p.get("text") or "").strip() for p in data["posts"]):
        return None
    return data


async def collect(n_list: int, max_render: int, con, run, *, workers: int = 4,
                  settle_ms: int = 2500) -> base.Tally:
    from playwright.async_api import async_playwright

    tally = base.Tally()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        listed = await _list(page, n_list)
        existing = {r[0] for r in con.execute(
            "SELECT native_id FROM records WHERE source='gp_help'")}
        screened = [(tid, t) for tid, t in listed if SCREEN.search(t)]
        todo = [(tid, t) for tid, t in screened if tid not in existing][:max_render]
        print(f"  listed {len(listed)} · screen matched {len(screened)} · already have "
              f"{len(screened) - len([1 for tid, _ in screened if tid not in existing])} · "
              f"rendering {len(todo)}", flush=True)
        failures: list[str] = []
        queue: asyncio.Queue = asyncio.Queue()
        for item in todo:
            queue.put_nowait(item)
        done = 0

        async def worker(pg) -> None:
            nonlocal done
            while not queue.empty():
                tid, snippet = queue.get_nowait()
                try:
                    data = await _render(pg, tid, settle_ms=settle_ms)
                except Exception:                           # noqa: BLE001
                    data = None
                done += 1
                if data is None:
                    failures.append(tid)
                else:
                    m = SCREEN.search(snippet)
                    rec, n_del = thread_record(tid, data, run_id=run.run_id,
                                               query=f"gp_help listing screen: {m.group(0).lower()}")
                    tally.add(con, rec, n_del, "gp_help listing screen")
                if done % 25 == 0:
                    print(f"    {done}/{len(todo)} rendered, {len(failures)} failed", flush=True)

        pages = [page] + [await browser.new_page() for _ in range(workers - 1)]
        await asyncio.gather(*(worker(pg) for pg in pages))
        await browser.close()
    tally.render = {"listed": len(listed), "screen_matched": len(screened),
                    "attempted": len(todo), "render_failed": len(failures),
                    "failed_ids": failures[:50]}
    return tally


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=int, default=2000, help="threads to list")
    ap.add_argument("--max-render", type=int, default=150)
    ap.add_argument("--workers", type=int, default=4, help="pages rendered at once")
    args = ap.parse_args()
    vals = envm.load()
    if not vals.get("AUTHOR_SALT"):
        print("AUTHOR_SALT must be set in .env", file=sys.stderr)
        return 2
    base.set_salt(vals["AUTHOR_SALT"])
    con = dbm.init()
    with rmod.Run(con, "collect-gp_help", model=None, estimate_usd=0, source="gp_help",
                  collect_method="headless_render", n_list=args.list,
                  max_render=args.max_render, workers=args.workers) as run:
        tally = asyncio.run(collect(args.list, args.max_render, con, run,
                                    workers=args.workers))
        render = tally.render
        del tally.render
        base.finish(con, run, tally, render=render)
    rate = render["render_failed"] / max(render["attempted"], 1)
    print(f"  gp_help: new {tally.written_new}, already {tally.already_present}, "
          f"render failures {render['render_failed']}/{render['attempted']} ({rate:.0%})")
    if render["attempted"] and rate > 0.2:
        print("  RENDER FAILURE RATE > 20% — EC-COL-14. Switch to the Apify fallback "
              "(EC-COL-11) before scaling up.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
