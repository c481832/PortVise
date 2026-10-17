"""Format the portfolio book as prompt text."""

from __future__ import annotations

from advisor.schemas.portfolio import Portfolio


def portfolio_to_text(portfolio: Portfolio) -> str:
    pos_sum = sum(p.quantity * p.current_price for p in portfolio.positions)
    cw = portfolio.cash_weight
    if cw <= 0:
        cash_line = f"Cash: $0 {portfolio.base_currency}"
    elif cw < 1.0:
        cash_usd = cw * float(pos_sum) / (1.0 - cw)
        cash_line = f"Cash: ${cash_usd:,.0f} {portfolio.base_currency}"
    else:
        cash_line = f"Cash: entire portfolio in {portfolio.base_currency} (no position MV to size)"
    lines = [
        f"PORTFOLIO: {portfolio.name}  |  Benchmark: {portfolio.benchmark}"
        f"  |  Date: {portfolio.review_date}",
        cash_line,
        "",
        "POSITIONS:",
    ]
    for p in portfolio.positions:
        pnl = p.pnl_pct
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"  {p.ticker:<6} | {p.weight * 100:5.1f}% | {p.sector:<20} | "
            f"Entry: {p.entry_date} @ ${p.entry_price:.2f}"
            f" → ${p.current_price:.2f} ({sign}{pnl:.1f}%)"
        )
        lines.append(f"         | Asset class: {p.asset_class}")
        lines.append(f'         | Thesis: "{p.entry_thesis}"')
        lines.append("")

    if portfolio.context_note:
        lines.append(f"CONTEXT: {portfolio.context_note}")

    return "\n".join(lines)
