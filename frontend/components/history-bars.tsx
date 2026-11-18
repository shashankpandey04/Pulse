import type { UptimeBucket } from "@/lib/schemas";

function shortStart(iso: string, granularity: "hour" | "day"): string {
  const date = new Date(iso);
  return granularity === "hour"
    ? date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

/** One uptime bar strip; every bucket is a square colored by the backend. */
export function HistoryBars({ buckets, granularity }: { buckets: UptimeBucket[]; granularity: "hour" | "day" }) {
  return (
    <div className="flex h-6 w-full items-stretch gap-px" role="img" aria-label="uptime history bars">
      {buckets.map((bucket) => {
        const when = shortStart(bucket.start, granularity);
        const rate = ((bucket.success_rate ?? 0) * 100).toFixed(1);
        const detail =
          bucket.total_checks === 0
            ? "no checks"
            : `${rate}% ok · ${bucket.total_checks} check${bucket.total_checks === 1 ? "" : "s"}${
                bucket.avg_latency_ms !== null ? ` · avg ${Math.round(bucket.avg_latency_ms)} ms` : ""
              }`;
        return (
          <div
            key={bucket.start}
            className="min-w-[2px] flex-1 border-r border-white/60 last:border-r-0"
            style={{ backgroundColor: bucket.color }}
            title={`${when} — ${detail}`}
          />
        );
      })}
    </div>
  );
}

/** Small legend explaining the bar colors (no-data gray included). */
export function HistoryLegend({ colors, noDataColor = "#D4D4D4" }: { colors: Record<string, string>; noDataColor?: string }) {
  const entries: Array<[string, string]> = [
    ["healthy", colors["healthy"] ?? "#22C55E"],
    ["down", colors["down"] ?? "#EF4444"],
    ["slow", colors["slow"] ?? "#EAB308"],
    ["flaky", colors["flaky"] ?? "#800000"],
    ["no data", noDataColor],
  ];
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs uppercase tracking-wide text-muted">
      {entries.map(([label, color]) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-3 w-3 border border-black" style={{ backgroundColor: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}
