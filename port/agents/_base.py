"""Shared helpers for agent nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from port.portfolio import market_data_to_text, news_to_text, portfolio_to_text

if TYPE_CHECKING:
    from port.state import GraphState

_CuratedRole = Literal["risk", "regime", "theme"]


def build_analysis_prompt(
    state: GraphState,
    portfolio_prefix: str = "Portfolio to review",
    *,
    curated_for: _CuratedRole | None = None,
) -> str:
    """Build the standard content string for parallel analysis agents."""
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]
    dc = state.get("downstream_context")

    content = f"{portfolio_prefix}:\n\n{portfolio_to_text(portfolio)}"
    if dc is not None and curated_for is not None:
        label = curated_for.upper()
        slice_map: dict[_CuratedRole, str] = {
            "risk": dc.risk_focus,
            "regime": dc.regime_focus,
            "theme": dc.theme_focus,
        }
        focus = (slice_map[curated_for] or "").strip()
        if focus:
            content += f"\n\n=== PLANNER-CURATED CONTEXT FOR {label} ANALYSIS ===\n\n{focus}"
    if news:
        content += f"\n\n{news_to_text(news)}"
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"
    return content
