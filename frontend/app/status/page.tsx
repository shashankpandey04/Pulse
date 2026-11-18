import { Suspense } from "react";
import Link from "next/link";
import { SiteHeader, HeaderFallback } from "@/components/site-header";
import { StateLabel, Panel } from "@/components/ui";
import { HistoryBars, HistoryLegend } from "@/components/history-bars";
import { pageApi } from "@/lib/server-api";
import { PublicStatusSchema } from "@/lib/schemas";

function formatWhen(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

async function StatusContent() {
  const status = await pageApi("/public/status", PublicStatusSchema);

  return (
    <div className="flex flex-col gap-6">
      <Panel title="All services">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
              <th className="py-2 pr-4">Service</th>
              <th className="py-2 pr-4">State</th>
              <th className="py-2 pr-4">Last 24 hours</th>
              <th className="py-2 pr-4">Last checked</th>
              <th className="py-2">Latency</th>
            </tr>
          </thead>
          <tbody>
            {status.services.length === 0 && (
              <tr>
                <td colSpan={5} className="py-3 text-muted">
                  No services are being monitored yet.
                </td>
              </tr>
            )}
            {status.services.map((service) => (
              <tr key={service.service_id} className="border-b border-edge last:border-b-0">
                <td className="py-2 pr-4">
                  <Link href={`/status/${service.slug}`} className="font-medium underline-offset-2 hover:underline">
                    {service.name}
                  </Link>
                  {service.description && <div className="text-xs text-muted">{service.description}</div>}
                </td>
                <td className="py-2 pr-4">
                  <StateLabel state={service.state} color={service.color} />
                </td>
                <td className="py-2 pr-4 w-64">
                  <HistoryBars buckets={service.history} granularity="hour" />
                </td>
                <td className="py-2 pr-4 font-mono text-xs">{formatWhen(service.last_check_at)}</td>
                <td className="py-2 font-mono text-xs">
                  {service.last_latency_ms === null ? "—" : `${service.last_latency_ms} ms`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <HistoryLegend colors={status.colors} />
      </Panel>

      <Panel title="Active incidents">
        {status.active_incidents.length === 0 ? (
          <p className="text-sm text-muted">No active incidents.</p>
        ) : (
          <ul className="flex flex-col gap-4">
            {status.active_incidents.map((incident) => (
              <li key={incident.incident_id} className="border border-edge p-4">
                <div className="flex items-baseline justify-between gap-4">
                  <h3 className="font-medium">{incident.title}</h3>
                  <span className="font-mono text-xs uppercase text-muted">{incident.status}</span>
                </div>
                <p className="mt-1 font-mono text-xs text-muted">Opened {formatWhen(incident.opened_at)}</p>
                <ol className="mt-3 flex flex-col gap-1 border-l border-edge pl-4 text-sm">
                  {incident.events.map((event, index) => (
                    <li key={`${incident.incident_id}-${index}`}>
                      <span className="font-mono text-xs text-muted">{formatWhen(event.at)}</span> — {event.message}
                    </li>
                  ))}
                </ol>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

export default function StatusPage() {
  return (
    <>
      <Suspense fallback={<HeaderFallback />}>
        <SiteHeader />
      </Suspense>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Service status</h1>
        <p className="mt-1 text-sm text-muted">Live health of every monitored service, refreshed on each visit.</p>
        <div className="mt-6">
          <Suspense fallback={<p className="text-sm text-muted">Loading status…</p>}>
            <StatusContent />
          </Suspense>
        </div>
      </main>
    </>
  );
}
