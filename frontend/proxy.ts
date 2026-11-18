import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic auth gate for the dashboard area (Next.js 16 Proxy, formerly
 * Middleware). Requests without a session cookie get a real HTTP redirect to
 * the login page before any page renders — pages themselves still validate the
 * cookie against the backend, because the Proxy must stay fast and must not
 * call the API (see the Proxy "Limitations" docs).
 */
export function proxy(request: NextRequest) {
  // Same cookie name as lib/auth (inlined to keep the Proxy bundle lean).
  const token = request.cookies.get("pulse_token")?.value;
  if (!token) {
    const login = new URL("/auth/login", request.url);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
