import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";
import { AdminUserUpdateInputSchema, MessageSchema, UserResponseSchema } from "@/lib/schemas";

/** PATCH /api/admin/users/[uid] -> change role / active (admin only). */
export async function PATCH(request: Request, { params }: { params: Promise<{ uid: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { uid } = await params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const parsedInput = AdminUserUpdateInputSchema.safeParse(body);
  if (!parsedInput.success) {
    return NextResponse.json({ error: parsedInput.error.issues[0]?.message ?? "Invalid input." }, { status: 422 });
  }

  const result = await backend(`/admin/users/${encodeURIComponent(uid)}`, { method: "PATCH", body: parsedInput.data, token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = UserResponseSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}

/** DELETE /api/admin/users/[uid] -> soft delete / deactivate (admin only). */
export async function DELETE(_request: Request, { params }: { params: Promise<{ uid: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { uid } = await params;

  const result = await backend(`/admin/users/${encodeURIComponent(uid)}`, { method: "DELETE", token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = MessageSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
