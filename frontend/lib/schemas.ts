import { z } from "zod";

/* -----------------------------------------------------------------------------
 * Shared primitives
 * --------------------------------------------------------------------------- */

export const RoleSchema = z.enum(["admin", "operator", "subscriber"]);
export type Role = z.infer<typeof RoleSchema>;

export const HealthStateSchema = z.enum(["healthy", "down", "slow", "flaky"]);
export type HealthState = z.infer<typeof HealthStateSchema>;

const isoDatetime = z.iso.datetime({ offset: true });
const id = z.string().min(1);

/* -----------------------------------------------------------------------------
 * Auth / users
 * --------------------------------------------------------------------------- */

export const RegisterInputSchema = z.object({
  email: z.email(),
  password: z.string().min(8).max(72),
  pfp_link: z.url().nullable().optional(),
});
export type RegisterInput = z.infer<typeof RegisterInputSchema>;

export const LoginInputSchema = z.object({
  email: z.email(),
  password: z.string().min(1),
});
export type LoginInput = z.infer<typeof LoginInputSchema>;

export const UserResponseSchema = z.object({
  uid: id,
  email: z.email(),
  pfp_link: z.url().nullable(),
  role: RoleSchema,
  active: z.boolean(),
  created_at: isoDatetime,
  updated_at: isoDatetime,
});
export type UserResponse = z.infer<typeof UserResponseSchema>;

export const UserListResponseSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  users: z.array(UserResponseSchema),
});

/** Backend AuthResponse: token + user. The token never reaches the browser. */
export const AuthEnvelopeSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string(),
  user: UserResponseSchema,
});

export const AdminUserUpdateInputSchema = z
  .object({
    role: RoleSchema.optional(),
    active: z.boolean().optional(),
  })
  .refine((v) => v.role !== undefined || v.active !== undefined, {
    message: "Provide a role or an active flag.",
  });
export type AdminUserUpdateInput = z.infer<typeof AdminUserUpdateInputSchema>;

/* -----------------------------------------------------------------------------
 * Service catalogue
 * --------------------------------------------------------------------------- */

export const ServiceMonitoringSchema = z.object({
  current_state: HealthStateSchema,
  consecutive_failures: z.number().int(),
  consecutive_successes: z.number().int(),
  last_check_at: isoDatetime.nullable(),
  last_latency_ms: z.number().int().nullable(),
  last_error: z.string().nullable(),
  next_check_at: isoDatetime.nullable(),
});

export const ServiceResponseSchema = z.object({
  service_id: id,
  name: z.string().min(1),
  slug: z.string().min(1),
  description: z.string().nullable(),
  health_url: z.url(),
  check_interval_seconds: z.number().int(),
  timeout_seconds: z.number().int(),
  owner_uid: id,
  owner_email: z.email(),
  reliability_target: z.number(),
  enabled: z.boolean(),
  created_at: isoDatetime,
  updated_at: isoDatetime,
});
export type ServiceResponse = z.infer<typeof ServiceResponseSchema>;

export const ServiceListResponseSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  services: z.array(ServiceResponseSchema),
});

export const ServiceCreateInputSchema = z.object({
  name: z.string().min(1).max(120),
  slug: z
    .string()
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
    .optional()
    .or(z.literal("").transform(() => undefined)),
  description: z.string().max(500).optional().nullable(),
  health_url: z.url(),
  check_interval_seconds: z.number().int().min(5).max(86400),
  timeout_seconds: z.number().int().min(1).max(60),
  owner_email: z.email(),
  reliability_target: z.number().gt(0),
  enabled: z.boolean().default(true),
});
export type ServiceCreateInput = z.infer<typeof ServiceCreateInputSchema>;

export const ServiceUpdateInputSchema = z.object({
  name: z.string().min(1).max(120).optional(),
  slug: z
    .string()
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
    .optional(),
  description: z.string().max(500).optional().nullable(),
  health_url: z.url().optional(),
  check_interval_seconds: z.number().int().min(5).max(86400).optional(),
  timeout_seconds: z.number().int().min(1).max(60).optional(),
  owner_email: z.email().optional(),
  reliability_target: z.number().gt(0).optional(),
  enabled: z.boolean().optional(),
});
export type ServiceUpdateInput = z.infer<typeof ServiceUpdateInputSchema>;

/* -----------------------------------------------------------------------------
 * Service states
 * --------------------------------------------------------------------------- */

export const DownPolicySchema = z.object({ consecutive_failures: z.number().int().min(1).max(1000) });
export const SlowPolicySchema = z.object({ latency_ms: z.number().int().min(1).max(600000) });
export const FlakyPolicySchema = z.object({
  failure_rate: z.number().min(0).max(1),
  window_size: z.number().int().min(2).max(1000),
});
export const RecoveryPolicySchema = z.object({ consecutive_successes: z.number().int().min(1).max(1000) });

export const StateConfigResponseSchema = z.object({
  state_id: id,
  service_id: id,
  down: DownPolicySchema,
  slow: SlowPolicySchema,
  flaky: FlakyPolicySchema,
  recovery: RecoveryPolicySchema,
  colors: z.record(z.string(), z.string()),
  created_at: isoDatetime,
  updated_at: isoDatetime,
});
export type StateConfigResponse = z.infer<typeof StateConfigResponseSchema>;

export const StateConfigListResponseSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  states: z.array(StateConfigResponseSchema),
});

export const StateConfigUpsertInputSchema = z.object({
  down: DownPolicySchema.optional(),
  slow: SlowPolicySchema.optional(),
  flaky: FlakyPolicySchema.optional(),
  recovery: RecoveryPolicySchema.optional(),
});
export type StateConfigUpsertInput = z.infer<typeof StateConfigUpsertInputSchema>;

/* -----------------------------------------------------------------------------
 * Incidents
 * --------------------------------------------------------------------------- */

export const TimelineEventSchema = z.object({
  event_id: id,
  type: z.enum(["opened", "state_changed", "acknowledged", "note", "resolved"]),
  message: z.string(),
  at: isoDatetime,
  by_uid: id.nullable(),
  by_email: z.string().nullable(),
  visibility: z.enum(["public", "internal"]),
});
export type TimelineEvent = z.infer<typeof TimelineEventSchema>;

export const IncidentResponseSchema = z.object({
  incident_id: id,
  service_id: id,
  service_name: z.string(),
  title: z.string(),
  status: z.enum(["open", "acknowledged", "resolved"]),
  current_state: HealthStateSchema,
  opened_at: isoDatetime,
  opened_reason: z.string(),
  acknowledged_by_uid: id.nullable(),
  acknowledged_by_email: z.string().nullable(),
  acknowledged_at: isoDatetime.nullable(),
  resolved_at: isoDatetime.nullable(),
  resolved_reason: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  timeline: z.array(TimelineEventSchema),
  created_at: isoDatetime,
  updated_at: isoDatetime,
});
export type IncidentResponse = z.infer<typeof IncidentResponseSchema>;

export const IncidentListResponseSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  incidents: z.array(IncidentResponseSchema),
});

export const AckInputSchema = z.object({ note: z.string().max(500).optional() });
export const NoteInputSchema = z.object({
  note: z.string().min(1).max(2000),
  visibility: z.enum(["public", "internal"]).default("public"),
});
export const ResolveInputSchema = z.object({ note: z.string().max(2000).optional() });

/* -----------------------------------------------------------------------------
 * Metrics & reliability
 * --------------------------------------------------------------------------- */

export const CheckResultSchema = z.object({
  check_id: id,
  service_id: id,
  checked_at: isoDatetime,
  success: z.boolean(),
  state: HealthStateSchema,
  status_code: z.number().int().nullable(),
  latency_ms: z.number().int().nullable(),
  error: z.string().nullable(),
  timed_out: z.boolean(),
});

export const CheckResultListResponseSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  checks: z.array(CheckResultSchema),
});

export const ServiceMetricsSchema = z.object({
  service_id: id,
  service_name: z.string(),
  window_hours: z.number().int(),
  total_checks: z.number().int(),
  failed_checks: z.number().int(),
  success_rate: z.number(),
  avg_latency_ms: z.number().nullable(),
  p95_latency_ms: z.number().nullable(),
  mttd_seconds: z.number().nullable(),
  mttr_seconds: z.number().nullable(),
  open_incidents: z.number().int(),
  last_check_at: isoDatetime.nullable(),
  last_state: HealthStateSchema.nullable(),
});
export type ServiceMetrics = z.infer<typeof ServiceMetricsSchema>;

export const MetricsOverviewSchema = z.object({
  window_hours: z.number().int(),
  services: z.array(ServiceMetricsSchema),
});
export type MetricsOverview = z.infer<typeof MetricsOverviewSchema>;

export const ReliabilitySchema = z.object({
  service_id: id,
  service_name: z.string(),
  window_days: z.number().int(),
  target_pct: z.number(),
  availability_pct: z.number(),
  meeting_target: z.boolean(),
  error_budget_pct: z.number(),
  error_budget_remaining_pct: z.number(),
  allowed_downtime_minutes: z.number(),
  consumed_downtime_minutes: z.number(),
  total_checks: z.number().int(),
  failed_checks: z.number().int(),
  incident_count: z.number().int(),
  last_state: HealthStateSchema.nullable(),
  computed_at: isoDatetime,
});
export type Reliability = z.infer<typeof ReliabilitySchema>;

export const ReliabilityListSchema = z.object({
  window_days: z.number().int(),
  services: z.array(ReliabilitySchema),
});
export type ReliabilityList = z.infer<typeof ReliabilityListSchema>;

/* -----------------------------------------------------------------------------
 * Notifications
 * --------------------------------------------------------------------------- */

export const NotificationSchema = z.object({
  notification_id: id,
  event_type: z.enum(["incident_opened", "incident_resolved", "incident_acknowledged", "note_added"]),
  service_id: id,
  service_name: z.string(),
  incident_id: id.nullable(),
  message: z.string(),
  payload: z.record(z.string(), z.unknown()),
  delivered: z.boolean(),
  attempts: z.number().int(),
  last_error: z.string().nullable(),
  delivered_at: isoDatetime.nullable(),
  created_at: isoDatetime,
});

export const NotificationListSchema = z.object({
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  notifications: z.array(NotificationSchema),
});
export type NotificationList = z.infer<typeof NotificationListSchema>;

/* -----------------------------------------------------------------------------
 * Public status page
 * --------------------------------------------------------------------------- */

export const PublicStatusEventSchema = z.object({
  type: z.string(),
  message: z.string(),
  at: isoDatetime,
});

/** One uptime bar: check outcomes over a time bucket (backend-computed colors). */
export const UptimeBucketSchema = z.object({
  start: isoDatetime,
  total_checks: z.number().int(),
  failed_checks: z.number().int(),
  success_rate: z.number().nullable(),
  avg_latency_ms: z.number().nullable(),
  color: z.string(),
});
export type UptimeBucket = z.infer<typeof UptimeBucketSchema>;

export const PublicIncidentSchema = z.object({
  incident_id: id,
  title: z.string(),
  status: z.string(),
  current_state: z.string(),
  opened_at: isoDatetime,
  resolved_at: isoDatetime.nullable(),
  duration_seconds: z.number().nullable(),
  events: z.array(PublicStatusEventSchema),
});

export const PublicServiceStatusSchema = z.object({
  service_id: id,
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable(),
  state: z.string(),
  color: z.string(),
  last_check_at: isoDatetime.nullable(),
  last_latency_ms: z.number().int().nullable(),
  history: z.array(UptimeBucketSchema).default([]), // hourly bars, last 24 hours
});

export const PublicStatusSchema = z.object({
  generated_at: isoDatetime,
  summary: z.record(z.string(), z.number()),
  colors: z.record(z.string(), z.string()),
  services: z.array(PublicServiceStatusSchema),
  active_incidents: z.array(PublicIncidentSchema),
});
export type PublicStatus = z.infer<typeof PublicStatusSchema>;

export const PublicServiceDetailSchema = z.object({
  service: PublicServiceStatusSchema,
  incidents: z.array(PublicIncidentSchema),
  daily_history: z.array(UptimeBucketSchema).default([]), // daily bars, last 30 days
});
export type PublicServiceDetail = z.infer<typeof PublicServiceDetailSchema>;

/* -----------------------------------------------------------------------------
 * Push devices (Firebase Cloud Messaging tokens)
 * --------------------------------------------------------------------------- */

export const DeviceTokenCreateInputSchema = z.object({
  fcm_token: z.string().min(16).max(4096),
  device_label: z.string().max(100).optional(),
});
export type DeviceTokenCreateInput = z.infer<typeof DeviceTokenCreateInputSchema>;

export const DeviceTokenSchema = z.object({
  token_id: id,
  token_preview: z.string(),
  device_label: z.string().nullable(),
  user_agent: z.string().nullable(),
  created_at: isoDatetime,
  updated_at: isoDatetime,
  last_sent_at: isoDatetime.nullable(),
  send_count: z.number().int(),
  fail_count: z.number().int(),
  last_error: z.string().nullable(),
});
export type DeviceToken = z.infer<typeof DeviceTokenSchema>;

export const DeviceTokenListSchema = z.object({
  total: z.number().int(),
  tokens: z.array(DeviceTokenSchema),
});
export type DeviceTokenList = z.infer<typeof DeviceTokenListSchema>;

/* -----------------------------------------------------------------------------
 * Dashboard
 * --------------------------------------------------------------------------- */

export const DashboardSchema = z.object({
  role: RoleSchema,
  generated_at: isoDatetime,
  status: PublicStatusSchema.nullable(),
  services: z.array(ServiceResponseSchema).nullable(),
  incidents_summary: z
    .object({ open: z.number().int(), acknowledged: z.number().int(), resolved_24h: z.number().int() })
    .nullable(),
  metrics: MetricsOverviewSchema.nullable(),
  reliability: ReliabilityListSchema.nullable(),
  users_summary: z
    .object({
      total: z.number().int(),
      by_role: z.record(z.string(), z.number()),
      active: z.number().int(),
      deactivated: z.number().int(),
    })
    .nullable(),
  notifications_summary: z
    .object({ total: z.number().int(), delivered: z.number().int(), failed: z.number().int() })
    .nullable(),
  devices: z
    .object({
      total: z.number().int(),
      notifications_required: z.boolean(),
      fcm_enabled: z.boolean(),
    })
    .nullable(),
});
export type Dashboard = z.infer<typeof DashboardSchema>;

/* -----------------------------------------------------------------------------
 * Shared constants (mirror backend STATE_COLORS — part of the product spec)
 * --------------------------------------------------------------------------- */

export const STATE_COLORS: Record<HealthState, string> = {
  healthy: "#22C55E", // green
  down: "#EF4444", // red
  slow: "#EAB308", // yellow
  flaky: "#800000", // maroon
};

/* -----------------------------------------------------------------------------
 * Generic backend envelope
 * --------------------------------------------------------------------------- */

export const MessageSchema = z.object({ message: z.string() });
