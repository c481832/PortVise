"""Typed config sub-models. Every field is required — no Python-level defaults.

All values come from `config.toml` (committed) + `config.local.toml` (gitignored) +
whitelisted env-var overrides. Loaded once via `port.config.load(...)`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMSettings(_StrictModel):
    base_url: str
    model: str
    api_key: str
    model_options: str
    model_base_urls: str
    model_extra_args: str
    connect_timeout: float
    read_timeout: float
    max_retries: int
    invoke_max_attempts: int
    retry_base_seconds: float
    retry_max_seconds: float
    max_tokens_ceiling: int
    length_markers: tuple[str, ...]
    default_temperature: float
    default_max_tokens: int
    planner_temperature: float
    planner_max_tokens: int
    summary_temperature: float
    summary_max_tokens: int
    translation_temperature: float
    translation_max_tokens: int
    structured_temperature: float
    structured_max_tokens: int


class AgentModelSettings(_StrictModel):
    planner: str
    news_tools: str
    news_synthesis: str
    risk: str
    regime: str
    theme: str
    validation: str
    manager: str
    agent_summary: str


class LogSettings(_StrictModel):
    file: str
    max_bytes: int
    backup_count: int


class SearchSettings(_StrictModel):
    provider: Literal["tavily", "searxng"]
    searxng_url: str
    tavily_api_key: str
    user_agent: str
    concurrent_requests: int
    provider_max_attempts: int
    provider_backoff_seconds: float
    request_timeout_seconds: float
    tavily_topic: str
    tavily_days: int
    body_truncation_chars: int
    default_max_results: int


class MarketSettings(_StrictModel):
    fetch_max_attempts: int
    fetch_backoff_base_seconds: float
    fetch_backoff_max_seconds: float
    yfinance_timeout_seconds: float
    price_history_period: str
    local_data_dir: str


class MacroSettings(_StrictModel):
    indicator_universe: tuple[str, ...]
    indicator_labels: dict[str, str]
    required_for_regime: tuple[str, ...]
    indicator_aliases: dict[str, str]
    lookback_period: str
    interval: str
    change_window_days: int
    thread_pool_size: int
    fetched_at_format: str


class HistoricalScenario(_StrictModel):
    name: str
    start: str
    end: str


class RiskEngineSettings(_StrictModel):
    history_period: str
    yfinance_timeout_seconds: float
    download_max_attempts: int
    download_backoff_base_seconds: float
    download_backoff_max_seconds: float
    min_observations: int
    min_return_coverage: float
    factor_tickers: dict[str, str]
    historical_scenarios: tuple[HistoricalScenario, ...]
    min_beta_observations: int
    correlation_threshold: float
    top_n_marginal: int
    top_n_concentration: int
    concentration_threshold: float
    volatility_divisor: float
    risk_formula_intercept: float
    risk_formula_concentration_weight: float
    risk_formula_volatility_weight: float


class IndicatorThresholds(_StrictModel):
    high: float
    low: float


class RegimeSettings(_StrictModel):
    indicator_thresholds: dict[str, IndicatorThresholds]
    min_trading_days: int
    return_smoothing_window: int
    top_n_analogs: int
    backtest_lookback_days: int
    backtest_forward_days: int
    backtest_min_analog_gap_days: int
    backtest_min_aligned_observations: int


class RunnerSettings(_StrictModel):
    """Retry/backoff for the risk + regime agent wrappers around their engine runners."""

    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float


class TruncationSettings(_StrictModel):
    log_safe_text_max_chars: int
    error_detail_chars: int


class ServerSettings(_StrictModel):
    host: str
    port: int
    log_level: str
    heartbeat_seconds: float
    sse_stream_version: str
    ticker_regex_pattern: str
    llm_test_timeout_seconds: float
    llm_test_temperature: float
    llm_test_max_tokens: int


class I18nSettings(_StrictModel):
    default_locale: str
    supported_locales: tuple[str, ...]
    cjk_pattern: str
    ascii_pattern: str
    tokenish_pattern: str
    translation_chunk_max_chars: int
    translation_chunk_max_items: int


class ValidationSettings(_StrictModel):
    max_request_rounds: int


class ArenaSettings(_StrictModel):
    starting_cash: float
    transaction_cost_bps: float
    max_position_weight: float
    max_holdings: int
    cash_return_annual_pct: float
    min_trade_value: float
    min_cash_weight: float
    advisor_timeout_seconds: int
    default_benchmark: str
    default_run_name: str
    corporate_actions_mode: str
    rebalance_cadence: str
    trade_time: str
    timezone: str
    minimum_position_threshold: float
    cash_round_decimals: int
    leaderboard_drawdown_weight: float
    leaderboard_turnover_weight: float
    annualization_factor: float
    advisor_temperature: float
    advisor_max_tokens: int
    server_host: str
    server_port: int


class PlannerPromptVars(_StrictModel):
    portfolio_query_count: int
    macro_indicator_min: int
    macro_indicator_max: int
    max_query_chars: int


class NewsPromptVars(_StrictModel):
    macro_context_sentence_max: int
    themes_min: int
    themes_max: int
    key_events_max: int


class RiskPromptVars(_StrictModel):
    top_risks_min: int
    top_risks_max: int


class RegimePromptVars(_StrictModel):
    summary_sentence_min: int
    summary_sentence_max: int


class ThemePromptVars(_StrictModel):
    research_excerpt_max_chars: int
    per_ticker_research_max_chars: int
    per_ticker_item_max_chars: int


class ManagerPromptVars(_StrictModel):
    top_risks_max: int
    scenario_losses_max: int
    concentration_issues_max: int
    hidden_concentration_max: int
    marginal_risk_tickers_max: int
    regime_analogs_max: int
    regime_mismatch_drivers_max: int
    regime_tilts_max: int
    theme_assessments_max: int
    theme_list_items_max: int
    validation_issues_max: int
    validation_thesis_breaks_max: int
    validation_contradictions_max: int


class PromptsSettings(_StrictModel):
    planner: PlannerPromptVars
    news: NewsPromptVars
    risk: RiskPromptVars
    regime: RegimePromptVars
    theme: ThemePromptVars
    manager: ManagerPromptVars


class AgentSummarySettings(_StrictModel):
    max_input_chars: int
    summary_truncate_chars: int
    bullet_truncate_chars: int
    max_bullets: int


class RootConfig(_StrictModel):
    """Root config — every domain is a typed sub-model. No defaults anywhere."""

    llm: LLMSettings
    agents: AgentModelSettings
    log: LogSettings
    search: SearchSettings
    market: MarketSettings
    macro: MacroSettings
    risk_engine: RiskEngineSettings
    regime: RegimeSettings
    runner: RunnerSettings
    truncation: TruncationSettings
    server: ServerSettings
    i18n: I18nSettings
    validation: ValidationSettings
    arena: ArenaSettings
    prompts: PromptsSettings
    agent_summary: AgentSummarySettings


__all__ = [
    "AgentModelSettings",
    "AgentSummarySettings",
    "ArenaSettings",
    "HistoricalScenario",
    "I18nSettings",
    "IndicatorThresholds",
    "LLMSettings",
    "LogSettings",
    "MacroSettings",
    "ManagerPromptVars",
    "MarketSettings",
    "NewsPromptVars",
    "PlannerPromptVars",
    "PromptsSettings",
    "RegimePromptVars",
    "RegimeSettings",
    "RiskEngineSettings",
    "RiskPromptVars",
    "RootConfig",
    "RunnerSettings",
    "SearchSettings",
    "ServerSettings",
    "ThemePromptVars",
    "TruncationSettings",
    "ValidationSettings",
]
