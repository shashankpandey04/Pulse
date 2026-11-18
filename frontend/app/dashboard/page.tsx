import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { NotificationSetup } from "@/components/notification-setup";
import { StateLabel, Panel, Stat } from "@/components/ui";
import { pageApi, PageApiError } from "@/lib/server-api";
import { DashboardSchema, UserResponseSchema } from "@/lib/schemas";

// Auth-gated: the session check intentionally blocks rendering (redirects
// anonymous users / staff to the right place), so opt out of the instant
// navigation + static-shell validation of Cache Components.
export const instant = false;

async function loadSession(): Promise<{ role: string } | null> {
  try {
    const user = await pageApi("/auth/me", UserResponseSchema);
    return { role: user.role };
  } catch (error) {
    if (error instanceof PageApiError && (error.status === 401 || error.status === 400)) return null;
    throw error;
  }
}

async function SubscriberView() {
  const dashboard = await pageApi("/dashboard", DashboardSchema);
  const status = dashboard.status;

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Your dashboard</h1>
      <p className="mt-1 text-sm text-muted">You are subscribed to the status of all monitored services.</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {status &&
          Object.entries(status.summary).map(([state, count]) => (
            <Stat key={state} label={state} value={count} />
          ))}
      </div>
      {status && status.services.length > 0 && (
        <div className="mt-6">
          <Panel title="Monitored services">
            <ul className="flex flex-col divide-y divide-edge">
              {status.services.map((service) => (
                <li key={service.service_id} className="flex items-center justify-between py-2 text-sm">
                  <span>{service.name}</span>
                  <StateLabel state={service.state} color={service.color} />
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}
    </main>
  );
}

export default async function DashboardPage() {
  const session = await loadSession();
  if (!session) {
    // Anonymous visitors are already redirected here by proxy.ts; this path
    // only runs for an expired/invalid cookie. (Cache Components streams this
    // redirect instruction to the client router.)
    redirect("/auth/login");
  }
  if (session.role === "operator") {
    redirect("/dashboard/operator");
  }
  if (session.role === "admin") {
    redirect("/dashboard/admin");
  }
  return (
    <>
      <SiteHeader />
      <NotificationSetup required={false} />
      <SubscriberView />
    </>
  );
}
