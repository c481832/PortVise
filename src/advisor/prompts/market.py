"""Format market data snapshots as prompt text."""

from __future__ import annotations

from advisor.schemas.market import MarketData


def market_data_to_text(md: MarketData) -> str:
    """Format a MarketData snapshot as compact text for injection into agent prompts."""
    lines = ["=== LIVE MARKET DATA ===", ""]

    if md.indicators:
        lines.append("MARKET INDICATORS:")
        for ind in md.indicators:
            lines.append(
                f"  {ind.label:<22} {ind.current:>9.2f}  "
                f"1d: {ind.change_1d_pct:+5.1f}%  1w: {ind.change_1w_pct:+5.1f}%  "
                f"1m: {ind.change_1m_pct:+5.1f}%  1y: {ind.change_1y_pct:+5.1f}%  "
                f"3m: {ind.change_3m_pct:+5.1f}%  "
                f"52w hi: {ind.week_52_high:.2f} ({ind.pct_from_52w_high:+.1f}%)"
            )
        lines.append("")

    if md.positions:
        lines.append("POSITION SNAPSHOTS:")
        for snap in md.positions:
            lines.append(
                f"  {snap.ticker:<6}  ${snap.current_price:>9.2f}  "
                f"1d: {snap.change_1d_pct:+5.1f}%  1w: {snap.change_1w_pct:+5.1f}%  "
                f"1m: {snap.change_1m_pct:+5.1f}%  1y: {snap.change_1y_pct:+5.1f}%  "
                f"3m: {snap.change_3m_pct:+5.1f}%  "
                f"52w hi: ${snap.week_52_high:.2f} ({snap.pct_from_52w_high:+.1f}%)"
            )
            lines.append(f"    dividend: {snap.dividend:.6g}  split: {snap.split:.6g}")
            lines.append("")

    lines.append(f"Data as of: {md.fetched_at}")
    return "\n".join(lines)
