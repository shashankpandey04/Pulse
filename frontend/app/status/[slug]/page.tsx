import { Suspense } from "react";
import { notFound } from "next/navigation";
import { SiteHeader, HeaderFallback } from "@/components/site-header";
import { StateLabel, Panel } from "@/components/ui";
import { pageApi, PageApiError } from "@/lib/server-api";
import { PublicServiceDetailSchema } from "@/lib/schemas";

function formatWhen(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

async function ServiceContent({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params; // awaited inside Suspense so the shell can prerender
  let detail;
  try {
    detail = await pageApi(`/public/status/${encodeURIComponent(slug)}`, PublicServiceDetailSchema);
  } catch (error) {
    if (error instanceof PageApiError && error.status === 404) notFound();
    throw error;
  }
  const { service, incidents } = detail;

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Current state">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
          <StateLabel state={service.state} color={service.color} />
          <span className="font-mono text-xs text-muted">
            Last checked: {formatWhen(service.last_check_at)}
          </span>
          <span className="font-mono text-xs text-muted">
            Latency: {service.last_latency_ms === null ? "—" : `${service.last_latency_ms} ms`}
          </span>
        </div>
        {service.description && <p className="mt-3 text-sm text-muted">{service.description}</p>}
      </Panel>

      <Panel title="Incident history">
        {incidents.length === 0 ? (
          <p className="text-sm text-muted">No incidents recorded for this service.</p>
        ) : (
          <ul className="flex flex-col gap-4">
            {incidents.map((incident) => (
              <li key={incident.incident_id} className="border border-edge p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-medium">{incident.title}</h3>
                  <span className="font-mono text-xs uppercase text-muted">{incident.status}</span>
                </div>
                <p className="mt-1 font-mono text-xs text-muted">
                  {formatWhen(incident.opened_at)}
                  {incident.resolved_at ? ` → ${formatWhen(incident.resolved_at)}` : " → ongoing"}
                  {incident.duration_seconds !== null
                    ? ` · ${Math.round(incident.duration_seconds / 60)} min`
                    : ""}
                </p>
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

export default function ServiceStatusPage({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <>
      <Suspense fallback={<HeaderFallback />}>
        <SiteHeader />
      </Suspense>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <div className="mt-6">
          <Suspense fallback={<p className="text-sm text-muted">Loading service…</p>}>
            <ServiceContent params={params} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
