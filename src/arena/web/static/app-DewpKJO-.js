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
//#region frontend/arena/src/app.js
var AGENTS = [{
	id: "baseline",
	label: "Baseline",
	tag: "Plain LLM"
}, {
	id: "advisor_enabled",
	label: "PortVise-Advised",
	tag: "LLM + PortVise"
}];
var root = null;
function startApp(mount) {
	root = mount;
	window.addEventListener("hashchange", route);
	route();
}
async function api(path, options) {
	const res = await fetch(path, options);
	if (!res.ok) {
		let detail = res.statusText;
		try {
			detail = (await res.json()).detail || detail;
		} catch (_) {}
		throw new Error(detail);
	}
	return res.json();
}
var getJSON = (path) => api(path);
var postJSON = (path, body) => api(path, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify(body)
});
var deleteJSON = (path) => api(path, { method: "DELETE" });
var money = (v) => (v ?? 0).toLocaleString("en-US", {
	style: "currency",
	currency: "USD",
	maximumFractionDigits: 0
});
var money2 = (v) => (v ?? 0).toLocaleString("en-US", {
	style: "currency",
	currency: "USD",
	maximumFractionDigits: 2
});
var pct = (v) => `${((v ?? 0) * 100).toFixed(2)}%`;
var signedPct = (v) => `${v >= 0 ? "+" : ""}${((v ?? 0) * 100).toFixed(2)}%`;
var cls = (v) => v > 0 ? "pos" : v < 0 ? "neg" : "";
var statusText = (status) => ({
	not_started: "not run",
	pending: "pending",
	running: "running",
	complete: "complete",
	failed: "failed",
	partial: "partial"
})[status || ""] || "unknown";
var statusClass = (status) => ({
	not_started: "idle",
	pending: "pending",
	running: "running",
	complete: "completed",
	failed: "failed",
	partial: "failed"
})[status || ""] || "idle";
var fileSize = (bytes) => {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
var esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({
	"&": "&amp;",
	"<": "&lt;",
	">": "&gt;",
	"\"": "&quot;"
})[c]);
function parseStamp(s) {
	const m = String(s ?? "").match(/^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})Z)?/);
	if (!m) return null;
	return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)));
}
function asDate(s) {
	if (!s) return null;
	const iso = new Date(s);
	return Number.isNaN(iso.getTime()) ? parseStamp(s) : iso;
}
var fmtDate = (s) => {
	const d = parseStamp(s);
	return d ? d.toLocaleDateString("en-US", {
		month: "short",
		day: "numeric",
		timeZone: "UTC"
	}) : String(s ?? "—");
};
var fmtClock = (s) => {
	const d = asDate(s);
	return d ? d.toLocaleTimeString([], {
		hour: "2-digit",
		minute: "2-digit"
	}) : "";
};
var fmtWhen = (s) => {
	const d = asDate(s);
	if (!d) return "—";
	return `${d.toLocaleDateString("en-US", {
		weekday: "short",
		month: "short",
		day: "numeric"
	})} ${d.toLocaleTimeString([], {
		hour: "2-digit",
		minute: "2-digit"
	})}`;
};
var relTime = (s) => {
	const d = asDate(s);
	if (!d) return "";
	const mins = Math.round((d.getTime() - Date.now()) / 6e4);
	if (mins <= 0) return "any moment now";
	if (mins < 60) return `in ${mins}m`;
	return `in ${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
};
function csvRows(text) {
	const rows = [];
	let row = [];
	let cell = "";
	let quoted = false;
	for (let i = 0; i < text.length; i += 1) {
		const char = text[i];
		if (char === "\"") if (quoted && text[i + 1] === "\"") {
			cell += "\"";
			i += 1;
		} else quoted = !quoted;
		else if (char === "," && !quoted) {
			row.push(cell.trim());
			cell = "";
		} else if ((char === "\n" || char === "\r") && !quoted) {
			if (char === "\r" && text[i + 1] === "\n") i += 1;
			row.push(cell.trim());
			if (row.some(Boolean)) rows.push(row);
			row = [];
			cell = "";
		} else cell += char;
	}
	row.push(cell.trim());
	if (row.some(Boolean)) rows.push(row);
	return rows;
}
function parseWatchlistText(text) {
	const rows = csvRows(String(text ?? "").replace(/^\uFEFF/, "").trim());
	if (!rows.length) throw new Error("Investment pool file is empty.");
	const tickerColumn = rows[0].map((cell) => cell.toLowerCase()).findIndex((cell) => [
		"ticker",
		"tickers",
		"symbol",
		"symbols"
	].includes(cell));
	let rawSymbols;
	if (tickerColumn >= 0) rawSymbols = rows.slice(1).map((row) => row[tickerColumn] || "");
	else if (rows.every((row) => row.length === 1)) rawSymbols = rows.flatMap((row) => row[0].split(/\s+/));
	else if (rows.length === 1) rawSymbols = rows[0];
	else throw new Error("CSV must include a 'ticker' or 'symbol' column.");
	const symbols = [];
	const seen = /* @__PURE__ */ new Set();
	rawSymbols.forEach((raw) => {
		const symbol = raw.trim().toUpperCase();
		if (!symbol) return;
		if (!/^[A-Z0-9][A-Z0-9.-]*$/.test(symbol)) throw new Error(`Invalid ticker symbol: ${raw}.`);
		if (!seen.has(symbol)) {
			symbols.push(symbol);
			seen.add(symbol);
		}
	});
	if (!symbols.length) throw new Error("Investment pool file contains no ticker symbols.");
	return symbols;
}
function route() {
	clearDashTimer();
	const hash = window.location.hash || "#/";
	if (hash === "#/new") return renderSetup();
	if (hash.startsWith("#/c/")) return renderDashboard(decodeURIComponent(hash.slice(4)));
	return renderHome();
}
var go = (hash) => {
	window.location.hash = hash;
};
function shell(content) {
	root.innerHTML = `
    <header class="topbar">
      <a class="brand" href="#/">
        <span class="brand-logo">Port<span class="accent">Vise</span></span>
        <span class="brand-divider" aria-hidden="true"></span>
        <span class="brand-tag">Arena</span>
      </a>
      <nav><a class="btn ghost" href="#/">Competitions</a><a class="btn" href="#/new">+ New</a></nav>
    </header>
    <main class="container">${content}</main>`;
}
function loading(msg = "Loading…") {
	shell(`<div class="card empty">${esc(msg)}</div>`);
}
function fatal(err) {
	shell(`<div class="card error">⚠ ${esc(err.message || err)}</div>`);
}
async function renderHome() {
	loading();
	let comps;
	try {
		comps = await getJSON("/api/competitions");
	} catch (e) {
		return fatal(e);
	}
	shell(`<h1>Competitions</h1><div class="grid">${comps.length ? comps.map((c) => {
		const rows = AGENTS.map((a) => {
			const st = c.agent_status?.[a.id] || {};
			return `<div class="mini"><span>${a.label}</span>
                <b class="${cls(c.standings[a.id])}" title="Total return since competition start">${signedPct(c.standings[a.id])}</b>
                <em class="mini-status ${statusClass(st.status)}">${esc(statusText(st.status))}</em></div>`;
		}).join("");
		return `<div class="card comp" role="link" tabindex="0" data-href="#/c/${encodeURIComponent(c.run_id)}">
            <div class="comp-head">
              <h3>${esc(c.run_name)}</h3>
              <span class="comp-actions">
                <button class="icon-btn danger remove-competition" type="button" title="Remove competition" aria-label="Remove ${esc(c.run_name)}" data-run-id="${esc(c.run_id)}" data-run-name="${esc(c.run_name)}">×</button>
                <span class="pill ${c.status}">${esc(c.status)}</span>
              </span>
            </div>
            <div class="muted">${c.rounds} round(s) · last round ${esc(fmtDate(c.last_round_date))}</div>
            <div class="standings">${rows}</div>
          </div>`;
	}).join("") : `<div class="card empty">No competitions yet. <a href="#/new">Create one →</a></div>`}</div>`);
	document.querySelectorAll(".comp[data-href]").forEach((card) => {
		card.addEventListener("click", () => go(card.dataset.href));
		card.addEventListener("keydown", (event) => {
			if (event.key === "Enter" || event.key === " ") {
				event.preventDefault();
				go(card.dataset.href);
			}
		});
	});
	document.querySelectorAll(".remove-competition").forEach((button) => {
		button.addEventListener("click", async (event) => {
			event.preventDefault();
			event.stopPropagation();
			const runId = button.dataset.runId;
			const runName = button.dataset.runName || runId;
			if (!runId || !window.confirm(`Remove competition "${runName}"? This cannot be undone.`)) return;
			button.disabled = true;
			try {
				await deleteJSON(`/api/competitions/${encodeURIComponent(runId)}`);
				await renderHome();
			} catch (e) {
				button.disabled = false;
				window.alert(e.message || String(e));
			}
		});
	});
}
async function renderSetup() {
	loading("Loading defaults…");
	let d;
	try {
		d = await getJSON("/api/defaults");
	} catch (e) {
		return fatal(e);
	}
	shell(`
    <h1>New competition</h1>
    <div class="setup">
      <section class="card">
        <h3>Rules</h3>
        <div class="form-grid">
          ${field("run_name", "Run name", "text", "advisor-arena")}
          ${field("starting_cash", "Initial capital ($)", "number", d.starting_cash)}
          ${field("max_position_weight", "Max weight per single position (0–1)", "number", d.max_position_weight, "0.01")}
          ${field("max_holdings", "Max holdings (count)", "number", d.max_holdings, "1")}
          ${field("cash_return_annual_pct", "Cash return (% / yr)", "number", d.cash_return_annual_pct, "0.1")}
          ${field("min_cash_weight", "Min cash weight (0–1)", "number", d.min_cash_weight, "0.01")}
          ${field("transaction_cost_bps", "Transaction cost (bps)", "number", d.transaction_cost_bps, "0.1")}
          ${field("min_trade_value", "Min trade value ($)", "number", d.min_trade_value)}
          ${field("benchmark", "Benchmark", "text", d.benchmark)}
          ${field("trade_time", "Trade time (HH:MM)", "text", d.trade_time)}
          ${field("timezone", "Timezone", "text", d.timezone)}
          ${field("advisor_timeout_seconds", "Advisor timeout (s)", "number", d.advisor_timeout_seconds)}
        </div>
      </section>

      <section class="card">
        <h3>Investment pool</h3>
        <p class="muted">Upload a CSV with a ticker or symbol column, or a text file with one ticker per line ·
          <a href="/sample_watchlist.csv" download>sample</a></p>
        <label class="file-picker" for="watchlist-file">
          <span class="file-picker-title">Choose investment pool file</span>
          <span class="file-picker-hint">CSV or TXT</span>
        </label>
        <input class="file-input" type="file" id="watchlist-file" accept=".csv,.txt,text/csv,text/plain" />
        <div id="watchlist-file-state" class="file-state empty">
          <span class="file-state-icon">CSV</span>
          <span><b>No file selected</b><small>Choose an investment pool file to preview its tickers.</small></span>
        </div>
        <div id="watchlist-preview"></div>
      </section>

      <section class="card">
        <h3>Initial positions</h3>
        <p class="muted">Columns: ticker,name,sector,quantity,entry_date,entry_price,entry_thesis ·
          <a href="/sample_positions.csv" download>sample</a></p>
        <label class="file-picker" for="csv-file">
          <span class="file-picker-title">Choose initial positions file</span>
          <span class="file-picker-hint">CSV</span>
        </label>
        <input class="file-input" type="file" id="csv-file" accept=".csv,text/csv" />
        <div id="positions-file-state" class="file-state empty">
          <span class="file-state-icon">CSV</span>
          <span><b>No file selected</b><small>Choose a positions file to validate and preview it.</small></span>
        </div>
        <div id="positions-preview"></div>
      </section>

      <div class="actions">
        <button class="btn big" id="create-btn" type="button" disabled>Create competition</button>
        <span id="setup-msg" class="muted"></span>
      </div>
    </div>
  `);
	let positions = [];
	let watchlist = [];
	const setMsg = (m, isErr) => {
		const el = document.getElementById("setup-msg");
		el.textContent = m;
		el.className = isErr ? "error-text" : "muted";
	};
	const updateCreateState = () => {
		document.getElementById("create-btn").disabled = positions.length === 0 || watchlist.length === 0;
	};
	const renderFileState = (id, file, status, detail) => {
		const el = document.getElementById(id);
		const displayName = file?.name || (status === "loading" || status === "success" ? "Pasted CSV" : "No file selected");
		el.className = `file-state ${status}`;
		el.innerHTML = `
      <span class="file-state-icon">${status === "error" ? "!" : "CSV"}</span>
      <span><b>${esc(displayName)}</b>
        <small>${file ? `${fileSize(file.size)} · ` : ""}${esc(detail)}</small></span>`;
	};
	const parsePositions = async (csvText, file = null) => {
		try {
			positions = (await postJSON("/api/positions/parse-csv", { csv_text: csvText })).positions;
			renderPositionsPreview(positions);
			updateCreateState();
			renderFileState("positions-file-state", file, "success", `${positions.length} position(s) validated`);
			setMsg(`Parsed ${positions.length} initial position(s).`, false);
		} catch (error) {
			positions = [];
			updateCreateState();
			document.getElementById("positions-preview").innerHTML = "";
			renderFileState("positions-file-state", file, "error", error.message);
			setMsg(error.message, true);
		}
	};
	document.getElementById("watchlist-file").addEventListener("change", async (e) => {
		const file = e.target.files[0];
		watchlist = [];
		renderWatchlistPreview(watchlist);
		updateCreateState();
		if (!file) {
			renderFileState("watchlist-file-state", null, "empty", "Choose an investment pool file to preview its tickers.");
			return;
		}
		try {
			watchlist = parseWatchlistText(await file.text());
			renderWatchlistPreview(watchlist);
			updateCreateState();
			renderFileState("watchlist-file-state", file, "success", `${watchlist.length} unique ticker(s) loaded`);
			setMsg(`Loaded ${watchlist.length} investment-pool ticker(s).`, false);
		} catch (error) {
			renderFileState("watchlist-file-state", file, "error", error.message);
			setMsg(error.message, true);
		}
	});
	document.getElementById("csv-file").addEventListener("change", async (e) => {
		const file = e.target.files[0];
		if (!file) {
			positions = [];
			renderPositionsPreview(positions);
			updateCreateState();
			renderFileState("positions-file-state", null, "empty", "Choose a positions file to validate and preview it.");
			return;
		}
		const csvText = await file.text();
		renderFileState("positions-file-state", file, "loading", "Validating positions…");
		await parsePositions(csvText, file);
	});
	document.getElementById("create-btn").addEventListener("click", async () => {
		const num = (id) => parseFloat(document.getElementById(id).value);
		if (!watchlist.length) return setMsg("Investment pool cannot be empty.", true);
		const body = {
			run_name: document.getElementById("run_name").value.trim() || "advisor-arena",
			starting_cash: num("starting_cash"),
			transaction_cost_bps: num("transaction_cost_bps"),
			max_position_weight: num("max_position_weight"),
			max_holdings: parseInt(document.getElementById("max_holdings").value, 10),
			cash_return_annual_pct: num("cash_return_annual_pct"),
			min_trade_value: num("min_trade_value"),
			min_cash_weight: num("min_cash_weight"),
			benchmark: document.getElementById("benchmark").value.trim().toUpperCase(),
			trade_time: document.getElementById("trade_time").value.trim(),
			timezone: document.getElementById("timezone").value.trim(),
			corporate_actions: d.corporate_actions,
			advisor_timeout_seconds: num("advisor_timeout_seconds"),
			watchlist,
			positions,
			notes: ""
		};
		setMsg("Creating… fetching opening prices.", false);
		document.getElementById("create-btn").disabled = true;
		try {
			const res = await postJSON("/api/competitions", body);
			go(`#/c/${encodeURIComponent(res.run_id)}`);
		} catch (e) {
			setMsg(e.message, true);
			document.getElementById("create-btn").disabled = false;
		}
	});
}
function field(id, label, type, value, step) {
	const stepAttr = step ? ` step="${step}"` : type === "number" ? " step=\"any\"" : "";
	return `<label class="fld"><span>${esc(label)}</span>
    <input id="${id}" type="${type}" value="${esc(value)}"${stepAttr} /></label>`;
}
function renderPositionsPreview(positions) {
	if (!positions.length) {
		document.getElementById("positions-preview").innerHTML = "";
		return;
	}
	const totalCost = positions.reduce((sum, position) => sum + position.quantity * position.entry_price, 0);
	const sectors = new Set(positions.map((position) => position.sector).filter(Boolean)).size;
	const rows = positions.map((p) => `<tr><td>${esc(p.ticker)}</td><td>${esc(p.name)}</td><td>${esc(p.sector)}</td>
         <td class="num">${p.quantity}</td><td class="num">${money2(p.entry_price)}</td></tr>`).join("");
	document.getElementById("positions-preview").innerHTML = `
    <div class="upload-summary">
      <span><b>${positions.length}</b> positions</span>
      <span><b>${sectors}</b> sectors</span>
      <span><b>${money2(totalCost)}</b> entry value</span>
    </div>
    <div class="preview-table"><table class="tbl"><thead><tr><th>Ticker</th><th>Name</th><th>Sector</th>
      <th class="num">Qty</th><th class="num">Entry</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function renderWatchlistPreview(watchlist) {
	const visible = watchlist.slice(0, 30);
	const remaining = watchlist.length - visible.length;
	document.getElementById("watchlist-preview").innerHTML = watchlist.length ? `<div class="upload-summary"><span><b>${watchlist.length}</b> unique tickers</span></div>
       <div class="ticker-list">${visible.map((ticker) => `<span>${esc(ticker)}</span>`).join("")}
       ${remaining > 0 ? `<span class="ticker-more">+${remaining} more</span>` : ""}</div>` : "";
}
var AGENT_LABEL = Object.fromEntries(AGENTS.map((a) => [a.id, a.label]));
var dashTimer = null;
var manualRunActive = false;
var dashFingerprint = "";
function clearDashTimer() {
	if (dashTimer) {
		clearInterval(dashTimer);
		dashTimer = null;
	}
}
function dashboardFingerprint(data) {
	return JSON.stringify([
		data.rounds,
		data.metadata?.last_round_date,
		data.round_status?.phase,
		data.round_status?.attempts,
		AGENTS.map((a) => data.agents[a.id]?.run_status?.status)
	]);
}
function roundStatusInner(rs) {
	if (!rs) return "";
	const err = rs.last_error ? `<div class="strip-detail">${esc(rs.last_error)}</div>` : "";
	if (rs.phase === "running") return `<span class="dot pulse"></span><span><b>Round in progress</b> — ${esc(AGENT_LABEL[rs.running_agent] || "agents")} trading now</span>`;
	if (rs.phase === "due") return `<span class="dot pulse"></span><span><b>Round due</b> — the engine starts it within ~30 s</span>`;
	if (rs.phase === "complete") return `<span class="dot ok"></span><span><b>Today's round complete</b>${rs.completed_at ? ` at ${fmtClock(rs.completed_at)}` : ""} ·
      next round ${esc(fmtWhen(rs.next_run_at))} (${esc(relTime(rs.next_run_at))})</span>`;
	if (rs.phase === "retrying") return `<span class="dot warn"></span><span><b>Round failed</b> (attempt ${rs.attempts}/${rs.max_attempts})
      — retrying ${esc(relTime(rs.next_attempt_at))}</span>${err}`;
	if (rs.phase === "failed") return `<span class="dot bad"></span><span><b>Round failed ${rs.attempts}×</b> —
      giving up until ${esc(fmtWhen(rs.next_run_at))}</span>${err}`;
	return `<span class="dot"></span><span>${rs.market_open_today ? "" : "Market closed (weekend) · "}<b>Next round</b>
    ${esc(fmtWhen(rs.next_run_at))} (${esc(relTime(rs.next_run_at))})</span>`;
}
async function refreshDashboard(runId) {
	if (manualRunActive) return;
	let data;
	try {
		data = await getJSON(`/api/competitions/${encodeURIComponent(runId)}`);
	} catch (e) {
		const strip = document.getElementById("round-status-strip");
		if (strip) strip.innerHTML = `<span class="dot bad"></span><span>Status refresh failed: ${esc(e.message)}</span>`;
		return;
	}
	if (dashboardFingerprint(data) !== dashFingerprint) {
		renderDashboard(runId);
		return;
	}
	const strip = document.getElementById("round-status-strip");
	if (strip) strip.innerHTML = roundStatusInner(data.round_status);
}
async function renderDashboard(runId) {
	clearDashTimer();
	loading("Loading competition…");
	let data;
	try {
		data = await getJSON(`/api/competitions/${encodeURIComponent(runId)}`);
	} catch (e) {
		return fatal(e);
	}
	const bench = benchmarkReturn(data.benchmark_series);
	shell(`
    <div class="dash-head">
      <div><h1>${esc(data.config.run_name)}</h1>
        <div class="muted">${data.rounds} round(s) ·
          benchmark ${esc(data.config.benchmark)} ${signedPct(bench)} since start</div></div>
      <div class="dash-actions">
        <button class="btn big" id="run-btn">Run round now</button>
        <div id="run-status" class="run-status"></div>
      </div>
    </div>
    <div id="round-status-strip" class="status-strip ${esc(data.round_status?.phase || "")}">
      ${roundStatusInner(data.round_status)}
    </div>
    <div class="scoreboard">${AGENTS.map((a) => scoreCard(a, data, bench)).join("")}</div>
    <section class="card"><h3>Equity curve</h3>${equityChart(data)}</section>
    ${advisorPanel(data.advisor_insight)}
    <div class="cols">${AGENTS.map((a) => holdingsCard(a, data)).join("")}</div>
    <section class="card"><h3>Transaction log</h3>
      <div class="tabs" id="ledger-tabs">
        ${AGENTS.map((a, i) => `<button class="tab ${i === 0 ? "active" : ""}" data-agent="${a.id}">${a.label}</button>`).join("")}
      </div>
      <div id="ledger-body" class="ledger-body">Loading…</div>
    </section>
  `);
	document.getElementById("run-btn").addEventListener("click", () => runRound(runId));
	const tabs = document.getElementById("ledger-tabs");
	tabs.addEventListener("click", (e) => {
		const btn = e.target.closest(".tab");
		if (!btn) return;
		[...tabs.children].forEach((c) => c.classList.toggle("active", c === btn));
		loadLedger(runId, btn.dataset.agent);
	});
	loadLedger(runId, AGENTS[0].id);
	wireChart();
	dashFingerprint = dashboardFingerprint(data);
	dashTimer = setInterval(() => refreshDashboard(runId), 25e3);
}
function agentMetrics(agentId, data) {
	const state = data.agents[agentId].state;
	const series = data.equity_series[agentId] || [];
	const first = series.length ? series[0].equity : state.equity;
	return {
		state,
		totalReturn: first > 0 ? state.equity / first - 1 : 0,
		row: (data.leaderboard || []).find((r) => r.agent_id === agentId) || {}
	};
}
function scoreCard(agent, data, bench) {
	const { state, totalReturn, row } = agentMetrics(agent.id, data);
	const st = data.agents[agent.id].run_status || {};
	const series = data.equity_series[agent.id] || [];
	const since = series.length ? fmtDate(series[0].date) : null;
	const cashPct = state.equity > 0 ? state.cash / state.equity : 0;
	const excess = (row.excess_return_vs_benchmark ?? totalReturn - bench) || 0;
	const benchName = esc(data.config.benchmark);
	return `<div class="card score ${agent.id}">
    <div class="score-head"><h3>${agent.label}</h3>
      <span class="agent-tags"><span class="tag">${agent.tag}</span>
      <span class="tag status ${statusClass(st.status)}"
        title="Last completed round: ${esc(fmtDate(st.last_completed_round))}">${esc(statusText(st.status))}</span></span></div>
    <div class="equity">${money(state.equity)}</div>
    <div class="ret ${cls(totalReturn)}">${signedPct(totalReturn)}<span class="ret-note"> total${since ? ` since ${esc(since)}` : ""}</span></div>
    <div class="metrics">
      <div><span title="Total return minus ${benchName} price return over the same period">vs ${benchName}</span>
        <b class="${cls(excess)}">${signedPct(excess)}</b></div>
      <div><span title="Positions currently held">Holdings</span><b>${Object.keys(state.holdings).length}</b></div>
      <div><span title="Cash as a share of current equity">Cash</span><b>${pct(cashPct)}</b></div>
      <div><span title="Largest peak-to-trough equity decline so far">Max DD</span><b class="neg">${pct(row.max_drawdown ?? 0)}</b></div>
      <div><span title="Sum over rounds of traded value ÷ equity">Turnover</span><b>${pct(row.turnover ?? 0)}</b></div>
    </div>
  </div>`;
}
function holdingsCard(agent, data) {
	const holdings = data.agents[agent.id].holdings || [];
	const rows = holdings.length ? holdings.map((h) => `<tr><td>${esc(h.ticker)}</td><td class="num">${h.quantity.toFixed(2)}</td>
             <td class="num">${money2(h.average_cost)}</td><td class="num">${money2(h.price)}</td>
             <td class="num">${money(h.mkt_value)}</td>
             <td class="num ${cls(h.unrealized_pnl)}">${signedMoney(h.unrealized_pnl)}</td>
             <td class="num">${pct(h.weight)}</td></tr>`).join("") : `<tr><td colspan="7" class="muted">All cash.</td></tr>`;
	return `<section class="card"><h3>${agent.label} — holdings</h3>
    <div class="holdings-table-wrap">
      <table class="tbl holdings-table">
        <colgroup>
          <col class="holding-ticker"><col class="holding-qty"><col class="holding-avg">
          <col class="holding-price"><col class="holding-value"><col class="holding-pnl">
          <col class="holding-weight">
        </colgroup>
        <thead><tr><th>Ticker</th><th class="num">Qty</th><th class="num">Avg cost</th>
          <th class="num">Price</th><th class="num">Value</th><th class="num">Unreal. P&L</th><th class="num">Weight</th>
        </tr></thead><tbody>${rows}</tbody>
      </table>
    </div>
  </section>`;
}
var signedMoney = (v) => `${v >= 0 ? "+" : "−"}${money2(Math.abs(v)).replace("$", "$")}`;
function advisorPanel(insight) {
	if (!insight) return "";
	const v = insight.portfolio_verdict || {};
	const risks = (insight.top_risks || []).map((r) => `<li>${esc(r)}</li>`).join("");
	return `<section class="card advisor">
    <h3>PortVise insight <span class="muted">(drove the advised agent · ${esc(fmtDate(insight.as_of))})</span></h3>
    ${insight.executive_summary ? `<p>${esc(insight.executive_summary)}</p>` : ""}
    ${v.recommended_posture ? `<div class="verdict"><b>Posture:</b> ${esc(v.recommended_posture)} ·
       <b>Timing:</b> ${esc(v.action_timing || "")} · <b>Primary risk:</b> ${esc(v.primary_risk || "")}</div>` : ""}
    ${risks ? `<b>Top risks</b><ul>${risks}</ul>` : ""}
  </section>`;
}
async function loadLedger(runId, agentId) {
	const body = document.getElementById("ledger-body");
	body.textContent = "Loading…";
	let trades;
	try {
		trades = (await getJSON(`/api/competitions/${encodeURIComponent(runId)}/agents/${agentId}/ledger`)).trades;
	} catch (e) {
		body.innerHTML = `<div class="error-text">${esc(e.message)}</div>`;
		return;
	}
	if (!trades.length) {
		body.innerHTML = `<div class="muted">No trades yet.</div>`;
		return;
	}
	body.innerHTML = `<table class="tbl"><thead><tr><th>Date</th><th>Side</th><th>Ticker</th>
    <th class="num">Qty</th><th class="num">Price</th><th class="num">Fee</th>
    <th class="num">Realized P&L</th><th class="num">Cash after</th></tr></thead><tbody>${trades.slice().reverse().map((t) => `<tr><td>${esc(fmtDate(t.date))}</td><td class="${t.side}">${t.side.toUpperCase()}</td>
         <td>${esc(t.ticker)}</td><td class="num">${t.quantity.toFixed(2)}</td>
         <td class="num">${money2(t.price)}</td><td class="num">${money2(t.transaction_cost)}</td>
         <td class="num ${cls(t.realized_pnl)}">${t.side === "sell" ? signedMoney(t.realized_pnl) : "—"}</td>
         <td class="num">${money2(t.cash_after)}</td></tr>`).join("")}</tbody></table>`;
}
function runRound(runId) {
	const btn = document.getElementById("run-btn");
	const status = document.getElementById("run-status");
	btn.disabled = true;
	manualRunActive = true;
	status.className = "run-status active";
	status.textContent = "Starting…";
	const es = new EventSource(`/api/competitions/${encodeURIComponent(runId)}/run-round`);
	es.onmessage = (ev) => {
		const msg = JSON.parse(ev.data);
		if (msg.type === "progress") status.textContent = msg.message || msg.stage;
		else if (msg.type === "done") {
			es.close();
			manualRunActive = false;
			status.textContent = "Round complete.";
			renderDashboard(runId);
		} else if (msg.type === "error") {
			es.close();
			manualRunActive = false;
			status.className = "run-status error-text";
			status.textContent = `Error: ${msg.error}`;
			btn.disabled = false;
		}
	};
	es.onerror = () => {
		es.close();
		manualRunActive = false;
		status.className = "run-status error-text";
		status.textContent = "Connection lost.";
		btn.disabled = false;
	};
}
function benchmarkReturn(series) {
	if (!series || series.length < 2 || !series[0].price) return 0;
	return series[series.length - 1].price / series[0].price - 1;
}
function niceTicks(lo, hi, n = 4) {
	const rawStep = (hi - lo) / Math.max(1, n);
	const mag = 10 ** Math.floor(Math.log10(Math.max(rawStep, 1e-9)));
	const norm = rawStep / mag;
	const step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
	const ticks = [];
	for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(v);
	return ticks;
}
var axisPct = (v) => `${v - 100 >= 0 ? "+" : ""}${(v - 100).toFixed(1)}%`;
var chartModel = null;
function equityChart(data) {
	const series = [];
	AGENTS.forEach((a, i) => {
		const pts = data.equity_series[a.id] || [];
		if (pts.length) series.push({
			label: a.label,
			color: i === 0 ? "#79a8ff" : "#69d8a8",
			dates: pts.map((p) => p.date),
			raw: pts.map((p) => p.equity),
			money: true
		});
	});
	const bench = data.benchmark_series || [];
	if (bench.length) series.push({
		label: `${data.config.benchmark} (price)`,
		color: "#e0c26f",
		dashed: true,
		dates: bench.map((p) => p.date),
		raw: bench.map((p) => p.price),
		money: false
	});
	if (!series.length || series.every((s) => s.raw.length < 2)) {
		chartModel = null;
		return `<div class="muted chart-empty">Run at least one round to plot the curve.</div>`;
	}
	series.forEach((s) => {
		s.idx = s.raw.map((v) => v / s.raw[0] * 100);
	});
	const W = 920;
	const H = 300;
	const padL = 56;
	const padR = 16;
	const padT = 12;
	const padB = 30;
	const maxLen = Math.max(...series.map((s) => s.idx.length));
	const all = series.flatMap((s) => s.idx);
	let lo = Math.min(...all, 100);
	let hi = Math.max(...all, 100);
	const span = Math.max(hi - lo, .5);
	lo -= span * .06;
	hi += span * .06;
	const x = (i) => padL + i / Math.max(1, maxLen - 1) * (W - padL - padR);
	const y = (v) => H - padB - (v - lo) / (hi - lo) * (H - padT - padB);
	const grid = niceTicks(lo, hi).map((v) => {
		const isBase = Math.abs(v - 100) < 1e-9;
		return `<line x1="${padL}" y1="${y(v).toFixed(1)}" x2="${W - padR}" y2="${y(v).toFixed(1)}"
        stroke="${isBase ? "#3a4a5c" : "#1c2532"}" ${isBase ? "stroke-dasharray=\"2 3\"" : ""}/>
      <text x="${padL - 8}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end" class="axis">${axisPct(v)}</text>`;
	}).join("");
	const labels = series.find((s) => s.dates.length === maxLen).dates;
	const tickCount = Math.min(6, maxLen);
	const xLabels = [...new Set(Array.from({ length: tickCount }, (_, k) => Math.round(k * (maxLen - 1) / Math.max(1, tickCount - 1))))].map((i) => `<text x="${x(i).toFixed(1)}" y="${H - padB + 17}" text-anchor="middle" class="axis">${esc(fmtDate(labels[i]))}</text>`).join("");
	const paths = series.map((s) => {
		return `<path d="${s.idx.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2" ${s.dashed ? "stroke-dasharray=\"5 4\"" : ""}/>`;
	}).join("");
	chartModel = {
		series,
		labels,
		maxLen,
		W,
		padL,
		padR
	};
	return `<div class="legend">${series.map((s) => `<span class="leg"><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("")}</div>
    <div class="chart-wrap" id="chart-wrap">
      <svg viewBox="0 0 ${W} ${H}" class="chart" id="chart-svg">
        ${grid}${xLabels}${paths}
        <line id="chart-guide" x1="0" x2="0" y1="${padT}" y2="${H - padB}" stroke="#3a4a5c" visibility="hidden"/>
      </svg>
      <div class="chart-tip" id="chart-tip" hidden></div>
    </div>
    <p class="muted chart-note">All lines indexed to 100 at competition start; the left axis is return since start.
      ${esc(data.config.benchmark)} (dashed) is price return, excluding dividends. Hover for daily values.</p>`;
}
function wireChart() {
	const svg = document.getElementById("chart-svg");
	if (!svg || !chartModel) return;
	const wrap = document.getElementById("chart-wrap");
	const tip = document.getElementById("chart-tip");
	const guide = document.getElementById("chart-guide");
	const { series, labels, maxLen, W, padL, padR } = chartModel;
	svg.addEventListener("mouseleave", () => {
		tip.hidden = true;
		guide.setAttribute("visibility", "hidden");
	});
	svg.addEventListener("mousemove", (ev) => {
		const rect = svg.getBoundingClientRect();
		const vx = (ev.clientX - rect.left) / rect.width * W;
		const i = Math.max(0, Math.min(maxLen - 1, Math.round((vx - padL) / (W - padL - padR) * (maxLen - 1))));
		const px = padL + i / Math.max(1, maxLen - 1) * (W - padL - padR);
		guide.setAttribute("x1", px);
		guide.setAttribute("x2", px);
		guide.setAttribute("visibility", "visible");
		const rows = series.filter((s) => i < s.raw.length).map((s) => {
			const chg = s.idx[i] - 100;
			const val = s.money ? money2(s.raw[i]) : s.raw[i].toFixed(2);
			return `<div><i style="background:${s.color}"></i>${esc(s.label)}
          <b>${val}</b><em class="${cls(chg)}">${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</em></div>`;
		}).join("");
		tip.innerHTML = `<div class="tip-date">${esc(fmtDate(labels[i]))}</div>${rows}`;
		tip.hidden = false;
		const wrapRect = wrap.getBoundingClientRect();
		let left = ev.clientX - wrapRect.left + 14;
		if (left + tip.offsetWidth > wrapRect.width - 4) left = ev.clientX - wrapRect.left - tip.offsetWidth - 14;
		tip.style.left = `${Math.max(4, left)}px`;
		tip.style.top = `${Math.max(4, Math.min(ev.clientY - wrapRect.top + 12, wrapRect.height - tip.offsetHeight - 4))}px`;
	});
}
//#endregion
//#region frontend/arena/src/main.js
startApp(document.getElementById("app"));
//#endregion
