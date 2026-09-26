"""Materialise the Data Bank tables: `analysis_funnel` and `analysis_sources`.

The app performs no aggregation over records (architecture.md §4); it reads
these. Both are derived, so they are rebuilt whole on every run — the
`run_id` on each row says which build produced them.

Every step is COUNTED, not derived by subtraction, and the build asserts that
collected == kept + excluded for every source before writing (P1-INV-1), so a
funnel that does not balance cannot reach the page.

    python -m pipeline.analyse.funnel
"""

from __future__ import annotations

import json

from pipeline.common import db as dbm
from pipeline.common import runs as rmod

EXCLUDED_AT_RECORD = "SELECT DISTINCT record_id FROM exclusions WHERE story_id IS NULL"


def build(con) -> dict[str, int]:
    with rmod.Run(con, "analyse-funnel", model=None, estimate_usd=0) as run:
        rid = run.run_id
        con.execute("DELETE FROM analysis_funnel")
        con.execute("DELETE FROM analysis_sources")
        sources = [r[0] for r in con.execute("SELECT DISTINCT source FROM records ORDER BY 1")]
        for src in [*sources, "_all"]:
            where, args = ("", ()) if src == "_all" else ("WHERE source = ?", (src,))
            tot = con.execute(f"SELECT count(*), count(DISTINCT author_key) FROM records {where}",
                              args).fetchone()
            kept = con.execute(
                f"SELECT count(*), count(DISTINCT author_key) FROM records {where}"
                f"{' AND' if where else ' WHERE'} record_id NOT IN ({EXCLUDED_AT_RECORD})",
                args).fetchone()
            excl = con.execute(
                "SELECT e.reason, count(DISTINCT e.record_id), count(DISTINCT r.author_key)"
                " FROM exclusions e JOIN records r USING (record_id)"
                f" WHERE e.story_id IS NULL {'AND r.source = ?' if src != '_all' else ''}"
                " GROUP BY e.reason", args).fetchall()
            n_excl = con.execute(
                f"SELECT count(*) FROM records {where}{' AND' if where else ' WHERE'}"
                f" record_id IN ({EXCLUDED_AT_RECORD})", args).fetchone()[0]
            assert tot[0] == kept[0] + n_excl, f"{src}: funnel does not balance (P1-INV-1)"
            rows = [("collected", 0, tot[0], tot[1])]
            rows += [(f"excluded:{reason}", 10 + i, n, a)
                     for i, (reason, n, a) in enumerate(sorted(excl, key=lambda x: -x[1]))]
            rows.append(("kept", 99, kept[0], kept[1]))
            con.executemany("INSERT INTO analysis_funnel VALUES (?,?,?,?,?,?,?)",
                            [(s, o, src, n, tot[0], a, rid) for s, o, n, a in rows])
            # P2: the unit changes from records to stories. Story steps carry
            # the story total as their denominator, and distinct STORY authors
            # (A.2), not record authors.
            # Only stories not marked at story level (gpt-5 confirmation, D-8).
            live = ("s.story_id NOT IN (SELECT story_id FROM exclusions"
                    " WHERE story_id IS NOT NULL)")
            swhere = f"WHERE {live}" + ("" if src == "_all" else " AND r.source = ?")
            st = con.execute("SELECT count(*), count(DISTINCT s.author_key) FROM stories s"
                             f" JOIN records r USING (record_id) {swhere}", args).fetchone()
            if st[0]:
                srows = [("stories", 100, st[0], st[1])]
                for k, b in enumerate(("core", "adjacent", "irrelevant"), 101):
                    bn = con.execute(
                        "SELECT count(*), count(DISTINCT s.author_key) FROM stories s JOIN records r"
                        f" USING (record_id) WHERE s.bucket = ? AND {live}"
                        f" {'AND r.source = ?' if args else ''}",
                        (b, *args)).fetchone()
                    srows.append((f"stories:{b}", k, bn[0], bn[1]))
                con.executemany("INSERT INTO analysis_funnel VALUES (?,?,?,?,?,?,?)",
                                [(s, o, src, n, st[0], a, rid) for s, o, n, a in srows])

        spend: dict[str, float] = {}
        for stage, params in con.execute("SELECT stage, params_json FROM runs"
                                         " WHERE stage LIKE 'collect-%'"):
            usd = json.loads(params or "{}").get("apify_usd")
            if usd:
                src = stage.removeprefix("collect-")
                spend[src] = spend.get(src, 0.0) + float(usd)
        for r in con.execute(f"""
            SELECT source, min(collect_method) AS method, count(*) AS n,
                   count(DISTINCT author_key) AS a, sum(posts_json IS NOT NULL) AS t,
                   sum(created_at IS NOT NULL) AS d, min(created_at) AS lo, max(created_at) AS hi,
                   sum(record_id NOT IN ({EXCLUDED_AT_RECORD})) AS kept
            FROM records GROUP BY source""").fetchall():
            con.execute("INSERT INTO analysis_sources VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (r["source"], r["method"], r["n"], r["a"], r["t"], r["d"], r["lo"],
                         r["hi"], r["kept"], round(spend.get(r["source"], 0.0), 4), rid))
        con.commit()
        n = con.execute("SELECT count(*) FROM records").fetchone()[0]
        run.n_input = run.n_output = n
    return {"records": n, "sources": len(sources)}


if __name__ == "__main__":
    print(build(dbm.init()))
