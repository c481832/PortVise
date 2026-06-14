from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from port.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    apply_translations_to_payload,
    build_locale_instruction,
    inject_locale_instruction,
    needs_translation_fallback,
    normalize_locale,
)


def test_normalize_locale_english_variants() -> None:
    assert normalize_locale("en") == "en"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("en_GB") == "en"


def test_normalize_locale_chinese_variants() -> None:
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh-CN") == "zh-CN"
    assert normalize_locale("zh-Hans-CN") == "zh-CN"


def test_normalize_locale_unknown_defaults_to_english() -> None:
    assert normalize_locale("") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE
    assert normalize_locale("fr-FR") == DEFAULT_LOCALE


def test_build_locale_instruction_for_simplified_chinese() -> None:
    instruction = build_locale_instruction("zh-Hans-CN")
    assert "Simplified Chinese" in instruction
    assert "machine-readable identifiers unchanged" in instruction


def test_inject_locale_instruction_appends_to_existing_system_message() -> None:
    messages = [SystemMessage(content="Base system prompt"), HumanMessage(content="Hello")]
    localized = inject_locale_instruction(messages, "zh-CN")
    assert len(localized) == 2
    assert "Base system prompt" in localized[0].content
    assert "OUTPUT LANGUAGE: Simplified Chinese." in localized[0].content


def test_needs_translation_fallback_detects_english_free_text_for_chinese() -> None:
    payload = {
        "summary": "Concentration risk is rising in the technology sleeve.",
        "action_type": "reduce",
        "position": "AAPL",
    }
    assert needs_translation_fallback(payload, "zh-CN") is True


def test_apply_translations_to_payload_skips_enum_like_fields() -> None:
    payload = {
        "summary": "Reduce concentration risk.",
        "action_type": "reduce",
        "position": "AAPL",
        "nested": [{"label": "Macro pressure is building."}],
    }

    def fake_translate(strings: list[str], locale: str) -> list[str]:
        assert locale == "zh-CN"
        return [f"ZH:{value}" for value in strings]

    translated = apply_translations_to_payload(payload, "zh-CN", fake_translate)
    assert translated["summary"] == "ZH:Reduce concentration risk."
    assert translated["nested"][0]["label"] == "ZH:Macro pressure is building."
    assert translated["action_type"] == "reduce"
    assert translated["position"] == "AAPL"


def test_locale_catalog_keys_match() -> None:
    locale_dir = Path(__file__).resolve().parent.parent / "src" / "port" / "static" / "locales"
    en = json.loads((locale_dir / "en.json").read_text())
    zh = json.loads((locale_dir / "zh-CN.json").read_text())
    assert SUPPORTED_LOCALES == ("en", "zh-CN")
    assert _flatten_keys(en) == _flatten_keys(zh)


def test_frontend_translation_keys_exist_in_catalog() -> None:
    locale_dir = Path(__file__).resolve().parent.parent / "src" / "port" / "static" / "locales"
    catalog_keys = _flatten_keys(json.loads((locale_dir / "en.json").read_text()))
    missing = _frontend_translation_keys() - catalog_keys
    assert not missing


def _flatten_keys(value, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        out: set[str] = set()
        for key, item in value.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            out |= _flatten_keys(item, full)
        return out
    if isinstance(value, list):
        out: set[str] = set()
        for index, item in enumerate(value):
            full = f"{prefix}.{index}" if prefix else str(index)
            out |= _flatten_keys(item, full)
        return out
    return {prefix}


def _frontend_translation_keys() -> set[str]:
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "advisor" / "src" / "app.js").read_text()
    index_html = (root / "src" / "port" / "static" / "index.html").read_text()

    data_attr_re = re.compile(r'data-i18n(?:-placeholder|-title|-aria-label)?="([^"]+)"')
    t_call_re = re.compile(r'(?<![A-Za-z0-9_$.])t\(\s*["\']([^"\']+)["\']')
    helper_key_re = re.compile(r'(?:labelKey|descKey|hintKey|detailKey):\s*"([^"]+)"')
    detail_helper_re = re.compile(r'dataLoaderDetail\(\s*"([^"]+)"')
    step_keys_re = re.compile(r"stepKeys:\s*\[([^\]]+)\]")
    quoted_re = re.compile(r'"([^"]+)"')

    keys = set(data_attr_re.findall(index_html))
    keys |= set(data_attr_re.findall(app_js))
    keys |= set(t_call_re.findall(app_js))
    keys |= set(helper_key_re.findall(app_js))
    keys |= set(detail_helper_re.findall(app_js))
    for match in step_keys_re.findall(app_js):
        keys |= set(quoted_re.findall(match))

    keys |= {
        "actionType.reduce",
        "actionType.exit",
        "actionType.hedge",
        "actionType.rotate",
        "actionType.add",
        "actionType.monitor",
        "actionType.no-action",
        "priority.urgent",
        "priority.this-week",
        "priority.next-review",
        "priority.watch",
        "severity.critical",
        "severity.high",
        "severity.medium",
        "severity.low",
        "stateValue.up",
        "stateValue.down",
        "stateValue.stable",
        "stateValue.accelerating",
        "stateValue.slowing",
        "stateValue.tight",
        "stateValue.neutral",
        "stateValue.loose",
        "stateValue.high",
        "stateValue.low",
        "positions.row.asset.equity",
        "positions.row.asset.bond",
        "positions.row.asset.commodity",
        "positions.row.asset.fx",
        "positions.row.asset.crypto",
    }
    return {key for key in keys if "${" not in key}
