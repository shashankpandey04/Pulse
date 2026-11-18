"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/client";
import { RegisterInputSchema, UserResponseSchema } from "@/lib/schemas";
import { Field, Notice, PrimaryButton, inputClass } from "@/components/ui";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const raw = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    };

    const parsed = RegisterInputSchema.safeParse(raw);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }

    setBusy(true);
    try {
      await apiFetch("/api/auth/register", { method: "POST", body: JSON.stringify(parsed.data) });
      // Every new account is a subscriber.
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Create account</h1>
      <p className="mt-1 text-sm text-muted">New accounts are subscribers — they can follow the public status page.</p>
      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4 border border-edge p-6">
        {error && <Notice kind="error">{error}</Notice>}
        <Field label="Email">
          <input name="email" type="email" required autoComplete="email" className={inputClass} />
        </Field>
        <Field label="Password (min 8 characters)">
          <input name="password" type="password" required minLength={8} autoComplete="new-password" className={inputClass} />
        </Field>
        <PrimaryButton type="submit" disabled={busy} className="w-full">
          {busy ? "Creating…" : "Create account"}
        </PrimaryButton>
        <p className="text-sm text-muted">
          Already registered? <Link href="/auth/login" className="underline">Sign in</Link>.
        </p>
      </form>
    </main>
  );
}
