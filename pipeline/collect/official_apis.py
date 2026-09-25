"""YouTube, Stack Exchange and Hacker News — official, documented APIs (D-1).

YouTube Data API v3: search is 100 of the 10,000 daily units, a page of
comment threads is 1 — so few searches, many comments per video. A record is
one top-level comment with its replies (A.11); the video title is context.

Stack Exchange API 2.3 (Web Apps, Android, Ask Different): a record is one
question with its answers — the answers carry the workarounds. Keyless quota
is 300 requests a day; bodies are HTML and are reduced to text.

Hacker News via Algolia: a record is one story or comment; the story title is
context. Bodies are HTML.

    python -m pipeline.collect.official_apis youtube --pilot
    python -m pipeline.collect.official_apis stackexchange
    python -m pipeline.collect.official_apis hackernews
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from pipeline.collect import base, config
from pipeline.common import db as dbm
from pipeline.common import env as envm
from pipeline.common import runs as rmod


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "gp-discovery-engine/0.1",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"(?i)</?(p|br|li|pre|blockquote|h\d)[^>]*>")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    return html.unescape(_TAG.sub("", _BLOCK.sub("\n", s))).strip()


# ------------------------------------------------------------------ YouTube
YT = "https://www.googleapis.com/youtube/v3"


def youtube_record(thread: dict, *, video_title: str, query: str,
                   run_id: str) -> tuple[dict | None, int]:
    top = thread["snippet"]["topLevelComment"]["snippet"]
    posts = [base.Post(top.get("authorDisplayName"), top.get("textOriginal")
                       or html_to_text(top.get("textDisplay")), top.get("publishedAt"))]
    for rep in sorted((thread.get("replies") or {}).get("comments", []),
                      key=lambda c: c["snippet"].get("publishedAt", "")):
        s = rep["snippet"]
        posts.append(base.Post(s.get("authorDisplayName"),
                               s.get("textOriginal") or html_to_text(s.get("textDisplay")),
                               s.get("publishedAt")))
    vid = thread["snippet"]["videoId"]
    return base.make_record(
        source="youtube", native_id=thread["id"],
        source_url=f"https://www.youtube.com/watch?v={vid}&lc={thread['id']}", posts=posts,
        ingest_run_id=run_id, collect_query=query, engagement=top.get("likeCount"),
        thread_context=video_title)


def collect_youtube(con, run, key: str, terms: list[str], videos: int, pages: int,
                    per_page: int = 100) -> base.Tally:
    tally = base.Tally()
    units = 0
    for term in terms:
        q = config.anchored(term)
        try:
            res = get_json(f"{YT}/search?" + urllib.parse.urlencode(
                {"part": "snippet", "q": q, "type": "video", "maxResults": videos,
                 "relevanceLanguage": "en", "key": key}))
            units += 100
        except urllib.error.HTTPError as e:
            print(f"  search {q!r}: HTTP {e.code} — recorded", flush=True)
            tally.failed_queries.append(term)
            continue
        for v in res.get("items", []):
            vid, title = v["id"]["videoId"], v["snippet"]["title"]
            token = None
            for _ in range(pages):
                params = {"part": "snippet,replies", "videoId": vid, "maxResults": per_page,
                          "textFormat": "plainText", "order": "relevance", "key": key}
                if token:
                    params["pageToken"] = token
                try:
                    page = get_json(f"{YT}/commentThreads?" + urllib.parse.urlencode(params))
                    units += 1
                except urllib.error.HTTPError as e:           # comments disabled → 403
                    if e.code != 403:
                        tally.failed_queries.append(f"{term} / {vid}")
                    break
                for th in page.get("items", []):
                    rec, n_del = youtube_record(th, video_title=html.unescape(title),
                                                query=term, run_id=run.run_id)
                    tally.add(con, rec, n_del, term)
                token = page.get("nextPageToken")
                if not token:
                    break
        print(f"  youtube {q!r}: {tally.by_query.get(term, 0)} new · ~{units} units used",
              flush=True)
    tally.quota_units = units
    return tally


# ----------------------------------------------------------- Stack Exchange
SE = "https://api.stackexchange.com/2.3"
SE_SITES = ["webapps", "android", "apple"]


def se_record(q: dict, answers: list[dict], *, site: str, query: str,
              run_id: str) -> tuple[dict | None, int]:
    posts = [base.Post((q.get("owner") or {}).get("display_name"),
                       f"{html.unescape(q['title'])}\n\n{html_to_text(q.get('body'))}",
                       q.get("creation_date"))]
    for a in sorted(answers, key=lambda a: a.get("creation_date", 0)):
        posts.append(base.Post((a.get("owner") or {}).get("display_name"),
                               html_to_text(a.get("body")), a.get("creation_date")))
    return base.make_record(
        source="stackexchange", native_id=f"{site}-{q['question_id']}", source_url=q["link"],
        posts=posts, ingest_run_id=run_id, collect_query=query, engagement=q.get("score"),
        thread_context=f"{site}.stackexchange | {', '.join(q.get('tags', []))}")


def collect_stackexchange(con, run, terms: list[str], per_term: int) -> base.Tally:
    tally = base.Tally()
    for site in SE_SITES:
        for term in terms:
            q = config.anchored(term)
            try:
                res = get_json(f"{SE}/search/advanced?" + urllib.parse.urlencode(
                    {"q": q, "site": site, "pagesize": per_term, "order": "desc",
                     "sort": "relevance", "filter": "withbody"}))
            except urllib.error.HTTPError as e:
                print(f"  {site} {q!r}: HTTP {e.code} — recorded", flush=True)
                tally.failed_queries.append(f"{site}: {term}")
                continue
            qs = res.get("items", [])
            answers: dict[int, list[dict]] = {}
            ids = [str(x["question_id"]) for x in qs if x.get("answer_count")]
            if ids:
                ar = get_json(f"{SE}/questions/{';'.join(ids)}/answers?" + urllib.parse.urlencode(
                    {"site": site, "pagesize": 100, "filter": "withbody"}))
                for a in ar.get("items", []):
                    answers.setdefault(a["question_id"], []).append(a)
            for x in qs:
                rec, n_del = se_record(x, answers.get(x["question_id"], []), site=site,
                                       query=term, run_id=run.run_id)
                tally.add(con, rec, n_del, term)
            if res.get("backoff"):
                time.sleep(res["backoff"])
            print(f"  {site} {q!r}: {len(qs)} questions · quota left "
                  f"{res.get('quota_remaining')}", flush=True)
    return tally


# -------------------------------------------------------------- Hacker News
HN = "https://hn.algolia.com/api/v1/search"


def hn_record(hit: dict, *, query: str, run_id: str) -> tuple[dict | None, int]:
    text = hit.get("comment_text") or hit.get("story_text") or ""
    if hit.get("title") and not hit.get("comment_text"):
        text = f"{hit['title']}\n\n{html_to_text(text)}".strip()
    else:
        text = html_to_text(text)
    return base.make_record(
        source="hackernews", native_id=str(hit["objectID"]),
        source_url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
        posts=[base.Post(hit.get("author"), text, hit.get("created_at"))],
        ingest_run_id=run_id, collect_query=query, engagement=hit.get("points"),
        thread_context=hit.get("story_title") or hit.get("title"))


def collect_hackernews(con, run, terms: list[str], per_term: int) -> base.Tally:
    tally = base.Tally()
    for term in terms:
        q = config.anchored(term)
        try:
            res = get_json(f"{HN}?" + urllib.parse.urlencode(
                {"query": q, "tags": "(story,comment)", "hitsPerPage": per_term}))
        except urllib.error.HTTPError as e:
            print(f"  hn {q!r}: HTTP {e.code} — recorded", flush=True)
            tally.failed_queries.append(term)
            continue
        for h in res.get("hits", []):
            rec, n_del = hn_record(h, query=term, run_id=run.run_id)
            tally.add(con, rec, n_del, term)
        print(f"  hn {q!r}: {len(res.get('hits', []))} hits", flush=True)
    return tally


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["youtube", "stackexchange", "hackernews"])
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--terms", nargs="*")
    ap.add_argument("-n", type=int, default=None,
                    help="YouTube: videos per term; SE: questions per site-term; HN: hits per term")
    ap.add_argument("--pages", type=int, default=2, help="YouTube: comment pages per video")
    args = ap.parse_args()
    vals = envm.load()
    if not vals.get("AUTHOR_SALT"):
        print("AUTHOR_SALT must be set in .env", file=sys.stderr)
        return 2
    base.set_salt(vals["AUTHOR_SALT"])
    terms = args.terms or (config.PILOT_TERMS if args.pilot else config.lexicon_terms())
    n = args.n or {"youtube": 3 if args.pilot else 5, "stackexchange": 5 if args.pilot else 25,
                   "hackernews": 10 if args.pilot else 40}[args.source]
    con = dbm.init()
    with rmod.Run(con, f"collect-{args.source}", model=None, estimate_usd=0,
                  source=args.source, collect_method="official_api", terms=terms, n=n) as run:
        if args.source == "youtube":
            if not vals.get("YOUTUBE_API_KEY"):
                print("YOUTUBE_API_KEY must be set in .env", file=sys.stderr)
                return 2
            tally = collect_youtube(con, run, vals["YOUTUBE_API_KEY"], terms, n,
                                    1 if args.pilot else args.pages,
                                    20 if args.pilot else 100)
            extra = {"quota_units": tally.quota_units}
            del tally.quota_units
        elif args.source == "stackexchange":
            tally, extra = collect_stackexchange(con, run, terms, n), {}
        else:
            tally, extra = collect_hackernews(con, run, terms, n), {}
        base.finish(con, run, tally, **extra)
    print(f"  {args.source}: fetched {tally.fetched}, new {tally.written_new}, "
          f"already {tally.already_present}, failed {len(tally.failed_queries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
