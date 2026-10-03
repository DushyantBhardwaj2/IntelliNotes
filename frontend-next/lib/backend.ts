export function getBackendUrl(): string {
  const url = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  return url.replace(/\/+$/, "");
}

export function getBackendHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const apiKey = process.env.API_KEY;
  if (apiKey && apiKey.trim()) {
    headers["X-API-Key"] = apiKey.trim();
  }
  return headers;
}
