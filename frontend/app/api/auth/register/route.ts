import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { AUTH_COOKIE, TOKEN_MAX_AGE_SECONDS, authCookieOptions, requestIsSecure } from "@/lib/auth";
import { AuthEnvelopeSchema, RegisterInputSchema, UserResponseSchema } from "@/lib/schemas";

/** POST /api/auth/register -> creates a subscriber account and signs the user in. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsedInput = RegisterInputSchema.safeParse(body);
  if (!parsedInput.success) {
    return NextResponse.json({ error: parsedInput.error.issues[0]?.message ?? "Invalid input." }, { status: 422 });
  }

  const result = await backend("/auth/register", { method: "POST", body: parsedInput.data });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = AuthEnvelopeSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }

  const response = NextResponse.json(UserResponseSchema.parse(parsed.data.user), { status: 201 });
  response.cookies.set(AUTH_COOKIE, parsed.data.access_token, authCookieOptions(TOKEN_MAX_AGE_SECONDS, requestIsSecure(request)));
  return response;
}
