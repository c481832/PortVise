// Display formatting shared by the advisor and arena frontends.

const LOCALE = "en-US";
const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}

function toFiniteNumber(value) {
  if (value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function formatCurrency(value) {
  const number = toFiniteNumber(value);
  if (number == null) return "—";
  return new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(number);
}

export function formatPrice(value) {
  const number = toFiniteNumber(value);
  if (number == null) return "—";
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(number);
}

export function formatNumber(value, digits = 2, signed = false) {
  const number = toFiniteNumber(value);
  if (number == null) return "—";
  const sign = number < 0 ? "-" : signed ? "+" : "";
  const magnitude = new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Math.abs(number));
  return `${sign}${magnitude}`;
}

// Ratios in, percentages out: 0.123 -> "12.3%".
export function formatPercent(ratio, digits = 1, signed = false) {
  const number = toFiniteNumber(ratio);
  if (number == null) return "—";
  return `${formatNumber(number * 100, digits, signed)}%`;
}

export function formatDateTime(value) {
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
