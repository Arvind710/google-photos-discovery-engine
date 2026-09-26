"""The registered limitations — the caveats an Ask AI answer must cite when it
reports a count (architecture.md §7: "a caveat clause citing a method flag";
evals.md P5-INV-9). Free: built from the tables, rebuilt whole.

Each flag is one plain sentence carrying its own numbers, read from the
database at build time, so the caveat an answer quotes is as current as the
counts it qualifies.

    python -m pipeline.analyse.method_flags
"""

from __future__ import annotations

from pipeline.common import db as dbm
from pipeline.common import runs as rmod


def flags(con) -> dict[str, str]:
    f = {r[0]: r for r in con.execute("SELECT step, n, n_authors FROM analysis_funnel"
                                      " WHERE source='_all'")}
    core, adj = f["stories:core"][1], f["stories:adjacent"][1]
    rel = {r[0]: r for r in con.execute("SELECT field, value, verdict FROM analysis_reliability")}
    low = sorted(k for k, r in rel.items() if r[2] == "low_reliability")
    reg = con.execute("SELECT count(*) FROM analysis_coverage WHERE source='_all' AND"
                      " disposition='register'").fetchone()[0]
    ps = rel["primary_stage"]
    return {
        "proxy_not_success_rate": (
            "Every share is a share of coded public stories — never a retrieval success "
            "rate, a share of Google Photos users, or a share of searches."),
        "public_selection_bias": (
            "People post when something goes wrong, so quiet successes and people who "
            "never search are under-counted by construction."),
        "thin_core": (
            f"There are {core} core stories, below the 300 the engine was designed for: "
            "a group under 30 stories is reported as a count only, and 30 to 79 as "
            "directional."),
        "stage5_inferred": (
            "What search did (Stage 5) is inferred from what users say; nobody outside "
            "Google can see why a search missed."),
        "no_gold_standard": (
            "There is no human-checked gold set. Reliability is agreement between two AI "
            f"models — primary stage kappa {ps[1]:.2f} — which measures consistency, not "
            "correctness."),
        "low_reliability_fields": (
            "The two AI coders agreed too little on these to rest a finding on them: "
            + ", ".join(x.replace("q:", "question ") for x in low) + "."),
        "interview_register": (
            f"{reg} of the 60 codebook questions are answered by too few public stories "
            "and are left to the interviews."),
        "adjacent_apart": (
            f"{adj} adjacent stories (precise memories, or photos that were never there) "
            "are counted separately from the core and never pooled with it."),
        "missing_cuts": (
            "The stories carry no reliable demographics, location, phone platform or dates "
            "for a before-and-after, and do not compare other apps' search, so none of "
            "those splits is made."),
        "emerging_themes": (
            "Four themes found after the codebook froze are reported as counts only and "
            "never ranked."),
    }


def main() -> int:
    con = dbm.init()
    with rmod.Run(con, "analyse-method-flags", model=None, estimate_usd=0) as run:
        fs = flags(con)
        con.execute("DELETE FROM analysis_method_flags")
        con.executemany("INSERT INTO analysis_method_flags (flag, text, run_id) VALUES (?,?,?)",
                        [(k, v, run.run_id) for k, v in fs.items()])
        con.commit()
        run.n_output = len(fs)
    for k, v in fs.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
