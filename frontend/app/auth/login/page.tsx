"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/client";
import { LoginInputSchema } from "@/lib/schemas";
import { Field, Notice, PrimaryButton, inputClass } from "@/components/ui";
import { UserResponseSchema } from "@/lib/schemas";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const input = { email: String(form.get("email") ?? ""), password: String(form.get("password") ?? "") };

    const parsed = LoginInputSchema.safeParse(input);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }

    setBusy(true);
    try {
      await apiFetch("/api/auth/login", { method: "POST", body: JSON.stringify(parsed.data) });
      const me = await apiFetch<unknown>("/api/auth/me");
      const user = UserResponseSchema.parse(me);
      router.push(user.role === "subscriber" ? "/dashboard" : `/dashboard/${user.role}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4 border border-edge p-6">
        {error && <Notice kind="error">{error}</Notice>}
        <Field label="Email">
          <input name="email" type="email" required autoComplete="email" className={inputClass} />
        </Field>
        <Field label="Password">
          <input name="password" type="password" required autoComplete="current-password" className={inputClass} />
        </Field>
        <PrimaryButton type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </PrimaryButton>
        <p className="text-sm text-muted">
          No account? <Link href="/auth/register" className="underline">Create one</Link>.
        </p>
      </form>
    </main>
  );
}
