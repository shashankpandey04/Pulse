"use client";

/**
 * Email notification subscription panel (replaces the Firebase push panel).
 *
 * Subscribing stores the signed-in account's own email address in the backend
 * (`email_subscriptions` collection); whenever a monitored service changes
 * state, the backend emails every subscribed account individually. The
 * initial state comes from the dashboard payload as props — this component
 * only talks to the network on subscribe/unsubscribe clicks.
 *
 * Subscription is optional for subscribers; operators and admins must stay
 * subscribed (`required`), so the panel stays pinned until they are.
 */

import { useState } from "react";
import { apiFetch } from "@/lib/client";
import { EmailSubscriptionSchema, EmailSubscriptionStatusSchema, type EmailSubscription } from "@/lib/schemas";
import { Notice, PrimaryButton, SecondaryButton } from "@/components/ui";

type Summary = { subscribed: boolean; email: string | null };
type Props = { required: boolean; summary: Summary };

function formatWhen(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function EmailNotifications({ required, summary }: Props) {
  const [state, setState] = useState<Summary>(summary);
  const [stats, setStats] = useState<EmailSubscription | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSubscribed, setJustSubscribed] = useState(false);

  async function subscribe() {
    setBusy(true);
    setError(null);
    try {
      const sub = EmailSubscriptionSchema.parse(
        await apiFetch<unknown>("/api/email-subscriptions", { method: "POST", body: JSON.stringify({}) }),
      );
      setState({ subscribed: true, email: sub.email });
      setStats(sub);
      setJustSubscribed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not subscribe.");
    } finally {
      setBusy(false);
    }
  }

  async function unsubscribe() {
    setBusy(true);
    try {
      await apiFetch("/api/email-subscriptions", { method: "DELETE" });
      setState({ subscribed: false, email: null });
      setStats(null);
      setJustSubscribed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unsubscribe.");
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    setBusy(true);
    try {
      const status = EmailSubscriptionStatusSchema.parse(
        await apiFetch<unknown>("/api/email-subscriptions"),
      );
      if (status.subscription) {
        setState({ subscribed: true, email: status.subscription.email });
        setStats(status.subscription);
      } else {
        setState({ subscribed: false, email: null });
        setStats(null);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load subscription state.");
    } finally {
      setBusy(false);
    }
  }

  const missingRequired = required && !state.subscribed;

  return (
    <section className={`border bg-white ${missingRequired ? "border-black" : "border-edge"}`}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          Email notifications{required ? " — required for staff" : ""}
        </h2>
        {state.subscribed && state.email && (
          <span className="font-mono text-xs text-muted">{state.email}</span>
        )}
      </header>
      <div className="flex flex-col gap-3 p-4">
        <p className="text-sm text-muted">
          Receive an email at your account address whenever a monitored service changes state (healthy → down →
          recovered, slow, flaky).{" "}
          {missingRequired && (
            <strong className="text-black">Operators and admins must stay subscribed by email.</strong>
          )}
        </p>

        {error && <Notice kind="error">{error}</Notice>}
        {justSubscribed && state.subscribed && (
          <Notice kind="success">Subscribed — state-change emails will be sent to {state.email}.</Notice>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {!state.subscribed ? (
            <PrimaryButton type="button" onClick={subscribe} disabled={busy}>
              {busy ? "Subscribing…" : "Subscribe by email"}
            </PrimaryButton>
          ) : (
            <>
              <span className="font-mono text-xs text-muted">subscribed</span>
              <SecondaryButton type="button" onClick={unsubscribe} disabled={busy}>
                {busy ? "Working…" : "Unsubscribe"}
              </SecondaryButton>
              <SecondaryButton type="button" onClick={refresh} disabled={busy}>
                Refresh delivery stats
              </SecondaryButton>
            </>
          )}
        </div>

        {stats && (
          <p className="font-mono text-xs text-muted">
            subscribed {formatWhen(stats.created_at)} · {stats.send_count} sent
            {stats.fail_count > 0 ? ` · ${stats.fail_count} failed` : ""}
            {stats.last_error ? ` · last error: ${stats.last_error}` : ""}
          </p>
        )}
      </div>
    </section>
  );
}
