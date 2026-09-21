import ENGLISH_COPY from "./copy.json";

const ENGLISH_LOCALE = "en-US";

function getPathValue(obj, key) {
  return String(key || "")
    .split(".")
    .reduce((acc, part) => (acc && typeof acc === "object" ? acc[part] : undefined), obj);
}

function interpolate(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, key) => {
    const value = vars[key];
    return value == null ? "" : String(value);
  });
}

export function copy(key, vars = {}) {
  return interpolate(getPathValue(ENGLISH_COPY, key) ?? key, vars);
}

export function formatCurrency(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
    ...options,
  }).format(value);
}

export function formatPrice(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, options).format(value);
}

export function formatPercent(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    ...options,
  }).format(value);
}

export function formatDateTime(value, options = {}) {
  try {
    return new Intl.DateTimeFormat(ENGLISH_LOCALE, {
      dateStyle: "medium",
      timeStyle: "short",
      ...options,
    }).format(new Date(value));
  } catch {
    return "";
  }
}

export function formatSignedNumber(value, digits = 2, { percent = false } = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  const n = Number(value);
  const sign = n >= 0 ? "+" : "";
  if (percent) {
    return `${sign}${formatNumber(Math.abs(n), {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}%`.replace(/^\+-/, "-");
  }
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`.replace(/^\+-/, "-");
}
