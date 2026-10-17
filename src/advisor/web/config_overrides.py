from __future__ import annotations

import json

import tomlkit

import advisor.config
from advisor.llm.client import configured_agent_models

UI_LLM_KEYS: tuple[str, ...] = (
    "base_url",
    "model",
    "api_key",
    "model_options",
    "model_base_urls",
    "model_extra_args",
)
UI_SEARCH_KEYS: tuple[str, ...] = ("provider", "searxng_url", "tavily_api_key")
UI_CAPITAL_ALLOCATION_KEYS: tuple[str, ...] = (
    "min_allocated_capital",
    "max_drawdown",
    "cash_yield_annual_pct",
)


def write_ui_overrides(
    *,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    model_options: list[str] | None,
    model_base_urls: dict[str, str] | None,
    model_extra_args: str | None,
    agent_models: dict[str, str] | None,
    search_provider: str | None,
    searxng_url: str | None,
    tavily_api_key: str | None,
    min_allocated_capital: float | None,
    max_drawdown: float | None,
    cash_yield_annual_pct: float | None,
) -> None:
    if advisor.config.LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(advisor.config.LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
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
        for key in sorted(configured_agent_models()):
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

    advisor.config.LOCAL_CONFIG_PATH.write_text(tomlkit.dumps(doc), encoding="utf-8")
    advisor.config.reload()


def drop_table_keys(doc, table_name: str, keys: tuple[str, ...]) -> None:
    table = doc.get(table_name)
    if table is None:
        return
    for key in keys:
        if key in table:
            del table[key]
    if not len(table):
        del doc[table_name]


def clear_ui_overrides() -> None:
    if advisor.config.LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(advisor.config.LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        drop_table_keys(doc, "llm", UI_LLM_KEYS)
        drop_table_keys(doc, "search", UI_SEARCH_KEYS)
        drop_table_keys(doc, "capital_allocation", UI_CAPITAL_ALLOCATION_KEYS)
        if "agents" in doc:
            del doc["agents"]
        remaining = tomlkit.dumps(doc)
        if remaining.strip():
            advisor.config.LOCAL_CONFIG_PATH.write_text(remaining, encoding="utf-8")
        else:
            advisor.config.LOCAL_CONFIG_PATH.unlink()
    advisor.config.reload()
