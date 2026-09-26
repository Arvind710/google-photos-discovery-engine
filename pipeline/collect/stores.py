"""Play Store and App Store reviews of the Google Photos app (D-1).

Play: `google-play-scraper` (`collect_method = public_scraper_lib`), newest
first — the relevance sort surfaces long promotional praise, which skews toward
exactly the reviews the analysis discards (Myntra's finding). English and
Hindi, India and US.

App Store: Apple's own customer-review RSS feed (`public_feed`) — no auth, no
third party. `app-store-scraper` was dropped: unmaintained, and it pins
requests<2.24. The feed stops at 10 pages (~500 reviews) per country, so
breadth comes from several countries.

EXPECT LOW RELEVANCE YIELD. Reviews are short and skew to backup, storage and
crash complaints; that ratio is [CTX] §13's short-text bias, reported, not
fixed.

    python -m pipeline.collect.stores play --per-lane 100
    python -m pipeline.collect.stores appstore --pages 2
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from pipeline.collect import base
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod

PLAY_APP = "com.google.android.apps.photos"
# en-US returned the same reviews as en-IN in the pilot (D-4), so it is not a lane.
PLAY_LANES = [("en", "in"), ("hi", "in")]
IOS_APP = "962194608"
IOS_COUNTRIES = ["us", "in", "gb", "ca", "au"]
FEED = "https://itunes.apple.com/{c}/rss/customerreviews/page={p}/id={a}/sortby=mostrecent/json"


def play_record(r: dict, *, lang: str, country: str, run_id: str) -> tuple[dict | None, int]:
    return base.make_record(
        source="play", native_id=r["reviewId"],
        source_url=f"https://play.google.com/store/apps/details?id={PLAY_APP}"
                   f"&reviewId={r['reviewId']}",
        posts=[base.Post(r.get("userName"), r.get("content"), r.get("at"))],
        ingest_run_id=run_id, collect_query=f"play newest {lang}-{country}",
        # No region_hint: the pilot showed en-IN and en-US return the SAME
        # reviews, so the country parameter says nothing about the reviewer.
        rating=r.get("score"), engagement=r.get("thumbsUpCount"), platform_hint="android")


def appstore_record(e: dict, *, country: str, run_id: str) -> tuple[dict | None, int]:
    def lab(k):
        v = e.get(k)
        return v.get("label") if isinstance(v, dict) else None
    title, body = lab("title") or "", lab("content") or ""
    rid = lab("id")
    rating = int(lab("im:rating")) if lab("im:rating") else None
    return base.make_record(
        source="appstore", native_id=f"{country}-{rid}",
        source_url=f"https://apps.apple.com/{country}/app/google-photos/id{IOS_APP}"
                   f"?see-all=reviews#review-{rid}",
        posts=[base.Post((e.get("author") or {}).get("name", {}).get("label"),
                         f"{title}\n\n{body}".strip(), lab("updated"))],
        ingest_run_id=run_id, collect_query=f"appstore mostrecent {country}", rating=rating,
        platform_hint="ios", region_hint=country.upper())


def collect_play(con, run, per_lane: int) -> base.Tally:
    from google_play_scraper import Sort, reviews

    tally = base.Tally()
    for lang, country in PLAY_LANES:
        token, got = None, 0
        while got < per_lane:
            try:
                batch, token = reviews(PLAY_APP, lang=lang, country=country, sort=Sort.NEWEST,
                                       count=min(200, per_lane - got),
                                       continuation_token=token)
            except Exception as e:                           # noqa: BLE001
                print(f"  {lang}-{country}: ERROR {type(e).__name__} after {got} — kept",
                      flush=True)
                tally.failed_queries.append(f"{lang}-{country}")
                break
            if not batch:
                break
            for r in batch:
                rec, n_del = play_record(r, lang=lang, country=country, run_id=run.run_id)
                tally.add(con, rec, n_del, f"play newest {lang}-{country}")
            got += len(batch)
            if token is None:
                break
        print(f"  play {lang}-{country}: {got} fetched", flush=True)
    return tally


def collect_appstore(con, run, pages: int) -> base.Tally:
    tally = base.Tally()
    for c in IOS_COUNTRIES:
        got = 0
        for p in range(1, pages + 1):
            try:
                req = urllib.request.Request(FEED.format(c=c, p=p, a=IOS_APP),
                                             headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read())
            except Exception as e:                           # noqa: BLE001
                print(f"  {c} page {p}: ERROR {type(e).__name__} — recorded", flush=True)
                tally.failed_queries.append(f"{c}-p{p}")
                continue
            entries = [e for e in data.get("feed", {}).get("entry", []) or []
                       if isinstance(e, dict) and "im:rating" in e]
            if not entries:
                break
            for e in entries:
                rec, n_del = appstore_record(e, country=c, run_id=run.run_id)
                tally.add(con, rec, n_del, f"appstore mostrecent {c}")
            got += len(entries)
        print(f"  appstore {c}: {got} fetched", flush=True)
    return tally


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["play", "appstore"])
    ap.add_argument("--per-lane", type=int, default=700, help="Play: reviews per lang-country")
    ap.add_argument("--pages", type=int, default=10, help="App Store: feed pages per country")
    args = ap.parse_args()
    vals = envm.load()
    if not vals.get("AUTHOR_SALT"):
        print("AUTHOR_SALT must be set in .env", file=sys.stderr)
        return 2
    base.set_salt(vals["AUTHOR_SALT"])
    con = dbm.init()
    method = base.SOURCE_METHOD[args.source]
    with rmod.Run(con, f"collect-{args.source}", model=None, estimate_usd=0,
                  source=args.source, collect_method=method,
                  per_lane=args.per_lane, pages=args.pages) as run:
        tally = (collect_play(con, run, args.per_lane) if args.source == "play"
                 else collect_appstore(con, run, args.pages))
        base.finish(con, run, tally)
    print(f"  {args.source}: fetched {tally.fetched}, new {tally.written_new}, "
          f"already {tally.already_present}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
