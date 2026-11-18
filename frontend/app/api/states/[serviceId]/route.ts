import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { MessageSchema, StateConfigResponseSchema, StateConfigUpsertInputSchema } from "@/lib/schemas";

/** GET /api/states/[serviceId] -> effective config (staff). */
export async function GET(_request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const result = await backend(`/states/${encodeURIComponent(serviceId)}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = StateConfigResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** PUT /api/states/[serviceId] -> upsert config (operator/admin). */
export async function PUT(request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsedInput = StateConfigUpsertInputSchema.safeParse(body);
  if (!parsedInput.success) {
    return NextResponse.json({ error: parsedInput.error.issues[0]?.message ?? "Invalid input." }, { status: 422 });
  }

  const result = await backend(`/states/${encodeURIComponent(serviceId)}`, {
    method: "PUT",
    body: parsedInput.data,
    token,
  });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = StateConfigResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** DELETE /api/states/[serviceId] -> reset to defaults (admin). */
export async function DELETE(_request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const result = await backend(`/states/${encodeURIComponent(serviceId)}`, { method: "DELETE", token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = MessageSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
