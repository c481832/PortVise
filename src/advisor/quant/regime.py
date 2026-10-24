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

    # SHY/TLT are bond prices: up means yields fell. Negate so "up" = rising yields.
    shy_1m = change_1m(tickers.short_rates)
    tlt_1m = change_1m(tickers.long_rates)
    spy_1m = change_1m(tickers.equity)
    eem_1m = change_1m(tickers.em)
    gsg_1m = change_1m(tickers.inflation)
    uso_1m = change_1m(tickers.oil)
    vix = analogs.require_indicator(market_data, config.regime.volatility_ticker)
    liquidity_score = analogs.require_indicator(market_data, config.regime.liquidity_ticker)

    short_rates_trend = classify_trend(
        -shy_1m, thresholds.short_rates.high, thresholds.short_rates.low
    )
    long_rates_trend = classify_trend(
        -tlt_1m, thresholds.long_rates.high, thresholds.long_rates.low
    )
    inflation_trend = classify_trend(gsg_1m, thresholds.inflation.high, thresholds.inflation.low)

    if spy_1m > thresholds.growth.high and eem_1m > 0.0:
        growth_trend = "accelerating"
    elif spy_1m < thresholds.growth.low or eem_1m < thresholds.growth.low:
        growth_trend = "slowing"
    else:
        growth_trend = "stable"

    # KCROROL: positive = risk-off / tighter funding; negative = risk-on / looser.
    score = float(liquidity_score.current)
    if score >= thresholds.liquidity.high:
        liquidity = "tight"
    elif score <= thresholds.liquidity.low:
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
        short_rates_trend=short_rates_trend,  # type: ignore[arg-type]
        long_rates_trend=long_rates_trend,  # type: ignore[arg-type]
        growth_trend=growth_trend,
        liquidity=liquidity,
        volatility="high" if stressed else "low",
    )


def build_regime_label(state_vector: RegimeStateVector) -> str:
    inflation = {"up": "rising", "down": "cooling", "stable": "stable"}[
        state_vector.inflation_trend
    ]
    short_rates = {"up": "rising", "down": "falling", "stable": "stable"}[
        state_vector.short_rates_trend
    ]
    long_rates = {"up": "rising", "down": "falling", "stable": "stable"}[
        state_vector.long_rates_trend
    ]
    return (
        f"{inflation} inflation, {short_rates} short rates, {long_rates} long rates, "
        f"{state_vector.growth_trend} growth, {state_vector.liquidity} liquidity, "
        f"{state_vector.volatility} volatility"
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
