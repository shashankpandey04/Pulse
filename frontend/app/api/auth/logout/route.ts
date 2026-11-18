import { NextResponse } from "next/server";
import { AUTH_COOKIE, requestIsSecure } from "@/lib/auth";

/** POST /api/auth/logout -> clears the session cookie. */
export async function POST(request: Request) {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: requestIsSecure(request),
    path: "/",
    maxAge: 0,
  });
  return response;
}
