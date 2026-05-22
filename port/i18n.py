from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import SystemMessage

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "zh-CN")
DEFAULT_LOCALE = "en"

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_TOKENISH_RE = re.compile(r"^[A-Z0-9^._:/-]{1,32}$")
_NON_TRANSLATABLE_KEYS = frozenset(
    {
        "ticker",
        "position",
        "action_type",
        "priority",
        "hedge_instrument",
        "scenario_kind",
        "source_agents",
        "affected_positions",
        "supporting_assets",
        "most_affected_positions",
        "maps_to",
        "strength",
        "regime_confidence",
        "concentration_top5_pct",
        "estimated_portfolio_loss_pct",
        "runner_available",
        "avg_return",
        "max_drawdown",
        "win_rate",
        "analog_periods_identified",
    }
)


@dataclass
class LocaleRuntimeState:
    requested_locale: str = DEFAULT_LOCALE
    content_locale: str = DEFAULT_LOCALE
    translation_fallback_used: bool = False


def normalize_locale(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_LOCALE
    lowered = raw.replace("_", "-").lower()
    if lowered.startswith("zh"):
        return "zh-CN"
    if lowered.startswith("en"):
        return "en"
    return DEFAULT_LOCALE


def is_supported_locale(value: str | None) -> bool:
    return normalize_locale(value) in SUPPORTED_LOCALES


def prompt_language_name(locale: str) -> str:
    return "Simplified Chinese" if normalize_locale(locale) == "zh-CN" else "English"


def build_locale_instruction(locale: str) -> str:
    resolved = normalize_locale(locale)
    if resolved == DEFAULT_LOCALE:
        return ""
    language = prompt_language_name(resolved)
    return (
        f"OUTPUT LANGUAGE: {language}. Write all user-facing free-text fields in {language}. "
        "Keep schema keys, field names, enum values, ticker symbols, dates, numbers, and other "
        "machine-readable identifiers unchanged. Do not silently translate user-supplied "
        "portfolio names, goals, or thesis text; quote them verbatim when needed."
    )


def inject_locale_instruction(messages: list[Any], locale: str) -> list[Any]:
    instruction = build_locale_instruction(locale)
    if not instruction:
        return list(messages)
    copied = list(messages)
    if copied and isinstance(copied[0], SystemMessage):
        first = copied[0]
        copied[0] = SystemMessage(content=f"{first.content}\n\n{instruction}")
        return copied
    return [SystemMessage(content=instruction), *copied]


def _path_key(path: tuple[str, ...]) -> str:
    return path[-1] if path else ""


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _looks_english(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 4 or _contains_cjk(stripped):
        return False
    ascii_letters = len(_ASCII_LETTER_RE.findall(stripped))
    return ascii_letters >= 4


def _should_translate(path: tuple[str, ...], value: str) -> bool:
    key = _path_key(path)
    stripped = value.strip()
    if not stripped:
        return False
    if key in _NON_TRANSLATABLE_KEYS:
        return False
    return not _TOKENISH_RE.fullmatch(stripped)


def collect_translatable_strings(
    value: Any, path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], str]]:
    if value is None:
        return []
    if hasattr(value, "model_dump"):
        return collect_translatable_strings(value.model_dump(mode="json"), path)
    if isinstance(value, str):
        return [(path, value)] if _should_translate(path, value) else []
    if isinstance(value, list):
        out: list[tuple[tuple[str, ...], str]] = []
        for index, item in enumerate(value):
            out.extend(collect_translatable_strings(item, (*path, str(index))))
        return out
    if isinstance(value, dict):
        out: list[tuple[tuple[str, ...], str]] = []
        for key, item in value.items():
            out.extend(collect_translatable_strings(item, (*path, str(key))))
        return out
    return []


def needs_translation_fallback(value: Any, locale: str) -> bool:
    if normalize_locale(locale) == DEFAULT_LOCALE:
        return False
    texts = [text for _, text in collect_translatable_strings(value)]
    if not texts:
        return False
    localized = sum(_contains_cjk(text) for text in texts)
    englishish = sum(_looks_english(text) for text in texts)
    return localized == 0 and englishish >= max(1, len(texts) // 2)


def apply_translations_to_payload(
    payload: Any,
    locale: str,
    translate_many: Callable[[list[str], str], list[str]],
) -> Any:
    pairs = collect_translatable_strings(payload)
    if not pairs:
        return payload
    texts = [text for _, text in pairs]
    translated = translate_many(texts, locale)
    if len(translated) != len(texts):
        raise ValueError("translated string count did not match input count")
    replacements = {
        path: (translated_text.strip() or original)
        for (path, original), translated_text in zip(pairs, translated, strict=False)
    }
    return _replace_payload_strings(payload, replacements)


def _replace_payload_strings(
    value: Any, replacements: dict[tuple[str, ...], str], path: tuple[str, ...] = ()
) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return replacements.get(path, value)
    if isinstance(value, list):
        return [
            _replace_payload_strings(item, replacements, (*path, str(index)))
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            key: _replace_payload_strings(item, replacements, (*path, str(key)))
            for key, item in value.items()
        }
    return value


def chunk_strings(items: Iterable[str]) -> list[list[str]]:
    # Caps come from config; imported lazily to avoid a circular import (config imports i18n).
    from port.config import config

    max_chars = config.i18n.translation_chunk_max_chars
    max_items = config.i18n.translation_chunk_max_items
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for item in items:
        item_size = len(item)
        if current and (len(current) >= max_items or size + item_size > max_chars):
            batches.append(current)
            current = []
            size = 0
        current.append(item)
        size += item_size
    if current:
        batches.append(current)
    return batches
