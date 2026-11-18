"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/client";
import {
  IncidentListResponseSchema,
  type IncidentResponse,
  type Role,
} from "@/lib/schemas";
import { Field, Notice, PrimaryButton, SecondaryButton, inputClass, labelClass } from "@/components/ui";

type StatusFilter = "all" | "open" | "acknowledged" | "resolved";

function formatWhen(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function IncidentsPanel({ role }: { role: Role }) {
  const [filter, setFilter] = useState<StatusFilter>("open");
  const [incidents, setIncidents] = useState<IncidentResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState<{ id: string; text: string; visibility: "public" | "internal" } | null>(null);
  const [openTimeline, setOpenTimeline] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const query = filter === "all" ? "" : `?status=${filter}`;
      const data = await apiFetch<unknown>(`/api/incidents${query}`);
      setIncidents(IncidentListResponseSchema.parse(data).incidents);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents.");
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(path: string, init: RequestInit, id: string) {
    setBusyId(id);
    try {
      await apiFetch(path, init);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function submitNote() {
    if (!noteDraft) return;
    await act(
      `/api/incidents/${noteDraft.id}/notes`,
      {
        method: "POST",
        body: JSON.stringify({ note: noteDraft.text, visibility: noteDraft.visibility }),
      },
      noteDraft.id,
    );
    setNoteDraft(null);
  }

  return (
    <section className="border border-edge bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">Incidents</h2>
        <div>
          <span className={labelClass}>Status</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value as StatusFilter)} className={`${inputClass} w-40`}>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
            <option value="all">All</option>
          </select>
        </div>
      </header>
      <div className="flex flex-col gap-4 p-4">
        {error && <Notice kind="error">{error}</Notice>}
        {!incidents && !error && <p className="text-sm text-muted">Loading…</p>}
        {incidents && incidents.length === 0 && <p className="text-sm text-muted">No incidents for this filter.</p>}

        {incidents?.map((incident) => (
          <article key={incident.incident_id} className="border border-edge p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-medium">{incident.title}</h3>
              <span className="font-mono text-xs uppercase text-muted">
                {incident.status} · {incident.current_state}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted">{incident.opened_reason}</p>
            <p className="mt-1 font-mono text-xs text-muted">
              Opened {formatWhen(incident.opened_at)}
              {incident.acknowledged_at ? ` · Acked ${formatWhen(incident.acknowledged_at)}` : ""}
              {incident.resolved_at ? ` · Resolved ${formatWhen(incident.resolved_at)}` : ""}
              {incident.duration_seconds !== null ? ` · ${Math.round(incident.duration_seconds / 60)} min` : ""}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <SecondaryButton type="button" onClick={() => setOpenTimeline(openTimeline === incident.incident_id ? null : incident.incident_id)}>
                {openTimeline === incident.incident_id ? "Hide timeline" : "Timeline"}
              </SecondaryButton>
              {role !== "subscriber" && incident.status === "open" && (
                <PrimaryButton
                  type="button"
                  disabled={busyId === incident.incident_id}
                  onClick={() =>
                    act(`/api/incidents/${incident.incident_id}/ack`, { method: "PATCH", body: JSON.stringify({}) }, incident.incident_id)
                  }
                >
                  Acknowledge
                </PrimaryButton>
              )}
              {role !== "subscriber" && incident.status !== "resolved" && (
                <SecondaryButton
                  type="button"
                  disabled={busyId === incident.incident_id}
                  onClick={() =>
                    act(`/api/incidents/${incident.incident_id}/resolve`, { method: "POST", body: JSON.stringify({}) }, incident.incident_id)
                  }
                >
                  Resolve
                </SecondaryButton>
              )}
              {role !== "subscriber" && incident.status !== "resolved" && (
                <SecondaryButton
                  type="button"
                  onClick={() =>
                    setNoteDraft({ id: incident.incident_id, text: "", visibility: "public" })
                  }
                >
                  Add note
                </SecondaryButton>
              )}
            </div>

            {openTimeline === incident.incident_id && (
              <ol className="mt-3 flex flex-col gap-1 border-l border-edge pl-4 text-sm">
                {incident.timeline.map((event) => (
                  <li key={event.event_id}>
                    <span className="font-mono text-xs text-muted">{formatWhen(event.at)}</span> — {event.message}
                    {event.by_email && <span className="font-mono text-xs text-muted"> · {event.by_email}</span>}
                    {event.visibility === "internal" && <span className="font-mono text-xs uppercase text-muted"> · internal</span>}
                  </li>
                ))}
              </ol>
            )}

            {noteDraft?.id === incident.incident_id && (
              <div className="mt-3 flex flex-col gap-3 border border-edge p-3">
                <Field label="Note">
                  <textarea
                    className={`${inputClass} h-20 py-1`}
                    value={noteDraft.text}
                    onChange={(e) => setNoteDraft({ ...noteDraft, text: e.target.value })}
                  />
                </Field>
                <Field label="Visibility">
                  <select
                    className={inputClass}
                    value={noteDraft.visibility}
                    onChange={(e) => setNoteDraft({ ...noteDraft, visibility: e.target.value as "public" | "internal" })}
                  >
                    <option value="public">Public (visible on status page)</option>
                    <option value="internal">Internal (staff only)</option>
                  </select>
                </Field>
                <div className="flex gap-2">
                  <PrimaryButton type="button" disabled={busyId === incident.incident_id || noteDraft.text.trim().length === 0} onClick={submitNote}>
                    Save note
                  </PrimaryButton>
                  <SecondaryButton type="button" onClick={() => setNoteDraft(null)}>
                    Cancel
                  </SecondaryButton>
                </div>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
