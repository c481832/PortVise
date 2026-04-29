from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from port.agent_api_models import AgentLLMConfig, AgentReviewRequest, AgentReviewResult
from port.i18n import DEFAULT_LOCALE
from port.portfolio import Portfolio
from port.review_runner import run_review

mcp = FastMCP("Portfolio Advisor")


@mcp.tool()
async def run_portfolio_review(
    portfolio: Portfolio,
    locale: str = DEFAULT_LOCALE,
    corporate_actions: Literal["best_effort", "strict", "off"] = "best_effort",
    timeout_seconds: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Maximum seconds to wait for the review. Use 0 to disable the explicit "
                "runner timeout; this can run indefinitely."
            ),
        ),
    ] = 1800,
    llm: AgentLLMConfig | None = None,
) -> AgentReviewResult:
    """Run the portfolio review workflow and return the final structured review."""
    request = AgentReviewRequest(
        portfolio=portfolio,
        locale=locale,
        corporate_actions=corporate_actions,
        timeout_seconds=timeout_seconds,
        llm=llm,
    )
    result = await run_review(request)
    if result.status != "done":
        raise RuntimeError(result.error or f"Review finished with status: {result.status}")
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
