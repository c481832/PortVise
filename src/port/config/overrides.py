"""Persist UI-editable settings back into `config.local.toml`.

Only the keys listed here may be written from the web UI; everything else in
the config file is owned by the operator.
"""

from __future__ import annotations

import json

import tomlkit

import port.config
from port.llm.client import AGENT_MODEL_KEYS

_UI_LLM_KEYS: tuple[str, ...] = (
    "base_url",
    "model",
    "api_key",
    "model_options",
    "model_base_urls",
    "model_extra_args",
    "reasoning_enabled",
)
_UI_SEARCH_KEYS: tuple[str, ...] = ("provider", "searxng_url", "tavily_api_key")
_UI_CAPITAL_ALLOCATION_KEYS: tuple[str, ...] = (
    "min_allocated_capital",
    "max_drawdown",
    "cash_yield_annual_pct",
)
def write_ui_overrides(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    model_options: list[str] | None = None,
    model_base_urls: dict[str, str] | None = None,
    model_extra_args: str | None = None,
    agent_models: dict[str, str] | None = None,
    search_provider: str | None = None,
    searxng_url: str | None = None,
    tavily_api_key: str | None = None,
    min_allocated_capital: float | None = None,
    max_drawdown: float | None = None,
    cash_yield_annual_pct: float | None = None,
) -> None:
    if port.config.LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(port.config.LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    if any(
        v is not None
        for v in (base_url, model, api_key, model_options, model_base_urls, model_extra_args)
    ):
        if "llm" not in doc:
            doc["llm"] = tomlkit.table()
        llm = doc["llm"]
        if base_url is not None:
            llm["base_url"] = base_url.strip()
        if model is not None:
            llm["model"] = model.strip()
        if api_key is not None:
            llm["api_key"] = api_key
        if model_options is not None:
            llm["model_options"] = ", ".join(m.strip() for m in model_options if m.strip())
        if model_base_urls is not None:
            clean_urls = {
                str(k).strip(): str(v).strip()
                for k, v in model_base_urls.items()
                if str(k).strip() and str(v).strip()
            }
            llm["model_base_urls"] = json.dumps(clean_urls, sort_keys=True, separators=(",", ":"))
        if model_extra_args is not None:
            llm["model_extra_args"] = model_extra_args.strip()

    if any(v is not None for v in (search_provider, searxng_url, tavily_api_key)):
        if "search" not in doc:
            doc["search"] = tomlkit.table()
        search = doc["search"]
        if search_provider is not None:
            search["provider"] = search_provider.strip()
        if searxng_url is not None:
            search["searxng_url"] = searxng_url.strip()
        if tavily_api_key is not None:
            search["tavily_api_key"] = tavily_api_key

    if agent_models is not None:
        if "agents" not in doc:
            doc["agents"] = tomlkit.table()
        agents = doc["agents"]
        for key in sorted(AGENT_MODEL_KEYS):
            agents[key] = (agent_models.get(key) or "").strip()

    if any(v is not None for v in (min_allocated_capital, max_drawdown, cash_yield_annual_pct)):
        if "capital_allocation" not in doc:
            doc["capital_allocation"] = tomlkit.table()
        capital = doc["capital_allocation"]
        if min_allocated_capital is not None:
            capital["min_allocated_capital"] = min_allocated_capital
        if max_drawdown is not None:
            capital["max_drawdown"] = max_drawdown
        if cash_yield_annual_pct is not None:
            capital["cash_yield_annual_pct"] = cash_yield_annual_pct

    port.config.LOCAL_CONFIG_PATH.write_text(tomlkit.dumps(doc), encoding="utf-8")
    port.config.reload()
def _drop_table_keys(doc, table_name: str, keys: tuple[str, ...]) -> None:
    table = doc.get(table_name)
    if table is None:
        return
    for key in keys:
        if key in table:
            del table[key]
    if not len(table):
        del doc[table_name]
def clear_ui_overrides() -> None:
    if port.config.LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(port.config.LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        _drop_table_keys(doc, "llm", _UI_LLM_KEYS)
        _drop_table_keys(doc, "search", _UI_SEARCH_KEYS)
        _drop_table_keys(doc, "capital_allocation", _UI_CAPITAL_ALLOCATION_KEYS)
        if "agents" in doc:
            del doc["agents"]
        if "agent_reasoning" in doc:
            del doc["agent_reasoning"]
        remaining = tomlkit.dumps(doc)
        if remaining.strip():
            port.config.LOCAL_CONFIG_PATH.write_text(remaining, encoding="utf-8")
        else:
            port.config.LOCAL_CONFIG_PATH.unlink()
    port.config.reload()
