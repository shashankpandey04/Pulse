import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { AckInputSchema, IncidentResponseSchema } from "@/lib/schemas";

/** PATCH /api/incidents/[incidentId]/ack -> acknowledge (operator/admin). */
export async function PATCH(request: Request, { params }: { params: Promise<{ incidentId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { incidentId } = await params;

  let body: unknown = {};
  try {
    const text = await request.text();
    if (text) body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsedInput = AckInputSchema.safeParse(body);
  if (!parsedInput.success) {
    return NextResponse.json({ error: parsedInput.error.issues[0]?.message ?? "Invalid input." }, { status: 422 });
  }

  const result = await backend(`/incidents/${encodeURIComponent(incidentId)}/ack`, {
    method: "PATCH",
    body: parsedInput.data,
    token,
  });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = IncidentResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
