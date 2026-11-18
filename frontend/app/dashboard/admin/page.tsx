import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { AccessPanel } from "@/components/access-panel";
import { Panel, Stat } from "@/components/ui";
import { UsersPanel } from "@/components/users-panel";
import { ServicesPanel } from "@/components/services-panel";
import { pageApi, PageApiError } from "@/lib/server-api";
import { DashboardSchema, NotificationListSchema, UserResponseSchema } from "@/lib/schemas";

// Auth-gated admin console: blocks on the session check by design.
export const instant = false;

async function loadAdmin(): Promise<{ uid: string } | null> {
  try {
    const user = await pageApi("/auth/me", UserResponseSchema);
    return user.role === "admin" ? { uid: user.uid } : null;
  } catch (error) {
    if (error instanceof PageApiError && (error.status === 401 || error.status === 400)) return null;
    throw error;
  }
}

function formatWhen(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

async function AdminSummaries() {
  const dashboard = await pageApi("/dashboard", DashboardSchema);
  return (
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {dashboard.users_summary && (
        <>
          <Stat label="Users" value={dashboard.users_summary.total} />
          <Stat label="Admins" value={dashboard.users_summary.by_role["admin"] ?? 0} />
          <Stat label="Operators" value={dashboard.users_summary.by_role["operator"] ?? 0} />
          <Stat label="Subscribers" value={dashboard.users_summary.by_role["subscriber"] ?? 0} />
        </>
      )}
      {dashboard.notifications_summary && <Stat label="Webhook failed" value={dashboard.notifications_summary.failed} />}
    </div>
  );
}

async function NotificationsTable() {
  const data = await pageApi("/notifications?page_size=20", NotificationListSchema);
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
          <th className="py-2 pr-4">When</th>
          <th className="py-2 pr-4">Event</th>
          <th className="py-2 pr-4">Service</th>
          <th className="py-2 pr-4">Delivered</th>
          <th className="py-2">Message</th>
        </tr>
      </thead>
      <tbody>
        {data.notifications.length === 0 && (
          <tr>
            <td colSpan={5} className="py-3 text-muted">
              No webhook deliveries recorded yet.
            </td>
          </tr>
        )}
        {data.notifications.map((n) => (
          <tr key={n.notification_id} className="border-b border-edge last:border-b-0">
            <td className="py-2 pr-4 font-mono text-xs">{formatWhen(n.created_at)}</td>
            <td className="py-2 pr-4 font-mono text-xs">{n.event_type}</td>
            <td className="py-2 pr-4">{n.service_name}</td>
            <td className="py-2 pr-4 font-mono text-xs">{n.delivered ? "yes" : `no (${n.last_error ?? "error"})`}</td>
            <td className="py-2 text-xs text-muted">{n.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function AdminDashboardPage() {
  const admin = await loadAdmin();
  if (!admin) {
    // Signed in without the admin role (anonymous visitors are already turned
    // away by proxy.ts before the page renders).
    return (
      <AccessPanel
        title="Admin access required"
        message="Your account does not have the admin role needed for the admin console."
      />
    );
  }

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-8">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Admin console</h1>
            <p className="mt-1 text-sm text-muted">Manage users, the service catalogue and state thresholds.</p>
          </div>
          <Link
            href="/dashboard/operator"
            className="inline-flex h-9 items-center border border-black bg-white px-3 text-sm font-medium hover:bg-neutral-100"
          >
            Operations console
          </Link>
        </header>

        <div className="border border-edge p-4">
          <Suspense fallback={<p className="text-sm text-muted">Loading summaries…</p>}>
            <AdminSummaries />
          </Suspense>
        </div>

        <UsersPanel selfUid={admin.uid} />

        <ServicesPanel canManage />

        <Panel title="Webhook notifications (latest 20)">
          <Suspense fallback={<p className="text-sm text-muted">Loading notifications…</p>}>
            <NotificationsTable />
          </Suspense>
        </Panel>
      </main>
    </>
  );
}
