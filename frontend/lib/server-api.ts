/**
 * Server-side data access for pages.
 *
 * Pages NEVER call the FastAPI backend. They call our own Next.js API routes
 * (the self-hosted API layer), which in turn talk to the backend and validate
 * every payload with zod. This helper forwards the auth cookie to those routes.
 */

import { cookies, headers } from "next/headers";
import { AUTH_COOKIE } from "@/lib/auth";
import type { z } from "zod";

export async function ownOrigin(): Promise<string> {
  const h = await headers();
  const host = h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") || host.startsWith("127.") ? "http" : "https");
  return `${proto}://${host}`;
}

export class PageApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Fetch one of our own /api routes (server component) and validate the response. */
export async function pageApi<S extends z.ZodType>(path: string, schema: S): Promise<z.output<S>> {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;

  let response: Response;
  try {
    response = await fetch(`${await ownOrigin()}/api${path}`, {
      headers: token ? { cookie: `${AUTH_COOKIE}=${token}` } : undefined,
      cache: "no-store",
    });
  } catch {
    throw new PageApiError("Pulse API is unreachable.", 502);
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
      payload && typeof payload === "object" && "error" in payload && typeof (payload as { error: unknown }).error === "string"
        ? (payload as { error: string }).error
        : `Request failed (${response.status}).`;
    throw new PageApiError(detail, response.status);
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new PageApiError("Pulse API returned an unexpected payload.", 502);
  }
  return parsed.data;
}
