import Link from "next/link";
import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { AccessPanel } from "@/components/access-panel";
import { NotificationSetup } from "@/components/notification-setup";
import { Panel, StateLabel } from "@/components/ui";
import { IncidentsPanel } from "@/components/incidents-panel";
import { pageApi, PageApiError } from "@/lib/server-api";
import { MetricsOverviewSchema, ReliabilityListSchema, ServiceListResponseSchema, UserResponseSchema, STATE_COLORS } from "@/lib/schemas";

// Auth-gated staff console: blocks on the session check by design.
export const instant = false;

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

async function loadStaffSession(): Promise<{ uid: string; role: "admin" | "operator" } | null> {
  try {
    const user = await pageApi("/auth/me", UserResponseSchema);
    if (user.role === "admin" || user.role === "operator") return { uid: user.uid, role: user.role };
    return null;
  } catch (error) {
    if (error instanceof PageApiError && (error.status === 401 || error.status === 400)) return null;
    throw error;
  }
}

export default async function OperatorDashboardPage() {
  const session = await loadStaffSession();
  if (!session) {
    // Signed in without a staff role (anonymous visitors are already turned
    // away by proxy.ts before the page renders).
    return (
      <AccessPanel
        title="Operator access required"
        message="Your account does not have the operator or admin role needed for the operations console."
      />
    );
  }

  const [metrics, reliability, catalogue] = await Promise.all([
    pageApi("/metrics", MetricsOverviewSchema),
    pageApi("/reliability", ReliabilityListSchema),
    pageApi("/catalogue?page_size=100", ServiceListResponseSchema),
  ]);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-8">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Operations console</h1>
          <p className="mt-1 text-sm text-muted">
            Incidents, detection/resolution speed, and reliability of every monitored service (24h metrics · 30d
            reliability).
          </p>
        </header>

        <IncidentsPanel role={session.role} />

        <NotificationSetup required />

        <Panel title="Metrics — last 24 hours">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-4">Service</th>
                <th className="py-2 pr-4">Checks</th>
                <th className="py-2 pr-4">Success</th>
                <th className="py-2 pr-4">Avg latency</th>
                <th className="py-2 pr-4">p95</th>
                <th className="py-2 pr-4">MTTD</th>
                <th className="py-2 pr-4">MTTR</th>
                <th className="py-2">State</th>
              </tr>
            </thead>
            <tbody>
              {metrics.services.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-3 text-muted">
                    No services registered.
                  </td>
                </tr>
              )}
              {metrics.services.map((m) => (
                <tr key={m.service_id} className="border-b border-edge last:border-b-0">
                  <td className="py-2 pr-4 font-medium">{m.service_name}</td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    {m.total_checks} ({m.failed_checks} failed)
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">{pct(m.success_rate)}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{m.avg_latency_ms === null ? "—" : `${Math.round(m.avg_latency_ms)} ms`}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{m.p95_latency_ms === null ? "—" : `${Math.round(m.p95_latency_ms)} ms`}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{m.mttd_seconds === null ? "—" : `${Math.round(m.mttd_seconds)}s`}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{m.mttr_seconds === null ? "—" : `${Math.round(m.mttr_seconds)}s`}</td>
                  <td className="py-2">{m.last_state ? <StateLabel state={m.last_state} color={STATE_COLORS[m.last_state]} /> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Reliability — last 30 days">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-4">Service</th>
                <th className="py-2 pr-4">Availability</th>
                <th className="py-2 pr-4">Target</th>
                <th className="py-2 pr-4">Meeting target</th>
                <th className="py-2 pr-4">Budget left</th>
                <th className="py-2 pr-4">Downtime used</th>
                <th className="py-2">Incidents</th>
              </tr>
            </thead>
            <tbody>
              {reliability.services.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-3 text-muted">
                    No services registered.
                  </td>
                </tr>
              )}
              {reliability.services.map((r) => (
                <tr key={r.service_id} className="border-b border-edge last:border-b-0">
                  <td className="py-2 pr-4 font-medium">{r.service_name}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.availability_pct.toFixed(3)}%</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.target_pct}%</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.meeting_target ? "yes" : "no"}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.error_budget_remaining_pct.toFixed(1)}%</td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    {r.consumed_downtime_minutes.toFixed(1)} / {r.allowed_downtime_minutes.toFixed(1)} min
                  </td>
                  <td className="py-2 font-mono text-xs">{r.incident_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Service catalogue">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-4">Service</th>
                <th className="py-2 pr-4">Owner</th>
                <th className="py-2 pr-4">Interval</th>
                <th className="py-2 pr-4">Timeout</th>
                <th className="py-2 pr-4">Target</th>
                <th className="py-2">Enabled</th>
              </tr>
            </thead>
            <tbody>
              {catalogue.services.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-3 text-muted">
                    No services registered.
                  </td>
                </tr>
              )}
              {catalogue.services.map((service) => (
                <tr key={service.service_id} className="border-b border-edge last:border-b-0">
                  <td className="py-2 pr-4 font-medium">
                    <Link href={`/dashboard/services/${service.service_id}`} className="underline-offset-2 hover:underline">
                      {service.name}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">{service.owner_email}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{service.check_interval_seconds}s</td>
                  <td className="py-2 pr-4 font-mono text-xs">{service.timeout_seconds}s</td>
                  <td className="py-2 pr-4 font-mono text-xs">{service.reliability_target}%</td>
                  <td className="py-2 font-mono text-xs">{service.enabled ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </main>
    </>
  );
}
