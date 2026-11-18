// Server-only bridge to the Pulse FastAPI backend, used by the self-hosted
// Next.js API routes under app/api. Pages and client components never import this.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export type BackendResult<T> = { ok: true; status: number; data: T } | { ok: false; status: number; detail: string };

export async function backend(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<BackendResult<unknown>> {
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 502, detail: "Pulse backend is unreachable." };
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload && typeof (payload as { detail: unknown }).detail === "string"
        ? (payload as { detail: string }).detail
        : `Backend request failed (${response.status}).`;
    return { ok: false, status: response.status, detail };
  }
  return { ok: true, status: response.status, data: payload };
}
