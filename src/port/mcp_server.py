from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from port.agent_api_models import AgentLLMConfig, AgentReviewRequest, AgentReviewResult
from port.i18n import DEFAULT_LOCALE
from port.portfolio import Portfolio
from port.review_runner import run_review

mcp = FastMCP("Portfolio Advisor")


def _progress_message(event: dict) -> str:
    label = str(event.get("label") or event.get("type") or "progress")
    agent = event.get("agent")
    if isinstance(agent, str) and agent:
        return f"{agent}: {label}"
    return label


async def _report_context_progress(ctx: Context, progress: float, message: str) -> None:
    await ctx.info(message)
    await ctx.report_progress(progress=progress, total=10.0, message=message)


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
    ctx: Context | None = None,
) -> AgentReviewResult:
    """Run the portfolio review workflow and return the final structured review."""
    request = AgentReviewRequest(
        portfolio=portfolio,
        locale=locale,
        corporate_actions=corporate_actions,
        timeout_seconds=timeout_seconds,
        llm=llm,
    )
    loop = asyncio.get_running_loop()
    progress_count = 0
    progress_futures: list[asyncio.Future] = []

    def _progress_callback(event: dict) -> None:
        if ctx is None:
            return
        nonlocal progress_count
        progress_count += 1
        future = asyncio.run_coroutine_threadsafe(
            _report_context_progress(
                ctx,
                min(float(progress_count), 10.0),
                _progress_message(event),
            ),
            loop,
        )
        progress_futures.append(asyncio.wrap_future(future))

    result = await run_review(
        request,
        progress_callback=_progress_callback if ctx is not None else None,
    )
    if progress_futures:
        await asyncio.gather(*progress_futures, return_exceptions=True)
    if result.status != "done":
        raise RuntimeError(result.error or f"Review finished with status: {result.status}")
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
