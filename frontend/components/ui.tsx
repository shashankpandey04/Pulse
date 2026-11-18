/** Tiny shared UI pieces: square, bordered, black & white only. */

import Link from "next/link";

export function StateLabel({ state, color }: { state: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-wide">
      <span aria-hidden className="inline-block h-3 w-3 border border-black" style={{ backgroundColor: color }} />
      {state}
    </span>
  );
}

export function Panel({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border border-edge bg-white">
      <header className="flex items-center justify-between border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">{title}</h2>
        {actions}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border border-edge px-4 py-3">
      <div className="font-mono text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

const buttonBase =
  "inline-flex h-9 items-center justify-center border border-black px-3 text-sm font-medium transition-colors";

export function PrimaryButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: React.ReactNode }) {
  return (
    <button {...props} className={`${buttonBase} bg-black text-white hover:bg-neutral-800 disabled:opacity-50 ${props.className ?? ""}`}>
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: React.ReactNode }) {
  return (
    <button
      {...props}
      className={`${buttonBase} bg-white text-black hover:bg-neutral-100 disabled:opacity-50 ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex h-9 items-center justify-center border border-black bg-white px-3 text-sm font-medium text-black hover:bg-neutral-100"
    >
      {children}
    </Link>
  );
}

export const inputClass =
  "h-9 w-full border border-edge bg-white px-2 text-sm text-black placeholder:text-neutral-400 focus:border-black";
export const labelClass = "mb-1 block font-mono text-xs uppercase tracking-wide text-muted";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      {children}
    </label>
  );
}

export function Notice({ kind, children }: { kind: "error" | "success"; children: React.ReactNode }) {
  return (
    <p className={`border px-3 py-2 text-sm ${kind === "error" ? "border-black bg-black text-white" : "border-black bg-white text-black"}`}>
      {children}
    </p>
  );
}
