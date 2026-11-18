import { SiteHeader } from "@/components/site-header";
import { LinkButton } from "@/components/ui";

/**
 * Shown when a signed-in user without the required role opens a staff console.
 * Rendered instead of a redirect so the page stays correct even without
 * JavaScript (Cache Components streams redirect() instructions only to the
 * client router).
 */
export function AccessPanel({ title, message }: { title: string; message: string }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-4 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted">{message}</p>
        <div className="mt-6">
          <LinkButton href="/dashboard">Back to your dashboard</LinkButton>
        </div>
      </main>
    </>
  );
}
