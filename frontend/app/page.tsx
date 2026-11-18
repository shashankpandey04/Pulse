import { Suspense } from "react";
import Link from "next/link";
import { SiteHeader, HeaderFallback } from "@/components/site-header";
import { LinkButton } from "@/components/ui";

export default function Home() {
  return (
    <>
      <Suspense fallback={<HeaderFallback />}>
        <SiteHeader />
      </Suspense>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-16">
        <h1 className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight">
          Pulse watches your services, opens incidents when they misbehave, and closes them when they recover.
        </h1>
        <p className="mt-4 max-w-xl text-base text-muted">
          A status and incident hub: continuous health checks, a public status page for your customers, and
          reliability reporting against each service&apos;s target.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <LinkButton href="/status">View status page</LinkButton>
          <LinkButton href="/auth/login">Sign in</LinkButton>
          <LinkButton href="/auth/register">Create account</LinkButton>
        </div>

        <div className="mt-16 grid gap-4 border border-edge md:grid-cols-3">
          <section className="border-edge p-6 md:border-r">
            <h2 className="font-mono text-xs uppercase tracking-widest">Monitor</h2>
            <p className="mt-2 text-sm text-muted">
              Every service gets its own check schedule, state thresholds and health URL. Checks run on independent
              timers so one slow service never blocks another.
            </p>
          </section>
          <section className="border-edge p-6 md:border-r">
            <h2 className="font-mono text-xs uppercase tracking-widest">Incidents</h2>
            <p className="mt-2 text-sm text-muted">
              Incidents open automatically after repeated failures and resolve on recovery. Staff acknowledge them
              and keep a public timeline of notes.
            </p>
          </section>
          <section className="p-6">
            <h2 className="font-mono text-xs uppercase tracking-widest">Reliability</h2>
            <p className="mt-2 text-sm text-muted">
              Availability over time is compared against each service&apos;s target, with the error budget that
              remains before the target is missed.
            </p>
          </section>
        </div>

        <p className="mt-10 text-sm text-muted">
          New here? <Link href="/auth/register" className="underline">Create an account</Link> — accounts start as
          subscribers and can view the public status page.
        </p>
      </main>
      <footer className="border-t border-edge">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 font-mono text-xs uppercase tracking-widest text-muted">
          Pulse · status &amp; incident hub
        </div>
      </footer>
    </>
  );
}
