"""Reddit, X and Quora through Apify (Docs/decisions.md D-1).

Reddit's API is closed to new developers; all three publish `Disallow: /`
in robots.txt, and the PM decided to collect them through Apify anyway, with
the method disclosed on every record (`collect_method = apify`).

Mapping lessons carried from Myntra, each load-bearing (EC-COL-13):
- Reddit comments arrive NESTED (`comments[].replies[]`). They are flattened
  into the thread, depth-first, so the whole thread is one record (A.11).
- Key on the platform's own id (`reddit_id`, tweet `id`, Quora answer id) —
  never Apify's per-run `id`, which would re-key every thread on every run.
- `includePostText` must be set explicitly: the actor now defaults it to
  false and would return titles only.
- Bot authors are dropped and counted.

    python -m pipeline.collect.apify_sources reddit --pilot
    python -m pipeline.collect.apify_sources x --max-per-term 40
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from typing import Any

from pipeline.collect import apify, base, config
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod

# X: `apidojo~tweet-scraper` was the first choice (D-1), but it caps runs per month
# for accounts on Apify's free plan and then returns "no results" placeholders
# under a SUCCEEDED status (found 2026-09-26). Pay-per-result replacement:
ACTORS = {"reddit": "webdatalabs~reddit-scraper-pro",
          "x": "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest",
          "quora": "fatihtahta~quora-scraper"}

BOT_AUTHORS = {"automoderator", "automod", "botdefense", "remindmebot", "sneakpeekbot",
               "repostsleuthbot", "savevideo", "vredditdownloader", "wikitextbot"}


def is_bot(author: str | None) -> bool:
    a = (author or "").strip().lower().removeprefix("u/")
    return a in BOT_AUTHORS or a.endswith(("-bot", "_bot"))


# ------------------------------------------------------------------ Reddit
def _flatten(comments: list[dict], out: list[dict]) -> list[dict]:
    for c in comments or []:
        out.append(c)
        _flatten(c.get("replies") or [], out)
    return out


def reddit_records(item: dict, *, query: str, run_id: str) -> tuple[dict | None, int, int]:
    """One Reddit post + its whole comment tree → one record.
    Returns (record, deleted posts, bot posts dropped)."""
    title = (item.get("title") or "").strip()
    body = (item.get("body") or "").strip()
    op_text = f"{title}\n\n{body}".strip() if body and not base.is_deleted(body) else title
    posts = [base.Post(item.get("author"), op_text, item.get("created_utc"))]
    bots = 0
    for c in _flatten(item.get("comments") or [], []):
        if is_bot(c.get("author")):
            bots += 1
            continue
        posts.append(base.Post(c.get("author"), c.get("body"), c.get("created_utc")))
    url = item.get("reddit_url") or item.get("permalink") or ""
    if url.startswith("/"):
        url = f"https://www.reddit.com{url}"
    sub = item.get("subreddit")
    rec, n_del = base.make_record(
        source="reddit", native_id=f"t3_{item['reddit_id']}", source_url=url, posts=posts,
        ingest_run_id=run_id, collect_query=query, created_at=item.get("created_utc"),
        engagement=item.get("score"), thread_context=f"r/{sub} | {title}" if sub else title)
    return rec, n_del, bots


def reddit_payload(term: str, per_sub: int) -> dict:
    return {"searchMode": "keyword", "keywords": [term], "subreddits": config.SUBREDDITS,
            "maxItemsPerSubreddit": per_sub, "searchSort": "relevance",
            "includePostText": True, "includeComments": True, "commentDepth": 3,
            "includeAuthorNames": True, "analyzeSentiment": False}


# ---------------------------------------------------------------------- X
def x_records(item: dict, *, query: str, run_id: str) -> tuple[dict | None, int, int]:
    if item.get("isRetweet") or item.get("retweeted_tweet"):
        return None, 0, 0
    author = (item.get("author") or {}).get("userName")
    # The LONGER of the two: apidojo's `fullText` is the one clipped at 280
    # characters while `text` is whole (found by P1-INV-6, 2026-09-26).
    text = html.unescape(max(item.get("fullText") or "", item.get("text") or "", key=len))
    rec, n_del = base.make_record(
        # x.com/i/status/<id> resolves without the handle; the actor's URL carries
        # the author's username, which is PII in a public corpus (EC-OPS-8).
        source="x", native_id=str(item["id"]), source_url=f"https://x.com/i/status/{item['id']}",
        posts=[base.Post(author, text, item.get("createdAt"))], ingest_run_id=run_id,
        collect_query=query, created_at=item.get("createdAt"),
        engagement=item.get("likeCount"),
        thread_context="reply" if item.get("isReply") else None)
    return rec, n_del, 0


def x_payload(term: str, n: int) -> dict:
    return {"twitterContent": f"{config.anchored(term)} -filter:retweets", "maxItems": n,
            "queryType": "Top"}


# ------------------------------------------------------------------- Quora
def quora_url(item: dict, native) -> str:
    q = item.get("question") or {}
    base_url = q.get("url") or re.sub(r"/answer/[^/?#]+.*$", "", item.get("url") or "")
    return f"{base_url}#answer-{native}"


def quora_records(item: dict, *, query: str, run_id: str) -> tuple[dict | None, int, int]:
    ans = item.get("answer") or {}
    q = item.get("question") or {}
    text = ans.get("text") or item.get("text")
    native = ans.get("id") or item.get("url")
    author = ((ans.get("author") or {}).get("name") or (item.get("author") or {}).get("name"))
    rec, n_del = base.make_record(
        # The answer URL ends /answer/<Author-Name> (PII); link the question page
        # and name the answer by id instead (EC-OPS-8).
        source="quora", native_id=str(native), source_url=quora_url(item, native),
        posts=[base.Post(author, text, ans.get("posted_at") or item.get("posted_at"))],
        ingest_run_id=run_id, collect_query=query,
        engagement=(item.get("metrics") or {}).get("upvotes"),
        thread_context=q.get("title") or item.get("title"))
    return rec, n_del, 0


def quora_payload(term: str, n: int) -> dict:
    return {"queries": [config.anchored(term)], "searchType": "Answer", "maxItemsPerQuery": n,
            "timeFilter": "All Time"}


MAPPERS = {"reddit": (reddit_records, reddit_payload), "x": (x_records, x_payload),
           "quora": (quora_records, quora_payload)}


def collect(source: str, terms: list[str], n: int, token: str) -> dict[str, Any]:
    mapper, payload_fn = MAPPERS[source]
    con = dbm.init()
    runs_meta, bots = [], 0
    with rmod.Run(con, f"collect-{source}", model=None, estimate_usd=0, source=source,
                  actor=ACTORS[source], collect_method="apify", terms=terms, n=n) as run:
        tally = base.Tally()
        for term in terms:
            print(f"  {source} · {term!r}", flush=True)
            items, meta = apify.safe_run(ACTORS[source], payload_fn(term, n), token,
                                         label=f"{source}-{run.run_id}")
            meta["term"] = term
            runs_meta.append(meta)
            if meta["status"] != "SUCCEEDED":
                tally.failed_queries.append(term)
            # A search with no hits comes back as placeholder items
            # ({"noResults": true}), not an empty list (X, 2026-09-26). They
            # are not records; counted so a zero yield is still visible.
            placeholders = [it for it in items if it.get("noResults")]
            meta["no_results_placeholders"] = len(placeholders)
            if placeholders and len(placeholders) == len(items):
                why = apify.log_says_limited(meta.get("apify_run_id", ""), token)
                if why:                                   # refused, not empty (EC-COL-13)
                    meta["status"] = f"REFUSED: {why}"
                    tally.failed_queries.append(term)
                    print(f"    REFUSED by the actor, not a zero yield: {why}", flush=True)
                tally.by_query.setdefault(term, 0)
            for it in items:
                if it.get("noResults"):
                    continue
                rec, n_del, n_bot = mapper(it, query=term, run_id=run.run_id)
                bots += n_bot
                tally.add(con, rec, n_del, term)
        usd = sum(m.get("usd") or 0 for m in runs_meta)
        base.finish(con, run, tally, apify_runs=runs_meta, apify_usd=round(usd, 4),
                    bot_posts_dropped=bots)
    print(f"  {source}: fetched {tally.fetched}, new {tally.written_new}, already "
          f"{tally.already_present}, all-deleted {tally.all_deleted}, bots dropped {bots}, "
          f"Apify ${usd:.3f}")
    for term, k in tally.by_query.items():
        print(f"    {k:>5}  {term}")
    for term in tally.failed_queries:
        print(f"    FAILED  {term}  (recorded — not a zero yield)")
    return {"tally": tally.as_params(), "apify_usd": usd}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(ACTORS))
    ap.add_argument("--pilot", action="store_true", help="config.PILOT_TERMS, small n")
    ap.add_argument("--terms", nargs="*")
    ap.add_argument("-n", type=int, default=None,
                    help="Reddit: posts per subreddit per term; X/Quora: items per term")
    args = ap.parse_args()
    vals = envm.load()
    base.set_salt(vals.get("AUTHOR_SALT", ""))
    token = vals.get("APIFY_TOKEN")
    if not token or not vals.get("AUTHOR_SALT"):
        print("APIFY_TOKEN and AUTHOR_SALT must be set in .env", file=sys.stderr)
        return 2
    terms = args.terms or (config.PILOT_TERMS if args.pilot else config.lexicon_terms())
    n = args.n or ({"reddit": 2, "x": 15, "quora": 5}[args.source] if args.pilot
                   else {"reddit": 10, "x": 40, "quora": 15}[args.source])
    collect(args.source, terms, n, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
