import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { MessageSchema, ServiceResponseSchema, ServiceUpdateInputSchema } from "@/lib/schemas";

/** GET /api/catalogue/[serviceId] -> one service (staff). */
export async function GET(_request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const result = await backend(`/catalogue/${encodeURIComponent(serviceId)}`, { token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = ServiceResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** PATCH /api/catalogue/[serviceId] -> partial update (admin). */
export async function PATCH(request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
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

  const parsedInput = ServiceUpdateInputSchema.safeParse(body);
  if (!parsedInput.success) {
    return NextResponse.json({ error: parsedInput.error.issues[0]?.message ?? "Invalid input." }, { status: 422 });
  }

  const result = await backend(`/catalogue/${encodeURIComponent(serviceId)}`, {
    method: "PATCH",
    body: parsedInput.data,
    token,
  });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = ServiceResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** DELETE /api/catalogue/[serviceId] -> remove service (admin). */
export async function DELETE(_request: Request, { params }: { params: Promise<{ serviceId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { serviceId } = await params;

  const result = await backend(`/catalogue/${encodeURIComponent(serviceId)}`, { method: "DELETE", token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = MessageSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
