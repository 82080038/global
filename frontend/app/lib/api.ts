const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  if (extra) {
    const entries = extra instanceof Headers
      ? Array.from(extra.entries())
      : Array.isArray(extra)
        ? extra
        : Object.entries(extra);
    for (const [k, v] of entries) {
      headers[k] = v as string;
    }
  }
  return headers;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = buildHeaders(init?.headers) as Record<string, string>;
  if (init?.body && !("Content-Type" in headers)) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export { API_BASE };
