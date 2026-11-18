# Pulse — Design Document

Companion to `README.md` (what the product is, how to run it) and `PROGRESS.md` (task log).
This document explains **how Pulse is built and why**: the architecture, the data model,
the state machine, the notification pipeline, and the frontend rendering strategy.

```
            ┌──────────────────────────── Next.js 16 (frontend) ──────────────────────────┐
 browser ──▶│  pages ──────▶ app/api/* route handlers (BFF, Zod)  ◀── httpOnly JWT cookie │
            └────────────────────────────────┬───────────────────────────────────────────┘
                                             │ http + bearer (server-side only)
            ┌────────────────────────────────▼──────────────────────────────────────────┐
            │                       FastAPI backend (uvicorn :8000)                     │
            │  auth · catalogue · states · devices · email-subscriptions · incidents    │
            │  metrics · reliability · notifications · public · dashboard · admin       │
            │        ▲ APScheduler CRON, every 10s:  health sweep  ·  mail dispatch     │
            │          (checks + state detection)    (mail_outbox → SMTP, retries)      │
            └───┬──────────────┬──────────────┬────────────────────────────────────────┘
                │              │              │
             MongoDB      webhook receiver   SMTP (Gmail App Password)
          (pulse database) (PULSE_WEBHOOK_URL)  + dormant FCM (service account)
```

## 1. Architectural decisions

### 1.1 Backend-for-Frontend (BFF)

The browser **never talks to the FastAPI backend directly**. Every page request goes to
self-hosted Next.js route handlers (`app/api/**`), which:

1. read the session from the httpOnly cookie (the JWT never reaches browser JS),
2. forward the request to FastAPI with the bearer token attached server-side,
3. validate the backend's response payload with **Zod** before returning it,
4. validate write payloads in the other direction too (`lib/schemas.ts` holds
   `*InputSchema` forms used by client components).

Why: origin isolation (cookies for :3000 can't be replayed against :8000), one place to
shape/limit what the UI sees, and the option to change backend URLs/stacks without
touching browser code. `lib/client.ts` enforces this by only accepting relative `/api`
paths.

### 1.2 Scheduler: one sweep, per-service schedules

A single `AsyncIOScheduler` job runs every `SWEEP_INTERVAL_SECONDS` (10s) and claims
every service whose `monitoring.next_check_at` is due (atomic claim, `max_instances=1`,
`coalesce=True`). Each claimed check runs as an **independent asyncio task** with its own
timeout, so:

- every service gets its own cadence (`check_interval_seconds`), not a global one;
- one slow/hanging service never delays the others;
- catalogue changes (create/edit/pause/delete) are picked up by the next sweep — no
  restart, no per-service APScheduler jobs to keep in sync.

### 1.3 Pure state evaluation

`core/health_check.evaluate_state()` is a pure function of
`(previous state, success, latency, consecutive failures/successes, window failure rate,
config)` — no I/O. Side effects (writing the check result, incidents, notifications) live
in the caller. This keeps the tricky part testable and makes the state machine inspectable
in one screen of code.

### 1.4 Durable outbox for mail (never fire mail inside the check)

The health-check path only **enqueues** a `mail_outbox` row (a single fast insert).
Delivery is a second CRON job (`mail-dispatch`, same 10s cadence) that drains due rows.
This is the standard outbox pattern, chosen because mail is slow, flaky, and may not even
be configured (SMTP credentials missing):

- an SMTP outage or restart never loses a notification;
- retries have a schedule (5 attempts, 60s × attempt backoff) instead of blocking checks;
- with no credentials, rows simply wait — mail starts flowing automatically the moment
  `PULSE_SMTP_USER`/`PULSE_SMTP_PASSWORD` are set (plus a startup flush on boot);
- every row is kept after terminal states (`sent` / `failed` / `skipped`) for inspection.

The webhook receiver and the dormant FCM fan-out use fire-and-forget tasks instead (they
are local/cheap and already record attempt stats), drained by the sweep and on shutdown so
they're never cut short.

### 1.5 MongoDB

Document-per-entity collections with explicit indexes created at startup
(`database.ensure_indexes`). Dates are stored as ISO strings in JSON mode and read with
`tz_aware=True` clients; uptime buckets exploit ISO-string prefixing (see §4.4).
No migrations are needed — index creation is idempotent and the schema evolves with the
Pydantic models.

## 2. Data model

Nine collections. `*_id` fields are system-generated (`schemas/common.new_uid`), and every
document carries `created_at` / `updated_at` (`TimestampedModel`).

| Collection            | Purpose & key fields | Indexes |
| --------------------- | -------------------- | ------- |
| `users`               | accounts: `uid`, unique `email`, bcrypt `hashed_password`, `role` (subscriber/operator/admin), `active` | unique `uid` |
| `services`            | catalogue: `service_id`, unique `name`, unique `slug`, `health_url`, `enabled`, `check_interval_seconds`, `owner_email`, `monitoring.next_check_at` | unique `service_id`, `name`, `slug` |
| `service_states`      | per-service threshold overrides (§3); absent = defaults | unique `service_id`, `state_id` |
| `incidents`           | lifecycle + `timeline[]` events (public/internal notes, state shifts, ack) | unique `incident_id`; **unique partial** `(service_id, status)` where status ∈ {open, acknowledged} — at most one active incident per service; `(status, opened_at)` for listing |
| `check_results`       | one row per check: `service_id`, `checked_at`, `success`, `latency_ms`, `error` | `(service_id, checked_at desc)` |
| `notifications`       | webhook delivery audit: event, payload message, `delivered`, `last_error` | `(created_at desc)` |
| `device_tokens`       | **dormant FCM**: `uid`, unique `fcm_token` (masked in API responses as `first6…last4`), device label/UA, send/fail stats | unique `fcm_token`; `(uid, created_at desc)` |
| `email_subscriptions` | the user-facing channel: one per account, `email` = **the account's own address** (never accepted from the request body), send/fail stats | unique `uid`, unique `email` |
| `mail_outbox`         | durable queue for state-change mails: service id/name/slug, `old_state`/`new_state`, `incident_id`, lifecycle `pending → sent | failed | skipped`, `attempts`, `next_attempt_at` | `(status, next_attempt_at)` for the dispatcher; `created_at` for FIFO |

Relationships are by id (`uid`, `service_id`, `incident_id`); there are no joins —
dashboards assemble role-shaped payloads in one place (`GET /dashboard`, §5.3).

## 3. Health states & the state machine

States: `healthy` → `down` (red), `slow` (yellow), `flaky` (maroon). Recovery returns to
`healthy`. Colors are the *only* colors in the UI (`STATE_COLORS` shared by backend
schemas and the frontend's Zod module):

| State    | Trigger                                             | Color            |
| -------- | --------------------------------------------------- | ---------------- |
| healthy  | default; also the recovery target                   | green `#22C55E`  |
| down     | N consecutive failed/no-response checks             | red `#EF4444`    |
| slow     | successful response over the latency threshold      | yellow `#EAB308` |
| flaky    | failure rate over the recent window above threshold | maroon `#800000` |

Evaluation precedence after each check (first match wins; otherwise the previous state is
kept — a failure blip below the down threshold is recorded but doesn't flip state):

1. **down** — `!success` and consecutive failures ≥ `down.consecutive_failures` (default 3);
2. **healthy (recovered)** — success and consecutive successes ≥ `recovery.consecutive_successes` (default 2), even while the flaky window still carries older failures;
3. **flaky** — failure rate over the last `window_size` (default 10) checks, including the current one, > `flaky.failure_rate` (default 0.3); returns `None` (never fires) until a full window of history exists;
4. **slow** — success with `latency_ms > slow.latency_ms` (default 2000).

All thresholds are per-service (`service_states` collection, editable via
`GET|PUT|DELETE /states/{service_id}` with admin RBAC); the request schemas allow partial
updates (`PUT` fully replaces, omitted policies reset to defaults).

Every check is persisted (`check_results`), so metrics, reliability and uptime history
survive restarts.

## 4. Incidents, metrics, public pages

### 4.1 Incident lifecycle

- **Opened** automatically when a service degrades (enters `down`, or escalates between
  degraded states) — the state machine's consequences section does this, guarded by the
  partial unique index (no duplicates under concurrent checks).
- **Timeline** events appended atomically (`$push`): state shifts, public/internal notes,
  acknowledge. Internal notes never leave the backend — public payloads filter to
  `visibility == "public"` only.
- **Acknowledged** via `PATCH /incidents/{id}/ack`; **resolved** via
  `POST /incidents/{id}/resolve`, either manually or automatically on recovery. 409s guard
  re-ack / re-resolve.

### 4.2 Metrics & reliability

- 24h metrics per service from `check_results`: total checks, success rate, avg/p95
  latency, MTTD (time to first detection), MTTR (open → resolved).
- 30d reliability: availability vs the service's target %, error budget, downtime used.

### 4.3 Public sanitization

`GET /public/status[/{slug}]` builds payloads from scratch — never serializing internal
documents: no owner emails, no internal notes, no config. Unknown slugs render the
frontend's not-found page, which streams `notFound()` (HTTP 200 + `noindex` metadata).

### 4.4 Uptime history bars

`analytics.uptime_history()` buckets `checked_at` (stored as ISO strings) by string
prefix — `YYYY-MM-DDTHH` (hourly, 24 buckets) or `YYYY-MM-DD` (daily, 30 buckets) — which
is both the bucket identity and the chronological sort. One aggregation covers all
requested services. Bucket color mirrors the state palette:

- all checks succeeded → green (yellow if avg latency exceeds the service's slow threshold);
- all failed → red; mixed → maroon; no checks → neutral gray `#D4D4D4`.

Bars render server-side-colored and are titled with "% ok / checks / avg latency".

## 5. Notifications pipeline

```
state change (CRON check) ──▶ consequences: incident open/escalate/resolve
        │
        ├─ webhook: fire-and-forget POST to PULSE_WEBHOOK_URL (attempt audited in `notifications`)
        ├─ FCM push: dormant — only with a configured service account (stale tokens auto-pruned)
        └─ mail: enqueue `mail_outbox` row (fast insert, never fails the check)
                     │
             mail-dispatch CRON job (every sweep)
                     │  due pending rows, oldest first
                     ▼
             SMTP fan-out: one individual email per subscribed, active account
                     │  subject "[Pulse] <service> is <state>"; body: old → new,
                     │  incident notice, link to /status/{slug}
             outcome → sent │ retry (backoff 60s × attempt, ≤5) → failed │ skipped (no audience)
```

- **Subscription**: every signed-in account can subscribe from its dashboard with its own
  account email (`POST /email-subscriptions`, idempotent 201/200). Subscribers opt in;
  operators/admins must stay subscribed — `GET /dashboard` reports
  `email_notifications.notifications_required` for staff without a subscription.
- **Privacy**: recipients are mailed individually over one SMTP connection, so addresses
  are never shared between subscribers; only registered, active accounts can be on the
  list (the address always comes from the authenticated user).
- **Delivery stats**: per-address `send_count`/`fail_count`/`last_sent_at`/`last_error` on
  the subscription document, surfaced in the frontend panel with a refresh button.
- **SMTP**: STARTTLS (default `smtp.gmail.com:587`), auth via Google **App Password**
  (`PULSE_SMTP_USER` + `PULSE_SMTP_PASSWORD`). Unconfigured → mailer disabled, rows wait.

## 6. Auth, RBAC & security

- **JWT** (PyJWT, HS256, `aud=pulse-frontend`, `iss=pulse-backend`, 12h default) issued by
  `/auth/register|login`; passwords hashed with bcrypt. The frontend stores the token in
  an **httpOnly cookie** (`pulse_token`, 12h max-age; `Secure` added automatically when the
  request arrives over HTTPS via `x-forwarded-proto`) — browser JS and XSS cannot read it.
- **RBAC** via FastAPI dependencies: `CurrentUser` (any signed-in role),
  `RequireStaff` (operator/admin), `RequireAdmin`. Registration always creates
  `subscriber`; the first admin comes from `PULSE_ADMIN_EMAIL`/`PULSE_ADMIN_PASSWORD` at
  startup (idempotent bootstrap). Deletion is soft (`active=false`).
- **Edge gate**: `proxy.ts` (Next 16 middleware) answers anonymous `/dashboard/*` requests
  with a real HTTP 307 to `/auth/login` before any page renders. Role gates *inside*
  pages render access panels instead of streamed redirects (a client-side redirect would
  flash the page shell); streamed `notFound()` on the public detail page is accepted
  (200 + `noindex`).
- **Secrets** all come from env (`PULSE_JWT_SECRET` etc.); FCM credentials are optional and
  disable gracefully.

## 7. Frontend rendering strategy (Next.js 16)

- **Cache Components on**: public pages (`/`, `/status`, `/status/[slug]`) prerender a
  static shell and stream dynamic data inside `<Suspense>`; `instant` navigation stays on
  for them.
- **Auth-gated dashboards** export `instant = false` and block on the session check —
  the redirect decision must be made before any role-specific HTML is produced.
- **Server components fetch** through `lib/server-api.ts` (cookie forwarding + Zod);
  client panels (incidents, users, services, email panel) talk only to the BFF.
- **`params` are Promises** in Next 16; route handlers and pages await them.
- Pages never call `localhost:8000`; only `app/api/**` route handlers do.

### Dashboard shapes

`GET /dashboard` returns one role-shaped payload (the page's single data source):

| Role       | Contents |
| ---------- | -------- |
| subscriber | public status view + own services watchlist + email panel (optional) |
| operator   | subscriber data + incidents console, 24h metrics, 30d reliability, catalogue, per-service state config, email panel (required) |
| admin      | operator data + user management (role/active/delete), service management, webhook delivery stats, email panel (required) |

## 8. UI design system

Minimal **black & white, boxy**: square corners, 1px borders, no shadows, no pills or
badges, no animations/transitions. Hierarchy comes from typography (uppercase,
letter-spaced headings) and spacing; state is communicated only through the four state
colors (plus neutral gray for no data). Panels are white boxes with `border-edge`
1px borders; a required-but-missing email subscription is the one black border accent.

## 9. Design trade-offs at a glance

| Decision | Alternative | Why this way |
| -------- | ----------- | ------------ |
| BFF route handlers | browser → FastAPI directly | cookie isolation, one contract place, Zod both ways |
| Sweep + atomic claim | one APScheduler job per service | per-service intervals without job churn; catalogue changes need no restart |
| Pure `evaluate_state` | state machine inline in the check task | testable, single-screen logic |
| Mail outbox + CRON dispatch | send mail inside the check | survives SMTP outages/restarts; retries with backoff; no blocked checks |
| Outbox rows kept after delivery | delete after send | observability without a log system |
| Partial unique index for incidents | check-then-insert | duplicate-proof under concurrent checks |
| ISO-prefix bucketing for uptime bars | Mongo aggregation time buckets | exact bucket identity from stored ISO strings; one pass, no timezone math |
| httpOnly cookie session | localStorage JWT | XSS cannot exfiltrate the token |
| Access panels for in-page role gates | streamed redirects | avoids redirect-flash inside an already-streamed shell |
| FCM kept dormant | delete it | backend machinery already verified; a future channel switch is config-only |

## 10. Module map (backend `core/`, frontend `lib/`)

- `core/config.py` — env-driven settings (Mongo/JWT/webhook/SMTP/FCM/public URL).
- `core/database.py` — shared client, `ensure_indexes`, thin CRUD helpers.
- `core/dependencies.py` — RBAC dependency gates.
- `core/jwt.py` — token issue/verify.
- `core/scheduler.py` — APScheduler: `health-sweep` + `mail-dispatch` jobs.
- `core/health_check.py` — check execution, state machine, incident consequences,
  webhook/FCM fan-out, mail enqueue (the automated trigger).
- `core/mailer.py` — SMTP sender + durable outbox (`enqueue_state_change`,
  `process_outbox`, startup flush).
- `core/fcm.py` — dormant Firebase Admin sender (per-device stats, stale-token pruning).
- `core/analytics.py` — metrics, reliability, uptime buckets, dashboard summaries.
- `lib/schemas.ts` — every Zod schema (backend payloads + form inputs, `STATE_COLORS`).
- `lib/backend.ts` / `server-api.ts` / `auth.ts` / `client.ts` — the BFF plumbing
  (server bridge, cookie session, browser fetch guard).
