//#region \0vite/modulepreload-polyfill.js
(function polyfill() {
	const relList = document.createElement("link").relList;
	if (relList && relList.supports && relList.supports("modulepreload")) return;
	for (const link of document.querySelectorAll("link[rel=\"modulepreload\"]")) processPreload(link);
	new MutationObserver((mutations) => {
		for (const mutation of mutations) {
			if (mutation.type !== "childList") continue;
			for (const node of mutation.addedNodes) if (node.tagName === "LINK" && node.rel === "modulepreload") processPreload(node);
		}
	}).observe(document, {
		childList: true,
		subtree: true
	});
	function getFetchOpts(link) {
		const fetchOpts = {};
		if (link.integrity) fetchOpts.integrity = link.integrity;
		if (link.referrerPolicy) fetchOpts.referrerPolicy = link.referrerPolicy;
		if (link.crossOrigin === "use-credentials") fetchOpts.credentials = "include";
		else if (link.crossOrigin === "anonymous") fetchOpts.credentials = "omit";
		else fetchOpts.credentials = "same-origin";
		return fetchOpts;
	}
	function processPreload(link) {
		if (link.ep) return;
		link.ep = true;
		const fetchOpts = getFetchOpts(link);
		fetch(link.href, fetchOpts);
	}
})();
//#endregion
//#region frontend/shared/api.js
async function readErrorDetail(response) {
	const body = await response.json().catch(() => ({}));
	if (!body.detail) return `HTTP ${response.status}`;
	return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
}
async function requestJson(url, options) {
	const response = await fetch(url, options);
	if (!response.ok) throw new Error(await readErrorDetail(response));
	return response.json();
}
function getJson(url) {
	return requestJson(url);
}
function postJson(url, payload) {
	return requestJson(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(payload)
	});
}
function deleteJson(url) {
	return requestJson(url, { method: "DELETE" });
}
//#endregion
//#region frontend/shared/csv.js
function parseCsvRows(text) {
	const rows = [];
	let row = [];
	let cell = "";
	let quoted = false;
	const endCell = () => {
		row.push(cell.trim());
		cell = "";
	};
	const endRow = () => {
		endCell();
		if (row.some(Boolean)) rows.push(row);
		row = [];
	};
	const body = text.replace(/^﻿/, "");
	for (let i = 0; i < body.length; i += 1) {
		const char = body[i];
		if (quoted) if (char === "\"" && body[i + 1] === "\"") {
			cell += "\"";
			i += 1;
		} else if (char === "\"") quoted = false;
		else cell += char;
		else if (char === "\"") quoted = true;
		else if (char === ",") endCell();
		else if (char === "\n") endRow();
		else if (char !== "\r") cell += char;
	}
	if (quoted) throw new Error("CSV file has an unclosed quoted field.");
	endRow();
	return rows;
}
//#endregion
//#region frontend/shared/format.js
var LOCALE = "en-US";
var HTML_ESCAPES = {
	"&": "&amp;",
	"<": "&lt;",
	">": "&gt;",
	"\"": "&quot;",
	"'": "&#39;"
};
function escapeHtml(value) {
	return String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}
function toFiniteNumber(value) {
	if (value == null) return null;
	const number = Number(value);
	return Number.isFinite(number) ? number : null;
}
function formatCurrency(value) {
	const number = toFiniteNumber(value);
	if (number == null) return "—";
	return new Intl.NumberFormat(LOCALE, {
		style: "currency",
		currency: "USD",
		maximumFractionDigits: 0
	}).format(number);
}
function formatPrice(value) {
	const number = toFiniteNumber(value);
	if (number == null) return "—";
	return new Intl.NumberFormat(LOCALE, {
		style: "currency",
		currency: "USD",
		minimumFractionDigits: 2,
		maximumFractionDigits: 2
	}).format(number);
}
function formatNumber(value, digits = 2, signed = false) {
	const number = toFiniteNumber(value);
	if (number == null) return "—";
	return `${number < 0 ? "-" : signed ? "+" : ""}${new Intl.NumberFormat(LOCALE, {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	}).format(Math.abs(number))}`;
}
function formatPercent(ratio, digits = 1, signed = false) {
	const number = toFiniteNumber(ratio);
	if (number == null) return "—";
	return `${formatNumber(number * 100, digits, signed)}%`;
}
function formatDateTime(value) {
	return new Intl.DateTimeFormat(LOCALE, {
		dateStyle: "medium",
		timeStyle: "short"
	}).format(new Date(value));
}
var copy_default = {
	page: { "title": "PortVise" },
	common: {
		"portfolio": "Portfolio",
		"durationSeconds": "{seconds}s",
		"durationMinutes": "{minutes}m",
		"durationMinutesSeconds": "{minutes}m {seconds}s"
	},
	ribbon: {
		"idle": "idle",
		"running": "running…",
		"done": "done",
		"error": "error",
		"etaRunning": "completed",
		"etaComplete": "completed",
		"etaError": "error"
	},
	status: {
		"idle": "Idle",
		"running": "Running",
		"waiting": "Waiting",
		"done": "Done",
		"stopped": "Stopped",
		"error": "Error",
		"failedWithReason": "Failed: {reason}"
	},
	sidebar: { "timeNotStarted": "Not started" },
	dataLoader: {
		"showDetails": "Show ticker status",
		"hideDetails": "Hide ticker status",
		"waitingToLoad": "Waiting to load market data.",
		"noTickerStatusYet": "No tickers queued yet.",
		"tickerQueued": "Queued",
		"tickerLoading": "Loading",
		"tickerLoaded": "Loaded",
		"tickerError": "Error",
		"retrying": "Retrying review and reloading history…",
		"starting": "Starting review and waiting for data loader…",
		"waitingForMarketData": "Waiting for market data agent to finish…",
		"loadingMarketData": "Loading historical and macro market data…",
		"marketDataLoaded": "Market data loaded successfully.",
		"reviewStopped": "Review stopped by user.",
		"missingAnalogHistory": "Missing analog-matching history for: {items}.",
		"missingHoldingsHistory": "Missing holdings history for: {items}."
	},
	buttons: {
		"runReviewBusy": "Review running",
		"stopReview": "Stop Review",
		"stopReviewStopping": "Stopping...",
		"refreshMarketData": "Refresh market data",
		"close": "Close"
	},
	summary: {
		"positionsSub": "Of total",
		"positionsSubCount": "{count} positions"
	},
	positions: {
		"metaNone": "No positions loaded",
		"metaLoaded": "{count} {positionLabel} loaded · {noteCount} {noteLabel}",
		"positionSingular": "position",
		"positionPlural": "positions",
		"noteSingular": "thesis note",
		"notePlural": "thesis notes",
		"row": {
			"tickerPlaceholder": "SYM",
			"namePlaceholder": "Name",
			"sectorPlaceholder": "Sector",
			"quantityPlaceholder": "0",
			"showAssertion": "Show or hide assertion",
			"removePosition": "Remove position",
			"yourAssertion": "Your assertion",
			"assertionPlaceholder": "Why you own this position…",
			"tickerTitle": "Ticker",
			"nameTitle": "Name",
			"weightTitle": "Weight % (computed automatically)",
			"sectorTitle": "Sector",
			"priceTitle": "Last fetched price",
			"quantityTitle": "Quantity",
			"valueTitle": "Position value",
			"month1Title": "1 month return",
			"year1Title": "1 year return",
			"assertionTitle": "Assertion"
		}
	},
	llm: {
		"modelLibraryEmpty": "No models yet. Add one below.",
		"removeModelTitle": "Remove from library",
		"removeModelAria": "Remove {name} from library",
		"modelMissingTag": "(not in library)",
		"useDefault": "Use default",
		"perAgentCountAllDefault": "all {total} use default",
		"perAgentCountOverrides": "{count} of {total} overridden",
		"saveStatus": {
			"loaded": "Loaded",
			"unsaved": "Unsaved changes",
			"saving": "Saving…",
			"saved": "Saved",
			"reset": "Reset to defaults",
			"error": "Could not save",
			"loadFailed": "Could not reload server config",
			"testing": "Testing",
			"connected": "Connected",
			"testFailed": "Test failed"
		},
		"agentHints": { "newsSummary": "summary" }
	},
	allocationConfig: { "maxCashHint": "This sets maximum cash to {maximum}." },
	history: {
		"countEmpty": "No saved reviews",
		"count": "{count} saved reviews",
		"previewFallback": "Open the saved decision memo.",
		"allocationBadge": "Invested {invested} / minimum {minimum}",
		"savedReviewLoadError": "Could not load saved review: {detail}"
	},
	pastFeedback: {
		"source": "From {portfolio} · {date}",
		"itemLabel": "Feedback {count}"
	},
	results: {
		"actionTiming": "Action timing",
		"primaryRisk": "Primary Risk",
		"rationale": "Rationale",
		"riskAddressed": "Risk addressed",
		"supportingEvidence": "Supporting evidence",
		"revisitTrigger": "Revisit trigger",
		"historicalRegimeAnalogs": "Historical Regime Analogs",
		"analogAvgReturn": "Avg return",
		"analogMaxDrawdown": "Max drawdown",
		"analogWinRate": "Win rate",
		"analogForwardWindow": "Forward window",
		"analogPortfolioReturn": "Portfolio return",
		"analogMatchScore": "Match",
		"showActionDetails": "Show action reasoning",
		"hideActionDetails": "Hide action reasoning",
		"allocation": {
			"valueVsMinimum": "{value} vs {minimum} minimum",
			"valueVsMaximum": "{value} vs {maximum} maximum",
			"deploymentRequired": "{value} of the portfolio required",
			"noDeployment": "No deployment required",
			"gateWithin": "Within budget",
			"gateBreached": "Budget breached",
			"gateUnavailable": "Unavailable",
			"unavailable": "Unavailable"
		},
		"columns": {
			"sizing": "Sizing",
			"hedge": "Hedge"
		},
		"noActions": "No position actions were returned. Check the do-nothing case or agent drawer for context.",
		"trackRecord": {
			"loading": "Scoring prior calls…",
			"none": "This review has no reduce, exit, or add calls to score.",
			"error": "Could not load track record:",
			"summary": "{validated} of {matured} matured calls validated · vs {benchmark} · since {date}",
			"columns": {
				"position": "Position",
				"call": "Call",
				"days": "Days",
				"daily": "Daily vs {benchmark}",
				"verdict": "Verdict"
			},
			"verdicts": {
				"validated": "Validated",
				"invalidated": "Wrong",
				"pending": "Pending"
			}
		}
	},
	share: {
		"topAction": "Top action",
		"noImmediateAction": "Monitor / no immediate action"
	},
	agentSummary: {
		"agentComplete": "{agent} complete",
		"dismiss": "Dismiss",
		"next": "Next"
	},
	review: {
		"startReviewError": "Could not start review: {detail}",
		"stopReviewError": "Could not stop review: {detail}",
		"addTickerFirst": "Add at least one position with a ticker.",
		"refreshQuotesAddPosition": "Add at least one position to refresh quotes.",
		"refreshQuotesEnterTicker": "Enter at least one ticker to refresh.",
		"marketDataRequired": "Refresh market data before running this review. Missing prices for: {tickers}.",
		"marketDataRefreshing": "Refreshing market data…",
		"marketDataRefreshed": "Market data refreshed from Yahoo Finance.",
		"sampleRestored": "Sample portfolio restored.",
		"sampleLoadError": "Could not load sample portfolio CSV (HTTP {status}).",
		"csvEmpty": "CSV file is empty.",
		"csvMissingTicker": "CSV file must include a ticker column.",
		"csvInvalidAssetClass": "CSV asset_class must be equity, bond, commodity, fx, or crypto. Found: {assetClass}.",
		"csvImported": "Loaded portfolio CSV: {filename}.",
		"csvSaved": "Portfolio CSV saved.",
		"resultLoadError": "Could not load the review result: {detail}"
	},
	agents: {
		"runTime": "Run time {duration}",
		"planner": {
			"label": "Planner",
			"steps": [
				"Prepare portfolio context",
				"Generate search queries",
				"Validate ticker coverage"
			]
		},
		"data": { "label": "Data" },
		"news": {
			"label": "News",
			"steps": [
				"Prepare planned searches",
				"Search news sources",
				"Combine search results",
				"Prepare briefing prompt",
				"Summarize briefing"
			]
		},
		"risk": {
			"label": "Risk",
			"steps": [
				"Prepare risk inputs",
				"Run factor/stress engine",
				"Build interpretation prompt",
				"Interpret risk findings",
				"Merge computed attribution"
			]
		},
		"regime": {
			"label": "Regime",
			"steps": [
				"Prepare regime inputs",
				"Run regime analog engine",
				"Build interpretation prompt",
				"Interpret regime fit",
				"Merge computed analogs"
			]
		},
		"theme": {
			"label": "Theme",
			"steps": [
				"Extract news evidence",
				"Map ticker evidence",
				"Synthesize theme review"
			]
		},
		"allocation": {
			"label": "Allocation",
			"steps": [
				"Compute allocation constraints",
				"Build allocation prompt",
				"Assess cash deployment options",
				"Merge allocation math"
			]
		},
		"manager": {
			"label": "Manager",
			"steps": [
				"Build decision packet",
				"Generate action plan",
				"Finalize decision memo"
			]
		}
	},
	agentOutput: {
		"news": {
			"macro": "Macro:",
			"themes": "Themes:",
			"keyEvents": "Key events:",
			"summary": "Summary:"
		},
		"risk": {
			"riskContribution": "Risk share by factor:",
			"riskContributionTicker": "Risk share by holding:",
			"volatilityContributionTicker": "Volatility contribution by holding (annualized):",
			"portfolioVolatility": "Portfolio volatility (annualized):",
			"cashAwareNote": "Risk shares are signed percentages of portfolio variance and sum to 100%; a negative share means that factor or holding hedges the rest of the book. Volatility figures use actual weights, so cash lowers them.",
			"topRisks": "Top risks:",
			"worstScenario": "Worst scenario:",
			"scenarios": "Scenarios:",
			"scenarioCashNote": "Scenario losses are portfolio-level estimates using actual position weights; cash is left uninvested, so it reduces the reported loss versus a fully-invested book.",
			"concentration": "Concentration:",
			"summary": "Summary:"
		},
		"regime": {
			"regime": "Regime:",
			"state": "State:",
			"stateVector": {
				"inflation": "infl",
				"shortRates": "short rates",
				"longRates": "long rates",
				"growth": "growth",
				"liquidity": "liq",
				"volatility": "vol"
			},
			"mismatchDrivers": "Mismatch drivers:",
			"summary": "Summary:"
		},
		"theme": {
			"implicitBet": "Implicit bet:",
			"dominant": "Dominant:",
			"summary": "Summary:"
		},
		"allocation": {
			"candidates": "Deployment candidates:",
			"conflicts": "Constraint conflicts:",
			"summary": "Summary:"
		}
	},
	agentAnalysis: {
		"empty": "No output available.",
		"feedback": {
			"title": "User feedback",
			"comment": "Feedback comment",
			"placeholder": "Add comments for the Manager to consider when revising the decision memo.",
			"submit": "Send feedback",
			"running": "Rerunning Manager with your feedback…",
			"runningButton": "Rerunning…",
			"history": "Feedback rounds",
			"latestTitle": "Latest revised decision",
			"updated": "Updated",
			"round": "Round {count}",
			"you": "You",
			"manager": "Manager",
			"complete": "Complete",
			"runningStatus": "Running",
			"actions": "Actions",
			"topActions": "Top actions",
			"actionCount": "{count} actions in revised memo",
			"investedCapital": "Invested capital",
			"cashPolicy": "Cash policy",
			"error": "Error",
			"saved": "Feedback saved and Manager rerun complete.",
			"emptyComment": "Enter feedback before sending."
		},
		"planner": {
			"portfolioGoal": "Portfolio goal",
			"macroTopics": "Macro topics"
		},
		"news": {
			"briefing": "Briefing",
			"thesisRisks": "Thesis risks",
			"consideredResearch": "News considered",
			"tickerSearches": "Ticker searches",
			"otherSearches": "Other searches",
			"unknownQuery": "Research block"
		},
		"risk": { "overview": "Risk overview" },
		"regime": { "overview": "Regime overview" },
		"theme": {
			"overview": "Theme overview",
			"drift": "Theme drift",
			"themeAssessments": "Theme assessments",
			"positionProfiles": "Position theme map",
			"crowdingMomentum": "Crowding and momentum",
			"redundantExposures": "Redundant exposures",
			"missingExposures": "Missing exposures",
			"businessModel": "Business model",
			"candidateThemes": "Candidate themes",
			"revenueDrivers": "Revenue drivers",
			"implication": "Portfolio implication",
			"evidence": "Evidence"
		},
		"allocation": {
			"overview": "Allocation overview",
			"policy": "Capital policy",
			"allocatedCapital": "Allocated capital",
			"minimumAllocated": "Minimum allocated capital",
			"cashWeight": "Cash weight",
			"maximumCash": "Maximum cash weight",
			"requiredDeployment": "Required deployment",
			"deploymentStatus": "Deployment status",
			"required": "Required",
			"notRequired": "Not required",
			"opportunityCost": "Historical opportunity cost",
			"benchmarkReturn": "Benchmark 1-year return",
			"cashYield": "Assumed annual cash yield",
			"cashOpportunityCost": "1-year cash opportunity cost",
			"drawdownGate": "Drawdown gate",
			"drawdownBudget": "Maximum drawdown budget",
			"worstScenarioLoss": "Worst scenario loss",
			"budgetStatus": "Budget status",
			"withinBudget": "Within budget",
			"breached": "Breached",
			"unavailable": "Unavailable"
		}
	},
	actionType: {
		"reduce": "Reduce",
		"exit": "Exit",
		"hedge": "Hedge",
		"rotate": "Rotate",
		"add": "Add",
		"monitor": "Monitor",
		"no-action": "No action"
	},
	actionScope: {
		"portfolio": "Portfolio",
		"position": "Position"
	},
	priority: {
		"urgent": "Urgent",
		"this-week": "This week",
		"next-review": "Next review",
		"watch": "Watch"
	},
	notifications: { "completedIn": "Portfolio review completed in {elapsed}." },
	stateValue: {
		"up": "up",
		"down": "down",
		"stable": "stable",
		"accelerating": "accelerating",
		"slowing": "slowing",
		"tight": "tight",
		"neutral": "neutral",
		"loose": "loose",
		"high": "high",
		"low": "low"
	}
};
//#endregion
//#region frontend/advisor/src/copy.js
function getPathValue(obj, key) {
	return String(key || "").split(".").reduce((acc, part) => acc && typeof acc === "object" ? acc[part] : void 0, obj);
}
function interpolate(template, vars = {}) {
	return String(template).replace(/\{(\w+)\}/g, (_, key) => {
		const value = vars[key];
		return value == null ? "" : String(value);
	});
}
function copy(key, vars = {}) {
	return interpolate(getPathValue(copy_default, key) ?? key, vars);
}
function copyList(key) {
	return getPathValue(copy_default, key);
}
//#endregion
//#region frontend/advisor/src/app.js
var SAMPLE_PORTFOLIO_CSV_URL = "/ui/sample_portfolio.csv";
var PORTFOLIO_CSV_COLUMNS = [
	"portfolio_name",
	"benchmark",
	"cash_usd",
	"review_date",
	"context_note",
	"ticker",
	"name",
	"sector",
	"asset_class",
	"quantity",
	"entry_thesis"
];
var POSITION_ASSET_CLASSES = [
	"equity",
	"bond",
	"commodity",
	"fx",
	"crypto"
];
var PIPELINE_AGENTS = [
	"data",
	"planner",
	"news",
	"risk",
	"regime",
	"theme",
	"allocation",
	"manager"
];
var CARD_STATES = [
	"running",
	"done",
	"error"
];
var ANALYSIS_TABS = [
	"planner",
	"news",
	"risk",
	"regime",
	"theme",
	"allocation",
	"feedback"
];
var MODAL_IDS = [
	"llm-config-modal",
	"history-modal",
	"past-feedback-modal",
	"results-modal",
	"agent-analysis-modal"
];
function todayLocalIso() {
	const now = /* @__PURE__ */ new Date();
	const offsetMs = now.getTimezoneOffset() * 60 * 1e3;
	return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}
function ensureReviewDate() {
	const input = document.getElementById("p-date");
	if (!input.value) input.value = todayLocalIso();
	return input.value;
}
var currentReviewId = null;
var eventSource = null;
var lastStartBody = null;
var currentResultsView = null;
var currentGlobalStatusState = "idle";
var returnToHistoryOnResultsClose = false;
var activeAgentAnalysisTab = "planner";
var feedbackRerunInFlight = false;
var pendingReviewStartBody = null;
var pendingFeedbackMatch = null;
var REVIEW_TIMER_TICK_MS = 1e3;
var agentStartTimes = {};
var agentEndTimes = {};
var agentTimerIds = {};
var agentStepProgress = {};
var agentSummaryQueue = [];
var activeAgentSummary = null;
var finalResultReviewId = null;
var quoteTimers = /* @__PURE__ */ new WeakMap();
var profileTimers = /* @__PURE__ */ new WeakMap();
var MAX_REVIEW_HISTORY = 30;
var DATA_LOADER_ERROR_RE = /(missing portfolio history for analog matching|missing price history for holdings|yfinance returned no data for analog matching|insufficient historical windows for analog matching)/i;
var STATUS_DETAIL_MAX_CHARS = 64;
var dataLoaderTickerStatus = /* @__PURE__ */ new Map();
var PRIORITY_ORDER = [
	"urgent",
	"this-week",
	"next-review",
	"watch"
];
var AGENT_MODEL_SLOTS = [
	{
		id: "planner",
		labelKey: "agents.planner.label"
	},
	{
		id: "news_summary",
		labelKey: "agents.news.label",
		hintKey: "llm.agentHints.newsSummary"
	},
	{
		id: "risk",
		labelKey: "agents.risk.label"
	},
	{
		id: "regime",
		labelKey: "agents.regime.label"
	},
	{
		id: "theme",
		labelKey: "agents.theme.label"
	},
	{
		id: "allocation",
		labelKey: "agents.allocation.label"
	},
	{
		id: "manager",
		labelKey: "agents.manager.label"
	}
];
function agentLabel(agent) {
	return copy(`agents.${agent}.label`);
}
function agentSteps(agent) {
	return copyList(`agents.${agent}.steps`);
}
function newStepProgress() {
	return {
		active: -1,
		done: /* @__PURE__ */ new Set(),
		labels: {}
	};
}
function cfgVal(id) {
	return document.getElementById(id).value.trim();
}
var modelLibrary = [];
var modelEndpointMap = {};
function rememberEndpointForSelectedModel() {
	const model = cfgVal("cfg-llm-model");
	const url = cfgVal("cfg-llm-base-url");
	if (model && url) modelEndpointMap[model] = url;
}
function applyEndpointForSelectedModel() {
	const url = modelEndpointMap[cfgVal("cfg-llm-model")];
	if (url) document.getElementById("cfg-llm-base-url").value = url;
}
function addModelToLibrary(name) {
	const text = name.trim();
	if (!text || modelLibrary.includes(text)) return false;
	modelLibrary = [...modelLibrary, text];
	const url = cfgVal("cfg-llm-base-url");
	if (url) modelEndpointMap[text] = url;
	renderModelLibrary();
	refreshModelSelectors();
	markModelConfigUnsaved();
	return true;
}
function removeModelFromLibrary(name) {
	modelLibrary = modelLibrary.filter((m) => m !== name);
	delete modelEndpointMap[name];
	renderModelLibrary();
	refreshModelSelectors();
	markModelConfigUnsaved();
}
function renderModelLibrary() {
	const ul = document.getElementById("llm-model-library");
	ul.innerHTML = "";
	if (!modelLibrary.length) {
		const empty = document.createElement("li");
		empty.className = "llm-model-library__empty muted-text";
		empty.textContent = copy("llm.modelLibraryEmpty");
		ul.appendChild(empty);
		return;
	}
	for (const name of modelLibrary) {
		const li = document.createElement("li");
		li.className = "llm-model-library__row";
		const span = document.createElement("span");
		span.className = "llm-model-library__name";
		const endpoint = modelEndpointMap[name];
		span.textContent = endpoint ? `${name} · ${endpoint}` : name;
		const btn = document.createElement("button");
		btn.type = "button";
		btn.className = "llm-model-library__remove";
		btn.setAttribute("aria-label", copy("llm.removeModelAria", { name }));
		btn.title = copy("llm.removeModelTitle");
		btn.textContent = "×";
		btn.addEventListener("click", () => removeModelFromLibrary(name));
		li.appendChild(span);
		li.appendChild(btn);
		ul.appendChild(li);
	}
}
function populateSelectFromLibrary(sel, currentValue, leadingOption) {
	sel.innerHTML = "";
	if (leadingOption) {
		const o = document.createElement("option");
		o.value = leadingOption.value;
		o.textContent = leadingOption.label;
		sel.appendChild(o);
	}
	for (const m of modelLibrary) {
		const o = document.createElement("option");
		o.value = m;
		o.textContent = m;
		sel.appendChild(o);
	}
	if (currentValue && !modelLibrary.includes(currentValue) && currentValue !== leadingOption?.value) {
		const o = document.createElement("option");
		o.value = currentValue;
		o.textContent = `${currentValue} ${copy("llm.modelMissingTag")}`;
		o.dataset.missing = "1";
		sel.appendChild(o);
	}
	sel.value = currentValue;
}
function useDefaultOption() {
	return {
		value: "",
		label: copy("llm.useDefault")
	};
}
function refreshModelSelectors() {
	const defaultSel = document.getElementById("cfg-llm-model");
	populateSelectFromLibrary(defaultSel, defaultSel.value, null);
	document.querySelectorAll("select.agent-model-select").forEach((sel) => {
		populateSelectFromLibrary(sel, sel.value, useDefaultOption());
	});
}
function renderAgentModelSelects(savedAgentModels) {
	const wrap = document.getElementById("llm-agent-model-rows");
	wrap.innerHTML = "";
	for (const slot of AGENT_MODEL_SLOTS) {
		const row = document.createElement("div");
		row.className = "cfg-field cfg-field--agent";
		const lab = document.createElement("label");
		lab.setAttribute("for", `cfg-agent-model-${slot.id}`);
		lab.appendChild(document.createTextNode(copy(slot.labelKey)));
		if (slot.hintKey) {
			const sp = document.createElement("span");
			sp.className = "cfg-agent-hint";
			sp.textContent = ` (${copy(slot.hintKey)})`;
			lab.appendChild(sp);
		}
		const sel = document.createElement("select");
		sel.className = "cfg-select agent-model-select";
		sel.id = `cfg-agent-model-${slot.id}`;
		sel.dataset.agentKey = slot.id;
		populateSelectFromLibrary(sel, savedAgentModels[slot.id] || "", useDefaultOption());
		sel.addEventListener("change", () => {
			markModelConfigUnsaved();
			updatePerAgentCount();
		});
		row.appendChild(lab);
		row.appendChild(sel);
		wrap.appendChild(row);
	}
	updatePerAgentCount();
}
function updatePerAgentCount() {
	const overrides = Object.keys(collectAgentModelOverrides()).length;
	document.getElementById("llm-per-agent-count").textContent = overrides ? copy("llm.perAgentCountOverrides", {
		count: overrides,
		total: AGENT_MODEL_SLOTS.length
	}) : copy("llm.perAgentCountAllDefault", { total: AGENT_MODEL_SLOTS.length });
}
function setModelSaveStatus(key, detail = "") {
	const el = document.getElementById("llm-save-status");
	el.dataset.status = key;
	const label = copy(`llm.saveStatus.${key}`);
	el.querySelector(".llm-save-status-text").textContent = detail ? `${label}: ${detail}` : label;
	el.title = detail || label;
}
function markModelConfigUnsaved() {
	setModelSaveStatus("unsaved");
}
function collectAgentModelOverrides() {
	const out = {};
	document.querySelectorAll("select.agent-model-select").forEach((sel) => {
		if (sel.value) out[sel.dataset.agentKey] = sel.value;
	});
	return out;
}
function buildLlmTestPayload() {
	const out = { agent_models: collectAgentModelOverrides() };
	const url = cfgVal("cfg-llm-base-url");
	if (url) out.llm_base_url = url;
	const key = cfgVal("cfg-llm-api-key");
	if (key) out.llm_api_key = key;
	const model = cfgVal("cfg-llm-model");
	if (model) out.llm_model = model;
	return out;
}
async function saveModelConfig() {
	setModelSaveStatus("saving");
	rememberEndpointForSelectedModel();
	const payload = {
		llm_base_url: cfgVal("cfg-llm-base-url"),
		llm_model: cfgVal("cfg-llm-model"),
		model_options: [...modelLibrary],
		model_base_urls: { ...modelEndpointMap },
		model_extra_args: cfgVal("cfg-model-extra-args"),
		agent_models: collectAgentModelOverrides(),
		search_provider: cfgVal("cfg-search-provider"),
		searxng_url: cfgVal("cfg-searxng-url"),
		min_allocated_capital: Number(cfgVal("cfg-min-allocated-capital")) / 100,
		max_drawdown: Number(cfgVal("cfg-max-drawdown")) / 100,
		cash_yield_annual_pct: Number(cfgVal("cfg-cash-yield"))
	};
	const apiKey = cfgVal("cfg-llm-api-key");
	if (apiKey) payload.llm_api_key = apiKey;
	const tavilyKey = cfgVal("cfg-tavily-key");
	if (tavilyKey) payload.tavily_api_key = tavilyKey;
	try {
		await postJson("/api/config", payload);
		clearSecretFields();
		await loadModelConfigUi("saved");
	} catch (err) {
		setModelSaveStatus("error", err.message);
	}
}
function clearSecretFields() {
	document.getElementById("cfg-llm-api-key").value = "";
	document.getElementById("cfg-tavily-key").value = "";
}
async function runConfigTest(url, payload) {
	setModelSaveStatus("testing");
	try {
		setModelSaveStatus("connected", (await postJson(url, payload)).message);
	} catch (err) {
		setModelSaveStatus("testFailed", err.message);
	}
}
function testModelConnection() {
	return runConfigTest("/api/config/test", buildLlmTestPayload());
}
function testSearchConnection() {
	const payload = {
		search_provider: cfgVal("cfg-search-provider"),
		searxng_url: cfgVal("cfg-searxng-url")
	};
	const tavilyKey = cfgVal("cfg-tavily-key");
	if (tavilyKey) payload.tavily_api_key = tavilyKey;
	return runConfigTest("/api/config/search/test", payload);
}
async function resetModelConfig() {
	setModelSaveStatus("saving");
	try {
		await deleteJson("/api/config");
		clearSecretFields();
		await loadModelConfigUi("reset");
	} catch (err) {
		setModelSaveStatus("error", err.message);
	}
}
function updateMaxCashHint() {
	const minimum = Number(cfgVal("cfg-min-allocated-capital"));
	setElementText("cfg-max-cash-hint", Number.isFinite(minimum) ? copy("allocationConfig.maxCashHint", { maximum: `${formatNumber(100 - minimum, 1)}%` }) : "");
}
async function loadModelConfigUi(statusKey = "loaded") {
	let server;
	try {
		server = await getJson("/api/config");
	} catch (err) {
		setModelSaveStatus("loadFailed", err.message);
		return;
	}
	modelLibrary = [...new Set([...server.model_options, server.llm_model].filter(Boolean))];
	modelEndpointMap = { ...server.model_base_urls };
	if (server.llm_model && server.llm_base_url && !modelEndpointMap[server.llm_model]) modelEndpointMap[server.llm_model] = server.llm_base_url;
	renderModelLibrary();
	populateSelectFromLibrary(document.getElementById("cfg-llm-model"), server.llm_model || modelLibrary[0] || "", null);
	renderAgentModelSelects(server.default_agent_models);
	document.getElementById("cfg-model-extra-args").value = server.model_extra_args;
	document.getElementById("cfg-llm-base-url").value = server.llm_base_url;
	document.getElementById("cfg-search-provider").value = server.search_provider;
	document.getElementById("cfg-searxng-url").value = server.searxng_url;
	document.getElementById("cfg-min-allocated-capital").value = formatNumber(server.min_allocated_capital * 100, 1);
	document.getElementById("cfg-max-drawdown").value = formatNumber(server.max_drawdown * 100, 1);
	document.getElementById("cfg-cash-yield").value = formatNumber(server.cash_yield_annual_pct, 2);
	updateMaxCashHint();
	setModelSaveStatus(statusKey);
}
function wireModelConfigControls() {
	[
		"cfg-llm-base-url",
		"cfg-llm-api-key",
		"cfg-model-extra-args",
		"cfg-searxng-url",
		"cfg-tavily-key",
		"cfg-min-allocated-capital",
		"cfg-max-drawdown",
		"cfg-cash-yield"
	].forEach((id) => document.getElementById(id).addEventListener("input", markModelConfigUnsaved));
	document.getElementById("cfg-min-allocated-capital").addEventListener("input", updateMaxCashHint);
	document.getElementById("cfg-llm-base-url").addEventListener("input", () => {
		rememberEndpointForSelectedModel();
		renderModelLibrary();
	});
	document.getElementById("cfg-llm-model").addEventListener("change", () => {
		applyEndpointForSelectedModel();
		markModelConfigUnsaved();
	});
	document.getElementById("cfg-search-provider").addEventListener("change", markModelConfigUnsaved);
	document.getElementById("llm-save-config").addEventListener("click", saveModelConfig);
	document.getElementById("llm-test-config").addEventListener("click", testModelConnection);
	document.getElementById("search-test-config").addEventListener("click", testSearchConnection);
	document.getElementById("llm-reset-config").addEventListener("click", resetModelConfig);
	const addInput = document.getElementById("cfg-add-model-input");
	document.getElementById("cfg-add-model-btn").addEventListener("click", () => {
		if (addModelToLibrary(addInput.value)) addInput.value = "";
	});
}
var reviewStartTime = null;
var reviewEndTime = null;
var reviewTimerId = null;
var currentActiveAgent = null;
function fmtDuration(totalSecs) {
	if (totalSecs < 60) return copy("common.durationSeconds", { seconds: totalSecs });
	const m = Math.floor(totalSecs / 60);
	const s = totalSecs % 60;
	if (s > 0) return copy("common.durationMinutesSeconds", {
		minutes: m,
		seconds: s
	});
	return copy("common.durationMinutes", { minutes: m });
}
function reviewElapsedSeconds() {
	return Math.max(0, Math.floor(((reviewEndTime || Date.now()) - reviewStartTime) / 1e3));
}
function renderReviewElapsed() {
	document.getElementById("review-elapsed-value").textContent = reviewStartTime ? fmtDuration(reviewElapsedSeconds()) : copy("sidebar.timeNotStarted");
}
function startReviewElapsedTimer() {
	clearInterval(reviewTimerId);
	reviewStartTime = Date.now();
	reviewEndTime = null;
	renderReviewElapsed();
	reviewTimerId = setInterval(renderReviewElapsed, REVIEW_TIMER_TICK_MS);
}
function stopReviewElapsedTimer() {
	if (!reviewStartTime) return;
	reviewEndTime = Date.now();
	clearInterval(reviewTimerId);
	reviewTimerId = null;
	renderReviewElapsed();
}
function clearReviewElapsedTimer() {
	clearInterval(reviewTimerId);
	reviewTimerId = null;
	reviewStartTime = null;
	reviewEndTime = null;
	renderReviewElapsed();
}
function finishReviewRun(state, detail = "") {
	stopReviewElapsedTimer();
	setGlobalStatus(state, detail);
	setButtonBusy(document.getElementById("start-btn"), false);
	setStopButtonRunning(false);
}
function reviewFailureDetail(message) {
	return isDataLoaderError(message) ? formatDataLoaderError(message) : message;
}
async function syncReviewSnapshot(reviewId) {
	const data = await getJson(`/api/review/${reviewId}/snapshot`);
	if (data.agent_outputs.data) setDataLoaderTickerResult(data.agent_outputs.data);
	if (data.status === "stopped") {
		finishReviewRun("stopped");
		setDataLoaderStatus("idle", copy("dataLoader.reviewStopped"));
	} else if (data.status === "done") {
		finishReviewRun("done");
		await renderFinalResultOnce(reviewId);
	} else if (data.status === "error") {
		const { message, agent } = data.last_error;
		const failureDetail = reviewFailureDetail(message);
		finishReviewRun("error", failureDetail);
		const failedAgent = agent || currentActiveAgent;
		if (failedAgent) setCardState(failedAgent, "error", failureDetail);
		setDataLoaderStatus("error", failureDetail, isDataLoaderError(message));
	}
	return data;
}
function showToast(message, isError = false, duration = 5200) {
	document.querySelector(".toast")?.remove();
	document.querySelector(".toast-overlay")?.remove();
	const toastEl = document.createElement("div");
	toastEl.className = `toast${isError ? " error" : ""}`;
	toastEl.setAttribute("role", isError ? "alertdialog" : "alert");
	if (isError) toastEl.setAttribute("aria-modal", "true");
	function fadeOutAndRemove() {
		const overlayEl = document.querySelector(".toast-overlay");
		if (overlayEl) {
			overlayEl.style.opacity = "0";
			overlayEl.style.transition = "opacity 0.3s";
		}
		toastEl.style.opacity = "0";
		toastEl.style.transition = "opacity 0.3s";
		setTimeout(() => {
			toastEl.remove();
			if (overlayEl) overlayEl.remove();
		}, 320);
	}
	if (isError) {
		const overlay = document.createElement("div");
		overlay.className = "toast-overlay";
		document.body.appendChild(overlay);
		const msgEl = document.createElement("span");
		msgEl.className = "toast-msg";
		msgEl.textContent = message;
		const dismiss = document.createElement("button");
		dismiss.type = "button";
		dismiss.className = "toast-dismiss";
		dismiss.setAttribute("aria-label", copy("buttons.close"));
		dismiss.textContent = "×";
		dismiss.addEventListener("click", fadeOutAndRemove);
		toastEl.appendChild(msgEl);
		toastEl.appendChild(dismiss);
		requestAnimationFrame(() => dismiss.focus());
	} else {
		toastEl.textContent = message;
		setTimeout(fadeOutAndRemove, duration);
	}
	document.body.appendChild(toastEl);
}
var DATA_LOADER_TICKER_LABEL_KEYS = {
	queued: "dataLoader.tickerQueued",
	loading: "dataLoader.tickerLoading",
	loaded: "dataLoader.tickerLoaded",
	error: "dataLoader.tickerError"
};
function initializeDataLoaderTickerStatus(positions) {
	dataLoaderTickerStatus.clear();
	for (const position of positions) dataLoaderTickerStatus.set(position.ticker, "queued");
	renderDataLoaderHistory();
}
function setAllDataLoaderTickers(state) {
	for (const ticker of dataLoaderTickerStatus.keys()) dataLoaderTickerStatus.set(ticker, state);
	renderDataLoaderHistory();
}
function setDataLoaderTickerResult(output) {
	for (const { ticker } of output.market_data.positions) if (dataLoaderTickerStatus.has(ticker)) dataLoaderTickerStatus.set(ticker, "loaded");
	renderDataLoaderHistory();
}
function renderDataLoaderHistory() {
	const list = document.getElementById("data-loader-history");
	if (dataLoaderTickerStatus.size === 0) {
		list.innerHTML = `<li class="data-loader-empty">${escapeHtml(copy("dataLoader.noTickerStatusYet"))}</li>`;
		return;
	}
	list.innerHTML = Array.from(dataLoaderTickerStatus.entries()).map(([ticker, state]) => `
      <li>
        <span class="data-loader-ticker-symbol">${escapeHtml(ticker)}</span>
        <span class="data-loader-ticker-state data-loader-ticker-state-${state}">${escapeHtml(copy(DATA_LOADER_TICKER_LABEL_KEYS[state]))}</span>
      </li>`).join("");
}
function setDataLoaderExpanded(expanded) {
	const toggle = document.getElementById("card-data");
	toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
	toggle.setAttribute("title", expanded ? copy("dataLoader.hideDetails") : copy("dataLoader.showDetails"));
	document.getElementById("data-loader-expanded").classList.toggle("hidden", !expanded);
	if (expanded) renderDataLoaderHistory();
}
function toggleDataLoaderExpanded() {
	setDataLoaderExpanded(!(document.getElementById("card-data").getAttribute("aria-expanded") === "true"));
}
function setDataLoaderStatus(state, detail, allowRetry = false) {
	setCardState("data", state, state === "error" ? detail : "");
	const badge = document.getElementById("data-loader-status");
	badge.textContent = copy(`status.${state}`);
	badge.title = detail;
	document.getElementById("data-loader-detail").textContent = detail;
	const retryBtn = document.getElementById("retry-review-btn");
	retryBtn.classList.toggle("hidden", !allowRetry);
	retryBtn.disabled = !allowRetry;
}
function isDataLoaderError(message) {
	return DATA_LOADER_ERROR_RE.test(message);
}
function formatDataLoaderError(message) {
	const text = message.trim();
	const analogMissing = text.match(/missing portfolio history for analog matching:\s*(.+)$/i);
	if (analogMissing) return copy("dataLoader.missingAnalogHistory", { items: analogMissing[1] });
	const holdingsMissing = text.match(/missing price history for holdings:\s*(.+)$/i);
	if (holdingsMissing) return copy("dataLoader.missingHoldingsHistory", { items: holdingsMissing[1] });
	return text;
}
function compactStatusDetail(message) {
	const text = message.replace(/\s+/g, " ").trim();
	if (text.length <= STATUS_DETAIL_MAX_CHARS) return text;
	return `${text.slice(0, STATUS_DETAIL_MAX_CHARS - 1)}…`;
}
async function retryLastReview() {
	await runReviewWithBody(structuredClone(lastStartBody), { fromRetry: true });
}
function truncateText(value, limit = 140) {
	const text = value.trim();
	return text.length > limit ? `${text.slice(0, limit)}...` : text;
}
function setButtonBusy(btn, busy, busyLabel) {
	if (!btn.dataset.labelIdle) btn.dataset.labelIdle = btn.textContent.trim();
	btn.disabled = busy;
	btn.toggleAttribute("aria-busy", busy);
	btn.textContent = busy ? busyLabel : btn.dataset.labelIdle;
}
function setStopButtonRunning(running) {
	const stopBtn = document.getElementById("stop-btn");
	stopBtn.disabled = !running;
	stopBtn.removeAttribute("aria-busy");
	stopBtn.textContent = copy("buttons.stopReview");
}
function positionRows() {
	return Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
}
function fieldValue(wrap, field) {
	return wrap.querySelector(`[data-field="${field}"]`).value.trim();
}
function getLastPrice(wrap) {
	return parseFloat(wrap.querySelector("[data-ro=\"price\"]").dataset.lastPrice);
}
function getQuoteAction(wrap, key, fallback) {
	const v = parseFloat(wrap.querySelector("[data-ro=\"price\"]").dataset[key]);
	return Number.isNaN(v) ? fallback : v;
}
function getCashDollarsInput() {
	const v = parseFloat(document.getElementById("p-cash").value);
	if (Number.isNaN(v) || v < 0) return 0;
	return v;
}
function getPositionMarketValue(wrap) {
	const q = parseFloat(fieldValue(wrap, "quantity"));
	const cur = getLastPrice(wrap);
	return !Number.isNaN(q) && !Number.isNaN(cur) ? q * cur : 0;
}
function refreshMetrics(wrap) {
	const value = getPositionMarketValue(wrap);
	const valEl = wrap.querySelector("[data-ro=\"value\"]");
	valEl.textContent = value ? formatCurrency(value) : "—";
	valEl.classList.toggle("muted", !value);
}
function scheduleQuoteFetch(wrap) {
	clearTimeout(quoteTimers.get(wrap));
	quoteTimers.set(wrap, setTimeout(() => fetchQuoteForCard(wrap), 420));
}
function scheduleProfileFetch(wrap) {
	clearTimeout(profileTimers.get(wrap));
	profileTimers.set(wrap, setTimeout(() => fetchProfileForCard(wrap), 420));
}
async function fetchProfileForCard(wrap) {
	const nameInput = wrap.querySelector("[data-field=\"name\"]");
	const sectorInput = wrap.querySelector("[data-field=\"sector\"]");
	const ticker = fieldValue(wrap, "ticker").toUpperCase();
	if (!ticker || nameInput.value.trim() && sectorInput.value.trim()) return;
	wrap.dataset.profileTicker = ticker;
	const res = await fetch(`/api/market/profile/${encodeURIComponent(ticker)}`);
	if (!res.ok) return;
	const profile = await res.json();
	if (fieldValue(wrap, "ticker").toUpperCase() !== ticker || wrap.dataset.profileTicker !== ticker) return;
	if (!nameInput.value.trim()) nameInput.value = profile.name;
	if (!sectorInput.value.trim()) sectorInput.value = profile.sector;
}
function setQuoteCells(wrap, text) {
	const priceEl = wrap.querySelector("[data-ro=\"price\"]");
	delete priceEl.dataset.lastPrice;
	delete priceEl.dataset.dividend;
	delete priceEl.dataset.split;
	for (const el of [
		priceEl,
		wrap.querySelector("[data-ro=\"ret-1m\"]"),
		wrap.querySelector("[data-ro=\"ret-1y\"]")
	]) {
		el.textContent = text;
		el.classList.remove("positive", "negative");
		el.classList.add("muted");
	}
}
function setReturnCell(el, pct) {
	el.textContent = pct == null ? "—" : `${formatNumber(pct, 1, true)}%`;
	el.classList.toggle("positive", pct > 0);
	el.classList.toggle("negative", pct < 0);
	el.classList.remove("muted");
}
async function fetchQuoteForCard(wrap) {
	const ticker = fieldValue(wrap, "ticker").toUpperCase();
	if (!ticker) {
		wrap.dataset.quoteState = "idle";
		setQuoteCells(wrap, "—");
		refreshMetrics(wrap);
		return;
	}
	wrap.dataset.quoteState = "loading";
	setQuoteCells(wrap, "…");
	const params = new URLSearchParams({ actions_start: ensureReviewDate() });
	const res = await fetch(`/api/market/quote/${encodeURIComponent(ticker)}?${params}`);
	if (!res.ok) {
		wrap.dataset.quoteState = "error";
		setQuoteCells(wrap, "—");
	} else {
		const quote = await res.json();
		const priceEl = wrap.querySelector("[data-ro=\"price\"]");
		priceEl.dataset.lastPrice = String(quote.current_price);
		priceEl.dataset.dividend = String(quote.dividend);
		priceEl.dataset.split = String(quote.split);
		priceEl.textContent = formatPrice(quote.current_price);
		priceEl.classList.remove("muted");
		setReturnCell(wrap.querySelector("[data-ro=\"ret-1m\"]"), quote.change_1m_pct);
		setReturnCell(wrap.querySelector("[data-ro=\"ret-1y\"]"), quote.change_1y_pct);
		wrap.dataset.quoteState = "ready";
	}
	refreshMetrics(wrap);
	updateWeightSummary();
}
async function refreshAllQuotes() {
	const btn = document.getElementById("refresh-quotes-btn");
	const wraps = positionRows();
	if (wraps.length === 0) {
		showToast(copy("review.refreshQuotesAddPosition"), true);
		return;
	}
	if (!wraps.some((w) => fieldValue(w, "ticker"))) {
		showToast(copy("review.refreshQuotesEnterTicker"), true);
		return;
	}
	setButtonBusy(btn, true, copy("buttons.refreshMarketData"));
	try {
		await Promise.all(wraps.map((w) => fetchQuoteForCard(w)));
		showToast(copy("review.marketDataRefreshed"));
	} finally {
		setButtonBusy(btn, false);
		refreshPositionsState();
	}
}
function positionRowsMissingReadyQuotes() {
	return positionRows().filter((wrap) => {
		if (!fieldValue(wrap, "ticker")) return false;
		const quantity = parseFloat(fieldValue(wrap, "quantity"));
		if (Number.isNaN(quantity) || quantity <= 0) return false;
		return Number.isNaN(getLastPrice(wrap));
	});
}
async function refreshMissingQuotesForReview() {
	const startBtn = document.getElementById("start-btn");
	setButtonBusy(startBtn, true, copy("buttons.refreshMarketData"));
	try {
		showToast(copy("review.marketDataRefreshing"));
		await Promise.all(positionRowsMissingReadyQuotes().map((wrap) => fetchQuoteForCard(wrap)));
	} finally {
		setButtonBusy(startBtn, false);
		refreshPositionsState();
	}
	return positionRowsMissingReadyQuotes().map((wrap) => fieldValue(wrap, "ticker").toUpperCase());
}
function refreshPositionsState() {
	const rows = positionRows();
	const total = rows.length;
	const noteCount = rows.filter((wrap) => fieldValue(wrap, "entry_thesis")).length;
	const meta = document.getElementById("positions-meta");
	if (total === 0) meta.textContent = copy("positions.metaNone");
	else meta.textContent = copy("positions.metaLoaded", {
		count: total,
		noteCount,
		positionLabel: total === 1 ? copy("positions.positionSingular") : copy("positions.positionPlural"),
		noteLabel: noteCount === 1 ? copy("positions.noteSingular") : copy("positions.notePlural")
	});
	document.getElementById("positions-empty-state").classList.toggle("hidden", total !== 0);
	document.getElementById("meta-positions").textContent = String(total);
	document.getElementById("meta-notes").textContent = String(noteCount);
	document.getElementById("weight-positions-sub").textContent = total ? copy("summary.positionsSubCount", { count: total }) : copy("summary.positionsSub");
	const refreshBtn = document.getElementById("refresh-quotes-btn");
	if (!refreshBtn.hasAttribute("aria-busy")) refreshBtn.disabled = total === 0;
}
function updateWeightSummary() {
	const rows = positionRows();
	const cashD = getCashDollarsInput();
	const nav = rows.reduce((sum, wrap) => sum + getPositionMarketValue(wrap), 0) + cashD;
	let investedWeight = 0;
	for (const wrap of rows) {
		const wEl = wrap.querySelector("[data-ro=\"weight\"]");
		const weight = nav > 0 ? getPositionMarketValue(wrap) / nav : 0;
		wEl.textContent = formatPercent(weight, 1);
		wEl.classList.toggle("muted", nav <= 0);
		investedWeight += weight;
	}
	const investedText = formatPercent(investedWeight, 1);
	document.getElementById("weight-positions").textContent = investedText;
	document.getElementById("meta-invested").textContent = investedText;
	document.getElementById("weight-cash").textContent = formatCurrency(cashD);
	document.getElementById("weight-total").textContent = formatCurrency(nav);
	refreshPositionsState();
}
function wirePositionRow(wrap) {
	wrap.querySelector("[data-field=\"quantity\"]").addEventListener("input", () => refreshMetrics(wrap));
	const tickerEl = wrap.querySelector("[data-field=\"ticker\"]");
	tickerEl.addEventListener("blur", () => {
		fetchProfileForCard(wrap);
		fetchQuoteForCard(wrap);
	});
	tickerEl.addEventListener("input", () => {
		scheduleProfileFetch(wrap);
		scheduleQuoteFetch(wrap);
	});
	const toggle = wrap.querySelector(".btn-assert-toggle");
	const panel = wrap.querySelector(".position-assertion-panel");
	toggle.addEventListener("click", () => {
		const open = panel.classList.contains("hidden");
		panel.classList.toggle("hidden", !open);
		wrap.classList.toggle("is-open", open);
		toggle.setAttribute("aria-expanded", open ? "true" : "false");
		toggle.textContent = open ? "▾" : "▸";
	});
	wrap.querySelector(".delete-btn").addEventListener("click", () => {
		wrap.remove();
		updateWeightSummary();
	});
	refreshMetrics(wrap);
}
function wireAgentCardInteractions(card, agent) {
	const header = card.querySelector(".card-header");
	header.setAttribute("role", "button");
	header.setAttribute("tabindex", "0");
	header.setAttribute("aria-expanded", card.classList.contains("steps-open") ? "true" : "false");
	header.setAttribute("aria-controls", `card-${agent}-steps`);
	header.onclick = () => toggleAgentStepStatus(agent);
}
function startApp() {
	const click = (id, handler) => document.getElementById(id).addEventListener("click", handler);
	click("add-position-btn", () => addRow());
	click("empty-add-position-btn", () => addRow());
	click("restore-sample-btn", restoreDefaultPositions);
	click("save-portfolio-btn", savePortfolioCsv);
	click("refresh-quotes-btn", refreshAllQuotes);
	click("start-btn", startReview);
	click("stop-btn", stopReview);
	click("retry-review-btn", retryLastReview);
	click("open-review-history", showHistoryModal);
	click("open-llm-config", () => showModal("llm-config-modal", "llm-config-modal-close"));
	click("llm-config-modal-close", () => hideModal("llm-config-modal"));
	click("llm-config-modal-backdrop", () => hideModal("llm-config-modal"));
	click("history-modal-close", () => hideModal("history-modal"));
	click("history-modal-backdrop", () => hideModal("history-modal"));
	click("past-feedback-modal-close", hidePastFeedbackModal);
	click("past-feedback-modal-backdrop", hidePastFeedbackModal);
	click("past-feedback-skip", runPendingReviewWithoutFeedback);
	click("past-feedback-include", runPendingReviewWithFeedback);
	click("results-modal-close", hideResultsModal);
	click("results-modal-backdrop", hideResultsModal);
	click("open-agent-analysis", showAgentAnalysisModal);
	click("load-track-record", loadTrackRecord);
	click("agent-analysis-modal-close", () => hideModal("agent-analysis-modal"));
	click("agent-analysis-modal-backdrop", () => hideModal("agent-analysis-modal"));
	click("agent-summary-dismiss", dismissAgentSummary);
	click("agent-summary-close", dismissAgentSummary);
	click("card-data", (e) => {
		if (!e.target.closest("button")) toggleDataLoaderExpanded();
	});
	document.getElementById("portfolio-csv-input").addEventListener("change", handlePortfolioCsvImport);
	document.getElementById("p-cash").addEventListener("input", updateWeightSummary);
	const positionsBody = document.getElementById("positions-body");
	positionsBody.addEventListener("input", updateWeightSummary);
	positionsBody.addEventListener("change", updateWeightSummary);
	wireAgentAnalysisControls();
	wireModelConfigControls();
	document.querySelectorAll(".agent-card:not([data-agent='data'])").forEach((card) => {
		wireAgentCardInteractions(card, card.dataset.agent);
	});
	document.querySelectorAll(".ribbon-node").forEach((node) => {
		node.addEventListener("click", () => document.querySelector(`#card-${node.dataset.agent} .card-header`).click());
	});
	renderReviewElapsed();
	setDataLoaderExpanded(false);
	renderDataLoaderHistory();
	setDataLoaderStatus("idle", copy("dataLoader.waitingToLoad"));
	updateWeightSummary();
	loadModelConfigUi();
	loadSamplePortfolio({ silent: true }).catch((err) => showToast(err.message, true));
}
function addRow(data = {}) {
	const grid = document.getElementById("positions-body");
	const wrap = document.createElement("div");
	wrap.className = "position-row-wrap";
	wrap.dataset.quoteState = "idle";
	const tickerValue = escapeHtml(data.ticker);
	const n = escapeHtml(data.name);
	const qty = escapeHtml(data.quantity);
	const s = escapeHtml(data.sector);
	const thesis = escapeHtml(data.entry_thesis);
	wrap.innerHTML = `
    <div class="position-row">
      <button type="button" class="btn-assert-toggle" aria-expanded="false" aria-label="${escapeHtml(copy("positions.row.showAssertion"))}" title="${escapeHtml(copy("positions.row.assertionTitle"))}">▸</button>
      <input type="text" data-field="ticker" class="pc-ticker" value="${tickerValue}" placeholder="${escapeHtml(copy("positions.row.tickerPlaceholder"))}" autocomplete="off" title="${escapeHtml(copy("positions.row.tickerTitle"))}" />
      <input type="text" data-field="name" value="${n}" placeholder="${escapeHtml(copy("positions.row.namePlaceholder"))}" title="${escapeHtml(copy("positions.row.nameTitle"))}" />
      <span data-ro="weight" class="row-metric muted" title="${escapeHtml(copy("positions.row.weightTitle"))}">0.0%</span>
      <input type="text" data-field="sector" value="${s}" placeholder="${escapeHtml(copy("positions.row.sectorPlaceholder"))}" title="${escapeHtml(copy("positions.row.sectorTitle"))}" />
      <span data-ro="price" class="row-metric muted" title="${escapeHtml(copy("positions.row.priceTitle"))}">—</span>
      <input type="number" data-field="quantity" step="0.0001" value="${qty}" placeholder="${escapeHtml(copy("positions.row.quantityPlaceholder"))}" title="${escapeHtml(copy("positions.row.quantityTitle"))}" />
      <span data-ro="value" class="row-metric muted" title="${escapeHtml(copy("positions.row.valueTitle"))}">—</span>
      <span data-ro="ret-1m" class="row-metric muted" title="${escapeHtml(copy("positions.row.month1Title"))}">—</span>
      <span data-ro="ret-1y" class="row-metric muted" title="${escapeHtml(copy("positions.row.year1Title"))}">—</span>
      <button type="button" class="delete-btn" aria-label="${escapeHtml(copy("positions.row.removePosition"))}">✕</button>
    </div>
    <div class="position-assertion-panel hidden">
      <div class="assertion-inner">
        <span class="assertion-label">${copy("positions.row.yourAssertion")}</span>
        <textarea data-field="entry_thesis" rows="3" placeholder="${escapeHtml(copy("positions.row.assertionPlaceholder"))}">${thesis}</textarea>
      </div>
    </div>
  `;
	grid.appendChild(wrap);
	wirePositionRow(wrap);
	fetchProfileForCard(wrap);
	updateWeightSummary();
}
function parsePortfolioCsv(text) {
	const rows = parseCsvRows(text);
	if (rows.length === 0) throw new Error(copy("review.csvEmpty"));
	const headers = rows[0].map((value) => value.toLowerCase());
	if (headers.indexOf("ticker") === -1) throw new Error(copy("review.csvMissingTicker"));
	const objects = rows.slice(1).map((cells) => {
		const obj = {};
		headers.forEach((header, index) => {
			if (!header) return;
			obj[header] = cells[index] || "";
		});
		return obj;
	});
	const first = objects[0] || {};
	const positions = objects.filter((row) => row.ticker).map((row) => {
		const assetClass = row.asset_class || "equity";
		if (!POSITION_ASSET_CLASSES.includes(assetClass)) throw new Error(copy("review.csvInvalidAssetClass", { assetClass }));
		return {
			ticker: row.ticker,
			name: row.name || "",
			sector: row.sector || "",
			asset_class: assetClass,
			quantity: row.quantity || "",
			entry_thesis: row.entry_thesis || ""
		};
	});
	return {
		meta: {
			name: first.portfolio_name || "",
			benchmark: first.benchmark || "",
			cash_usd: first.cash_usd || "0",
			review_date: first.review_date || "",
			context_note: first.context_note || ""
		},
		positions
	};
}
function applyPortfolioCsv(text) {
	const { meta, positions } = parsePortfolioCsv(text);
	document.getElementById("p-name").value = meta.name;
	document.getElementById("p-benchmark").value = meta.benchmark;
	document.getElementById("p-cash").value = meta.cash_usd;
	document.getElementById("p-date").value = meta.review_date || todayLocalIso();
	document.getElementById("p-context").value = meta.context_note;
	document.getElementById("positions-body").innerHTML = "";
	positions.forEach(addRow);
	updateWeightSummary();
	positionRows().forEach(fetchQuoteForCard);
}
async function loadSamplePortfolio({ silent = false } = {}) {
	const res = await fetch(SAMPLE_PORTFOLIO_CSV_URL);
	if (!res.ok) throw new Error(copy("review.sampleLoadError", { status: res.status }));
	applyPortfolioCsv(await res.text());
	if (!silent) showToast(copy("review.sampleRestored"));
}
async function restoreDefaultPositions() {
	try {
		await loadSamplePortfolio();
	} catch (err) {
		showToast(err.message, true);
	}
}
async function handlePortfolioCsvImport(event) {
	const input = event.target;
	const file = input.files[0];
	if (!file) return;
	try {
		applyPortfolioCsv(await file.text());
		showToast(copy("review.csvImported", { filename: file.name }));
	} catch (err) {
		showToast(err.message, true);
	} finally {
		input.value = "";
	}
}
function csvEscape(value) {
	const text = String(value ?? "");
	if (/[",\n\r]/.test(text)) return `"${text.replaceAll("\"", "\"\"")}"`;
	return text;
}
function portfolioCsvFromForm() {
	const meta = {
		portfolio_name: document.getElementById("p-name").value.trim(),
		benchmark: document.getElementById("p-benchmark").value.trim(),
		cash_usd: document.getElementById("p-cash").value.trim(),
		review_date: document.getElementById("p-date").value,
		context_note: document.getElementById("p-context").value.trim()
	};
	const rows = positionRows().map((wrap) => ({
		...meta,
		ticker: fieldValue(wrap, "ticker").toUpperCase(),
		name: fieldValue(wrap, "name"),
		sector: fieldValue(wrap, "sector"),
		asset_class: "equity",
		quantity: fieldValue(wrap, "quantity"),
		entry_thesis: fieldValue(wrap, "entry_thesis")
	}));
	if (rows.length === 0) rows.push({
		...meta,
		ticker: "",
		name: "",
		sector: "",
		asset_class: "",
		quantity: "",
		entry_thesis: ""
	});
	return [PORTFOLIO_CSV_COLUMNS.join(","), ...rows.map((row) => PORTFOLIO_CSV_COLUMNS.map((column) => csvEscape(row[column])).join(","))].join("\n") + "\n";
}
function portfolioCsvFilename() {
	return `${(document.getElementById("p-name").value.trim() || "portfolio").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "portfolio"}-${(/* @__PURE__ */ new Date()).toISOString().slice(0, 10)}.csv`;
}
function savePortfolioCsv() {
	const blob = new Blob([portfolioCsvFromForm()], { type: "text/csv;charset=utf-8" });
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = portfolioCsvFilename();
	document.body.appendChild(link);
	link.click();
	link.remove();
	URL.revokeObjectURL(url);
	showToast(copy("review.csvSaved"));
}
function buildPortfolio() {
	const reviewDate = ensureReviewDate();
	const rows = positionRows();
	const cashD = getCashDollarsInput();
	const nav = rows.reduce((sum, wrap) => sum + getPositionMarketValue(wrap), 0) + cashD;
	const positions = [];
	for (const wrap of rows) {
		const ticker = fieldValue(wrap, "ticker");
		if (!ticker) continue;
		const quantity = parseFloat(fieldValue(wrap, "quantity")) || 0;
		const price = getLastPrice(wrap) || 0;
		positions.push({
			ticker: ticker.toUpperCase(),
			name: fieldValue(wrap, "name"),
			weight: nav > 0 ? quantity * price / nav : 0,
			quantity,
			sector: fieldValue(wrap, "sector"),
			asset_class: "equity",
			entry_date: reviewDate,
			entry_price: price,
			current_price: price,
			dividend: getQuoteAction(wrap, "dividend", 0),
			split: getQuoteAction(wrap, "split", 1),
			entry_thesis: fieldValue(wrap, "entry_thesis")
		});
	}
	return {
		name: document.getElementById("p-name").value.trim(),
		benchmark: document.getElementById("p-benchmark").value.trim(),
		cash_weight: nav > 0 ? cashD / nav : 0,
		review_date: reviewDate,
		context_note: document.getElementById("p-context").value.trim(),
		positions,
		base_currency: "USD"
	};
}
async function fetchPastFeedbackMatch(portfolio) {
	return (await postJson("/api/reviews/feedback-candidates", { portfolio })).match;
}
function renderPastFeedbackMatch(match) {
	document.getElementById("past-feedback-source").textContent = copy("pastFeedback.source", {
		portfolio: match.portfolio_name || copy("common.portfolio"),
		date: formatDateTime(match.saved_at)
	});
	document.getElementById("past-feedback-list").innerHTML = match.items.map((item, index) => `
    <label class="past-feedback-item">
      <input type="checkbox" value="${escapeHtml(item.round_id)}" data-feedback-index="${index}" ${index < 3 ? "checked" : ""} />
      <span>
        <strong>${escapeHtml(copy("pastFeedback.itemLabel", { count: index + 1 }))}</strong>
        <span>${escapeHtml(item.comment)}</span>
        <small>${escapeHtml(formatDateTime(item.submitted_at))}</small>
      </span>
    </label>
  `).join("");
}
function showPastFeedbackModal(startBody, match) {
	pendingReviewStartBody = structuredClone(startBody);
	pendingFeedbackMatch = match;
	renderPastFeedbackMatch(match);
	showModal("past-feedback-modal", "past-feedback-include");
}
function hidePastFeedbackModal() {
	hideModal("past-feedback-modal");
	pendingReviewStartBody = null;
	pendingFeedbackMatch = null;
}
async function launchPendingReview(inheritedFeedback) {
	const startBody = pendingReviewStartBody;
	hidePastFeedbackModal();
	startBody.inherited_feedback = inheritedFeedback;
	lastStartBody = structuredClone(startBody);
	await runReviewWithBody(startBody);
}
function runPendingReviewWithoutFeedback() {
	launchPendingReview([]);
}
function runPendingReviewWithFeedback() {
	const { items } = pendingFeedbackMatch;
	launchPendingReview(Array.from(document.querySelectorAll("#past-feedback-list input[type='checkbox']:checked")).map((input) => items[Number(input.dataset.feedbackIndex)]));
}
async function startReview() {
	let portfolio = buildPortfolio();
	if (portfolio.positions.length === 0) {
		showToast(copy("review.addTickerFirst"), true);
		return;
	}
	if (positionRowsMissingReadyQuotes().length > 0) {
		const missingQuotes = await refreshMissingQuotesForReview();
		if (missingQuotes.length > 0) {
			showToast(copy("review.marketDataRequired", { tickers: missingQuotes.join(", ") }), true, 9e3);
			return;
		}
		portfolio = buildPortfolio();
	}
	const startBody = { portfolio };
	let feedbackMatch;
	try {
		feedbackMatch = await fetchPastFeedbackMatch(portfolio);
	} catch (err) {
		showToast(err.message, true);
		return;
	}
	if (feedbackMatch) {
		showPastFeedbackModal(startBody, feedbackMatch);
		return;
	}
	lastStartBody = structuredClone(startBody);
	await runReviewWithBody(startBody);
}
async function runReviewWithBody(startBody, { fromRetry = false } = {}) {
	resetCards();
	startReviewElapsedTimer();
	initializeDataLoaderTickerStatus(startBody.portfolio.positions);
	setGlobalStatus("running");
	requestNotifPermission();
	setButtonBusy(document.getElementById("start-btn"), true, copy("buttons.runReviewBusy"));
	setStopButtonRunning(true);
	hideResultsModal();
	setDataLoaderStatus("running", copy(fromRetry ? "dataLoader.retrying" : "dataLoader.starting"));
	let data;
	try {
		data = await postJson("/api/review/start", startBody);
	} catch (err) {
		const detail = copy("review.startReviewError", { detail: err.message });
		showToast(detail, true);
		finishReviewRun("error");
		setDataLoaderStatus("error", detail, true);
		return;
	}
	currentReviewId = data.review_id;
	setDataLoaderStatus("running", copy("dataLoader.waitingForMarketData"));
	subscribeSSE(currentReviewId);
}
async function stopReview() {
	const stopBtn = document.getElementById("stop-btn");
	setButtonBusy(stopBtn, true, copy("buttons.stopReviewStopping"));
	try {
		await postJson(`/api/review/${currentReviewId}/stop`);
	} catch (err) {
		showToast(copy("review.stopReviewError", { detail: err.message }), true);
		setButtonBusy(stopBtn, false);
	}
}
function subscribeSSE(reviewId) {
	if (eventSource) eventSource.close();
	eventSource = new EventSource(`/api/review/${reviewId}/stream`);
	eventSource.onmessage = (e) => handleEvent(JSON.parse(e.data));
	eventSource.onerror = async () => {
		eventSource.close();
		if ([
			"done",
			"stopped",
			"error"
		].includes(currentGlobalStatusState)) return;
		try {
			const snapshot = await syncReviewSnapshot(reviewId);
			if ([
				"done",
				"stopped",
				"error"
			].includes(snapshot.status)) return;
			finishReviewRun("error");
		} catch (err) {
			finishReviewRun("error", err.message);
		}
	};
}
function handleEvent(msg) {
	switch (msg.type) {
		case "agent_start":
			setCardState(msg.agent, "running");
			if (msg.agent === "data") {
				setAllDataLoaderTickers("loading");
				setDataLoaderStatus("running", copy("dataLoader.loadingMarketData"));
			}
			agentStepProgress[msg.agent] = newStepProgress();
			currentActiveAgent = msg.agent;
			startElapsedTimer(msg.agent);
			break;
		case "agent_step":
			recordStep(msg.agent, msg.step_index, msg.label);
			break;
		case "agent_done":
			stopElapsedTimer(msg.agent);
			completeAllSteps(msg.agent);
			setCardState(msg.agent, "done");
			if (msg.agent === "data") {
				setDataLoaderTickerResult(msg.output);
				setDataLoaderStatus("done", copy("dataLoader.marketDataLoaded"));
			}
			currentActiveAgent = null;
			if (msg.agent === "manager") {
				renderFinalResultOnce(currentReviewId);
				finishReviewRun("done");
				sendCompletionNotification();
			}
			break;
		case "agent_summary":
			enqueueAgentSummary(msg);
			break;
		case "heartbeat": break;
		case "error": {
			markRunningCardsErrored();
			const failureDetail = reviewFailureDetail(msg.message);
			finishReviewRun("error", failureDetail);
			const failedAgent = msg.agent || currentActiveAgent;
			if (failedAgent) setCardState(failedAgent, "error", failureDetail);
			if (failedAgent === "data") setAllDataLoaderTickers("error");
			setDataLoaderStatus("error", failureDetail, isDataLoaderError(msg.message));
			showToast(msg.message, true, 12e3);
			currentActiveAgent = null;
			break;
		}
		case "stopped":
			finishReviewRun("stopped");
			setDataLoaderStatus("idle", copy("dataLoader.reviewStopped"));
			eventSource.close();
			showToast(msg.message);
			break;
	}
}
function setCardState(agent, state, detail = "") {
	const card = document.getElementById(`card-${agent}`);
	if (!card) return;
	card.classList.remove(...CARD_STATES);
	if (state !== "idle") card.classList.add(state);
	const label = card.querySelector(".agent-status-label");
	label.textContent = state === "error" && detail ? compactStatusDetail(detail) : copy(`status.${state}`);
	label.title = detail;
	if (card.classList.contains("steps-open")) renderAgentStepStatus(agent);
	renderRibbon();
}
function ribbonTimeText(agent, state) {
	return document.querySelector(`#card-${agent} .agent-elapsed`).textContent.trim() || copy(`ribbon.${state}`);
}
function renderRibbon() {
	const states = PIPELINE_AGENTS.map(cardStateForAgent);
	PIPELINE_AGENTS.forEach((agent, index) => {
		const node = document.querySelector(`.ribbon-node[data-agent="${agent}"]`);
		node.classList.remove(...CARD_STATES);
		if (states[index] !== "idle") node.classList.add(states[index]);
		node.querySelector(".node-time").textContent = ribbonTimeText(agent, states[index]);
	});
	const total = PIPELINE_AGENTS.length;
	const done = states.filter((state) => state === "done").length;
	document.getElementById("ribbon-progress-fill").style.width = `${done / total * 100}%`;
	document.getElementById("ribbon-progress-text").textContent = `${done} / ${total}`;
	let eta = "";
	if (states.includes("error")) eta = copy("ribbon.etaError");
	else if (done === total) eta = copy("ribbon.etaComplete");
	else if (states.includes("running")) eta = copy("ribbon.etaRunning");
	document.getElementById("ribbon-progress-eta").textContent = eta;
}
function markRunningCardsErrored() {
	document.querySelectorAll(".agent-card.running").forEach((card) => {
		stopElapsedTimer(card.dataset.agent);
		setCardState(card.dataset.agent, "error");
	});
}
function actionTypeLabel(value) {
	return copy(`actionType.${value}`);
}
function priorityLabel(value) {
	return copy(`priority.${value}`);
}
function actionScopeLabel(value) {
	return copy(`actionScope.${value}`);
}
function setElementText(id, text) {
	document.getElementById(id).textContent = text;
}
function evidenceListElement(className, items) {
	const ul = document.createElement("ul");
	ul.className = className;
	for (const item of items) {
		const li = document.createElement("li");
		li.textContent = item;
		ul.appendChild(li);
	}
	return ul;
}
function appendActionMemoDetail(parent, label, value) {
	const text = value.trim();
	if (!text) return;
	const wrap = document.createElement("div");
	wrap.className = "action-memo-block";
	const dt = document.createElement("dt");
	dt.textContent = label;
	const dd = document.createElement("dd");
	dd.textContent = text;
	wrap.append(dt, dd);
	parent.appendChild(wrap);
}
function appendActionEvidenceMemoDetail(parent, evidence) {
	const items = evidence.filter((item) => item.trim());
	if (!items.length) return;
	const wrap = document.createElement("div");
	wrap.className = "action-memo-block";
	const dt = document.createElement("dt");
	dt.textContent = copy("results.supportingEvidence");
	const dd = document.createElement("dd");
	dd.appendChild(evidenceListElement("action-card__evidence", items.slice(0, 3)));
	wrap.append(dt, dd);
	parent.appendChild(wrap);
}
function topPriorityActions(actions) {
	if (!actions.length) return [];
	const bestRank = Math.min(...actions.map((action) => PRIORITY_ORDER.indexOf(action.priority)));
	return actions.filter((action) => PRIORITY_ORDER.indexOf(action.priority) === bestRank);
}
function formatTopActionSummary(actions) {
	const topActions = topPriorityActions(actions);
	if (!topActions.length) return copy("share.noImmediateAction");
	const grouped = /* @__PURE__ */ new Map();
	for (const action of topActions) {
		const type = actionTypeLabel(action.action_type);
		const position = action.position.trim();
		if (!position) {
			grouped.set(type, null);
			continue;
		}
		if (grouped.get(type) === null) continue;
		const positions = grouped.get(type) || [];
		positions.push(position);
		grouped.set(type, positions);
	}
	return Array.from(grouped.entries()).map(([type, positions]) => positions ? `${type} ${positions.join(", ")}` : type).join("; ");
}
function topActionDirection(actionType) {
	if (actionType === "reduce" || actionType === "exit") return "sell";
	if (actionType === "add") return "buy";
	if (actionType === "rotate" || actionType === "hedge") return "shift";
	return "passive";
}
function chipElement(className, text) {
	const chip = document.createElement("span");
	chip.className = `table-chip ${className}`;
	chip.textContent = text;
	return chip;
}
function priorityChip(priority) {
	return chipElement(`priority-chip priority-${priority}`, priorityLabel(priority));
}
function scopeLabelElement(action) {
	const scope = document.createElement("span");
	scope.className = "action-scope-label";
	scope.textContent = actionScopeLabel(action.scope);
	return scope;
}
function renderActionCards(actions) {
	const list = document.getElementById("actions-list");
	list.innerHTML = "";
	if (!actions.length) {
		const empty = document.createElement("div");
		empty.className = "action-card action-card--empty";
		empty.textContent = copy("results.noActions");
		list.appendChild(empty);
		return;
	}
	actions.forEach((action, index) => {
		const article = document.createElement("article");
		article.className = `action-card action-card--${action.priority}`;
		const top = document.createElement("div");
		top.className = "action-card__top";
		top.setAttribute("role", "button");
		top.setAttribute("tabindex", "0");
		const rank = document.createElement("span");
		rank.className = "action-card__rank";
		rank.textContent = String(index + 1).padStart(2, "0");
		const chips = document.createElement("div");
		chips.className = "action-card__chips";
		chips.append(priorityChip(action.priority), chipElement(`action-chip action-${topActionDirection(action.action_type)}`, actionTypeLabel(action.action_type)));
		const target = document.createElement("div");
		target.className = "action-card__target";
		const position = document.createElement("strong");
		position.textContent = action.position;
		target.append(scopeLabelElement(action), position);
		const title = document.createElement("p");
		title.className = "action-card__title";
		title.textContent = action.rationale || action.risk_addressed || formatActionLine(action);
		const toggle = document.createElement("span");
		toggle.className = "action-card__toggle";
		toggle.setAttribute("aria-hidden", "true");
		top.append(rank, chips, target, title, toggle);
		const memo = document.createElement("div");
		memo.className = "action-card__memo";
		const memoId = `action-card-memo-${index}`;
		memo.id = memoId;
		memo.hidden = true;
		top.setAttribute("aria-expanded", "false");
		top.setAttribute("aria-controls", memoId);
		top.setAttribute("aria-label", `${copy("results.showActionDetails")}: ${title.textContent}`);
		const riskColumn = document.createElement("dl");
		riskColumn.className = "action-card__memo-col";
		appendActionMemoDetail(riskColumn, copy("results.riskAddressed"), action.risk_addressed);
		appendActionEvidenceMemoDetail(riskColumn, action.supporting_evidence);
		const executionColumn = document.createElement("dl");
		executionColumn.className = "action-card__memo-col";
		appendActionMemoDetail(executionColumn, copy("results.columns.sizing"), action.size_guidance);
		appendActionMemoDetail(executionColumn, copy("results.columns.hedge"), action.hedge_instrument || "—");
		appendActionMemoDetail(executionColumn, copy("results.revisitTrigger"), action.revisit_trigger);
		memo.append(riskColumn, executionColumn);
		article.append(top, memo);
		top.addEventListener("click", () => {
			const expanded = top.getAttribute("aria-expanded") !== "true";
			memo.hidden = !expanded;
			article.classList.toggle("action-card--expanded", expanded);
			top.setAttribute("aria-expanded", expanded ? "true" : "false");
			top.setAttribute("aria-label", `${expanded ? copy("results.hideActionDetails") : copy("results.showActionDetails")}: ${title.textContent}`);
		});
		list.appendChild(article);
	});
}
function sortedManagerActions(manager) {
	const rank = (action) => PRIORITY_ORDER.indexOf(action.priority);
	return [...manager.actions].sort((a, b) => rank(a) - rank(b));
}
function formatActionLine(action) {
	const risk = action.risk_addressed || action.rationale;
	return [
		actionTypeLabel(action.action_type),
		action.position,
		risk
	].filter(Boolean).join(" - ");
}
function stateValueLabel(value) {
	return copy(`stateValue.${value}`);
}
function sortedMetricEntries(values, { absolute = false } = {}) {
	const magnitude = (value) => absolute ? Math.abs(value) : value;
	return Object.entries(values).sort((a, b) => magnitude(b[1]) - magnitude(a[1]));
}
function emptyAnalysisHtml() {
	return `<p class="evidence-empty">${escapeHtml(copy("agentAnalysis.empty"))}</p>`;
}
function cleanTextList(items) {
	return items.map((item) => item.trim()).filter(Boolean);
}
function listHtml(items) {
	const clean = cleanTextList(items);
	if (!clean.length) return emptyAnalysisHtml();
	return `<ul class="analysis-list">${clean.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}
function pillRowHtml(items) {
	const clean = cleanTextList(items);
	if (!clean.length) return emptyAnalysisHtml();
	return `<div class="analysis-chip-row">${clean.map((item) => `<span class="analysis-pill">${escapeHtml(item)}</span>`).join("")}</div>`;
}
function kvHtml(rows) {
	const clean = rows.filter(([, value]) => String(value).trim() !== "");
	if (!clean.length) return emptyAnalysisHtml();
	return `<dl class="analysis-kv">${clean.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}</dl>`;
}
function meaningfulThemeDriftNote(value) {
	const text = value.trim();
	return /^(unknown|n\/a|not available)\b/i.test(text) ? "" : text;
}
function labeledAnalysisBlock(label, html, className = "") {
	return `<div class="analysis-field-group${className ? ` ${className}` : ""}"><div class="analysis-field-label">${escapeHtml(label)}</div>${html}</div>`;
}
function themeAssessmentHtml(item) {
	const kind = item.narrative_kind;
	const assets = cleanTextList(item.supporting_assets);
	const evidence = cleanTextList(item.key_evidence);
	return `
    <div class="analysis-item analysis-item--theme-assessment">
      <div class="theme-assessment-head">
        <span class="theme-assessment-title">${escapeHtml(item.theme)}</span>
        <span class="analysis-pill analysis-pill--meta">${escapeHtml(kind)}</span>
      </div>
      ${assets.length ? `<div class="theme-assessment-assets">${assets.map(escapeHtml).join(" · ")}</div>` : ""}
      <div class="theme-assessment-body">
        ${item.assessment ? `<p class="theme-assessment-assess">${escapeHtml(item.assessment)}</p>` : ""}
        ${item.implication ? `
          <p class="theme-assessment-impl">
            <span class="theme-assessment-lead">${escapeHtml(copy("agentAnalysis.theme.implication"))}</span>
            ${escapeHtml(item.implication)}
          </p>
        ` : ""}
      </div>
      ${evidence.length ? `
        <details class="theme-assessment-evidence">
          <summary>${escapeHtml(copy("agentAnalysis.theme.evidence"))} (${evidence.length})</summary>
          ${listHtml(evidence)}
        </details>
      ` : ""}
    </div>
  `;
}
function themePositionProfileHtml(item) {
	const sector = item.sector.trim();
	return `
    <div class="analysis-item">
      <div class="analysis-item-title">
        <span>${escapeHtml(item.ticker)}</span>
        ${sector ? `<span class="analysis-pill analysis-pill--meta">${escapeHtml(sector)}</span>` : ""}
      </div>
      ${item.business_model ? labeledAnalysisBlock(copy("agentAnalysis.theme.businessModel"), `<p>${escapeHtml(item.business_model)}</p>`) : ""}
      ${labeledAnalysisBlock(copy("agentAnalysis.theme.candidateThemes"), pillRowHtml(item.candidate_themes), "analysis-field-group--compact")}
      ${item.revenue_drivers ? labeledAnalysisBlock(copy("agentAnalysis.theme.revenueDrivers"), `<p class="muted-text">${escapeHtml(item.revenue_drivers)}</p>`) : ""}
    </div>
  `;
}
function analogPeriodsHtml(periods) {
	if (!periods.length) return emptyAnalysisHtml();
	return periods.map((item) => `
    <div class="analysis-item">
      <div class="analysis-item-title">
        <span>${escapeHtml(item.period)}</span>
        <span class="analysis-item-meta">${escapeHtml(`${copy("results.analogMatchScore")} ${formatNumber(item.match_score, 2)}`)}</span>
      </div>
      ${kvHtml([
		[copy("results.analogForwardWindow"), item.forward_window],
		[copy("results.analogPortfolioReturn"), formatPercent(item.portfolio_return, 1, true)],
		[copy("results.analogMaxDrawdown"), formatPercent(Math.abs(item.max_drawdown), 1)]
	])}
    </div>
  `).join("");
}
function metricBarsHtml(values, { percent = false, signed = false, maxItems = 10 } = {}) {
	const rows = sortedMetricEntries(values, { absolute: signed }).slice(0, maxItems);
	if (!rows.length) return emptyAnalysisHtml();
	const maxAbs = Math.max(...rows.map(([, value]) => Math.abs(value)), 1e-4);
	return rows.map(([name, value]) => {
		const width = Math.max(3, Math.min(100, Math.abs(value) / maxAbs * 100));
		const valueText = percent ? formatPercent(value, 1, true) : formatNumber(value, 2, signed);
		return `
      <div class="evidence-bar-row">
        <div class="evidence-bar-meta"><span>${escapeHtml(name)}</span><strong>${escapeHtml(valueText)}</strong></div>
        <div class="evidence-bar-track"><span class="evidence-bar-fill${value < 0 ? " negative" : ""}" style="width: ${width}%"></span></div>
      </div>
    `;
	}).join("");
}
function scenarioLossBarsHtml(scenarios) {
	if (!scenarios.length) return emptyAnalysisHtml();
	const maxAbs = Math.max(...scenarios.map((item) => Math.abs(item.estimated_portfolio_loss_pct)), 1e-4);
	return scenarios.map((item) => {
		const loss = item.estimated_portfolio_loss_pct;
		const width = Math.max(3, Math.min(100, Math.abs(loss) / maxAbs * 100));
		return `
      <div class="analysis-item">
        <div class="evidence-bar-meta"><span>${escapeHtml(item.scenario)}</span><strong>${escapeHtml(formatNumber(loss, 1, true))}%</strong></div>
        <div class="evidence-bar-track"><span class="evidence-bar-fill${loss < 0 ? " negative" : ""}" style="width: ${width}%"></span></div>
      </div>
    `;
	}).join("");
}
function parseNewsCollectorRuns(raw) {
	const text = raw.trim();
	if (!text) return [];
	return text.split(/\n\n---\n\n/g).map((block) => {
		const match = block.match(/^### Query:\s*(.+)\n([\s\S]*)$/);
		return match ? {
			query: match[1].trim(),
			body: match[2].trim()
		} : {
			query: copy("agentAnalysis.news.unknownQuery"),
			body: block.trim()
		};
	}).filter((item) => item.body || item.query);
}
function parseNewsConsideredItems(body) {
	return body.split("\n").map((line) => line.trim()).filter((line) => line.startsWith("• ")).map((line) => {
		const match = line.slice(2).trim().match(/^(?:\[(.*?)\]\s*)?(.+?)(?:\s+—\s+(https?:\/\/\S+))?$/);
		if (!match) return null;
		return {
			published: (match[1] || "").trim(),
			title: (match[2] || "").trim(),
			url: (match[3] || "").trim()
		};
	}).filter((item) => item && item.title);
}
function newsConsideredHtml(run) {
	const items = parseNewsConsideredItems(run.body);
	if (!items.length) return `<pre class="analysis-raw-block">${escapeHtml(truncateText(run.body, 1600))}</pre>`;
	return `<ul class="analysis-news-links">${items.map((item) => {
		const title = escapeHtml(item.title);
		return `<li>${`<span class="analysis-item-meta">${item.published ? escapeHtml(item.published) : "—"}</span>`}${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${title}</a>` : `<span>${title}</span>`}</li>`;
	}).join("")}</ul>`;
}
function normalizeNewsQueryKey(query) {
	return query.trim().toLowerCase();
}
function agentReview(view, agent) {
	return view.agent_outputs[agent][`${agent}_review`];
}
function managerReview(view) {
	return agentReview(view, "manager");
}
function plannedNewsCollectorSections(view, runs) {
	const focus = view.agent_outputs.planner.news_focus;
	const byQuery = /* @__PURE__ */ new Map();
	for (const run of runs) {
		const key = normalizeNewsQueryKey(run.query);
		if (key && !byQuery.has(key)) byQuery.set(key, run);
	}
	const used = /* @__PURE__ */ new Set();
	const plannedItem = (query, meta = "") => {
		const cleanQuery = query.trim();
		const key = normalizeNewsQueryKey(cleanQuery);
		if (key) used.add(key);
		return {
			query: cleanQuery,
			meta,
			run: byQuery.get(key) || null
		};
	};
	const plannerTopics = focus.portfolio_search_queries.map((query) => plannedItem(query)).filter((item) => item.query);
	const tickerSearches = focus.position_goals.map((goal) => plannedItem(goal.latest_news_query, goal.ticker)).filter((item) => item.query);
	const otherSearches = runs.filter((run) => !used.has(normalizeNewsQueryKey(run.query))).map((run) => ({
		query: run.query,
		run
	}));
	return [
		plannerTopics.length ? {
			title: "",
			items: plannerTopics
		} : null,
		tickerSearches.length ? {
			title: copy("agentAnalysis.news.tickerSearches"),
			items: tickerSearches
		} : null,
		otherSearches.length ? {
			title: copy("agentAnalysis.news.otherSearches"),
			items: otherSearches
		} : null
	].filter(Boolean);
}
function newsCollectorSectionsHtml(view, runs) {
	const sections = plannedNewsCollectorSections(view, runs);
	if (!sections.some((section) => section.items.length)) return emptyAnalysisHtml();
	return sections.map((section) => `
    <div class="analysis-subsection">
      ${section.title ? `<h5>${escapeHtml(section.title)}</h5>` : ""}
      ${section.items.map((item) => `
        <div class="analysis-item">
          <div class="analysis-item-title">
            <span>${escapeHtml(item.query)}</span>
            ${item.meta ? `<span class="analysis-item-meta">${escapeHtml(item.meta)}</span>` : ""}
          </div>
          ${item.run ? newsConsideredHtml(item.run) : emptyAnalysisHtml()}
        </div>
      `).join("")}
    </div>
  `).join("");
}
function analysisSection(title, body) {
	return `<div class="analysis-section"><h4>${escapeHtml(title)}</h4>${body}</div>`;
}
function analysisPanel(sections) {
	return `<div class="analysis-grid"><div class="analysis-main">${sections.join("")}</div></div>`;
}
function renderPlannerAnalysisTab(view) {
	const focus = view.agent_outputs.planner.news_focus;
	return analysisPanel([analysisSection(copy("agentAnalysis.planner.portfolioGoal"), focus.portfolio_goal ? `<p>${escapeHtml(focus.portfolio_goal)}</p>` : emptyAnalysisHtml()), analysisSection(copy("agentAnalysis.planner.macroTopics"), listHtml(focus.portfolio_search_queries))]);
}
function renderNewsAnalysisTab(view) {
	const out = view.agent_outputs.news;
	const review = out.news_review;
	return analysisPanel([
		analysisSection(copy("agentAnalysis.news.briefing"), kvHtml([[copy("agentOutput.news.macro"), review.macro_context], [copy("agentOutput.news.summary"), review.summary]])),
		analysisSection(copy("agentOutput.news.themes"), pillRowHtml(review.market_themes)),
		analysisSection(copy("agentOutput.news.keyEvents"), listHtml(review.key_events)),
		analysisSection(copy("agentAnalysis.news.thesisRisks"), listHtml(review.thesis_risks)),
		analysisSection(copy("agentAnalysis.news.consideredResearch"), newsCollectorSectionsHtml(view, parseNewsCollectorRuns(out.news_collector_text)))
	]);
}
function renderRiskAnalysisTab(view) {
	const risk = agentReview(view, "risk");
	const bars = (values) => metricBarsHtml(values, {
		percent: true,
		signed: true
	});
	return analysisPanel([
		analysisSection(copy("agentAnalysis.risk.overview"), kvHtml([
			[copy("agentOutput.risk.worstScenario"), risk.worst_scenario ? `${risk.worst_scenario.name} ${formatNumber(risk.worst_scenario.estimated_portfolio_loss_pct, 1, true)}%` : ""],
			[copy("agentOutput.risk.portfolioVolatility"), risk.portfolio_volatility == null ? "" : formatPercent(risk.portfolio_volatility, 2, true)],
			[copy("agentOutput.risk.summary"), risk.summary]
		])),
		analysisSection(copy("agentOutput.risk.riskContribution"), `<p class="muted-text">${escapeHtml(copy("agentOutput.risk.cashAwareNote"))}</p>${bars(risk.factor_risk_contribution)}`),
		analysisSection(copy("agentOutput.risk.riskContributionTicker"), bars(risk.risk_contribution_by_ticker)),
		analysisSection(copy("agentOutput.risk.volatilityContributionTicker"), bars(risk.volatility_contribution_by_ticker)),
		analysisSection(copy("agentOutput.risk.scenarios"), `<p class="muted-text">${escapeHtml(copy("agentOutput.risk.scenarioCashNote"))}</p>${scenarioLossBarsHtml(risk.scenario_losses)}`),
		analysisSection(copy("agentOutput.risk.topRisks"), listHtml(risk.top_risks)),
		analysisSection(copy("agentOutput.risk.concentration"), listHtml(risk.concentration_issues))
	]);
}
function renderRegimeAnalysisTab(view) {
	const regime = agentReview(view, "regime");
	const state = regime.state_vector;
	const hist = regime.historical_outcome;
	return analysisPanel([
		analysisSection(copy("agentAnalysis.regime.overview"), kvHtml([[copy("agentOutput.regime.regime"), regime.current_regime], [copy("agentOutput.regime.summary"), regime.summary]])),
		analysisSection(copy("agentOutput.regime.state"), kvHtml([
			[copy("agentOutput.regime.stateVector.inflation"), stateValueLabel(state.inflation_trend)],
			[copy("agentOutput.regime.stateVector.shortRates"), stateValueLabel(state.short_rates_trend)],
			[copy("agentOutput.regime.stateVector.longRates"), stateValueLabel(state.long_rates_trend)],
			[copy("agentOutput.regime.stateVector.growth"), stateValueLabel(state.growth_trend)],
			[copy("agentOutput.regime.stateVector.liquidity"), stateValueLabel(state.liquidity)],
			[copy("agentOutput.regime.stateVector.volatility"), stateValueLabel(state.volatility)]
		])),
		analysisSection(copy("results.historicalRegimeAnalogs"), kvHtml([
			[copy("results.analogAvgReturn"), hist.avg_return == null ? "" : formatPercent(hist.avg_return, 1, true)],
			[copy("results.analogMaxDrawdown"), hist.max_drawdown == null ? "" : formatPercent(Math.abs(hist.max_drawdown), 1)],
			[copy("results.analogWinRate"), hist.win_rate == null ? "" : formatPercent(Math.abs(hist.win_rate), 0)]
		]) + analogPeriodsHtml(hist.top_similar_periods)),
		analysisSection(copy("agentOutput.regime.mismatchDrivers"), listHtml(regime.mismatch_drivers))
	]);
}
function renderThemeAnalysisTab(view) {
	const theme = agentReview(view, "theme");
	const { synthesis } = theme;
	return analysisPanel([
		analysisSection(copy("agentAnalysis.theme.overview"), kvHtml([
			[copy("agentOutput.theme.implicitBet"), theme.implicit_portfolio_bet],
			[copy("agentOutput.theme.summary"), theme.summary],
			[copy("agentAnalysis.theme.drift"), meaningfulThemeDriftNote(synthesis.theme_drift_note)]
		])),
		analysisSection(copy("agentOutput.theme.dominant"), pillRowHtml(synthesis.dominant_themes)),
		analysisSection(copy("agentAnalysis.theme.themeAssessments"), theme.theme_assessments.length ? theme.theme_assessments.map(themeAssessmentHtml).join("") : emptyAnalysisHtml()),
		analysisSection(copy("agentAnalysis.theme.positionProfiles"), theme.position_profiles.length ? theme.position_profiles.map(themePositionProfileHtml).join("") : emptyAnalysisHtml()),
		analysisSection(copy("agentAnalysis.theme.crowdingMomentum"), listHtml([...theme.crowding_risks, ...theme.momentum_conflicts])),
		analysisSection(copy("agentAnalysis.theme.redundantExposures"), listHtml(synthesis.redundant_expressions)),
		analysisSection(copy("agentAnalysis.theme.missingExposures"), listHtml(synthesis.missing_exposures))
	]);
}
function deploymentCandidatesHtml(candidates) {
	if (!candidates.length) return emptyAnalysisHtml();
	return candidates.map((item) => `
    <div class="analysis-item">
      <div class="analysis-item-title"><span>${escapeHtml(item.ticker)}</span></div>
      ${item.rationale ? `<p>${escapeHtml(item.rationale)}</p>` : ""}
    </div>
  `).join("");
}
function drawdownGateKey(allocation) {
	if (allocation.drawdown_budget_breached == null) return "Unavailable";
	return allocation.drawdown_budget_breached ? "Breached" : "Within";
}
function renderAllocationAnalysisTab(view) {
	const allocation = agentReview(view, "allocation");
	const budgetStatus = {
		Unavailable: copy("agentAnalysis.allocation.unavailable"),
		Breached: copy("agentAnalysis.allocation.breached"),
		Within: copy("agentAnalysis.allocation.withinBudget")
	}[drawdownGateKey(allocation)];
	return analysisPanel([
		analysisSection(copy("agentAnalysis.allocation.overview"), kvHtml([[copy("agentOutput.allocation.summary"), allocation.summary]])),
		analysisSection(copy("agentAnalysis.allocation.policy"), kvHtml([
			[copy("agentAnalysis.allocation.allocatedCapital"), formatPercent(allocation.allocated_capital, 1, true)],
			[copy("agentAnalysis.allocation.minimumAllocated"), formatPercent(allocation.min_allocated_capital, 1, true)],
			[copy("agentAnalysis.allocation.cashWeight"), formatPercent(allocation.cash_weight, 1, true)],
			[copy("agentAnalysis.allocation.maximumCash"), formatPercent(allocation.max_cash_weight, 1, true)],
			[copy("agentAnalysis.allocation.requiredDeployment"), formatPercent(allocation.required_deployment_pct, 1, true)],
			[copy("agentAnalysis.allocation.deploymentStatus"), copy(allocation.deployment_required ? "agentAnalysis.allocation.required" : "agentAnalysis.allocation.notRequired")]
		])),
		analysisSection(copy("agentAnalysis.allocation.opportunityCost"), kvHtml([
			[copy("agentAnalysis.allocation.benchmarkReturn"), allocation.benchmark_return_1y_pct == null ? "" : `${formatNumber(allocation.benchmark_return_1y_pct, 2, true)}%`],
			[copy("agentAnalysis.allocation.cashYield"), `${formatNumber(allocation.cash_yield_annual_pct, 2)}%`],
			[copy("agentAnalysis.allocation.cashOpportunityCost"), allocation.cash_opportunity_cost_pct == null ? "" : `${formatNumber(allocation.cash_opportunity_cost_pct, 2, true)}%`]
		])),
		analysisSection(copy("agentAnalysis.allocation.drawdownGate"), kvHtml([
			[copy("agentAnalysis.allocation.drawdownBudget"), `${formatNumber(allocation.drawdown_budget_pct, 1)}%`],
			[copy("agentAnalysis.allocation.worstScenarioLoss"), allocation.worst_scenario_loss_pct == null ? "" : `${formatNumber(allocation.worst_scenario_loss_pct, 2)}%`],
			[copy("agentAnalysis.allocation.budgetStatus"), budgetStatus]
		])),
		analysisSection(copy("agentOutput.allocation.candidates"), deploymentCandidatesHtml(allocation.deployment_candidates)),
		analysisSection(copy("agentOutput.allocation.conflicts"), listHtml(allocation.constraint_conflicts))
	]);
}
function latestSuccessfulFeedbackRound(rounds) {
	return [...rounds].reverse().find((round) => round.status === "done");
}
function feedbackActionPreviewHtml(manager, maxItems = 3) {
	const actions = sortedManagerActions(manager).slice(0, maxItems);
	if (!actions.length) return emptyAnalysisHtml();
	return `
    <ul class="feedback-action-list">
      ${actions.map((action) => `
        <li>
          <span class="feedback-action-main">
            <strong>${escapeHtml(actionTypeLabel(action.action_type))}</strong>
            <span>${escapeHtml(action.position || copy("actionScope.portfolio"))}</span>
          </span>
          <span class="feedback-action-meta">${escapeHtml(priorityLabel(action.priority))}</span>
          ${action.rationale ? `<p>${escapeHtml(truncateText(action.rationale, 180))}</p>` : ""}
        </li>
      `).join("")}
    </ul>
  `;
}
function feedbackLatestSnapshotHtml(view) {
	const latest = latestSuccessfulFeedbackRound(view.feedback_rounds);
	const manager = latest ? latest.manager_review : managerReview(view);
	const verdict = manager.portfolio_verdict;
	const actions = sortedManagerActions(manager);
	const allocation = agentReview(view, "allocation");
	return `
    <div class="feedback-latest">
      <div class="feedback-latest-head">
        <h4>${escapeHtml(copy("agentAnalysis.feedback.latestTitle"))}</h4>
        ${latest ? `<span class="analysis-pill analysis-pill--meta">${escapeHtml(copy("agentAnalysis.feedback.updated"))}</span>` : ""}
      </div>
      ${manager.executive_summary ? `
        <p class="feedback-latest-summary">${escapeHtml(manager.executive_summary)}</p>
      ` : emptyAnalysisHtml()}
      <dl class="feedback-snapshot-grid">
        <div>
          <dt>${escapeHtml(copy("results.actionTiming"))}</dt>
          <dd>${escapeHtml(priorityLabel(verdict.action_timing))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(copy("results.primaryRisk"))}</dt>
          <dd>${escapeHtml(verdict.primary_risk)}</dd>
        </div>
        <div>
          <dt>${escapeHtml(copy("share.topAction"))}</dt>
          <dd>${escapeHtml(actions.length ? formatActionLine(actions[0]) : copy("share.noImmediateAction"))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(copy("agentAnalysis.feedback.actions"))}</dt>
          <dd>${escapeHtml(copy("agentAnalysis.feedback.actionCount", { count: actions.length }))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(copy("agentAnalysis.feedback.investedCapital"))}</dt>
          <dd>${escapeHtml(copy("history.allocationBadge", {
		invested: formatPercent(allocation.allocated_capital, 1, true),
		minimum: formatPercent(allocation.min_allocated_capital, 1, true)
	}))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(copy("agentAnalysis.feedback.cashPolicy"))}</dt>
          <dd>${escapeHtml(copy("results.allocation.valueVsMaximum", {
		value: formatPercent(allocation.cash_weight, 1, true),
		maximum: formatPercent(allocation.max_cash_weight, 1, true)
	}))}</dd>
        </div>
      </dl>
    </div>
  `;
}
var FEEDBACK_STATUS_KEYS = {
	done: "complete",
	running: "runningStatus",
	error: "error"
};
function feedbackRoundHtml(round, index) {
	const manager = round.manager_review;
	return `
    <div class="analysis-item feedback-round ${round.status === "error" ? "feedback-round--error" : ""}">
      <div class="feedback-round-head">
        <div>
          <span class="feedback-round-title">${escapeHtml(copy("agentAnalysis.feedback.round", { count: index + 1 }))}</span>
          <span class="analysis-item-meta">${escapeHtml(formatDateTime(round.submitted_at))}</span>
        </div>
        <span class="analysis-pill analysis-pill--meta">${escapeHtml(copy(`agentAnalysis.feedback.${FEEDBACK_STATUS_KEYS[round.status]}`))}</span>
      </div>
      <div class="feedback-message feedback-message--user">
        <div class="feedback-speaker">${escapeHtml(copy("agentAnalysis.feedback.you"))}</div>
        <p>${escapeHtml(round.user_comment)}</p>
      </div>
      ${round.status === "error" ? `
        <div class="feedback-message feedback-message--manager">
          <div class="feedback-speaker">${escapeHtml(copy("agentAnalysis.feedback.manager"))}</div>
          <p>${escapeHtml(round.error)}</p>
        </div>
      ` : ""}
      ${manager?.executive_summary ? `
        <div class="feedback-message feedback-message--manager">
          <div class="feedback-speaker">${escapeHtml(copy("agentAnalysis.feedback.manager"))}</div>
          <p>${escapeHtml(manager.executive_summary)}</p>
        </div>
      ` : ""}
      ${manager?.actions.length ? `
        <div class="feedback-round-actions">
          <div class="analysis-field-label">${escapeHtml(copy("agentAnalysis.feedback.topActions"))}</div>
          ${feedbackActionPreviewHtml(manager)}
        </div>
      ` : ""}
    </div>
  `;
}
function renderFeedbackAnalysisTab(view) {
	const rounds = view.feedback_rounds;
	const disabled = feedbackRerunInFlight ? "disabled" : "";
	return `
    <div class="feedback-layout">
      <div class="analysis-main">
        <div class="analysis-section">
          <h4>${escapeHtml(copy("agentAnalysis.feedback.title"))}</h4>
          <form class="feedback-form" data-feedback-form>
            <label class="sr-only" for="feedback-comment">${escapeHtml(copy("agentAnalysis.feedback.comment"))}</label>
            <textarea id="feedback-comment" class="feedback-textarea" rows="5" ${disabled} placeholder="${escapeHtml(copy("agentAnalysis.feedback.placeholder"))}"></textarea>
            <div class="feedback-actions">
              <span class="feedback-status" data-feedback-status aria-live="polite">${feedbackRerunInFlight ? escapeHtml(copy("agentAnalysis.feedback.running")) : ""}</span>
              <button type="submit" class="btn-primary" ${disabled}>${escapeHtml(feedbackRerunInFlight ? copy("agentAnalysis.feedback.runningButton") : copy("agentAnalysis.feedback.submit"))}</button>
            </div>
          </form>
        </div>
        ${analysisSection(copy("agentAnalysis.feedback.history"), rounds.length ? rounds.map(feedbackRoundHtml).join("") : emptyAnalysisHtml())}
      </div>
      <aside class="feedback-side">
        ${feedbackLatestSnapshotHtml(view)}
      </aside>
    </div>
  `;
}
async function submitUserFeedback(comment) {
	feedbackRerunInFlight = true;
	renderAgentAnalysisTabs();
	try {
		const view = await postJson(`/api/review/${encodeURIComponent(currentResultsView.review_id)}/feedback`, { comment });
		applyResultsFromData(view);
		const lastRound = view.feedback_rounds.at(-1);
		if (lastRound.status === "error") showToast(lastRound.error, true);
		else showToast(copy("agentAnalysis.feedback.saved"));
	} catch (err) {
		showToast(err.message, true);
	} finally {
		feedbackRerunInFlight = false;
		renderAgentAnalysisTabs();
	}
}
var ANALYSIS_TAB_RENDERERS = {
	planner: renderPlannerAnalysisTab,
	news: renderNewsAnalysisTab,
	risk: renderRiskAnalysisTab,
	regime: renderRegimeAnalysisTab,
	theme: renderThemeAnalysisTab,
	allocation: renderAllocationAnalysisTab,
	feedback: renderFeedbackAnalysisTab
};
function renderAgentAnalysisTabs() {
	for (const tab of ANALYSIS_TABS) document.getElementById(`agent-panel-${tab}`).innerHTML = ANALYSIS_TAB_RENDERERS[tab](currentResultsView);
	switchAgentAnalysisTab(activeAgentAnalysisTab, { render: false });
}
function switchAgentAnalysisTab(tabName, { render = true } = {}) {
	activeAgentAnalysisTab = tabName;
	document.querySelectorAll(".agent-analysis-tab").forEach((tab) => {
		const active = tab.dataset.agentTab === activeAgentAnalysisTab;
		tab.classList.toggle("active", active);
		tab.setAttribute("aria-selected", active ? "true" : "false");
		tab.setAttribute("tabindex", active ? "0" : "-1");
	});
	document.querySelectorAll(".agent-analysis-panel").forEach((panel) => {
		panel.classList.toggle("hidden", panel.id !== `agent-panel-${activeAgentAnalysisTab}`);
	});
	if (render) renderAgentAnalysisTabs();
}
function wireAgentAnalysisControls() {
	document.querySelectorAll(".agent-analysis-tab").forEach((tab) => {
		tab.addEventListener("click", () => switchAgentAnalysisTab(tab.dataset.agentTab));
	});
	document.getElementById("agent-analysis-panels").addEventListener("submit", (event) => {
		const form = event.target.closest("[data-feedback-form]");
		if (!form) return;
		event.preventDefault();
		const comment = form.querySelector("#feedback-comment").value.trim();
		if (!comment) {
			showToast(copy("agentAnalysis.feedback.emptyComment"), true);
			return;
		}
		submitUserFeedback(comment);
	});
}
function applyResultsFromData(view) {
	currentResultsView = view;
	const manager = managerReview(view);
	const allocation = agentReview(view, "allocation");
	const verdict = manager.portfolio_verdict;
	const actions = sortedManagerActions(manager);
	setElementText("exec-summary", manager.executive_summary);
	document.getElementById("allocation-summary").classList.remove("hidden");
	setElementText("allocation-invested", copy("results.allocation.valueVsMinimum", {
		value: formatPercent(allocation.allocated_capital, 1, true),
		minimum: formatPercent(allocation.min_allocated_capital, 1, true)
	}));
	setElementText("allocation-cash", copy("results.allocation.valueVsMaximum", {
		value: formatPercent(allocation.cash_weight, 1, true),
		maximum: formatPercent(allocation.max_cash_weight, 1, true)
	}));
	setElementText("allocation-deployment", allocation.deployment_required ? copy("results.allocation.deploymentRequired", { value: formatPercent(allocation.required_deployment_pct, 1, true) }) : copy("results.allocation.noDeployment"));
	setElementText("allocation-drawdown-gate", copy(`results.allocation.gate${drawdownGateKey(allocation)}`));
	setElementText("allocation-opportunity-cost", allocation.cash_opportunity_cost_pct == null ? copy("results.allocation.unavailable") : `${formatNumber(allocation.cash_opportunity_cost_pct, 2, true)}%`);
	document.getElementById("portfolio-stance").classList.remove("hidden");
	setElementText("verdict-action-timing", priorityLabel(verdict.action_timing));
	const horizonText = [verdict.investment_horizon, verdict.horizon_detail].filter(Boolean).join(", ");
	setElementText("verdict-horizon", horizonText);
	document.getElementById("verdict-horizon-item").classList.toggle("hidden", !horizonText);
	setElementText("stance-primary-risk", verdict.primary_risk);
	setElementText("stance-recommended-posture", verdict.recommended_posture);
	setElementText("stance-rationale", verdict.rationale);
	setElementText("overview-top-action", formatTopActionSummary(actions));
	renderAgentAnalysisTabs();
	renderActionCards(actions);
	setElementText("do-nothing", manager.do_nothing_case);
	resetTrackRecordSection();
}
function resetTrackRecordSection() {
	document.getElementById("track-record-status").textContent = "";
	document.getElementById("track-record-body").innerHTML = "";
	document.getElementById("load-track-record").disabled = false;
}
function formatDailyOutperf(value) {
	if (value == null) return "—";
	return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
async function loadTrackRecord() {
	const statusEl = document.getElementById("track-record-status");
	const btn = document.getElementById("load-track-record");
	document.getElementById("track-record-body").innerHTML = "";
	btn.disabled = true;
	statusEl.textContent = copy("results.trackRecord.loading");
	try {
		renderTrackRecord(await getJson(`/api/review/${encodeURIComponent(currentResultsView.review_id)}/track-record`));
	} catch (err) {
		statusEl.textContent = `${copy("results.trackRecord.error")} ${err.message}`;
	} finally {
		btn.disabled = false;
	}
}
function tableCell(tag, content) {
	const cell = document.createElement(tag);
	if (typeof content === "string") cell.textContent = content;
	else cell.appendChild(content);
	return cell;
}
function renderTrackRecord(data) {
	const statusEl = document.getElementById("track-record-status");
	const bodyEl = document.getElementById("track-record-body");
	bodyEl.innerHTML = "";
	const { outcomes, benchmark } = data;
	if (!outcomes.length) {
		statusEl.textContent = copy("results.trackRecord.none");
		return;
	}
	statusEl.textContent = copy("results.trackRecord.summary", {
		validated: data.validated_count,
		matured: data.matured_count,
		benchmark,
		date: data.review_date
	});
	const table = document.createElement("table");
	table.className = "track-record-table";
	const headRow = document.createElement("tr");
	headRow.append(...[
		copy("results.trackRecord.columns.position"),
		copy("results.trackRecord.columns.call"),
		copy("results.trackRecord.columns.days"),
		copy("results.trackRecord.columns.daily", { benchmark }),
		copy("results.trackRecord.columns.verdict")
	].map((label) => tableCell("th", label)));
	table.createTHead().appendChild(headRow);
	const tbody = table.createTBody();
	for (const outcome of outcomes) {
		const position = document.createElement("b");
		position.textContent = outcome.position;
		const verdictChip = chipElement(`track-verdict track-verdict--${outcome.verdict}`, copy(`results.trackRecord.verdicts.${outcome.verdict}`));
		if (outcome.note) verdictChip.title = outcome.note;
		const daily = tableCell("td", formatDailyOutperf(outcome.daily_outperf_pct));
		daily.className = "track-record-daily";
		const tr = document.createElement("tr");
		tr.append(tableCell("td", position), tableCell("td", chipElement(`action-chip action-${outcome.action_type}`, actionTypeLabel(outcome.action_type))), tableCell("td", outcome.verdict === "pending" && !outcome.days_elapsed ? "—" : String(outcome.days_elapsed)), daily, tableCell("td", verdictChip));
		tbody.appendChild(tr);
	}
	bodyEl.appendChild(table);
}
function syncBodyScroll() {
	const anyOpen = MODAL_IDS.some((id) => !document.getElementById(id).classList.contains("hidden"));
	document.body.style.overflow = anyOpen ? "hidden" : "";
}
function showModal(id, focusId) {
	document.getElementById(id).classList.remove("hidden");
	syncBodyScroll();
	document.getElementById(focusId).focus();
}
function hideModal(id) {
	document.getElementById(id).classList.add("hidden");
	syncBodyScroll();
}
function showResultsModal({ returnToHistory = false } = {}) {
	returnToHistoryOnResultsClose = returnToHistory;
	showModal("results-modal", "results-modal-close");
}
function hideResultsModal() {
	hideModal("agent-analysis-modal");
	hideModal("results-modal");
	if (returnToHistoryOnResultsClose) {
		returnToHistoryOnResultsClose = false;
		showHistoryModal();
	}
}
function showAgentAnalysisModal() {
	renderAgentAnalysisTabs();
	showModal("agent-analysis-modal", "agent-analysis-modal-close");
}
function fetchReviewResult(reviewId) {
	return getJson(`/api/review/${encodeURIComponent(reviewId)}/result`);
}
async function openReviewById(reviewId) {
	try {
		applyResultsFromData(await fetchReviewResult(reviewId));
		showResultsModal({ returnToHistory: true });
	} catch (err) {
		showToast(copy("history.savedReviewLoadError", { detail: err.message }), true);
	}
}
function historyRowHtml(summary) {
	const portfolioName = summary.portfolio_name.trim() || copy("common.portfolio");
	const savedAt = summary.saved_at ? formatDateTime(summary.saved_at) : "";
	const { allocation } = summary;
	const allocationBadge = allocation ? `<span class="history-row-allocation ${allocation.deployment_required ? "is-breached" : ""}">${escapeHtml(copy("history.allocationBadge", {
		invested: formatPercent(allocation.allocated_capital, 1, true),
		minimum: formatPercent(allocation.min_allocated_capital, 1, true)
	}))}</span>` : "";
	return `
    <span class="history-row-top">
      <span class="history-row-title">${escapeHtml(portfolioName)}</span>
      ${savedAt ? `<span class="history-row-time">${escapeHtml(savedAt)}</span>` : ""}
    </span>
    <span class="history-row-preview">${escapeHtml(truncateText(summary.preview || copy("history.previewFallback"), 160))}</span>
    ${allocationBadge}
  `;
}
async function renderHistoryList() {
	const ul = document.getElementById("history-list");
	const empty = document.getElementById("history-empty");
	const count = document.getElementById("history-count");
	let reviews;
	try {
		({reviews} = await getJson(`/api/reviews?limit=${MAX_REVIEW_HISTORY}`));
	} catch (err) {
		showToast(copy("history.savedReviewLoadError", { detail: err.message }), true);
		return;
	}
	ul.innerHTML = "";
	empty.classList.toggle("hidden", reviews.length > 0);
	count.textContent = reviews.length ? copy("history.count", { count: reviews.length }) : copy("history.countEmpty");
	for (const summary of reviews) {
		const btn = document.createElement("button");
		btn.type = "button";
		btn.className = "history-row-btn";
		btn.innerHTML = historyRowHtml(summary);
		btn.addEventListener("click", () => {
			hideModal("history-modal");
			openReviewById(summary.review_id);
		});
		const li = document.createElement("li");
		li.appendChild(btn);
		ul.appendChild(li);
	}
}
function showHistoryModal() {
	renderHistoryList();
	showModal("history-modal", "history-modal-close");
}
async function renderFinalResultOnce(reviewId) {
	if (finalResultReviewId === reviewId) return;
	finalResultReviewId = reviewId;
	try {
		applyResultsFromData(await fetchReviewResult(reviewId));
		showResultsModal();
	} catch (err) {
		finalResultReviewId = null;
		showToast(copy("review.resultLoadError", { detail: err.message }), true);
	}
}
function renderAgentElapsed(agent) {
	const start = agentStartTimes[agent];
	if (!start) return;
	const seconds = Math.max(0, Math.floor(((agentEndTimes[agent] || Date.now()) - start) / 1e3));
	document.querySelector(`#card-${agent} .agent-elapsed`).textContent = copy("agents.runTime", { duration: fmtDuration(seconds) });
	renderRibbon();
}
function startElapsedTimer(agent) {
	clearInterval(agentTimerIds[agent]);
	agentStartTimes[agent] = Date.now();
	delete agentEndTimes[agent];
	renderAgentElapsed(agent);
	agentTimerIds[agent] = setInterval(() => renderAgentElapsed(agent), 1e3);
}
function stopElapsedTimer(agent) {
	clearInterval(agentTimerIds[agent]);
	delete agentTimerIds[agent];
	agentEndTimes[agent] = Date.now();
	renderAgentElapsed(agent);
}
function streamElements(agent) {
	const card = document.getElementById(`card-${agent}`);
	return {
		card,
		log: card.querySelector(".agent-stream-log"),
		row: card.querySelector(".agent-stream-row")
	};
}
function renderCompactStep(agent, label, isActive) {
	const { log, row } = streamElements(agent);
	row.classList.remove("hidden", "agent-step-status-row");
	log.removeAttribute("id");
	const entry = document.createElement("div");
	entry.className = "stream-entry" + (isActive ? " active" : "");
	entry.textContent = label;
	log.replaceChildren(entry);
}
function clearStreamLog(agent) {
	const { log, row } = streamElements(agent);
	log.innerHTML = "";
	log.removeAttribute("id");
	row.classList.add("hidden");
	row.classList.remove("agent-step-status-row");
}
function cardStateForAgent(agent) {
	const card = document.getElementById(`card-${agent}`);
	return CARD_STATES.find((state) => card.classList.contains(state)) || "idle";
}
function stepStatusFor(agent, index) {
	const progress = agentStepProgress[agent] || newStepProgress();
	const cardState = cardStateForAgent(agent);
	if (progress.done.has(index) || cardState === "done") return "done";
	if (cardState === "error" && (progress.active === index || progress.active < 0)) return "error";
	if (progress.active === index) return "running";
	return "waiting";
}
var STEP_STATUS_ICONS = {
	done: "✓",
	running: "⟳",
	error: "!",
	waiting: "○"
};
function renderAgentStepStatus(agent) {
	const { log, row } = streamElements(agent);
	const progress = agentStepProgress[agent] || newStepProgress();
	row.classList.remove("hidden");
	row.classList.add("agent-step-status-row");
	log.id = `card-${agent}-steps`;
	log.innerHTML = agentSteps(agent).map((step, index) => {
		const status = stepStatusFor(agent, index);
		const liveLabel = progress.labels[index];
		const subHtml = liveLabel ? `<span class="agent-step-sub">${escapeHtml(liveLabel)}</span>` : "";
		return `
      <div class="agent-step-status agent-step-status-${status}">
        <span class="agent-step-icon" aria-hidden="true">${STEP_STATUS_ICONS[status]}</span>
        <span class="agent-step-name">${escapeHtml(step)}</span>
        <span class="agent-step-state">${escapeHtml(copy(`status.${status}`))}</span>
        ${subHtml}
      </div>`;
	}).join("");
}
function isCompletedStepEvent(agent, stepIndex, label) {
	return agent === "news" && stepIndex === 2 && label.startsWith("Combined ");
}
function toggleAgentStepStatus(agent) {
	const { card } = streamElements(agent);
	const opening = !card.classList.contains("steps-open");
	card.classList.toggle("steps-open", opening);
	card.querySelector(".card-header").setAttribute("aria-expanded", opening ? "true" : "false");
	if (opening) {
		renderAgentStepStatus(agent);
		return;
	}
	const progress = agentStepProgress[agent];
	const label = progress?.active >= 0 ? progress.labels[progress.active] : "";
	if (label) renderCompactStep(agent, label, true);
	else clearStreamLog(agent);
}
function recordStep(agent, stepIndex, label) {
	if (agent === "data") return;
	const progress = agentStepProgress[agent];
	if (progress.active >= 0 && progress.active !== stepIndex) progress.done.add(progress.active);
	const completed = isCompletedStepEvent(agent, stepIndex, label);
	if (completed) progress.done.add(stepIndex);
	progress.active = completed ? -1 : stepIndex;
	progress.labels[stepIndex] = label;
	if (streamElements(agent).card.classList.contains("steps-open")) renderAgentStepStatus(agent);
	else renderCompactStep(agent, label, !completed);
}
function completeAllSteps(agent) {
	if (agent === "data") return;
	const progress = agentStepProgress[agent];
	agentSteps(agent).forEach((_, i) => progress.done.add(i));
	progress.active = -1;
	if (streamElements(agent).card.classList.contains("steps-open")) renderAgentStepStatus(agent);
	else clearStreamLog(agent);
}
function enqueueAgentSummary(msg) {
	agentSummaryQueue.push(msg);
	showNextAgentSummary();
}
function showNextAgentSummary() {
	if (activeAgentSummary || agentSummaryQueue.length === 0) return;
	activeAgentSummary = agentSummaryQueue.shift();
	renderAgentSummaryPopup();
}
function renderAgentSummaryPopup() {
	const item = activeAgentSummary;
	setElementText("agent-summary-agent", copy("agentSummary.agentComplete", { agent: agentLabel(item.agent) }));
	setElementText("agent-summary-title", item.title);
	setElementText("agent-summary-body", item.summary);
	const bulletsEl = document.getElementById("agent-summary-bullets");
	bulletsEl.innerHTML = item.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("");
	bulletsEl.classList.toggle("hidden", item.bullets.length === 0);
	setElementText("agent-summary-dismiss", agentSummaryQueue.length > 0 ? copy("agentSummary.next") : copy("agentSummary.dismiss"));
	const popup = document.getElementById("agent-summary-popup");
	popup.classList.remove("hidden");
	requestAnimationFrame(() => popup.classList.add("visible"));
}
function dismissAgentSummary() {
	const popup = document.getElementById("agent-summary-popup");
	activeAgentSummary = null;
	popup.classList.remove("visible");
	setTimeout(() => {
		if (!activeAgentSummary) popup.classList.add("hidden");
	}, 180);
	showNextAgentSummary();
}
function clearAgentSummaryQueue() {
	agentSummaryQueue.length = 0;
	activeAgentSummary = null;
	finalResultReviewId = null;
	const popup = document.getElementById("agent-summary-popup");
	popup.classList.remove("visible");
	popup.classList.add("hidden");
}
function requestNotifPermission() {
	if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}
function sendCompletionNotification() {
	if (!("Notification" in window) || Notification.permission !== "granted") return;
	if (document.hasFocus()) return;
	const body = copy("notifications.completedIn", { elapsed: fmtDuration(reviewElapsedSeconds()) });
	const n = new Notification(copy("page.title"), { body });
	n.onclick = () => {
		window.focus();
		n.close();
	};
}
function setGlobalStatus(state, detail = "") {
	const el = document.getElementById("global-status");
	el.className = `badge badge-${state}`;
	currentGlobalStatusState = state;
	el.textContent = state === "error" && detail ? copy("status.failedWithReason", { reason: compactStatusDetail(detail) }) : copy(`status.${state}`);
	el.title = detail;
}
function resetCards() {
	currentResultsView = null;
	returnToHistoryOnResultsClose = false;
	for (const k of Object.keys(agentTimerIds)) {
		clearInterval(agentTimerIds[k]);
		delete agentTimerIds[k];
	}
	for (const k of Object.keys(agentStartTimes)) delete agentStartTimes[k];
	for (const k of Object.keys(agentEndTimes)) delete agentEndTimes[k];
	for (const k of Object.keys(agentStepProgress)) delete agentStepProgress[k];
	currentActiveAgent = null;
	clearReviewElapsedTimer();
	clearAgentSummaryQueue();
	document.querySelectorAll(".agent-card").forEach((card) => {
		const agent = card.dataset.agent;
		card.classList.remove(...CARD_STATES, "steps-open");
		if (agent !== "data") wireAgentCardInteractions(card, agent);
		card.querySelector(".agent-status-label").textContent = copy("status.idle");
		const elapsed = card.querySelector(".agent-elapsed");
		if (elapsed) elapsed.textContent = "";
		if (agent !== "data") clearStreamLog(agent);
	});
	dataLoaderTickerStatus.clear();
	renderDataLoaderHistory();
	setDataLoaderExpanded(false);
	setDataLoaderStatus("idle", copy("dataLoader.waitingToLoad"));
	setButtonBusy(document.getElementById("start-btn"), false);
	setStopButtonRunning(false);
	renderRibbon();
}
//#endregion
//#region frontend/advisor/src/main.js
startApp();
//#endregion
