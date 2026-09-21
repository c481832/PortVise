"""Shared enum normalizers and the common model config.

LLMs return loose synonyms for enum fields; these map the accepted aliases onto
the canonical values and raise on anything unrecognized.
"""

from __future__ import annotations

from pydantic import ConfigDict

IGNORE_EXTRA = ConfigDict(extra="ignore")

def norm_action_type(v) -> str:
    table = {
        "reduce": "reduce",
        "exit": "exit",
        "hedge": "hedge",
        "rotate": "rotate",
        "add": "add",
        "monitor": "monitor",
        "no-action": "no-action",
        "sell": "exit",
        "trim": "reduce",
        "buy": "add",
        "no_action": "no-action",
        "hold": "monitor",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized action_type value: {v!r}")
    return table[key]

def norm_priority(v) -> str:
    s = str(v).lower()
    if s in ("urgent", "immediate", "critical", "high"):
        return "urgent"
    if s in ("this-week", "this_week", "thisweek", "medium", "short-term"):
        return "this-week"
    if s in ("next-review", "next_review", "low", "medium-term"):
        return "next-review"
    if s == "watch":
        return "watch"
    raise ValueError(f"unrecognized priority value: {v!r}")

def norm_action_scope(v) -> str:
    s = str(v).lower()
    if s in ("portfolio", "portfolio-level", "portfolio_level", "book"):
        return "portfolio"
    if s in ("position", "ticker", "security", "holding"):
        return "position"
    raise ValueError(f"unrecognized action_scope value: {v!r}")

def coerce_string_list(v) -> list[str]:
    if v is None:
        raise ValueError("expected a list of strings; got None")
    if isinstance(v, str):
        text = v.strip()
        if not text:
            raise ValueError("expected a list of strings; got an empty string")
        return [text]
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    raise TypeError(f"expected a list of strings; got {type(v).__name__}")
