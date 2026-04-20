"""Lightweight in-process LRU cache for runner outputs (optional)."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any

_MAX = 32
_CACHE: OrderedDict[str, Any] = OrderedDict()


def payload_fingerprint(payload: dict[str, Any]) -> str:
    """Stable hash for JSON-serialisable dicts (sorted keys)."""
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cache_get(key: str) -> Any | None:
    if key not in _CACHE:
        return None
    _CACHE.move_to_end(key)
    return _CACHE[key]


def cache_set(key: str, value: Any) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _MAX:
        _CACHE.popitem(last=False)


def cache_key(task: str, fingerprint: str) -> str:
    return f"{task}:{fingerprint}"
