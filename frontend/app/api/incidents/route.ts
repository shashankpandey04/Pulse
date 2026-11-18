import { NextResponse, type NextRequest } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { IncidentListResponseSchema } from "@/lib/schemas";

/** GET /api/incidents -> paginated incident list (staff). */
export async function GET(request: NextRequest) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const query = request.nextUrl.searchParams.toString();
  const result = await backend(`/incidents${query ? `?${query}` : ""}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = IncidentListResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
