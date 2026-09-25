"""Every label the app shows comes from here, which reads
`codebook/plain_language.yaml` — no view hardcodes one (design language §9).
Free of Streamlit imports, like `evidence.py`, so the pipeline and tests can
use the same words."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).resolve().parents[2] / "codebook" / "plain_language.yaml"


@cache
def _all() -> dict[str, Any]:
    return yaml.safe_load(PATH.read_text())


def source(key: str) -> str:
    return (_all().get("sources", {}).get(key) or {}).get("label", key)


def source_kind(key: str) -> str:
    return (_all().get("sources", {}).get(key) or {}).get("kind", "")


def method(key: str) -> str:
    return " ".join(str(_all().get("collect_methods", {}).get(key, key)).split())


def exclusion(key: str) -> str:
    return _all().get("exclusion_reasons", {}).get(key, key.replace("_", " "))


def proxy_warning() -> str:
    return " ".join(_all()["proxy_warning"].split())


def metric(key: str) -> str:
    return " ".join(str(_all().get("metrics", {}).get(key, "")).split())
