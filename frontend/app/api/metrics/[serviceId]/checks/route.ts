import { NextResponse, type NextRequest } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { CheckResultListResponseSchema } from "@/lib/schemas";

/** GET /api/metrics/[serviceId]/checks -> raw stored check results (staff). */
export async function GET(request: NextRequest, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const query = request.nextUrl.searchParams.toString();
  const result = await backend(`/metrics/${encodeURIComponent(serviceId)}/checks${query ? `?${query}` : ""}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = CheckResultListResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
