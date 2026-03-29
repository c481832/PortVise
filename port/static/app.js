// ── Default example positions ──────────────────────────────────────────────
const DEFAULT_POSITIONS = [
  { ticker: "NVDA", name: "Nvidia", weight: 12, sector: "Technology", asset_class: "equity",
    entry_date: "2023-06-01", entry_price: 380, current_price: 875,
    tags: "AI, semiconductors, momentum",
    entry_thesis: "AI compute monopoly, data center capex supercycle driven by LLM training demand" },
  { ticker: "MSFT", name: "Microsoft", weight: 10, sector: "Technology", asset_class: "equity",
    entry_date: "2022-10-01", entry_price: 240, current_price: 415,
    tags: "cloud, AI, software, quality",
    entry_thesis: "Azure cloud + Copilot AI monetisation; recurring revenue model with pricing power" },
  { ticker: "TLT", name: "iShares 20Y Treasury", weight: 10, sector: "Fixed Income", asset_class: "bond",
    entry_date: "2023-10-01", entry_price: 88, current_price: 91,
    tags: "duration, rates, macro",
    entry_thesis: "Duration add at rate peak; Fed pivot trade for H1 2024" },
  { ticker: "XOM", name: "ExxonMobil", weight: 8, sector: "Energy", asset_class: "equity",
    entry_date: "2022-06-01", entry_price: 95, current_price: 112,
    tags: "energy, value, FCF, inflation-hedge",
    entry_thesis: "Energy transition underinvestment; strong FCF, buybacks, dividend growth" },
  { ticker: "JPM", name: "JPMorgan Chase", weight: 8, sector: "Financials", asset_class: "equity",
    entry_date: "2023-03-01", entry_price: 138, current_price: 195,
    tags: "financials, rates, quality",
    entry_thesis: "Best-in-class bank; benefits from higher-for-longer rates via NIM expansion" },
  { ticker: "ASML", name: "ASML Holding", weight: 7, sector: "Technology", asset_class: "equity",
    entry_date: "2023-01-01", entry_price: 640, current_price: 710,
    tags: "semiconductors, capex, monopoly",
    entry_thesis: "EUV monopoly; only supplier of lithography tools enabling sub-5nm chips" },
];

// ── State ──────────────────────────────────────────────────────────────────
let currentReviewId = null;
let eventSource = null;

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  DEFAULT_POSITIONS.forEach(addRow);
});

// ── Portfolio table ────────────────────────────────────────────────────────
function addRow(data = {}) {
  const tbody = document.getElementById("positions-body");
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" value="${data.ticker || ""}" placeholder="AAPL" /></td>
    <td><input type="text" value="${data.name || ""}" placeholder="Apple" /></td>
    <td><input type="number" step="0.1" value="${data.weight || ""}" placeholder="5.0" style="width:52px" /></td>
    <td><input type="text" value="${data.sector || ""}" placeholder="Technology" /></td>
    <td>
      <select>
        ${["equity","bond","commodity","fx","crypto"].map(a =>
          `<option${a === (data.asset_class || "equity") ? " selected" : ""}>${a}</option>`
        ).join("")}
      </select>
    </td>
    <td><input type="date" value="${data.entry_date || ""}" /></td>
    <td><input type="number" step="0.01" value="${data.entry_price || ""}" placeholder="100" style="width:60px" /></td>
    <td><input type="number" step="0.01" value="${data.current_price || ""}" placeholder="120" style="width:60px" /></td>
    <td><input type="text" value="${data.tags || ""}" placeholder="AI, growth" style="width:90px" /></td>
    <td><textarea rows="2" placeholder="Why you bought it...">${data.entry_thesis || ""}</textarea></td>
    <td><button class="delete-btn" onclick="this.closest('tr').remove()">✕</button></td>
  `;
  tbody.appendChild(tr);
}

function buildPortfolio() {
  const rows = document.querySelectorAll("#positions-body tr");
  const positions = [];
  for (const row of rows) {
    const inputs = row.querySelectorAll("input, select, textarea");
    const [ticker, name, weight, sector, asset_class, entry_date, entry_price, current_price, tags, entry_thesis] = inputs;
    if (!ticker.value.trim()) continue;
    positions.push({
      ticker:        ticker.value.trim().toUpperCase(),
      name:          name.value.trim(),
      weight:        parseFloat(weight.value) / 100,
      sector:        sector.value.trim(),
      asset_class:   asset_class.value,
      entry_date:    entry_date.value,
      entry_price:   parseFloat(entry_price.value),
      current_price: parseFloat(current_price.value),
      tags:          tags.value.split(",").map(t => t.trim()).filter(Boolean),
      entry_thesis:  entry_thesis.value.trim(),
      country:       "US",
    });
  }
  return {
    name:         document.getElementById("p-name").value.trim(),
    benchmark:    document.getElementById("p-benchmark").value.trim(),
    cash_weight:  parseFloat(document.getElementById("p-cash").value) / 100,
    review_date:  document.getElementById("p-date").value,
    context_note: document.getElementById("p-context").value.trim(),
    positions,
    base_currency: "USD",
  };
}

// ── Start review ───────────────────────────────────────────────────────────
async function startReview() {
  const portfolio = buildPortfolio();
  if (portfolio.positions.length === 0) {
    alert("Add at least one position.");
    return;
  }

  resetCards();
  setGlobalStatus("running");
  document.getElementById("start-btn").disabled = true;
  document.getElementById("results").classList.add("hidden");
  document.getElementById("confirm-box").classList.add("hidden");

  const res = await fetch("/api/review/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ portfolio }),
  });
  const { review_id } = await res.json();
  currentReviewId = review_id;

  subscribeSSE(review_id);
}

// ── SSE ────────────────────────────────────────────────────────────────────
function subscribeSSE(reviewId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/review/${reviewId}/stream`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };

  eventSource.onerror = () => {
    eventSource.close();
    // Don't show error if we're done
    if (document.getElementById("global-status").textContent !== "Done") {
      setGlobalStatus("error");
    }
  };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "agent_start":
      setCardState(msg.agent, "running");
      break;

    case "agent_done":
      setCardState(msg.agent, "done");
      renderCardOutput(msg.agent, msg.output);
      if (msg.agent === "planner") {
        renderResults(msg.output, currentReviewId);
        setGlobalStatus("done");
        document.getElementById("start-btn").disabled = false;
        if (eventSource) eventSource.close();
      }
      break;

    case "interrupt":
      setCardState("plan", "waiting");
      setGlobalStatus("waiting");
      showConfirmBox(msg.payload);
      break;

    case "error":
      setGlobalStatus("error");
      document.getElementById("start-btn").disabled = false;
      console.error("Review error:", msg.message);
      break;
  }
}

// ── Confirm box ────────────────────────────────────────────────────────────
function showConfirmBox(payload) {
  const box = document.getElementById("confirm-box");
  document.getElementById("confirm-preview").textContent =
    payload?.portfolio_summary || JSON.stringify(payload, null, 2);
  document.getElementById("confirm-input").value = "";
  box.classList.remove("hidden");
  document.getElementById("confirm-input").focus();
}

async function sendConfirm() {
  const userResponse = document.getElementById("confirm-input").value.trim() || "ok";
  document.getElementById("confirm-box").classList.add("hidden");
  setCardState("plan", "done");
  setGlobalStatus("running");

  await fetch(`/api/review/${currentReviewId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ response: userResponse }),
  });
  // SSE stream stays open — no need to resubscribe
}

// ── Card rendering ─────────────────────────────────────────────────────────
function setCardState(agent, state) {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  card.className = `agent-card ${state}`;
}

function renderCardOutput(agent, output) {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  const body = card.querySelector(".card-body");
  body.innerHTML = agentOutputHtml(agent, output);
  body.classList.remove("hidden");

  // Toggle on header click
  const header = card.querySelector(".card-header");
  header.onclick = () => body.classList.toggle("hidden");
}

function agentOutputHtml(agent, out) {
  if (!out) return "<em>No output</em>";

  const chip = (val, max = 10) => {
    const cls = val >= 7 ? "chip-green" : val >= 4 ? "chip-yellow" : "chip-red";
    return `<span class="chip ${cls}">${val}/${max}</span>`;
  };

  switch (agent) {
    case "news": {
      const data = out.news_review || out;
      const evts = (data.material_events || []).slice(0, 4);
      return [
        `<b>Macro:</b> ${(data.macro_context || "").slice(0, 200)}…`,
        `<b>Themes:</b> ${(data.market_themes || []).join(" · ")}`,
        evts.length ? `<b>Events:</b>\n${evts.map(e => `  [${e.ticker}] ${e.event} (${e.urgency})`).join("\n")}` : "",
        data.summary ? `<b>Summary:</b> ${data.summary}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "risk": {
      const data = Array.isArray(out.risk_results) ? out.risk_results[0] : out;
      return [
        `Risk score: ${chip(data.risk_score)}`,
        data.fragilities?.length ? `Fragilities:\n${data.fragilities.map(f => "  • " + f).join("\n")}` : "",
        data.concentration_issues?.length ? `Concentration: ${data.concentration_issues.join("; ")}` : "",
        data.summary ? `Summary: ${data.summary}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "regime": {
      const data = Array.isArray(out.regime_results) ? out.regime_results[0] : out;
      return [
        `Regime: <b>${data.current_regime}</b>`,
        `Fit: ${chip(data.portfolio_fit_score)} | Confidence: ${chip(data.regime_confidence)}`,
        data.mismatches?.length ? `Mismatches:\n${data.mismatches.map(m => "  • " + m).join("\n")}` : "",
        data.summary ? `Summary: ${data.summary}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "theme": {
      const data = Array.isArray(out.theme_results) ? out.theme_results[0] : out;
      return [
        `Alignment: ${chip(data.alignment_score)}`,
        (data.theme_alignments || []).slice(0, 4)
          .map(a => `  ${a.portfolio_stance.toUpperCase().padEnd(12)} ${a.theme}`)
          .join("\n"),
        data.crowding_risks?.length ? `Crowding: ${data.crowding_risks.join("; ")}` : "",
        data.summary ? `Summary: ${data.summary}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "validation": {
      const data = out.validation_review || out;
      return [
        `Consistency: ${chip(data.confidence_score)}`,
        (data.critical_issues || []).slice(0, 4)
          .map(i => `  [${i.severity.toUpperCase()}] ${i.issue}`).join("\n"),
        data.thesis_breaks?.length ? `Thesis breaks:\n${data.thesis_breaks.map(t => "  !! " + t).join("\n")}` : "",
        data.summary ? `Summary: ${data.summary}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "planner": {
      const data = out.planner_review || out;
      return [
        `Confidence: ${chip(data.overall_confidence)}`,
        (data.actions || []).slice(0, 5)
          .map(a => `  [${a.priority}] ${a.action_type.toUpperCase()} ${a.position}`).join("\n"),
        data.executive_summary ? `Summary: ${data.executive_summary.slice(0, 200)}…` : "",
      ].filter(Boolean).join("\n\n");
    }
    default:
      return `<pre>${JSON.stringify(out, null, 2).slice(0, 400)}</pre>`;
  }
}

// ── Results section ────────────────────────────────────────────────────────
async function renderResults(plannerOutput, reviewId) {
  // Fetch full state for validation score
  const res = await fetch(`/api/review/${reviewId}/result`);
  const { final_state } = await res.json();

  const planner = plannerOutput?.planner_review || plannerOutput;
  const validation = final_state?.validation_review;

  document.getElementById("exec-summary").textContent =
    planner?.executive_summary || "";

  document.getElementById("score-confidence").textContent =
    planner?.overall_confidence ?? "—";
  document.getElementById("score-consistency").textContent =
    validation?.confidence_score ?? "—";

  const tbody = document.getElementById("actions-body");
  tbody.innerHTML = "";
  const priorityOrder = ["urgent", "this-week", "next-review", "watch"];
  const actions = [...(planner?.actions || [])];
  actions.sort((a, b) =>
    priorityOrder.indexOf(a.priority) - priorityOrder.indexOf(b.priority)
  );
  for (const a of actions) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="priority-${a.priority}">${a.priority}</td>
      <td class="action-${a.action_type}">${a.action_type}</td>
      <td><b>${a.position}</b></td>
      <td>${a.rationale}</td>
      <td>${a.size_guidance}</td>
      <td>${a.hedge_instrument || "—"}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById("do-nothing").textContent =
    planner?.do_nothing_case || "";

  document.getElementById("results").classList.remove("hidden");
  document.getElementById("results").scrollIntoView({ behavior: "smooth" });
}

// ── Helpers ────────────────────────────────────────────────────────────────
function setGlobalStatus(state) {
  const el = document.getElementById("global-status");
  el.className = `badge badge-${state}`;
  const labels = { idle: "Idle", running: "Running", waiting: "Waiting", done: "Done", error: "Error" };
  el.textContent = labels[state] || state;
}

function resetCards() {
  document.querySelectorAll(".agent-card").forEach(card => {
    card.className = "agent-card";
    const body = card.querySelector(".card-body");
    body.innerHTML = "";
    body.classList.add("hidden");
    card.querySelector(".card-header").onclick = null;
  });
}
