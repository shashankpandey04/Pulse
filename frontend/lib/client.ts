/**
 * Client-side fetch helper for browser components.
 *
 * Browser components call ONLY our own Next.js API routes (relative /api/...),
 * never the FastAPI backend. Cookies are attached automatically by the browser.
 */

export type ApiError = Error & { status: number };

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });

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
      payload && typeof payload === "object" && "error" in payload && typeof (payload as { error: unknown }).error === "string"
        ? (payload as { error: string }).error
        : `Request failed (${response.status}).`;
    const error = new Error(detail) as ApiError;
    error.status = response.status;
    throw error;
  }
  return payload as T;
}
