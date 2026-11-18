import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { IncidentResponseSchema } from "@/lib/schemas";

/** GET /api/incidents/[incidentId] -> one incident with its timeline (staff). */
export async function GET(_request: Request, { params }: { params: Promise<{ incidentId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { incidentId } = await params;

  const result = await backend(`/incidents/${encodeURIComponent(incidentId)}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = IncidentResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
