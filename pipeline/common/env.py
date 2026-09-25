"""Single, tolerant reader for .env — and the ONLY place secrets are handled.

Ported from the Myntra build, with its two lessons:
1. Hand-written .env files drift between `KEY=value` and `KEY: value`. A parser
   that accepts only one returns nothing for the other, which looks exactly
   like "the key isn't set". Accept both.
2. NEVER print a secret. `masked()` is the only way a value leaves this module.

`.env` is gitignored and laptop-only. The deployed app reads OPENAI_API_KEY
from Streamlit secrets instead; the salt never leaves the laptop (EC-OPS-7).

    python -m pipeline.common.env      # which credentials are set (masked)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")

ALIASES = {
    "OPENAI_API_KEY": ("OPENAI_API_KEY", "OPENAI_KEY"),
    "REDDIT_CLIENT_ID": ("REDDIT_CLIENT_ID",),
    "REDDIT_CLIENT_SECRET": ("REDDIT_CLIENT_SECRET",),
    "REDDIT_USER_AGENT": ("REDDIT_USER_AGENT",),
    "AUTHOR_SALT": ("AUTHOR_SALT",),
}


def parse(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(1).strip().upper()] = m.group(2).strip().strip("\"'")
    return out


def load(*, export: bool = True) -> dict[str, str]:
    """Resolve aliases to canonical names; process env wins over .env."""
    raw = parse()
    resolved: dict[str, str] = {}
    for canonical, names in ALIASES.items():
        for n in names:
            v = os.environ.get(n) or raw.get(n)
            if v:
                resolved[canonical] = v
                break
    if export:
        for k, v in resolved.items():
            os.environ.setdefault(k, v)
    return resolved


def masked(value: str | None) -> str:
    """The ONLY safe way to show a credential."""
    if not value:
        return "not set"
    return f"set ({len(value)} chars, ends …{value[-4:]})" if len(value) > 8 else "set (short)"


def require(key: str) -> str:
    v = load().get(key, "")
    if not v:
        raise RuntimeError(f"{key} is not set — add it to .env (see .env.example)")
    return v


if __name__ == "__main__":
    vals = load(export=False)
    print("credentials:")
    for k in ALIASES:
        print(f"  {k:<22} {masked(vals.get(k))}")
