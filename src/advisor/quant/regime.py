from __future__ import annotations

from advisor.config import config
from advisor.quant import analogs
from advisor.schemas.market import MarketData
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.regime import RegimeReview, RegimeStateVector


def classify_trend(change: float, up: float, down: float) -> str:
    if change > up:
        return "up"
    if change < down:
        return "down"
    return "stable"


def infer_state_vector(market_data: MarketData | None) -> RegimeStateVector:
    tickers = config.regime.analog_tickers
    thresholds = config.regime.indicator_thresholds

    def change_1m(ticker: str) -> float:
        return float(analogs.require_indicator(market_data, ticker).change_1m_pct)

    tnx_1m = change_1m(tickers.rates)
    spy_1m = change_1m(tickers.equity)
    eem_1m = change_1m(tickers.em)
    xlf_1m = change_1m(tickers.financials)
    gld_1m = change_1m(tickers.gold)
    uso_1m = change_1m(tickers.oil)
    vix = analogs.require_indicator(market_data, config.regime.volatility_ticker)

    rates_trend = classify_trend(tnx_1m, thresholds.rates.high, thresholds.rates.low)
    inflation_trend = classify_trend(
        (gld_1m + uso_1m) / 2.0, thresholds.inflation.high, thresholds.inflation.low
    )

    if spy_1m > thresholds.growth.high and eem_1m > 0.0:
        growth_trend = "accelerating"
    elif spy_1m < thresholds.growth.low or eem_1m < thresholds.growth.low:
        growth_trend = "slowing"
    else:
        growth_trend = "stable"

    if eem_1m < spy_1m - thresholds.liquidity_eem_spy_gap.high and xlf_1m < 0.0:
        liquidity = "tight"
    elif eem_1m > 0.0 and xlf_1m > 0.0:
        liquidity = "loose"
    else:
        liquidity = "neutral"

    stressed = (
        float(vix.current) >= thresholds.volatility_vix_level.high
        or float(vix.change_1m_pct) > thresholds.volatility_vix_change.high
        or uso_1m >= thresholds.volatility_uso_change.high
        or uso_1m <= thresholds.volatility_uso_change.low
        or eem_1m <= thresholds.volatility_eem_change.low
    )

    return RegimeStateVector(
        inflation_trend=inflation_trend,  # type: ignore[arg-type]
        rates_trend=rates_trend,  # type: ignore[arg-type]
        growth_trend=growth_trend,
        liquidity=liquidity,
        volatility="high" if stressed else "low",
    )


def build_regime_label(state_vector: RegimeStateVector) -> str:
    inflation = {"up": "rising", "down": "cooling", "stable": "stable"}[
        state_vector.inflation_trend
    ]
    rates = {"up": "rising", "down": "falling", "stable": "stable"}[state_vector.rates_trend]
    return (
        f"{inflation} inflation, {rates} rates, {state_vector.growth_trend} growth, "
        f"{state_vector.liquidity} liquidity, {state_vector.volatility} volatility"
    )


def compute_regime_review_base(
    portfolio: Portfolio, market_data: MarketData | None
) -> RegimeReview:
    state_vector = infer_state_vector(market_data)
    similar_periods = analogs.find_similar_periods(
        market_data, portfolio, top_n=config.regime.top_n_analogs
    )
    return RegimeReview(
        current_regime=build_regime_label(state_vector),
        state_vector=state_vector,
        historical_outcome=analogs.summarize_analogs(similar_periods),
        mismatch_drivers=[],
        regime_appropriate_tilts=[],
        summary="",
    )
