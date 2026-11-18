import { NextResponse, type NextRequest } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { ServiceMetricsSchema } from "@/lib/schemas";

/** GET /api/metrics/[serviceId] -> single-service metrics (staff). */
export async function GET(request: NextRequest, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const query = request.nextUrl.searchParams.toString();
  const result = await backend(`/metrics/${encodeURIComponent(serviceId)}${query ? `?${query}` : ""}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = ServiceMetricsSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

