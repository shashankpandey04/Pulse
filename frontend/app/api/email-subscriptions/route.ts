import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { EmailSubscriptionSchema, EmailSubscriptionStatusSchema } from "@/lib/schemas";

/** GET /api/email-subscriptions -> the signed-in user's subscription (or null). */
export async function GET() {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const result = await backend("/email-subscriptions", { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = EmailSubscriptionStatusSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** POST /api/email-subscriptions -> subscribe the account's email address. */
export async function POST() {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const result = await backend("/email-subscriptions", { method: "POST", body: {}, token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = EmailSubscriptionSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data, { status: result.status === 201 ? 201 : 200 });
}

/** DELETE /api/email-subscriptions -> unsubscribe the account's email address. */
export async function DELETE() {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const result = await backend("/email-subscriptions", { method: "DELETE", token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }
  return new NextResponse(null, { status: 204 });
}
