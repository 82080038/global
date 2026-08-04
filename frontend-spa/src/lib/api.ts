const API_BASE = "";
const API_KEY = "dev-secret-key-2026";

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  if (extra) {
    const entries =
      extra instanceof Headers
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
  const headers = buildHeaders(init?.headers) as Record<string, string>;
  if (init?.body && !("Content-Type" in headers)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ message: response.statusText }));
    throw new APIError(response.status, errorData.message || `HTTP ${response.status}`, errorData);
  }
  return response;
}

export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: unknown,
  ) {
    super(message);
    this.name = "APIError";
  }
}

export async function safeApiFetch<T>(path: string, init?: RequestInit): Promise<{ data: T | null; error: APIError | null }> {
  try {
    const response = await apiFetch(path, init);
    const data = (await response.json()) as T;
    return { data, error: null };
  } catch (error) {
    return {
      data: null,
      error: error instanceof APIError ? error : new APIError(0, "Unknown error", { originalError: error }),
    };
  }
}

export { API_BASE };
