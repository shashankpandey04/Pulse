/** Server-rendered top bar. Shows session state via our own /api/auth/me. */

import Link from "next/link";
import { cookies } from "next/headers";
import { AUTH_COOKIE } from "@/lib/auth";
import { ownOrigin } from "@/lib/server-api";
import { UserResponseSchema } from "@/lib/schemas";
import { LogoutButton } from "@/components/logout-button";
import { LinkButton } from "@/components/ui";

async function fetchUser(): Promise<{ email: string; role: string } | null> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return null;
  try {
    const response = await fetch(`${await ownOrigin()}/api/auth/me`, {
      headers: { cookie: `${AUTH_COOKIE}=${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const parsed = UserResponseSchema.safeParse(await response.json());
    return parsed.success ? { email: parsed.data.email, role: parsed.data.role } : null;
  } catch {
    return null;
  }
}

/** Static shell shown while the real header streams in (Cache Components). */
export function HeaderFallback() {
  return (
    <header className="border-b border-edge">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-mono text-sm font-bold uppercase tracking-widest">
            Pulse
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/status" className="hover:underline">
              Status
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <LinkButton href="/auth/login">Sign in</LinkButton>
          <LinkButton href="/auth/register">Create account</LinkButton>
        </div>
      </div>
    </header>
  );
}

export async function SiteHeader() {
  const user = await fetchUser();
  return (
    <header className="border-b border-edge">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-mono text-sm font-bold uppercase tracking-widest">
            Pulse
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/status" className="hover:underline">
              Status
            </Link>
            {user && user.role !== "subscriber" && (
              <Link href={user.role === "admin" ? "/dashboard/admin" : "/dashboard/operator"} className="hover:underline">
                Dashboard
              </Link>
            )}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              <span className="font-mono text-xs text-muted">
                {user.email} · {user.role}
              </span>
              <LogoutButton />
            </>
          ) : (
            <>
              <LinkButton href="/auth/login">Sign in</LinkButton>
              <LinkButton href="/auth/register">Create account</LinkButton>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
