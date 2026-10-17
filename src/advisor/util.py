from __future__ import annotations

import json
from datetime import date
from typing import Any


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n... (truncated)"


def clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def safe_text(value: Any, *, max_chars: int) -> str:
    try:
        if hasattr(value, "model_dump"):
            text = json.dumps(value.model_dump(), ensure_ascii=True, default=str)
        elif isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=True, default=str)
        else:
            text = str(value)
    except Exception:
        text = repr(value)
    return truncate_text(text, max_chars)


def safe_json(value: Any, *, max_chars: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    return truncate_text(text, max_chars)


def serialise(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialise(i) for i in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def format_inherited_feedback(items: list, *, heading: str) -> str:
    comments = [
        str(item.get("comment") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("comment") or "").strip()
    ]
    if not comments:
        return ""
    return heading + "\n" + "\n".join(f"- {c}" for c in comments)
