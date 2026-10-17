import { copy } from "./copy.js";

// Keep the compact ribbon and metadata chips synchronized with the canonical form and cards.
const AGENTS = ["data", "planner", "news", "risk", "regime", "theme", "allocation", "manager"];
const STATES = ["running", "done", "error"];

function classState(el) {
  return STATES.find((s) => el.classList.contains(s)) || "";
}

function ribbonTimeFor(state, elapsedText) {
  const elapsed = elapsedText.trim();
  if (elapsed) return elapsed;
  if (state === "done") return copy("ribbon.done");
  if (state === "running") return copy("ribbon.running");
  if (state === "error") return copy("ribbon.errored");
  return copy("ribbon.idle");
}

function syncRibbonFromCard(agent) {
  const card = document.getElementById(`card-${agent}`);
  const node = document.querySelector(`.ribbon-node[data-agent="${agent}"]`);
  const state = classState(card);
  node.classList.remove(...STATES);
  if (state) node.classList.add(state);
  node.querySelector(".node-time").textContent =
    ribbonTimeFor(state, card.querySelector(".agent-elapsed").textContent);
}

function updateRibbonProgress() {
  const total = AGENTS.length;
  const states = AGENTS.map((agent) => classState(document.getElementById(`card-${agent}`)));
  const done = states.filter((s) => s === "done").length;
  const running = states.filter((s) => s === "running").length;
  const error = states.filter((s) => s === "error").length;
  document.getElementById("ribbon-progress-fill").style.width = `${(done / total) * 100}%`;
  document.getElementById("ribbon-progress-text").textContent = `${done} / ${total}`;
  const eta = document.getElementById("ribbon-progress-eta");
  if (error > 0) eta.textContent = copy("ribbon.etaError");
  else if (done === total) eta.textContent = copy("ribbon.etaComplete");
  else if (running > 0) eta.textContent = copy("ribbon.etaRunning");
  else eta.textContent = "";
}

function syncAllRibbon() {
  for (const agent of AGENTS) syncRibbonFromCard(agent);
  updateRibbonProgress();
}

function syncMetaChips() {
  const rows = document.querySelectorAll("#positions-body .position-row-wrap");
  const notes = Array.from(rows).filter((row) => row.querySelector('[data-field="entry_thesis"]').value.trim()).length;
  document.getElementById("meta-invested").textContent = document.getElementById("weight-positions").textContent;
  document.getElementById("meta-positions").textContent = String(rows.length);
  document.getElementById("meta-notes").textContent = String(notes);

  const sub = document.getElementById("weight-positions-sub");
  const subText = rows.length
    ? copy("summary.positionsSubCount", { count: rows.length })
    : copy("summary.positionsSub");
  if (sub.textContent !== subText) sub.textContent = subText;
}

export function initLayoutMirror() {
  document.querySelectorAll(".ribbon-node").forEach((node) => {
    node.addEventListener("click", () => document.getElementById(`card-${node.dataset.agent}`).click());
  });

  for (const agent of AGENTS) {
    new MutationObserver(syncAllRibbon).observe(document.getElementById(`card-${agent}`), {
      attributes: true,
      attributeFilter: ["class"],
      childList: true,
      subtree: true,
      characterData: true,
    });
  }
  syncAllRibbon();

  new MutationObserver(syncMetaChips).observe(document.getElementById("weight-summary"), {
    childList: true,
    subtree: true,
    characterData: true,
  });
  const positionsBody = document.getElementById("positions-body");
  new MutationObserver(syncMetaChips).observe(positionsBody, { childList: true, subtree: true });
  positionsBody.addEventListener("input", syncMetaChips);
  syncMetaChips();
}
