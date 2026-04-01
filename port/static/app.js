// ── Default example positions (price filled from quote API) ─────────────────
const DEFAULT_POSITIONS = [
  { ticker: "NVDA", name: "Nvidia", weight: 12, quantity: 25, sector: "Technology", asset_class: "equity",
    entry_thesis: "AI compute monopoly, data center capex supercycle driven by LLM training demand" },
  { ticker: "MSFT", name: "Microsoft", weight: 10, quantity: 30, sector: "Technology", asset_class: "equity",
    entry_thesis: "Azure cloud + Copilot AI monetisation; recurring revenue model with pricing power" },
  { ticker: "TLT", name: "iShares 20Y Treasury", weight: 10, quantity: 200, sector: "Fixed Income", asset_class: "bond",
    entry_thesis: "Duration add at rate peak; Fed pivot trade for H1 2024" },
  { ticker: "XOM", name: "ExxonMobil", weight: 8, quantity: 80, sector: "Energy", asset_class: "equity",
    entry_thesis: "Energy transition underinvestment; strong FCF, buybacks, dividend growth" },
  { ticker: "JPM", name: "JPMorgan Chase", weight: 8, quantity: 45, sector: "Financials", asset_class: "equity",
    entry_thesis: "Best-in-class bank; benefits from higher-for-longer rates via NIM expansion" },
  { ticker: "ASML", name: "ASML Holding", weight: 7, quantity: 5, sector: "Technology", asset_class: "equity",
    entry_thesis: "EUV monopoly; only supplier of lithography tools enabling sub-5nm chips" },
];

let currentReviewId = null;
let eventSource = null;
const quoteTimers = new WeakMap();
const LAST_REVIEW_STORAGE_KEY = "portAdvisorLastReview";
const REVIEW_HISTORY_STORAGE_KEY = "portAdvisorReviewHistory";
const MAX_REVIEW_HISTORY = 30;
const SIDEBAR_WIDTH_STORAGE_KEY = "portAdvisorSidebarWidth";
const SIDEBAR_MIN_PX = 180;
const SIDEBAR_MAX_PX = 560;

function sidebarWidthMax() {
  return Math.min(Math.floor(window.innerWidth * 0.5), SIDEBAR_MAX_PX);
}

function applySidebarWidth(px) {
  const max = sidebarWidthMax();
  const w = Math.round(Math.min(Math.max(px, SIDEBAR_MIN_PX), max));
  document.documentElement.style.setProperty("--sidebar-width", `${w}px`);
  try {
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(w));
  } catch {
    /* ignore */
  }
  return w;
}

function initSidebarResize() {
  const handle = document.getElementById("sidebar-resize-handle");
  const aside = document.querySelector(".agent-sidebar");
  if (!handle || !aside) return;

  try {
    const saved = localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    if (saved != null) {
      const n = parseInt(saved, 10);
      if (!Number.isNaN(n)) applySidebarWidth(n);
    }
  } catch {
    /* ignore */
  }

  window.addEventListener("resize", () => {
    const cur = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width").trim() || "260"
    );
    if (!Number.isNaN(cur)) applySidebarWidth(cur);
  });

  let startX = 0;
  let startWidth = 0;

  function onPointerMove(e) {
    const dx = e.clientX - startX;
    applySidebarWidth(startWidth + dx);
  }

  function onPointerUp(e) {
    try {
      handle.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    document.body.classList.remove("sidebar-resizing");
    document.body.style.userSelect = "";
  }

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (window.matchMedia("(max-width: 900px)").matches) return;
    e.preventDefault();
    startX = e.clientX;
    startWidth = aside.getBoundingClientRect().width;
    handle.setPointerCapture(e.pointerId);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.body.classList.add("sidebar-resizing");
    document.body.style.userSelect = "none";
  });

  handle.addEventListener("keydown", (e) => {
    if (window.matchMedia("(max-width: 900px)").matches) return;
    let delta = 0;
    if (e.key === "ArrowLeft") delta = -12;
    else if (e.key === "ArrowRight") delta = 12;
    else return;
    e.preventDefault();
    const cur = aside.getBoundingClientRect().width;
    applySidebarWidth(cur + delta);
  });
}

function escapeHtml(s) {
  if (s == null || s === "") return "";
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

function showToast(message, isError = false) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const t = document.createElement("div");
  t.className = `toast${isError ? " error" : ""}`;
  t.setAttribute("role", "alert");
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transition = "opacity 0.3s";
    setTimeout(() => t.remove(), 320);
  }, 5200);
}

function fmtUsd(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function fmtPrice(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

function fmtPctDisplay(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function getLastPrice(wrap) {
  const pe = wrap.querySelector('[data-ro="price"]');
  if (!pe) return NaN;
  const d = pe.dataset.lastPrice;
  if (d != null && d !== "") {
    const v = parseFloat(d);
    return Number.isNaN(v) ? NaN : v;
  }
  return NaN;
}

function getCashDollarsInput() {
  const v = parseFloat(document.getElementById("p-cash")?.value);
  if (Number.isNaN(v) || v < 0) return 0;
  return v;
}

/** Sum of quantity × last price for all rows (for cash weight and NAV). */
function sumPositionMarketValues() {
  let sum = 0;
  for (const wrap of document.querySelectorAll("#positions-body .position-row-wrap")) {
    sum += getPositionMarketValue(wrap);
  }
  return sum;
}

function getPositionMarketValue(wrap) {
  const q = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
  const cur = getLastPrice(wrap);
  const qtyOk = !Number.isNaN(q) && q !== 0;
  const curOk = !Number.isNaN(cur);
  return qtyOk && curOk ? q * cur : 0;
}

function refreshMetrics(wrap) {
  const q = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
  const cur = getLastPrice(wrap);
  const valEl = wrap.querySelector('[data-ro="value"]');

  const qtyOk = !Number.isNaN(q) && q !== 0;
  const curOk = !Number.isNaN(cur);

  if (valEl) {
    valEl.classList.remove("muted");
    if (qtyOk && curOk) {
      valEl.textContent = fmtUsd(q * cur);
    } else {
      valEl.textContent = "—";
      valEl.classList.add("muted");
    }
  }
}

function scheduleQuoteFetch(wrap) {
  const prev = quoteTimers.get(wrap);
  if (prev) clearTimeout(prev);
  quoteTimers.set(wrap, setTimeout(() => fetchQuoteForCard(wrap), 420));
}

async function fetchQuoteForCard(wrap) {
  const tickerInput = wrap.querySelector('[data-field="ticker"]');
  const priceEl = wrap.querySelector('[data-ro="price"]');
  const m1 = wrap.querySelector('[data-ro="ret-1m"]');
  const m1y = wrap.querySelector('[data-ro="ret-1y"]');
  if (!tickerInput || !priceEl || !m1 || !m1y) return;

  const ticker = tickerInput.value.trim().toUpperCase();
  if (!ticker) {
    delete priceEl.dataset.lastPrice;
    priceEl.textContent = "—";
    priceEl.classList.add("muted");
    m1.textContent = "—";
    m1y.textContent = "—";
    m1.classList.add("muted");
    m1y.classList.add("muted");
    refreshMetrics(wrap);
    return;
  }

  priceEl.textContent = "…";
  priceEl.classList.add("muted");
  m1.textContent = "…";
  m1y.textContent = "…";
  m1.classList.add("muted");
  m1y.classList.add("muted");

  try {
    const res = await fetch(`/api/market/quote/${encodeURIComponent(ticker)}`);
    if (!res.ok) throw new Error("bad");
    const j = await res.json();
    const px = Number(j.current_price);
    if (Number.isFinite(px)) {
      priceEl.dataset.lastPrice = String(px);
      priceEl.textContent = fmtPrice(px);
      priceEl.classList.remove("muted");
    } else {
      delete priceEl.dataset.lastPrice;
      priceEl.textContent = "—";
      priceEl.classList.add("muted");
    }

    const r1 = Number(j.change_1m_pct);
    const r1y = Number(j.change_1y_pct);
    m1.textContent = Number.isFinite(r1) ? fmtPctDisplay(r1) : "—";
    m1y.textContent = Number.isFinite(r1y) ? fmtPctDisplay(r1y) : "—";
    m1.classList.toggle("positive", r1 > 0);
    m1.classList.toggle("negative", r1 < 0);
    m1y.classList.toggle("positive", r1y > 0);
    m1y.classList.toggle("negative", r1y < 0);
    m1.classList.remove("muted");
    m1y.classList.remove("muted");
  } catch {
    delete priceEl.dataset.lastPrice;
    priceEl.textContent = "—";
    priceEl.classList.add("muted");
    m1.textContent = "—";
    m1y.textContent = "—";
    m1.classList.remove("positive", "negative");
    m1y.classList.remove("positive", "negative");
    m1.classList.add("muted");
    m1y.classList.add("muted");
  }
  refreshMetrics(wrap);
  updateWeightSummary();
}

async function refreshAllQuotes() {
  const btn = document.getElementById("refresh-quotes-btn");
  const wraps = Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
  if (wraps.length === 0) {
    showToast("Add at least one position to refresh quotes.", true);
    return;
  }
  const hasTicker = wraps.some((w) => w.querySelector('[data-field="ticker"]')?.value?.trim());
  if (!hasTicker) {
    showToast("Enter at least one ticker to refresh.", true);
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    await Promise.all(wraps.map((w) => fetchQuoteForCard(w)));
    showToast("Market data refreshed from Yahoo Finance.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

function updateWeightSummary() {
  const cashD = getCashDollarsInput();
  const sumPos = sumPositionMarketValues();
  const nav = sumPos + cashD;
  const impliedCashPct = nav > 0 ? (cashD / nav) * 100 : 0;
  let sumW = 0;

  for (const card of document.querySelectorAll("#positions-body .position-row-wrap")) {
    const wEl = card.querySelector('[data-field="weight"]');
    if (!wEl) continue;
    const positionValue = getPositionMarketValue(card);
    const pct = nav > 0 ? (positionValue / nav) * 100 : 0;
    wEl.value = pct.toFixed(1);
    sumW += pct;
  }

  const fmt = (n) => `${n.toFixed(1)}%`;
  const posEl = document.getElementById("weight-positions");
  const cashOut = document.getElementById("weight-cash");
  const totEl = document.getElementById("weight-total");
  if (posEl) posEl.textContent = fmt(sumW);
  if (cashOut) cashOut.textContent = fmtUsd(cashD);
  if (totEl) {
    totEl.textContent = fmtUsd(nav);
    totEl.className = "";
    const target = sumW + impliedCashPct;
    if (Math.abs(target - 100) > 2) totEl.classList.add("bad");
    else if (Math.abs(target - 100) > 0.5) totEl.classList.add("warn");
  }
}

function wirePositionRow(wrap) {
  wrap.querySelector('[data-field="quantity"]')?.addEventListener("input", () => refreshMetrics(wrap));

  const tickerEl = wrap.querySelector('[data-field="ticker"]');
  if (tickerEl) {
    tickerEl.addEventListener("blur", () => fetchQuoteForCard(wrap));
    tickerEl.addEventListener("input", () => scheduleQuoteFetch(wrap));
  }

  const toggle = wrap.querySelector(".btn-assert-toggle");
  const panel = wrap.querySelector(".position-assertion-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      const open = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !open);
      wrap.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "▾" : "▸";
    });
  }

  wrap.querySelector(".delete-btn")?.addEventListener("click", () => {
    wrap.remove();
    updateWeightSummary();
  });

  refreshMetrics(wrap);
}

document.addEventListener("DOMContentLoaded", () => {
  const weightCol = document.querySelector(".positions-head-row span:nth-child(3)");
  if (weightCol) weightCol.textContent = "Weight %";

  DEFAULT_POSITIONS.forEach(addRow);
  updateWeightSummary();

  document.getElementById("add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("refresh-quotes-btn")?.addEventListener("click", () => refreshAllQuotes());
  document.getElementById("start-btn")?.addEventListener("click", startReview);
  document.getElementById("confirm-send-btn")?.addEventListener("click", sendConfirm);
  document.getElementById("open-saved-review")?.addEventListener("click", openSavedReviewFromStorage);
  document.getElementById("open-review-history")?.addEventListener("click", showHistoryModal);
  document.getElementById("history-modal-close")?.addEventListener("click", hideHistoryModal);
  document.getElementById("history-modal-backdrop")?.addEventListener("click", hideHistoryModal);
  document.getElementById("results-modal-close")?.addEventListener("click", hideResultsModal);
  document.getElementById("results-modal-backdrop")?.addEventListener("click", hideResultsModal);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const historyModal = document.getElementById("history-modal");
    if (historyModal && !historyModal.classList.contains("hidden")) {
      e.preventDefault();
      hideHistoryModal();
      return;
    }
    const modal = document.getElementById("results-modal");
    if (modal && !modal.classList.contains("hidden")) {
      e.preventDefault();
      hideResultsModal();
    }
  });
  initSavedReview();
  initSidebarResize();
  document.getElementById("p-cash")?.addEventListener("input", updateWeightSummary);

  document.getElementById("positions-body")?.addEventListener("input", (e) => {
    if (e.target?.closest?.(".position-row-wrap")) updateWeightSummary();
  });
  document.getElementById("positions-body")?.addEventListener("change", (e) => {
    if (e.target?.closest?.(".position-row-wrap")) updateWeightSummary();
  });

  document.getElementById("confirm-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendConfirm();
    }
  });

  document.querySelectorAll("#positions-body .position-row-wrap").forEach((wrap) => {
    fetchQuoteForCard(wrap);
  });
});

function addRow(data = {}) {
  const grid = document.getElementById("positions-body");
  const wrap = document.createElement("div");
  wrap.className = "position-row-wrap";

  const t = escapeHtml(data.ticker);
  const n = escapeHtml(data.name);
  const qty = data.quantity != null && data.quantity !== "" ? escapeHtml(String(data.quantity)) : "";
  const s = escapeHtml(data.sector);
  const thesis = escapeHtml(data.entry_thesis);
  const ac = data.asset_class || "equity";

  wrap.innerHTML = `
    <div class="position-row">
      <input type="text" data-field="ticker" class="pc-ticker" value="${t}" placeholder="SYM" autocomplete="off" title="Ticker" />
      <input type="text" data-field="name" value="${n}" placeholder="Name" title="Name" />
      <input type="number" data-field="weight" step="0.1" value="0.0" placeholder="%" title="Weight %" readonly />
      <input type="text" data-field="sector" value="${s}" placeholder="Sector" title="Sector" />
      <select data-field="asset_class" title="Asset class">
        ${["equity", "bond", "commodity", "fx", "crypto"].map(a =>
          `<option${a === ac ? " selected" : ""}>${a}</option>`
        ).join("")}
      </select>
      <span data-ro="price" class="row-metric muted" title="Last fetched price">—</span>
      <input type="number" data-field="quantity" step="0.0001" value="${qty}" placeholder="0" title="Quantity" />
      <span data-ro="value" class="row-metric muted" title="Position value">—</span>
      <span data-ro="ret-1m" class="row-metric muted" title="1 month return">—</span>
      <span data-ro="ret-1y" class="row-metric muted" title="1 year return">—</span>
      <button type="button" class="btn-assert-toggle" aria-expanded="false" aria-label="Show or hide assertion" title="Assertion">▸</button>
      <button type="button" class="delete-btn" aria-label="Remove position">✕</button>
    </div>
    <div class="position-assertion-panel hidden">
      <div class="assertion-inner">
        <span class="assertion-label">Your assertion</span>
        <textarea data-field="entry_thesis" rows="3" placeholder="Why you own this position…">${thesis}</textarea>
      </div>
    </div>
  `;

  grid.appendChild(wrap);
  wirePositionRow(wrap);
  updateWeightSummary();
}

function buildPortfolio() {
  const reviewDate = document.getElementById("p-date")?.value || "";
  const positions = [];
  let sumPos = 0;
  const rows = Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
  const cashD = getCashDollarsInput();
  for (const wrap of rows) {
    sumPos += getPositionMarketValue(wrap);
  }
  const nav = sumPos + cashD;
  for (const wrap of rows) {
    const ticker = wrap.querySelector('[data-field="ticker"]')?.value?.trim();
    if (!ticker) continue;

    const num = (sel, fallback = NaN) => {
      const v = parseFloat(wrap.querySelector(sel)?.value);
      return Number.isNaN(v) ? fallback : v;
    };

    const qtyRaw = wrap.querySelector('[data-field="quantity"]')?.value;
    const qtyParsed = parseFloat(qtyRaw);
    const quantity = qtyRaw === "" || Number.isNaN(qtyParsed) ? 0 : qtyParsed;

    let current_price = getLastPrice(wrap);
    if (Number.isNaN(current_price)) current_price = 0;

    const positionValue = quantity * current_price;
    const weight = nav > 0 ? positionValue / nav : 0;

    positions.push({
      ticker: ticker.toUpperCase(),
      name: wrap.querySelector('[data-field="name"]')?.value?.trim() || "",
      weight,
      quantity,
      sector: wrap.querySelector('[data-field="sector"]')?.value?.trim() || "",
      asset_class: wrap.querySelector('[data-field="asset_class"]')?.value || "equity",
      entry_date: reviewDate,
      entry_price: current_price,
      current_price,
      tags: [],
      entry_thesis: wrap.querySelector('[data-field="entry_thesis"]')?.value?.trim() || "",
      country: "US",
    });
  }
  const cash_weight = nav > 0 ? cashD / nav : 0;

  return {
    name: document.getElementById("p-name").value.trim(),
    benchmark: document.getElementById("p-benchmark").value.trim(),
    cash_weight,
    review_date: document.getElementById("p-date").value,
    context_note: document.getElementById("p-context").value.trim(),
    positions,
    base_currency: "USD",
  };
}

async function startReview() {
  const portfolio = buildPortfolio();
  if (portfolio.positions.length === 0) {
    showToast("Add at least one position with a ticker.", true);
    return;
  }

  resetCards();
  setGlobalStatus("running");
  const startBtn = document.getElementById("start-btn");
  startBtn.disabled = true;
  hideResultsModal();
  document.getElementById("confirm-box").classList.add("hidden");

  let res;
  try {
    res = await fetch("/api/review/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio }),
    });
  } catch (err) {
    showToast("Network error — could not start review.", true);
    setGlobalStatus("error");
    startBtn.disabled = false;
    return;
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* ignore */ }
    showToast(`Could not start review: ${detail}`, true);
    setGlobalStatus("error");
    startBtn.disabled = false;
    return;
  }

  const data = await res.json();
  const review_id = data.review_id;
  if (!review_id) {
    showToast("Invalid response from server.", true);
    setGlobalStatus("error");
    startBtn.disabled = false;
    return;
  }
  currentReviewId = review_id;
  subscribeSSE(review_id);
}

function subscribeSSE(reviewId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/review/${reviewId}/stream`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };

  eventSource.onerror = () => {
    eventSource.close();
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
      if (msg.agent === "manager") {
        renderResults(msg.output, currentReviewId);
        setGlobalStatus("done");
        document.getElementById("start-btn").disabled = false;
        if (eventSource) eventSource.close();
      }
      break;

    case "interrupt":
      setCardState("planner", "waiting");
      setGlobalStatus("waiting");
      showConfirmBox(msg.payload);
      break;

    case "error":
      setGlobalStatus("error");
      document.getElementById("start-btn").disabled = false;
      showToast(msg.message || "Review failed.", true);
      break;
  }
}

function showConfirmBox(payload) {
  const box = document.getElementById("confirm-box");
  const preview = payload?.portfolio_summary != null
    ? String(payload.portfolio_summary)
    : JSON.stringify(payload, null, 2);
  document.getElementById("confirm-preview").textContent = preview;
  document.getElementById("confirm-input").value = "";
  box.classList.remove("hidden");
  document.getElementById("confirm-input").focus();
}

async function sendConfirm() {
  const userResponse = document.getElementById("confirm-input").value.trim() || "ok";
  document.getElementById("confirm-box").classList.add("hidden");
  setCardState("planner", "done");
  setGlobalStatus("running");

  try {
    await fetch(`/api/review/${currentReviewId}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response: userResponse }),
    });
  } catch {
    showToast("Could not send confirmation.", true);
  }
}

const AGENT_STATUS_LABELS = {
  idle: "Idle",
  running: "Running",
  done: "Done",
  waiting: "Waiting",
  error: "Error",
};

function setCardState(agent, state) {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  card.className = `agent-card ${state}`;
  const label = card.querySelector(".agent-status-label");
  if (label) {
    label.textContent = AGENT_STATUS_LABELS[state] ?? state;
  }
}

function renderCardOutput(agent, output) {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  const body = card.querySelector(".card-body");
  body.innerHTML = agentOutputHtml(agent, output);
  body.classList.remove("hidden");

  const header = card.querySelector(".card-header");
  header.onclick = () => body.classList.toggle("hidden");
}

function agentOutputHtml(agent, out) {
  if (!out) return "<em>No output</em>";

  const chip = (val, max = 10) => {
    const n = Number(val);
    if (Number.isNaN(n)) return escapeHtml(String(val));
    const cls = n >= 7 ? "chip-green" : n >= 4 ? "chip-yellow" : "chip-red";
    return `<span class="chip ${cls}">${escapeHtml(String(n))}/${max}</span>`;
  };

  switch (agent) {
    case "news": {
      const data = out.news_review || out;
      const evts = (data.material_events || []).slice(0, 4);
      const macro = (data.macro_context || "").slice(0, 200);
      const themes = (data.market_themes || []).map(escapeHtml).join(" · ");
      const evtLines = evts.map(e =>
        `  [${escapeHtml(e.ticker)}] ${escapeHtml(e.event)} (${escapeHtml(e.urgency)})`
      ).join("\n");
      return [
        `<b>Macro:</b> ${escapeHtml(macro)}${macro.length >= 200 ? "…" : ""}`,
        themes ? `<b>Themes:</b> ${themes}` : "",
        evtLines ? `<b>Events:</b>\n${evtLines}` : "",
        data.summary ? `<b>Summary:</b> ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "risk": {
      const data = Array.isArray(out.risk_results) ? out.risk_results[0] : out;
      const fr = (data.fragilities || []).map(f => "  • " + escapeHtml(f)).join("\n");
      const conc = (data.concentration_issues || []).map(escapeHtml).join("; ");
      return [
        `Risk score: ${chip(data.risk_score)}`,
        fr ? `Fragilities:\n${fr}` : "",
        conc ? `Concentration: ${conc}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "regime": {
      const data = Array.isArray(out.regime_results) ? out.regime_results[0] : out;
      const mm = (data.mismatches || []).map(m => "  • " + escapeHtml(m)).join("\n");
      return [
        `Regime: <b>${escapeHtml(data.current_regime)}</b>`,
        `Fit: ${chip(data.portfolio_fit_score)} | Confidence: ${chip(data.regime_confidence)}`,
        mm ? `Mismatches:\n${mm}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "theme": {
      const data = Array.isArray(out.theme_results) ? out.theme_results[0] : out;
      const aligns = (data.theme_alignments || []).slice(0, 4)
        .map(a => {
          const stance = String(a.portfolio_stance || "").toUpperCase().padEnd(12);
          return `  ${escapeHtml(stance)} ${escapeHtml(a.theme)}`;
        })
        .join("\n");
      const crowd = (data.crowding_risks || []).map(escapeHtml).join("; ");
      return [
        `Alignment: ${chip(data.alignment_score)}`,
        aligns || "",
        crowd ? `Crowding: ${crowd}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "validation": {
      const data = out.validation_review || out;
      const crit = (data.critical_issues || []).slice(0, 4)
        .map(i => `  [${escapeHtml((i.severity || "").toUpperCase())}] ${escapeHtml(i.issue)}`)
        .join("\n");
      const br = (data.thesis_breaks || []).map(t => "  !! " + escapeHtml(t)).join("\n");
      return [
        `Consistency: ${chip(data.confidence_score)}`,
        crit ? crit : "",
        br ? `Thesis breaks:\n${br}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "planner": {
      const nf = out.news_focus;
      if (!nf) return "<em>No search focus.</em>";
      const lines = [];
      const pg = nf.portfolio_goal || "";
      if (pg) lines.push(`<b>Portfolio goal:</b> ${escapeHtml(pg.length > 280 ? `${pg.slice(0, 280)}…` : pg)}`);
      const goals = nf.position_goals || [];
      if (goals.length) {
        lines.push("<b>Position goals (for news search):</b>");
        for (const g of goals.slice(0, 12)) {
          const t = escapeHtml(g.ticker || "");
          const gg = escapeHtml((g.goal || "").length > 160 ? `${(g.goal || "").slice(0, 160)}…` : (g.goal || ""));
          lines.push(`  <span class="mono">${t}</span> — ${gg || "—"}`);
        }
        if (goals.length > 12) lines.push(`  <span class="muted-text">… +${goals.length - 12} more</span>`);
      }
      return lines.length ? lines.join("\n") : "<em>No goals stated.</em>";
    }
    case "manager": {
      const data = out.manager_review || out.planner_review || out;
      const acts = (data.actions || []).slice(0, 5)
        .map(a =>
          `  [${escapeHtml(a.priority)}] ${escapeHtml((a.action_type || "").toUpperCase())} ${escapeHtml(a.position)}`
        )
        .join("\n");
      const es = data.executive_summary ? escapeHtml(data.executive_summary.slice(0, 200)) : "";
      return [
        `Confidence: ${chip(data.overall_confidence)}`,
        acts || "",
        es ? `Summary: ${es}${(data.executive_summary || "").length > 200 ? "…" : ""}` : "",
      ].filter(Boolean).join("\n\n");
    }
    default:
      return `<pre>${escapeHtml(JSON.stringify(out, null, 2).slice(0, 400))}</pre>`;
  }
}

function formatSavedAt(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return "";
  }
}

function formatSavedReviewMeta(savedAt, reviewId) {
  const when = savedAt ? formatSavedAt(savedAt) : "";
  const idShort = reviewId ? String(reviewId).slice(0, 8) : "";
  const parts = [when];
  if (idShort) parts.push(`ID ${idShort}…`);
  return parts.filter(Boolean).join(" · ");
}

function migrateLegacyReviewToHistory() {
  try {
    if (localStorage.getItem(REVIEW_HISTORY_STORAGE_KEY)) return;
    const raw = localStorage.getItem(LAST_REVIEW_STORAGE_KEY);
    if (!raw) return;
    const bundle = JSON.parse(raw);
    if (!bundle?.manager && !bundle?.planner) return;
    localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify([bundle]));
  } catch {
    /* ignore */
  }
}

function loadReviewHistory() {
  try {
    migrateLegacyReviewToHistory();
    const raw = localStorage.getItem(REVIEW_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function persistReviewBundle(bundle) {
  let list = loadReviewHistory().filter((b) => b?.reviewId !== bundle.reviewId);
  list.unshift(bundle);
  list = list.slice(0, MAX_REVIEW_HISTORY);
  try {
    localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify(list));
    localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(bundle));
  } catch {
    for (let n = list.length - 1; n >= 0; n--) {
      const trimmed = list.slice(0, n);
      try {
        if (trimmed.length) {
          localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
          localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(trimmed[0]));
        } else {
          localStorage.removeItem(REVIEW_HISTORY_STORAGE_KEY);
          localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(bundle));
        }
        return;
      } catch {
        /* try smaller */
      }
    }
  }
}

function refreshSavedReviewSidebar(bundle) {
  const block = document.getElementById("saved-review-block");
  const meta = document.getElementById("saved-review-meta");
  if (!block || !meta) return;
  block.classList.remove("hidden");
  meta.textContent = formatSavedReviewMeta(bundle.savedAt, bundle.reviewId);
}

function initSavedReview() {
  try {
    migrateLegacyReviewToHistory();
    const list = loadReviewHistory();
    const bundle = list[0];
    if (!bundle?.manager && !bundle?.planner) return;
    refreshSavedReviewSidebar(bundle);
  } catch {
    /* ignore */
  }
}

function applyResultsFromData(manager, validation) {
  const execEl = document.getElementById("exec-summary");
  execEl.textContent = manager?.executive_summary || "";

  document.getElementById("score-confidence").textContent =
    manager?.overall_confidence ?? "—";
  document.getElementById("score-consistency").textContent =
    validation?.confidence_score ?? "—";

  const tbody = document.getElementById("actions-body");
  tbody.innerHTML = "";
  const priorityOrder = ["urgent", "this-week", "next-review", "watch"];
  const actions = [...(manager?.actions || [])];
  actions.sort((a, b) =>
    priorityOrder.indexOf(a.priority) - priorityOrder.indexOf(b.priority)
  );
  for (const a of actions) {
    const tr = document.createElement("tr");
    const td = (cls, text) => {
      const cell = document.createElement("td");
      if (cls) cell.className = cls;
      cell.textContent = text ?? "—";
      return cell;
    };
    tr.appendChild(td(`priority-${a.priority}`, a.priority));
    tr.appendChild(td(`action-${a.action_type}`, a.action_type));
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const b = document.createElement("b");
      b.textContent = a.position ?? "—";
      cell.appendChild(b);
      return cell;
    })());
    tr.appendChild(td(null, a.rationale));
    tr.appendChild(td(null, a.size_guidance));
    tr.appendChild(td(null, a.hedge_instrument || "—"));
    tbody.appendChild(tr);
  }

  document.getElementById("do-nothing").textContent =
    manager?.do_nothing_case || "";
}

function showResultsModal() {
  const el = document.getElementById("results-modal");
  if (!el) return;
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("results-modal-close")?.focus();
}

function hideResultsModal() {
  const el = document.getElementById("results-modal");
  if (!el) return;
  el.classList.add("hidden");
  const historyOpen = document.getElementById("history-modal") && !document.getElementById("history-modal").classList.contains("hidden");
  if (!historyOpen) document.body.style.overflow = "";
}

function openSavedReviewFromStorage() {
  try {
    migrateLegacyReviewToHistory();
    const list = loadReviewHistory();
    const bundle = list[0];
    if (!bundle) {
      showToast("No saved review yet.", true);
      return;
    }
    const mgr = bundle.manager || bundle.planner;
    if (!mgr) {
      showToast("Saved review is missing data.", true);
      return;
    }
    applyResultsFromData(mgr, bundle.validation);
    showResultsModal();
  } catch {
    showToast("Could not load saved review.", true);
  }
}

function historyRowLabel(bundle) {
  const name = (bundle.portfolioName || "").trim() || "Portfolio";
  const when = bundle.savedAt ? formatSavedAt(bundle.savedAt) : "";
  const idShort = bundle.reviewId ? String(bundle.reviewId).slice(0, 8) : "";
  const parts = [name];
  if (when) parts.push(when);
  if (idShort) parts.push(`${idShort}…`);
  return parts.join(" · ");
}

function renderHistoryList() {
  const ul = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  if (!ul) return;
  const list = loadReviewHistory();
  ul.innerHTML = "";
  if (list.length === 0) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  let added = 0;
  for (const bundle of list) {
    const mgr = bundle.manager || bundle.planner;
    if (!mgr) continue;
    added += 1;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-row-btn";
    btn.textContent = historyRowLabel(bundle);
    btn.addEventListener("click", () => {
      applyResultsFromData(mgr, bundle.validation);
      hideHistoryModal();
      showResultsModal();
    });
    li.appendChild(btn);
    ul.appendChild(li);
  }
  if (added === 0 && empty) empty.classList.remove("hidden");
}

function showHistoryModal() {
  migrateLegacyReviewToHistory();
  renderHistoryList();
  const el = document.getElementById("history-modal");
  if (!el) return;
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("history-modal-close")?.focus();
}

function hideHistoryModal() {
  const el = document.getElementById("history-modal");
  if (!el) return;
  el.classList.add("hidden");
  if (!document.getElementById("results-modal")?.classList.contains("hidden")) {
    return;
  }
  document.body.style.overflow = "";
}

async function renderResults(managerOutput, reviewId) {
  const res = await fetch(`/api/review/${reviewId}/result`);
  const { final_state } = await res.json();

  const manager =
    managerOutput?.manager_review ||
    managerOutput?.planner_review ||
    managerOutput;
  const validation = final_state?.validation_review;

  applyResultsFromData(manager, validation);

  const bundle = {
    reviewId,
    savedAt: new Date().toISOString(),
    portfolioName: document.getElementById("p-name")?.value?.trim() || "",
    manager,
    validation: validation ?? null,
  };
  persistReviewBundle(bundle);
  refreshSavedReviewSidebar(bundle);
  showResultsModal();
}

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
    const label = card.querySelector(".agent-status-label");
    if (label) label.textContent = "Idle";
  });
}
