# Pulse — System Design

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

## System scope and boundaries

Pulse monitors configured HTTP endpoints, reports service health and incidents,
and notifies opted-in users. Its primary actors are anonymous visitors,
subscribers, operators and administrators. External dependencies are MongoDB,
the monitored HTTP endpoints, an optional webhook receiver and an SMTP server;
Firebase is an optional legacy backend integration, not part of the current UI.

### Component responsibilities

| Component | Responsibility | Persistent state |
| --- | --- | --- |
| Next.js frontend | Public pages, dashboards, session cookie and API proxy | None; the browser holds an httpOnly cookie |
| FastAPI | Authentication, authorization, APIs and business logic | MongoDB collections |
| Health scheduler | Claim due services and run HTTP checks | Service monitoring fields and check results |
| Mail scheduler | Select pending outbox entries and send email | Outbox entries and subscription delivery statistics |
| MongoDB | Store users, catalogue, checks, incidents and subscriptions | All application collections |
| SMTP server | Accept individually addressed state-change messages | External to Pulse |

### Principal flows

**Browser request:** browser → Next.js page or client component → Next.js
`/api/*` handler → FastAPI → MongoDB. Server components also use the Next.js
API layer. The backend validates JWTs and applies role checks; public status
responses are constructed separately from internal records.

**Health check:** scheduler claims a due service → HTTP GET with a timeout →
record result and update monitoring state → apply incident consequences → on a
state transition, attempt to enqueue an email and dispatch optional push.
Incident opening and recovery also initiate a webhook delivery.

**Email:** dashboard subscribes the signed-in account's email → MongoDB stores
the subscription → a state transition creates a mail-outbox row → the mail
job selects due rows → SMTP sends individually to currently subscribed active
accounts → the sender records delivery statistics and the outbox disposition.

## 1. Architectural decisions

### 1.1 Backend-for-Frontend (BFF)

The browser **never talks to the FastAPI backend directly**. Client components and
server-rendered pages fetch data through self-hosted Next.js route handlers (`app/api/**`), which:

1. read the session from the httpOnly cookie (the JWT never reaches browser JS),
2. forward the request to FastAPI with the bearer token attached server-side,
3. validate the backend's response payload with **Zod** before returning it,
4. validate write payloads in the other direction too (`lib/schemas.ts` holds
   `*InputSchema` forms used by client components).

Why: server-side token handling, one place to
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

The health-check path attempts to **enqueue** a `mail_outbox` row (a single insert).
Delivery is a second CRON job (`mail-dispatch`, same 10s cadence) that drains due rows.
This is the standard outbox pattern, chosen because mail is slow, flaky, and may not even
be configured (SMTP credentials missing):

- queued rows can survive a restart and are retried after SMTP failures;
- retries have a schedule (5 attempts, 60s × attempt backoff) instead of blocking checks;
- with no credentials, rows simply wait — mail starts flowing automatically the moment
  `PULSE_SMTP_USER`/`PULSE_SMTP_PASSWORD` are set and the backend is restarted
  (a startup pass processes up to 50 due rows; later passes process the rest);
- every row is kept after terminal states (`sent` / `failed` / `skipped`) for inspection.

The webhook and optional FCM fan-out use tracked background tasks rather than the
mail outbox. The sweep and shutdown attempt to drain them; abrupt termination can
still interrupt them. The outbox has important delivery limitations described in §11.

### 1.5 MongoDB

Document-per-entity collections with explicit indexes created at startup
(`database.ensure_indexes`). Some document timestamps are inserted as ISO strings in
JSON mode, while later updates can write BSON datetimes; the MongoDB client uses
`tz_aware=True`. Uptime buckets use the check results' ISO-string timestamps (§4.4).
Index creation runs at startup, but schema changes may still require migrations.

## 2. Data model

Nine collections use application-generated identifiers and references such as
`uid` and `service_id`. Timestamp fields vary by document type.

| Collection            | Purpose & key fields | Indexes |
| --------------------- | -------------------- | ------- |
| `users`               | accounts: `uid`, unique `email`, bcrypt `hashed_password`, `role` (subscriber/operator/admin), `active` | unique `uid`, `email` |
| `services`            | catalogue: `service_id`, unique `name`, unique `slug`, `health_url`, `enabled`, `check_interval_seconds`, `owner_email`, `monitoring.next_check_at` | unique `service_id`, `name`, `slug` |
| `service_states`      | per-service threshold overrides (§3); absent = defaults | unique `service_id`, `state_id` |
| `incidents`           | lifecycle + `timeline[]` events (public/internal notes, state shifts, ack) | unique `incident_id`; partial unique `(service_id, status)` for open/acknowledged; `(status, opened_at)` for listing |
| `check_results`       | one row per check: `service_id`, `checked_at`, `success`, `latency_ms`, `error` | `(service_id, checked_at desc)` |
| `notifications`       | webhook delivery audit: event, payload message, `delivered`, `last_error` | `(created_at desc)` |
| `device_tokens`       | **dormant FCM**: `uid`, unique `fcm_token` (masked in API responses as `first6…last4`), device label/UA, send/fail stats | unique `fcm_token`; `(uid, created_at desc)` |
| `email_subscriptions` | the user-facing channel: one per account, `email` = **the account's own address** (never accepted from the request body), send/fail stats | unique `uid`, unique `email` |
| `mail_outbox`         | queue for state-change mails: service id/name/slug, `old_state`/`new_state`, `incident_id`, lifecycle pending → sent, failed or skipped; attempts and next attempt time | `(status, next_attempt_at)` for the dispatcher; `created_at` for FIFO |

Relationships are by id (`uid`, `service_id`, `incident_id`); there are no joins —
dashboards use role-shaped payloads from `GET /dashboard` and other API calls.

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

All thresholds are per-service (`service_states` collection). Operators and admins
can read, replace (`PUT`) or partially update (`PATCH`) them; only admins can
reset them with `DELETE`. Omitted policies in a `PUT` revert to defaults.

Every check is persisted (`check_results`), so metrics, reliability and uptime history
survive restarts.

## 4. Incidents, metrics, public pages

### 4.1 Incident lifecycle

- **Opened** automatically when a service enters `down` or `flaky` and has no
  active incident. A transition to `slow` alone does not open one. Subsequent
  state changes can update an existing incident.
- **Timeline** events appended atomically (`$push`): state shifts, public/internal notes,
  acknowledge. Public payloads filter to `visibility == "public"` only; staff can
  access internal notes through authorized endpoints.
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
                     │  incident text if an incident ID is present, link to /status/{slug}
             outcome → sent (including partial success)
                     │ retry (backoff 60s × attempt, ≤5) → failed
                     │ skipped (no audience)
```

- **Subscription**: every signed-in account can subscribe from its dashboard with its own
  account email (`POST /email-subscriptions`, idempotent for sequential requests).
  `GET /dashboard` flags missing staff subscriptions, but the API currently allows
  operators and admins to unsubscribe; this is a reminder, not enforced policy.
- **Privacy**: recipients are mailed individually over one SMTP connection, so addresses
  are never shared between subscribers; only active accounts are selected at dispatch
  (the address comes from the authenticated user). Registration does not establish
  mailbox ownership; the design does not implement email verification.
- **Delivery stats**: per-address `send_count`/`fail_count`/`last_sent_at`/`last_error` on
  the subscription document, surfaced in the frontend panel with a refresh button.
  SMTP acceptance does not guarantee final delivery to a recipient's inbox.
- **SMTP**: Gmail defaults to `smtp.gmail.com:587`, with a Google **App Password**
  (`PULSE_SMTP_USER` + `PULSE_SMTP_PASSWORD`). The sender upgrades to STARTTLS if
  the server advertises it; it does not require TLS. Unconfigured → rows wait.

## 6. Auth, RBAC & security

- **JWT** (PyJWT, HS256, `aud=pulse-frontend`, `iss=pulse-backend`, 12h default) issued by
  `/auth/register|login`; passwords hashed with bcrypt. The frontend stores the token in
  an **httpOnly cookie** (`pulse_token`, 12h max-age; `Secure` added automatically when the
  request arrives over HTTPS via `x-forwarded-proto`). JavaScript cannot read an
  httpOnly cookie, but XSS can still make authenticated requests from the browser.
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

`GET /dashboard` returns role-shaped summary data; dashboard pages also fetch
additional resources through their respective API routes:

| Role       | Contents |
| ---------- | -------- |
| subscriber | public status summary and monitored service list; optional email panel |
| operator   | incidents console, metrics, reliability, catalogue, threshold configuration and email panel |
| admin      | user and service management, summary data, webhook delivery history and email panel; operator console is available separately |

## 8. UI design system

Minimal **black & white, boxy**: square corners, 1px borders, no shadows, no pills or
badges, no animations/transitions. Hierarchy comes from typography (uppercase,
letter-spaced headings) and spacing; state is communicated only through the four state
colors (plus neutral gray for no data). Panels are white boxes with `border-edge`
1px borders. Staff without an email subscription are flagged by the dashboard
summary; the backend does not enforce the requirement.

## 9. Design trade-offs at a glance

| Decision | Alternative | Why this way |
| -------- | ----------- | ------------ |
| BFF route handlers | browser → FastAPI directly | cookie isolation, one contract place, Zod both ways |
| Sweep + atomic claim | one APScheduler job per service | per-service intervals without job churn; catalogue changes need no restart |
| Pure `evaluate_state` | state machine inline in the check task | testable, single-screen logic |
| Mail outbox + CRON dispatch | send mail inside the check | keeps enqueued work across restarts and retries some failures; delivery guarantees are limited (§11) |
| Outbox rows kept after delivery | delete after send | observability without a log system |
| Partial unique index for incidents | no database constraint | prevents duplicate entries for the same service *and status*, but does not prevent one open and one acknowledged incident for the same service |
| ISO-prefix bucketing for uptime bars | Mongo aggregation time buckets | exact bucket identity from stored ISO strings; one pass, no timezone math |
| httpOnly cookie session | localStorage JWT | XSS cannot exfiltrate the token |
| Access panels for in-page role gates | streamed redirects | avoids redirect-flash inside an already-streamed shell |
| FCM backend retained | delete it | legacy backend tokens and API remain available; frontend registration has been removed |

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

## 11. Deployment, failure modes and current limits

### Deployment topology

For the current implementation, run one FastAPI process with its embedded
scheduler, one Next.js application, and a persistent MongoDB instance. Point
`BACKEND_URL` at FastAPI, configure `PULSE_MONGO_URI`, and supply
`PULSE_SMTP_USER` and `PULSE_SMTP_PASSWORD` to enable email. The default SMTP
endpoint is Gmail on port 587. `README.md` contains setup commands and the
full environment-variable list. Restrict direct backend access as appropriate;
use HTTPS and a trusted reverse proxy for non-local deployments.

Each FastAPI process starts its own scheduler. Although due health checks are
claimed through MongoDB, outbox rows are read without an atomic claim or lease.
Multiple backend workers or instances can therefore process the same mail
concurrently and send duplicates. `max_instances=1` limits a job only within
one scheduler, not across processes.

### Delivery semantics

- Service-state updates, incident changes and outbox insertion are separate
  writes, not a transaction. A crash or database error after updating the state
  but before enqueueing can lose the notification. Enqueue errors are logged.
- Once inserted, pending rows remain in MongoDB across a restart. On startup,
  one batch of up to 50 due rows is attempted; future scheduled passes handle
  other due rows. A missing SMTP configuration leaves them pending.
- A crash after SMTP accepts a message but before the row is marked sent can
  result in duplicate messages on a subsequent attempt. There is no exactly-once
  guarantee or per-recipient delivery ledger.
- If at least one recipient succeeds, the entire outbox row is classified as
  sent even when other recipients fail; those failed recipients are not retried
  for that event. When all recipients fail or the SMTP connection fails, the
  event is retried up to five attempts. Terminal rows are retained.
- Recipients are selected at dispatch time, not at the time of the transition.
  If there are no active subscribers, the row is marked skipped. New
  subscriptions can therefore receive old queued events, while unsubscribed or
  deactivated accounts are excluded when the audience is selected.
- STARTTLS is opportunistic, not required. A server that does not advertise it
  can receive authentication without an upgrade; use a trusted SMTP endpoint
  and do not assume enforced transport security. The sender uses `smtplib.SMTP`;
  implicit TLS on port 465 is not implemented.
- The email body says an incident was opened whenever an incident ID is
  present, including transitions that touched an existing or resolved
  incident. This wording should not be treated as a reliable incident event.

### Monitoring and data limitations

- The 10-second health sweep bounds scheduling granularity; a configured
  interval shorter than the sweep is not guaranteed. The sweep awaits all
  dispatched checks and outstanding notification tasks before finishing.
- The incident index is unique on `(service_id, status)`, not on `service_id`
  alone. It can permit an `open` and an `acknowledged` incident for the same
  service. Application logic tries to find an active incident first, but this
  is not a cross-status uniqueness guarantee under concurrency.
- Check results and outbox records have no retention policy in this design;
  storage and query costs grow with time. Email fan-out reads active users and
  matching subscriptions before sending, and a large audience can exceed a
  single mail-job interval.
- Logs, subscription statistics and retained outbox records provide basic
  diagnostics; there is no dedicated outbox administration UI or automatic
  replay of rows after the retry limit. Real Gmail delivery remains to be
  confirmed manually.

### Potential hardening (not implemented)

Use a transactional event/outbox write where MongoDB deployment supports it;
add atomic leased claims, per-recipient retry and idempotency strategy; enforce
TLS for SMTP authentication; add queue metrics, retention and replay tooling;
and enforce any mandatory staff-subscription policy in the backend. These are
future options, not guarantees of the current system.
