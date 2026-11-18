import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { DashboardSchema } from "@/lib/schemas";

/** GET /api/dashboard -> role-shaped dashboard payload. */
export async function GET() {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const result = await backend("/dashboard", { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = DashboardSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
