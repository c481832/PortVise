"""Macro regime signals from live indicators plus historical analog outcomes."""

from __future__ import annotations

from port.analysis import backtest
from port.analysis.registry import register_task
from port.config import config
from port.models.market import MarketData
from port.models.portfolio import Portfolio
from port.models.regime import HistoricalRegimeOutcome, RegimeReview, RegimeStateVector


def _ind_by_ticker(md: MarketData | None, ticker: str):
    if not md or not md.indicators:
        return None
    t = ticker.upper()
    for row in md.indicators:
        if row.ticker.upper() == t:
            return row
    return None


def _threshold(name: str):
    table = config.regime.indicator_thresholds
    if name not in table:
        raise RuntimeError(f"missing regime.indicator_thresholds.{name}")
    return table[name]


def _require_indicator(md: MarketData, ticker: str):
    row = _ind_by_ticker(md, ticker)
    if row is None:
        raise RuntimeError(f"missing required regime indicator {ticker}")
    return row


def _clip_trend(x: float, up: float, down: float) -> str:
    if x > up:
        return "up"
    if x < down:
        return "down"
    return "stable"


def infer_state_vector(md: MarketData | None) -> RegimeStateVector:
    """Map Yahoo macro rows into a coarse state vector. Required indicators must be present."""
    if md is None:
        raise RuntimeError("market_data is required for regime state inference")
    analog = config.regime.analog_tickers
    required = [*analog.model_dump().values(), config.regime.volatility_ticker]
    missing = [ticker for ticker in required if _ind_by_ticker(md, ticker) is None]
    if missing:
        raise RuntimeError("missing required regime indicators: " + ", ".join(missing))

    rates_t = _threshold("rates")
    growth_t = _threshold("growth")
    inflation_t = _threshold("inflation")
    vix_level_t = _threshold("volatility_vix_level")
    vix_change_t = _threshold("volatility_vix_change")
    uso_change_t = _threshold("volatility_uso_change")
    eem_change_t = _threshold("volatility_eem_change")
    liquidity_gap_t = _threshold("liquidity_eem_spy_gap")

    tnx = _require_indicator(md, analog.rates)
    spy = _require_indicator(md, analog.equity)
    eem = _require_indicator(md, analog.em)
    xlf = _require_indicator(md, analog.financials)
    gld = _require_indicator(md, analog.gold)
    uso = _require_indicator(md, analog.oil)
    vix = _require_indicator(md, config.regime.volatility_ticker)

    tnx_1m = float(tnx.change_1m_pct)
    if tnx_1m > rates_t.high:
        rates_literal = "up"
    elif tnx_1m < rates_t.low:
        rates_literal = "down"
    else:
        rates_literal = "stable"

    spy_1m = float(spy.change_1m_pct)
    eem_1m = float(eem.change_1m_pct)
    if spy_1m > growth_t.high and eem_1m > 0.0:
        growth = "accelerating"
    elif spy_1m < growth_t.low or eem_1m < growth_t.low:
        growth = "slowing"
    else:
        growth = "stable"

    gld_1m = float(gld.change_1m_pct)
    uso_1m = float(uso.change_1m_pct)
    infl = _clip_trend((gld_1m + uso_1m) / 2.0, up=inflation_t.high, down=inflation_t.low)
    inflation_trend = infl  # type: ignore[assignment]

    xlf_1m = float(xlf.change_1m_pct)
    if eem_1m < spy_1m - liquidity_gap_t.high and xlf_1m < 0.0:
        liquidity: str = "tight"
    elif eem_1m > 0.0 and xlf_1m > 0.0:
        liquidity = "loose"
    else:
        liquidity = "neutral"

    vix_level = float(vix.current)
    vix_1m = float(vix.change_1m_pct)
    if (
        vix_level >= vix_level_t.high
        or vix_1m > vix_change_t.high
        or uso_1m >= uso_change_t.high
        or uso_1m <= uso_change_t.low
        or eem_1m <= eem_change_t.low
    ):
        vol: str = "high"
    else:
        vol = "low"

    return RegimeStateVector(
        inflation_trend=inflation_trend,  # type: ignore[arg-type]
        rates_trend=rates_literal,  # type: ignore[arg-type]
        growth_trend=growth,  # type: ignore[arg-type]
        liquidity=liquidity,  # type: ignore[arg-type]
        volatility=vol,  # type: ignore[arg-type]
    )


def _regime_label(sv: RegimeStateVector) -> str:
    inflation = {
        "up": "rising inflation",
        "down": "cooling inflation",
        "stable": "stable inflation",
    }[sv.inflation_trend]
    rates = {
        "up": "rising rates",
        "down": "falling rates",
        "stable": "stable rates",
    }[sv.rates_trend]
    growth = {
        "accelerating": "accelerating growth",
        "slowing": "slowing growth",
        "stable": "stable growth",
    }[sv.growth_trend]
    liquidity = {
        "tight": "tight liquidity",
        "neutral": "neutral liquidity",
        "loose": "loose liquidity",
    }[sv.liquidity]
    volatility = {
        "high": "high volatility",
        "low": "low volatility",
    }[sv.volatility]
    return f"{inflation}, {rates}, {growth}, {liquidity}, {volatility}"


def compute_regime_review_base(portfolio: Portfolio, md: MarketData | None) -> RegimeReview:
    _ = portfolio
    sv = infer_state_vector(md)
    label = _regime_label(sv)
    hist = HistoricalRegimeOutcome(
        runner_available=False,
        message="Historical analog matching has not been run yet for this review.",
        analog_periods_identified=0,
        avg_return=None,
        max_drawdown=None,
        win_rate=None,
        top_similar_periods=[],
    )
    return RegimeReview(
        current_regime=label,
        state_vector=sv,
        historical_outcome=hist,
        mismatch_drivers=[],
        regime_appropriate_tilts=[],
        exposure_links=[],
        summary="",
    )




@register_task("regime_analysis")
def regime_analysis(payload: dict) -> dict:
    portfolio = Portfolio.model_validate(payload["portfolio"])
    raw_md = payload.get("market_data")
    md = None if raw_md is None else MarketData.model_validate(raw_md)

    analogs = backtest.find_similar_periods(md, portfolio, top_n=config.regime.top_n_analogs)
    performance = backtest.portfolio_performance(analogs)
    base = compute_regime_review_base(portfolio, md)
    hist = HistoricalRegimeOutcome(
        runner_available=bool(performance["available"]),
        message=str(performance["message"]),
        analog_periods_identified=len(analogs),
        avg_return=performance["avg_return"],
        max_drawdown=performance["max_drawdown_proxy"],
        win_rate=performance["win_rate"],
        top_similar_periods=performance["top_similar_periods"],
    )
    base = base.model_copy(update={"historical_outcome": hist})
    return {"regime_review": base.model_dump(mode="json")}
