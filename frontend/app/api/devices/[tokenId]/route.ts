import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { getAuthToken } from "@/lib/auth";

/** DELETE /api/devices/[tokenId] -> unsubscribe one of the caller's devices. */
export async function DELETE(_request: Request, { params }: { params: Promise<{ tokenId: string }> }) {
  const token = await getAuthToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  const { tokenId } = await params;

  const result = await backend(`/devices/${encodeURIComponent(tokenId)}`, { method: "DELETE", token });
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }
  return new NextResponse(null, { status: 204 });
}
