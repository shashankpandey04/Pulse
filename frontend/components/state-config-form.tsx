"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/client";
import { StateConfigResponseSchema } from "@/lib/schemas";
import { Field, Notice, PrimaryButton, SecondaryButton, inputClass } from "@/components/ui";

type Config = {
  down: { consecutive_failures: number };
  slow: { latency_ms: number };
  flaky: { failure_rate: number; window_size: number };
  recovery: { consecutive_successes: number };
  colors: Record<string, string>;
};

export function StateConfigForm({ serviceId, serviceSlug, isAdmin }: { serviceId: string; serviceSlug: string; isAdmin: boolean }) {
  const router = useRouter();
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<unknown>(`/api/states/${serviceId}`);
      const parsed = StateConfigResponseSchema.parse(data);
      setConfig({
        down: parsed.down,
        slow: parsed.slow,
        flaky: parsed.flaky,
        recovery: parsed.recovery,
        colors: parsed.colors,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load configuration.");
    }
  }, [serviceId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <Notice kind="error">{error}</Notice>;
  }
  if (!config) {
    return <p className="text-sm text-muted">Loading configuration…</p>;
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) return;
    const form = new FormData(event.currentTarget);
    const payload = {
      down: { consecutive_failures: Number(form.get("down_failures")) },
      slow: { latency_ms: Number(form.get("slow_latency")) },
      flaky: {
        failure_rate: Number(form.get("flaky_rate")),
        window_size: Number(form.get("flaky_window")),
      },
      recovery: { consecutive_successes: Number(form.get("recovery_successes")) },
    };
    setBusy(true);
    setSaved(false);
    try {
      await apiFetch(`/api/states/${serviceId}`, { method: "PUT", body: JSON.stringify(payload) });
      setSaved(true);
      await load();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  async function resetToDefaults() {
    if (!confirm("Remove the stored configuration and restore defaults?")) return;
    setBusy(true);
    setSaved(false);
    try {
      await apiFetch(`/api/states/${serviceId}`, { method: "DELETE" });
      await load();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      {error && <Notice kind="error">{error}</Notice>}
      {saved && <Notice kind="success">Configuration saved.</Notice>}

      <div className="grid gap-4 md:grid-cols-2">
        <fieldset className="border border-edge p-4">
          <legend className="px-1 font-mono text-xs uppercase tracking-wide">Down — {config.colors.down ?? ""}</legend>
          <Field label="Consecutive failed checks before Down">
            <input
              name="down_failures"
              type="number"
              min={1}
              max={1000}
              defaultValue={config.down.consecutive_failures}
              required
              className={inputClass}
            />
          </Field>
        </fieldset>

        <fieldset className="border border-edge p-4">
          <legend className="px-1 font-mono text-xs uppercase tracking-wide">Slow — {config.colors.slow ?? ""}</legend>
          <Field label="Latency threshold (ms)">
            <input name="slow_latency" type="number" min={1} max={600000} defaultValue={config.slow.latency_ms} required className={inputClass} />
          </Field>
        </fieldset>

        <fieldset className="border border-edge p-4">
          <legend className="px-1 font-mono text-xs uppercase tracking-wide">Flaky — {config.colors.flaky ?? ""}</legend>
          <div className="grid gap-3">
            <Field label="Failure rate threshold (0.3 = 30%)">
              <input name="flaky_rate" type="number" min={0} max={1} step={0.01} defaultValue={config.flaky.failure_rate} required className={inputClass} />
            </Field>
            <Field label="Window size (checks)">
              <input name="flaky_window" type="number" min={2} max={1000} defaultValue={config.flaky.window_size} required className={inputClass} />
            </Field>
          </div>
        </fieldset>

        <fieldset className="border border-edge p-4">
          <legend className="px-1 font-mono text-xs uppercase tracking-wide">Recovery — {config.colors.healthy ?? ""}</legend>
          <Field label="Consecutive successful checks before Healthy">
            <input
              name="recovery_successes"
              type="number"
              min={1}
              max={1000}
              defaultValue={config.recovery.consecutive_successes}
              required
              className={inputClass}
            />
          </Field>
        </fieldset>
      </div>

      <div className="flex flex-wrap gap-2">
        <PrimaryButton type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save configuration"}
        </PrimaryButton>
        {isAdmin && (
          <SecondaryButton type="button" onClick={resetToDefaults} disabled={busy}>
            Reset to defaults
          </SecondaryButton>
        )}
        <a
          href={`/status/${serviceSlug}`}
          className="inline-flex h-9 items-center border border-black bg-white px-3 text-sm font-medium hover:bg-neutral-100"
        >
          View status page
        </a>
      </div>
    </form>
  );
}
