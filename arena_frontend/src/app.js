// PortVise Arena — standalone head-to-head trading competition GUI.

const AGENTS = [
  { id: "baseline", label: "Baseline", tag: "Plain LLM" },
  { id: "advisor_enabled", label: "PortVise-Advised", tag: "LLM + PortVise" },
];

let root = null;

export function startApp(mount) {
  root = mount;
  window.addEventListener("hashchange", route);
  route();
}

// ── API ───────────────────────────────────────────────────────────────────
async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json();
}

const getJSON = (path) => api(path);
const postJSON = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// ── Formatting ──────────────────────────────────────────────────────────────
const money = (v) =>
  (v ?? 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const money2 = (v) =>
  (v ?? 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const pct = (v) => `${((v ?? 0) * 100).toFixed(2)}%`;
const signedPct = (v) => `${v >= 0 ? "+" : ""}${((v ?? 0) * 100).toFixed(2)}%`;
const cls = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ── Router ────────────────────────────────────────────────────────────────
function route() {
  const hash = window.location.hash || "#/";
  if (hash === "#/new") return renderSetup();
  if (hash.startsWith("#/c/")) return renderDashboard(decodeURIComponent(hash.slice(4)));
  return renderHome();
}
const go = (hash) => {
  window.location.hash = hash;
};

function shell(content) {
  root.innerHTML = `
    <header class="topbar">
      <a class="brand" href="#/">PORT<span>VISE</span> ARENA</a>
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

// ── Home: list competitions ─────────────────────────────────────────────────
async function renderHome() {
  loading();
  let comps;
  try {
    comps = await getJSON("/api/competitions");
  } catch (e) {
    return fatal(e);
  }
  const cards = comps.length
    ? comps
        .map((c) => {
          const rows = AGENTS.map(
            (a) =>
              `<div class="mini"><span>${a.label}</span><b class="${cls(c.standings[a.id])}">${signedPct(
                c.standings[a.id],
              )}</b></div>`,
          ).join("");
          return `<a class="card comp" href="#/c/${encodeURIComponent(c.run_id)}">
            <div class="comp-head"><h3>${esc(c.run_name)}</h3><span class="pill ${c.status}">${esc(
              c.status,
            )}</span></div>
            <div class="muted">${c.rounds} round(s) · last ${esc(c.last_round_date || "—")}</div>
            <div class="standings">${rows}</div>
          </a>`;
        })
        .join("")
    : `<div class="card empty">No competitions yet. <a href="#/new">Create one →</a></div>`;
  shell(`<h1>Competitions</h1><div class="grid">${cards}</div>`);
}

// ── Setup: create a competition ──────────────────────────────────────────────
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
          ${field("max_position_weight", "Max position weight (0–1)", "number", d.max_position_weight, "0.01")}
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
        <h3>Investment pool (watchlist)</h3>
        <p class="muted">Tickers both agents may trade. Comma- or space-separated.</p>
        <textarea id="watchlist" rows="2" placeholder="NVDA MSFT AAPL JPM XOM SPY GLD TLT"></textarea>
      </section>

      <section class="card">
        <h3>Initial positions (CSV)</h3>
        <p class="muted">Columns: ticker,name,sector,quantity,entry_date,entry_price,entry_thesis ·
          <a href="/sample_positions.csv" download>sample</a></p>
        <input type="file" id="csv-file" accept=".csv,text/csv" />
        <textarea id="csv-text" rows="5" placeholder="Paste CSV here or choose a file…"></textarea>
        <button class="btn ghost" id="parse-btn" type="button">Preview positions</button>
        <div id="positions-preview"></div>
      </section>

      <div class="actions">
        <button class="btn big" id="create-btn" type="button" disabled>Create competition</button>
        <span id="setup-msg" class="muted"></span>
      </div>
    </div>
  `);

  let positions = [];
  const setMsg = (m, isErr) => {
    const el = document.getElementById("setup-msg");
    el.textContent = m;
    el.className = isErr ? "error-text" : "muted";
  };

  document.getElementById("csv-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) document.getElementById("csv-text").value = await file.text();
  });

  document.getElementById("parse-btn").addEventListener("click", async () => {
    const csv_text = document.getElementById("csv-text").value.trim();
    if (!csv_text) return setMsg("Provide CSV first.", true);
    try {
      const res = await postJSON("/api/positions/parse-csv", { csv_text });
      positions = res.positions;
      renderPositionsPreview(positions);
      document.getElementById("create-btn").disabled = positions.length === 0;
      setMsg(`Parsed ${positions.length} position(s).`, false);
    } catch (e) {
      positions = [];
      document.getElementById("create-btn").disabled = true;
      document.getElementById("positions-preview").innerHTML = "";
      setMsg(e.message, true);
    }
  });

  document.getElementById("create-btn").addEventListener("click", async () => {
    const num = (id) => parseFloat(document.getElementById(id).value);
    const watchlist = document
      .getElementById("watchlist")
      .value.split(/[,\s]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
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
      notes: "",
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
  const stepAttr = step ? ` step="${step}"` : type === "number" ? ' step="any"' : "";
  return `<label class="fld"><span>${esc(label)}</span>
    <input id="${id}" type="${type}" value="${esc(value)}"${stepAttr} /></label>`;
}

function renderPositionsPreview(positions) {
  const rows = positions
    .map(
      (p) =>
        `<tr><td>${esc(p.ticker)}</td><td>${esc(p.name)}</td><td>${esc(p.sector)}</td>
         <td class="num">${p.quantity}</td><td class="num">${money2(p.entry_price)}</td></tr>`,
    )
    .join("");
  document.getElementById("positions-preview").innerHTML = `
    <table class="tbl"><thead><tr><th>Ticker</th><th>Name</th><th>Sector</th>
      <th class="num">Qty</th><th class="num">Entry</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ── Dashboard ────────────────────────────────────────────────────────────────
async function renderDashboard(runId) {
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
        <div class="muted">${data.metadata.rounds || (data.benchmark_series.length)} round(s) ·
          trades ${esc(data.config.trade_time)} ${esc(data.config.timezone)} ·
          benchmark ${esc(data.config.benchmark)} ${signedPct(bench)}</div></div>
      <div class="dash-actions">
        <button class="btn big" id="run-btn">Run round now</button>
        <div id="run-status" class="run-status"></div>
      </div>
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
}

function agentMetrics(agentId, data) {
  const state = data.agents[agentId].state;
  const series = data.equity_series[agentId] || [];
  const first = series.length ? series[0].equity : state.equity;
  const totalReturn = first > 0 ? state.equity / first - 1 : 0;
  const row = (data.leaderboard || []).find((r) => r.agent_id === agentId) || {};
  return { state, totalReturn, row };
}

function scoreCard(agent, data, bench) {
  const { state, totalReturn, row } = agentMetrics(agent.id, data);
  const cashPct = state.equity > 0 ? state.cash / state.equity : 0;
  const excess = (row.excess_return_vs_benchmark ?? totalReturn - bench) || 0;
  return `<div class="card score ${agent.id}">
    <div class="score-head"><h3>${agent.label}</h3><span class="tag">${agent.tag}</span></div>
    <div class="equity">${money(state.equity)}</div>
    <div class="ret ${cls(totalReturn)}">${signedPct(totalReturn)} total</div>
    <div class="metrics">
      <div><span>vs ${esc(data.config.benchmark)}</span><b class="${cls(excess)}">${signedPct(excess)}</b></div>
      <div><span>Holdings</span><b>${Object.keys(state.holdings).length}</b></div>
      <div><span>Cash</span><b>${pct(cashPct)}</b></div>
      <div><span>Max DD</span><b class="neg">${pct(row.max_drawdown ?? 0)}</b></div>
    </div>
  </div>`;
}

function holdingsCard(agent, data) {
  const holdings = data.agents[agent.id].holdings || [];
  const rows = holdings.length
    ? holdings
        .map(
          (h) =>
            `<tr><td>${esc(h.ticker)}</td><td class="num">${h.quantity.toFixed(2)}</td>
             <td class="num">${money2(h.average_cost)}</td><td class="num">${money2(h.price)}</td>
             <td class="num">${money(h.mkt_value)}</td>
             <td class="num ${cls(h.unrealized_pnl)}">${signedMoney(h.unrealized_pnl)}</td>
             <td class="num">${pct(h.weight)}</td></tr>`,
        )
        .join("")
    : `<tr><td colspan="7" class="muted">All cash.</td></tr>`;
  return `<section class="card"><h3>${agent.label} — holdings</h3>
    <table class="tbl"><thead><tr><th>Ticker</th><th class="num">Qty</th><th class="num">Avg cost</th>
      <th class="num">Price</th><th class="num">Value</th><th class="num">Unreal. P&L</th><th class="num">Weight</th>
      </tr></thead><tbody>${rows}</tbody></table></section>`;
}

const signedMoney = (v) => `${v >= 0 ? "+" : "−"}${money2(Math.abs(v)).replace("$", "$")}`;

function advisorPanel(insight) {
  if (!insight) return "";
  const v = insight.portfolio_verdict || {};
  const risks = (insight.top_risks || []).map((r) => `<li>${esc(r)}</li>`).join("");
  return `<section class="card advisor">
    <h3>PortVise insight <span class="muted">(drove the advised agent · ${esc(insight.as_of || "")})</span></h3>
    ${insight.executive_summary ? `<p>${esc(insight.executive_summary)}</p>` : ""}
    ${v.recommended_posture ? `<div class="verdict"><b>Posture:</b> ${esc(v.recommended_posture)} ·
       <b>Timing:</b> ${esc(v.action_timing || "")} · <b>Primary risk:</b> ${esc(v.primary_risk || "")}</div>` : ""}
    ${risks ? `<b>Top risks</b><ul>${risks}</ul>` : ""}
  </section>`;
}

// ── Ledger ────────────────────────────────────────────────────────────────
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
  const rows = trades
    .slice()
    .reverse()
    .map(
      (t) =>
        `<tr><td>${esc(t.date)}</td><td class="${t.side}">${t.side.toUpperCase()}</td>
         <td>${esc(t.ticker)}</td><td class="num">${t.quantity.toFixed(2)}</td>
         <td class="num">${money2(t.price)}</td><td class="num">${money2(t.transaction_cost)}</td>
         <td class="num ${cls(t.realized_pnl)}">${t.side === "sell" ? signedMoney(t.realized_pnl) : "—"}</td>
         <td class="num">${money2(t.cash_after)}</td></tr>`,
    )
    .join("");
  body.innerHTML = `<table class="tbl"><thead><tr><th>Date</th><th>Side</th><th>Ticker</th>
    <th class="num">Qty</th><th class="num">Price</th><th class="num">Fee</th>
    <th class="num">Realized P&L</th><th class="num">Cash after</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ── Run round (SSE) ──────────────────────────────────────────────────────────
function runRound(runId) {
  const btn = document.getElementById("run-btn");
  const status = document.getElementById("run-status");
  btn.disabled = true;
  status.className = "run-status active";
  status.textContent = "Starting…";
  const es = new EventSource(`/api/competitions/${encodeURIComponent(runId)}/run-round`);
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "progress") {
      status.textContent = msg.message || msg.stage;
    } else if (msg.type === "done") {
      es.close();
      status.textContent = "Round complete.";
      renderDashboard(runId);
    } else if (msg.type === "error") {
      es.close();
      status.className = "run-status error-text";
      status.textContent = `Error: ${msg.error}`;
      btn.disabled = false;
    }
  };
  es.onerror = () => {
    es.close();
    status.className = "run-status error-text";
    status.textContent = "Connection lost.";
    btn.disabled = false;
  };
}

// ── Equity chart (hand-rolled SVG) ───────────────────────────────────────────
function benchmarkReturn(series) {
  if (!series || series.length < 2 || !series[0].price) return 0;
  return series[series.length - 1].price / series[0].price - 1;
}

function equityChart(data) {
  const lines = [];
  AGENTS.forEach((a, i) => {
    const s = (data.equity_series[a.id] || []).map((p) => p.equity);
    if (s.length) lines.push({ label: a.label, color: i === 0 ? "#7aa2f7" : "#9ece6a", values: s });
  });
  const bench = (data.benchmark_series || []).map((p) => p.price);
  if (bench.length) lines.push({ label: data.config.benchmark, color: "#e0af68", values: bench, dashed: true });
  if (!lines.length || lines.every((l) => l.values.length < 2)) {
    return `<div class="muted chart-empty">Run at least one round to plot the curve.</div>`;
  }
  // Normalize every line to base 100 for fair comparison.
  const norm = lines.map((l) => ({ ...l, values: l.values.map((v) => (v / l.values[0]) * 100) }));
  const W = 920;
  const H = 280;
  const pad = 36;
  const maxLen = Math.max(...norm.map((l) => l.values.length));
  const all = norm.flatMap((l) => l.values);
  const lo = Math.min(...all, 100);
  const hi = Math.max(...all, 100);
  const x = (i) => pad + (i / Math.max(1, maxLen - 1)) * (W - 2 * pad);
  const y = (v) => H - pad - ((v - lo) / Math.max(1e-9, hi - lo)) * (H - 2 * pad);
  const paths = norm
    .map((l) => {
      const d = l.values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
      return `<path d="${d}" fill="none" stroke="${l.color}" stroke-width="2"
        ${l.dashed ? 'stroke-dasharray="5 4"' : ""}/>`;
    })
    .join("");
  const baseY = y(100);
  const legend = norm
    .map((l) => `<span class="leg"><i style="background:${l.color}"></i>${esc(l.label)}</span>`)
    .join("");
  return `<div class="legend">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" class="chart" preserveAspectRatio="none">
      <line x1="${pad}" y1="${baseY}" x2="${W - pad}" y2="${baseY}" stroke="#3b4261" stroke-dasharray="2 3"/>
      ${paths}
    </svg>`;
}
