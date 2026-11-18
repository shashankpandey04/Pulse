import { SiteHeader } from "@/components/site-header";
import { AccessPanel } from "@/components/access-panel";
import { Panel } from "@/components/ui";
import { StateConfigForm } from "@/components/state-config-form";
import { pageApi, PageApiError } from "@/lib/server-api";
import { ServiceResponseSchema, UserResponseSchema } from "@/lib/schemas";

// Auth-gated staff page: blocks on the session check by design.
export const instant = false;

export default async function ServiceConfigPage({ params }: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await params;

  // Guard: staff only (operator/admin); admins additionally may reset to defaults.
  let role: "admin" | "operator" | null = null;
  try {
    const user = await pageApi("/auth/me", UserResponseSchema);
    role = user.role === "admin" ? "admin" : user.role === "operator" ? "operator" : null;
  } catch (error) {
    if (error instanceof PageApiError && (error.status === 401 || error.status === 400)) role = null;
    else throw error;
  }
  if (!role) {
    // Signed in without a staff role (anonymous visitors are already turned
    // away by proxy.ts before the page renders).
    return (
      <AccessPanel
        title="Staff access required"
        message="Only operator and admin accounts can open the state thresholds for a service."
      />
    );
  }

  const service = await pageApi(`/catalogue/${encodeURIComponent(serviceId)}`, ServiceResponseSchema);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">State thresholds — {service.name}</h1>
          <p className="mt-1 text-sm text-muted">
            Operators decide when this service counts as down, slow or flaky, and when it has recovered. The health
            check job applies these thresholds on every check.
          </p>
          <p className="mt-3 font-mono text-xs text-muted">
            {service.health_url} · every {service.check_interval_seconds}s · timeout {service.timeout_seconds}s ·
            target {service.reliability_target}%
          </p>
        </header>

        <Panel title="Thresholds">
          <StateConfigForm serviceId={service.service_id} serviceSlug={service.slug} isAdmin={role === "admin"} />
        </Panel>
      </main>
    </>
  );
}
