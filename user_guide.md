# PortVise: a macro trader's guide

## The short version

PortVise is a portfolio review and decision-support system. Give it a live book, a cash balance,
a benchmark, and the reason each position is owned. It combines current market data, recent news,
historical risk analysis, and a rules-based macro regime read into one decision memo.

The easiest way to think about it is as a small investment committee operating from the same
snapshot:

- a news analyst surfaces what has changed around the book and each thesis;
- a macro strategist describes the current regime and finds similar historical setups;
- a risk officer identifies factor exposure, concentration, and historical stress losses;
- a thematic analyst tests whether the book's implicit narratives still have support;
- a capital allocator checks whether the portfolio is holding too much cash for its mandate; and
- a portfolio manager resolves conflicts and produces a prioritized action for every position.

PortVise does **not** place trades, optimize exact target weights, predict the next regime, or
replace a trader's judgment. Its job is to make the book's assumptions, failure modes, and next
decisions explicit.

## What goes into a review

The useful inputs are trading inputs, not technical settings:

| Input | Why it matters |
| --- | --- |
| Positions and quantities | Current prices convert these into live position and cash weights. |
| Cash balance | Determines gross capital deployment and the cost of staying defensive. |
| Benchmark | Used for the one-year cash opportunity-cost check and later call scoring. |
| Entry thesis for each line | Gives the review a falsifiable reason for ownership instead of treating every holding generically. |
| Portfolio context note | States the actual concern or decision at hand—for example, “Is AI capex rolling over?” or “How exposed is the book to another rates shock?” |
| Review date | Anchors the portfolio snapshot; the later call audit starts from the review's completion date. |

Prices and corporate actions are fetched through Yahoo Finance. PortVise
calculates weights from quantity and cash, and shows one-month and one-year moves before the
review starts.

A research planner turns the portfolio context into search priorities before the committee agents
run. PortVise also collects daily price history for the holdings, the benchmark, macro proxies, and
risk factors. The news evidence considered is visible in the review.

## News

The news agent surfaces what has changed around the book and each thesis. It is the market-
intelligence layer that every downstream agent receives as shared context.

A research planner first turns the portfolio context into three cross-book search topics and one
latest-news search for each position. The portfolio searches are deliberately macro or
cross-cutting—rates, dollar, growth, liquidity, credit, volatility—not duplicate single-name
searches. The news agent then runs those queries through the configured search provider (Tavily or
SearXNG), combines the retrieved items, and summarises only that evidence through the lens of the
portfolio goal and each position's entry thesis.

For example, given a context note like “Is AI capex rolling over?” and a book with NVDA, TLT, and
XLE, the planner might send:

| Source | Query |
| --- | --- |
| Planner — portfolio | AI data center capex spending outlook |
| Planner — portfolio | US rates and duration hedge after inflation data |
| Planner — portfolio | oil demand and energy equity flows |
| Planner — position | latest news for NVDA |
| Planner — position | latest news for TLT |
| Planner — position | latest news for XLE |

The three portfolio lines are free-form macro queries inferred from the context note and sector mix.
Each position line is fixed wording: `latest news for {TICKER}`.

The briefing covers:

- **macro context** — rates, USD, credit, equity vol, and central-bank posture;
- **market themes** — short labels for the dominant flow drivers;
- **key events** — recent developments tied to the book's tickers and sectors;
- **thesis risks** — names where recent events challenge the stated entry thesis; and
- a one-sentence summary.

Headlines and short excerpts can identify a question that deserves work; they are not a substitute
for primary-source diligence. The feed is only as complete and timely as the configured provider.

## Regime

The regime agent describes the current macro regime and finds similar historical setups. It answers:
how should this book behave in the current inflation/rates/growth/liquidity/volatility mix, and
how would today's weights have performed the last time the tape looked like this?

### The state vector

The regime is a five-part description:

1. **Inflation:** rising, stable, or cooling
2. **Rates:** rising, stable, or falling
3. **Growth:** accelerating, stable, or slowing
4. **Liquidity:** loose, neutral, or tight
5. **Volatility:** high or low

It is derived from one-month changes in liquid market proxies:

| Dimension | Proxies and current default logic |
| --- | --- |
| Rates | US 10-year yield index (`^TNX`); up or down outside a ±0.5% change band |
| Inflation | Average move in gold (`GLD`) and oil (`USO`); up or down outside a ±0.5% band |
| Growth | `SPY` and `EEM`; accelerating when SPY is above +0.5% and EEM is positive, slowing when either is below -0.5% |
| Liquidity | Tight when EEM lags SPY by more than 1 percentage point and financials (`XLF`) are down; loose when both EEM and XLF are positive |
| Volatility | High if VIX is at least 20, VIX rises more than 10%, oil moves at least ±6%, or EEM falls at least 3% |

These thresholds are configurable. They are best understood as a transparent market-state
classifier, not an economic nowcast. In particular, inflation is inferred from gold and oil rather
than CPI or breakevens, and the rates input uses the percentage move in the quoted 10-year yield
index rather than a basis-point change.

### Historical analogs

The analog engine compares today's 21-trading-day moves with past 21-day moves across six series:
10-year yields, SPY, EEM, gold, oil, and financials. It selects the three closest non-overlapping
setups and asks how the **current portfolio at current weights** would have performed over each
subsequent 21-trading-day window.

For those analogs, PortVise reports:

- the matched setup and forward window;
- the reconstructed portfolio return;
- maximum drawdown during the forward window;
- average return and win rate across the selected analogs; and
- the best and worst observed outcomes.

The useful question is not “Is this a backtest proving what happens next?” It is “When these
cross-asset moves previously resembled today's tape, where did this exact mix of exposures make or
lose money?” Three analogs are a scenario set, not a statistically meaningful forecast.

## Risk

The risk agent identifies factor exposure, concentration, and historical stress losses. It
answers: where does the book break? This lens focuses on factor loading, risk contribution,
correlated positions, concentration, and realized historical stress.

### Factor map

PortVise runs one joint regression of daily portfolio returns against:

- broad equity beta: `SPY`;
- growth relative to the market: `QQQ - SPY`;
- financials relative to the market: `XLF - SPY`;
- emerging markets relative to the market: `EEM - SPY`;
- long-duration Treasuries: `TLT`;
- gold: `GLD`;
- oil: `USO`; and
- the US dollar: `UUP`.

The output contains both beta and the signed share of portfolio variance attributable to each
factor. The remaining variance is labelled idiosyncratic. Because the factors are estimated
together and interact through covariance, a negative contribution means an exposure offset risk
elsewhere in the sample; it does not mean the factor is intrinsically safe.

Cash is respected through the actual portfolio weights. A 70%-invested book should show lower
portfolio volatility than the same risky assets normalized to 100%.

### Position-level risk

For each holding, PortVise shows:

- its signed percentage contribution to total portfolio variance;
- its contribution to annualized portfolio volatility; and
- in the risk narrative, its risk share relative to its share of invested capital.

This separates “large position” from “large risk.” A smaller high-beta line can carry more risk
than a larger defensive line. A negative risk contribution indicates that the holding historically
offset the rest of the book over the sample.

### Concentration and hidden concentration

The engine flags top-five concentration when the five largest names exceed 55% of total portfolio
value. It also identifies pairs whose daily-return correlation is at least 0.30 and reports their
combined portfolio weight. The thematic review adds a second form of concentration: different
tickers tied to the same economic or narrative outcome.

The correlation threshold is deliberately broad. Treat the pair list as a screening device, not a
claim that every flagged pair is one trade.

### Stress windows

The default historical windows are:

| Scenario | Window |
| --- | --- |
| COVID crash | 19 February–23 March 2020 |
| 2022 inflation shock | 3 January–14 October 2022 |
| 2023 regional-bank stress | 8–24 March 2023 |

PortVise compounds the covered holdings' historical daily returns at today's weights. If the
named windows are outside the available history, it falls back to the worst available two-week,
one-month, and one-quarter rolling windows.

## Theme

The theme agent tests whether the book's implicit narratives still have support. It answers:
what is the book implicitly betting on, are several positions expressing the same story, and does
recent evidence support or challenge the stated theses?

The theme review starts with the portfolio rather than a generic market narrative. For every
position, it describes the business model, revenue drivers, and candidate themes. It then rolls
those lines up into:

- dominant themes;
- redundant expressions of the same bet;
- missing exposures or hedges;
- narrative crowding;
- conflicts between the thesis and current momentum/news; and
- one sentence describing the book's implicit portfolio bet.

It uses the news briefing as evidence, but stays separate from risk and regime. A strong theme can
coexist with poor regime fit; a position can have a valid thesis and still dominate portfolio risk.

## Allocation

The allocation agent checks whether the portfolio is holding too much cash for its mandate. The
cash check prevents every uncertain review from ending with “raise cash.”

It asks two questions:

1. Is cash above the configured maximum?
2. Is the worst measured stress loss still inside the configured drawdown budget?

With the current default policy, at least 80% of capital should be invested, so cash should not
exceed 20%. If cash is above 20% and the stress loss is inside the 50% drawdown budget, the final
memo must include a way to deploy the excess into named current holdings. These are policy
defaults, not universal investing rules, and should be set to the mandate being reviewed.

Three figures drive the check:

- **Maximum cash:** one minus the configured minimum invested capital.
- **Required deployment:** cash weight minus maximum cash, floored at zero.
- **Historical cash opportunity cost:** current cash weight multiplied by the benchmark's trailing
  one-year return less the assumed cash yield.

The opportunity-cost number is explicitly backward-looking. It says what the existing cash weight
would have cost relative to the benchmark over the last year under the stated cash-yield
assumption; it does not forecast the next year's cost.

If the drawdown budget is breached, risk reduction takes priority. If that conflicts with the cash
ceiling, the memo must show the conflict rather than quietly forcing one answer.

## Manager

The manager agent resolves conflicts and produces a prioritized action for every position. The
final decision weighs six perspectives: downside risk, return potential, macro fit, thesis
integrity, portfolio construction, and the strongest case for doing nothing.

Risk is not allowed to veto a position merely because it is volatile. It has veto power for
severe concentration, unacceptable stress loss, broken hedge behavior, liquidity stress, or a
risk of permanent impairment. The cash-allocation rule has similar authority: if the book is too
defensive and remains inside its drawdown budget, the manager cannot casually recommend even more
cash.

The result includes:

- a portfolio-level posture and time horizon;
- the primary risk and a concrete revisit trigger;
- one action for every current holding;
- priority—today, this week, next review, or watch;
- qualitative size guidance;
- evidence supporting each action; and
- an honest “do nothing” case.

Actions can be **add, reduce, exit, hedge, rotate, monitor,** or **no action**. Sizing remains
qualitative because PortVise does not contain an optimizer or execution model.

## Feedback, saved reviews, and accountability

Reviews are saved locally. A trader can comment on a completed decision memo and ask the portfolio
manager to reconsider it. That feedback reruns only the final decision layer using the same risk,
regime, news, theme, and allocation evidence. It is useful for challenging judgment, but it does
not refresh the tape. Run a new full review when new market evidence matters.
