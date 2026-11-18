/** Auth cookie helpers for the self-hosted API routes (server-side only). */

import { cookies } from "next/headers";

export const AUTH_COOKIE = "pulse_token";

export async function getAuthToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(AUTH_COOKIE)?.value ?? null;
}

/**
 * Cookie attributes. `secure` is derived from the request protocol
 * (x-forwarded-proto, set by any TLS-terminating proxy) so the session works
 * both on plain-HTTP self-hosted deployments and behind HTTPS.
 */
export function authCookieOptions(maxAgeSeconds: number, secure: boolean) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure,
    path: "/",
    maxAge: maxAgeSeconds,
  };
}

/** True when the request came in over HTTPS (proxies set x-forwarded-proto). */
export function requestIsSecure(request: Request): boolean {
  return (request.headers.get("x-forwarded-proto") ?? "").split(",")[0].trim() === "https";
}

/** Default token lifetime — matches the backend's ACCESS_TOKEN_EXPIRE_MINUTES (720). */
export const TOKEN_MAX_AGE_SECONDS = 60 * 60 * 12;
