"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/client";
import {
  ServiceCreateInputSchema,
  ServiceListResponseSchema,
  type ServiceResponse,
} from "@/lib/schemas";
import { Field, Notice, PrimaryButton, SecondaryButton, inputClass } from "@/components/ui";

const EMPTY_FORM = {
  name: "",
  slug: "",
  description: "",
  health_url: "",
  check_interval_seconds: "60",
  timeout_seconds: "10",
  owner_email: "",
  reliability_target: "99.9",
  enabled: true,
};

export function ServicesPanel({ canManage }: { canManage: boolean }) {
  const [services, setServices] = useState<ServiceResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<unknown>("/api/catalogue?page_size=100");
      setServices(ServiceListResponseSchema.parse(data).services);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load services.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createService(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsed = ServiceCreateInputSchema.safeParse({
      name: form.name,
      slug: form.slug.trim() ? form.slug : undefined,
      description: form.description.trim() ? form.description : undefined,
      health_url: form.health_url,
      check_interval_seconds: Number(form.check_interval_seconds),
      timeout_seconds: Number(form.timeout_seconds),
      owner_email: form.owner_email,
      reliability_target: Number(form.reliability_target),
      enabled: form.enabled,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }
    try {
      await apiFetch("/api/catalogue", { method: "POST", body: JSON.stringify(parsed.data) });
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed.");
    }
  }

  async function act(serviceId: string, path: string, init: RequestInit) {
    setBusyId(serviceId);
    try {
      await apiFetch(path, init);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="border border-edge bg-white">
      <header className="flex items-center justify-between border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">Service catalogue</h2>
        {canManage && (
          <SecondaryButton type="button" onClick={() => setShowForm(!showForm)}>
            {showForm ? "Close form" : "Register service"}
          </SecondaryButton>
        )}
      </header>

      <div className="flex flex-col gap-4 p-4">
        {error && <Notice kind="error">{error}</Notice>}

        {canManage && showForm && (
          <form onSubmit={createService} className="flex flex-col gap-3 border border-edge p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Name">
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required className={inputClass} />
              </Field>
              <Field label="Slug (optional, derived from name)">
                <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} className={inputClass} />
              </Field>
              <Field label="Health URL">
                <input value={form.health_url} onChange={(e) => setForm({ ...form, health_url: e.target.value })} required className={inputClass} placeholder="https://api.example.com/health" />
              </Field>
              <Field label="Owner email (registered account)">
                <input value={form.owner_email} onChange={(e) => setForm({ ...form, owner_email: e.target.value })} required className={inputClass} />
              </Field>
              <Field label="Check interval (seconds, ≥5)">
                <input type="number" min={5} max={86400} value={form.check_interval_seconds} onChange={(e) => setForm({ ...form, check_interval_seconds: e.target.value })} required className={inputClass} />
              </Field>
              <Field label="Timeout (seconds, < interval)">
                <input type="number" min={1} max={60} value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: e.target.value })} required className={inputClass} />
              </Field>
              <Field label="Reliability target (% )">
                <input type="number" min={0.01} max={100} step={0.01} value={form.reliability_target} onChange={(e) => setForm({ ...form, reliability_target: e.target.value })} required className={inputClass} />
              </Field>
              <Field label="Description (optional)">
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={inputClass} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              Enable monitoring immediately
            </label>
            <div>
              <PrimaryButton type="submit">Create service</PrimaryButton>
            </div>
          </form>
        )}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
              <th className="py-2 pr-4">Service</th>
              <th className="py-2 pr-4">Health URL</th>
              <th className="py-2 pr-4">Interval</th>
              <th className="py-2 pr-4">Target</th>
              <th className="py-2 pr-4">Enabled</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {!services && !error && (
              <tr>
                <td colSpan={6} className="py-3 text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {services && services.length === 0 && (
              <tr>
                <td colSpan={6} className="py-3 text-muted">
                  No services registered yet.
                </td>
              </tr>
            )}
            {services?.map((service) => (
              <tr key={service.service_id} className="border-b border-edge last:border-b-0">
                <td className="py-2 pr-4 font-medium">
                  {service.name}
                  <div className="font-mono text-xs text-muted">/{service.slug}</div>
                </td>
                <td className="py-2 pr-4 font-mono text-xs">{service.health_url}</td>
                <td className="py-2 pr-4 font-mono text-xs">{service.check_interval_seconds}s</td>
                <td className="py-2 pr-4 font-mono text-xs">{service.reliability_target}%</td>
                <td className="py-2 pr-4 font-mono text-xs">{service.enabled ? "yes" : "no"}</td>
                <td className="py-2">
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={`/dashboard/services/${service.service_id}`}
                      className="inline-flex h-9 items-center border border-black bg-white px-3 text-sm font-medium hover:bg-neutral-100"
                    >
                      Configure states
                    </Link>
                    {canManage && (
                      <>
                        <SecondaryButton
                          type="button"
                          disabled={busyId === service.service_id}
                          onClick={() =>
                            act(service.service_id, `/api/catalogue/${service.service_id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ enabled: !service.enabled }),
                            })
                          }
                        >
                          {service.enabled ? "Pause" : "Resume"}
                        </SecondaryButton>
                        <PrimaryButton
                          type="button"
                          disabled={busyId === service.service_id}
                          onClick={() => {
                            if (confirm(`Delete ${service.name} from the catalogue?`)) {
                              void act(service.service_id, `/api/catalogue/${service.service_id}`, { method: "DELETE" });
                            }
                          }}
                        >
                          Delete
                        </PrimaryButton>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
