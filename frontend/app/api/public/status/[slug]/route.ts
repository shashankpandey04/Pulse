import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { backend } from "@/lib/backend";
import { PublicServiceDetailSchema } from "@/lib/schemas";

/** GET /api/public/status/[slug] -> one service + incident history (no auth). */
export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  await headers(); // keep request-time (see /api/public/status)
  const { slug } = await params;

  const result = await backend(`/public/status/${encodeURIComponent(slug)}`);
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = PublicServiceDetailSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
