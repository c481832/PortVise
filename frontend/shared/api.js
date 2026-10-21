// JSON fetch helpers shared by the advisor and arena frontends.

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

export function getJson(url) {
  return requestJson(url);
}

export function postJson(url, payload) {
  return requestJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteJson(url) {
  return requestJson(url, { method: "DELETE" });
}
