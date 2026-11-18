import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { backend } from "@/lib/backend";
import { PublicStatusSchema } from "@/lib/schemas";

/** GET /api/public/status -> sanitized public status page (no auth). */
export async function GET() {
  // Runtime data access: with cacheComponents enabled this keeps the handler
  // request-time instead of letting it prerender at build.
  await headers();

  const result = await backend("/public/status");
  if (!result.ok) {
    return NextResponse.json({ error: result.detail }, { status: result.status });
  }

  const parsed = PublicStatusSchema.safeParse(result.data);
  if (!parsed.success) {
    return NextResponse.json({ error: "Backend returned an unexpected payload." }, { status: 502 });
  }
  return NextResponse.json(parsed.data);
}
