# Pulse — Status & Incident Hub

Pulse is a self-hosted status & incident hub: a FastAPI backend runs a health-check
CRON over a catalogue of services, opens and resolves incidents from check results,
computes metrics and reliability, and notifies people (webhook + email) when
a service changes state. A Next.js frontend renders role-shaped dashboards and a
sanitized public status page.

Monorepo layout:

```
backend/    FastAPI + MongoDB (pymongo), APScheduler CRON, Firebase Admin
frontend/   Next.js 16 (App Router, TypeScript, Tailwind 4) + Zod
```

## Features

**Monitoring (backend CRON)**
- Per-service schedule: each service is checked on its own `check_interval_seconds`
  (a 10s sweep claims due services; checks run concurrently with per-check timeouts).
- State machine per service: `healthy` → `down` (N consecutive failures),
  `slow` (latency over threshold), `flaky` (failure rate over a rolling window),
  with recovery back to `healthy`. Thresholds are configurable per service.
- Every check is stored (`check_results`), so history outlives process restarts.
- Incidents open automatically when a service degrades; they are annotated on
  state shifts and resolved automatically on recovery.

**Incidents & workflow**
- Timeline events, acknowledge, public/internal notes, resolve (409s guard
  re-ack/re-resolve).
- Internal notes never leave the backend — the public pages only see
  `visibility="public"` events.

**Metrics & reliability**
- 24h metrics per service: total checks, success rate, avg/p95 latency, MTTD, MTTR.
- 30d reliability: availability vs the service's target %, error budget, downtime used.

**Notifications**
- Webhook receiver (`PULSE_WEBHOOK_URL`) gets incident opened/resolved events;
  every attempt is recorded for auditing.
- **Email (the user-facing channel)**: every account subscribes from its
  dashboard with its own account email (`email_subscriptions` collection —
  stored separately from the FCM token store). The health-check CRON
  **automatically triggers** the mail on every service state change — the
  change is first written to a durable outbox (`mail_outbox` collection) and a
  CRON job dispatches it, retrying on SMTP failures with backoff (5 attempts,
  1-minute base) and flushing anything queued while the backend was down on
  the next startup. Each subscribed, active account receives an individual
  email (one message per recipient; addresses are never shared). Mail is sent
  over SMTP — for Gmail, an **App Password** (`PULSE_SMTP_*`); without
  credentials subscriptions still work and rows wait in the outbox until SMTP
  is configured. Per-address send/fail stats are kept. Staff (operator/admin)
  must stay subscribed; `GET /dashboard` reports it via `email_notifications`.
- Firebase Cloud Messaging remains in the backend (`core/fcm.py`, devices API)
  in **dormant** form: the frontend no longer uses it and pushes only happen
  when a service account is configured.

**Public status page**
- `/status` — all enabled services with current state and 24 hourly uptime bars;
  `/status/{slug}` — detail with a 30-day daily uptime bar and incident history.
- Bucket colors mirror the live states (green/yellow/maroon/red, gray = no data)
  and are computed server-side. No owner data or internal notes ever reaches these
  pages. Unknown slugs render a not-found page marked `noindex`.

**Auth & RBAC**
- JWT bearer tokens (bcrypt password hashing). New accounts are always `subscriber`.
- The frontend holds the token in an httpOnly cookie (`pulse_token`, 12h max-age) —
  the JWT never reaches browser JS. Pages call only self-hosted `/api/*` routes
  (a BFF layer that validates payloads with Zod both ways); the browser never
  talks to the FastAPI backend directly.
- Role-shaped `GET /dashboard`: subscriber → status view; operator → incidents,
  metrics, reliability, catalogue; admin → operator view + user management,
  webhook delivery stats and service management.

## Roles

| Ability                                | Anonymous | Subscriber | Operator | Admin |
| -------------------------------------- | :-------: | :--------: | :------: | :---: |
| Public status pages                    |     ✓     |     ✓      |    ✓     |   ✓   |
| Register / sign in                     |     ✓     |     —      |    —     |   —   |
| Subscribe to email notifications        |     —     |     ✓      |    ✓     |   ✓   |
| Read incidents, metrics, reliability   |     —     |     —      |    ✓     |   ✓   |
| Ack / note / resolve incidents         |     —     |     —      |    ✓     |   ✓   |
| Configure state thresholds             |     —     |     —      |    ✓     |   ✓   |
| Create / edit / pause / delete services|     —     |     —      |    —     |   ✓   |
| Change roles, deactivate/delete users  |     —     |     —      |    —     |   ✓   |

## Architecture

```
            ┌──────────────────────────── Next.js (frontend) ───────────────────────────┐
 browser ──▶│  pages ──────▶ app/api/* route handlers (BFF, Zod)  ◀── cookie session     │
            └────────────────────────────────┬──────────────────────────────────────────┘
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

## Tech stack

| Layer    | Tech                                                                 |
| -------- | -------------------------------------------------------------------- |
| Backend  | Python 3.12+, FastAPI, Pydantic v2, pymongo (MongoDB), PyJWT, bcrypt, APScheduler, httpx, firebase-admin |
| Frontend | Next.js 16.4.6 (App Router, Turbopack, Cache Components), React 19, TypeScript, Tailwind CSS 4, Zod 4 |

## Getting started

### Prerequisites

- Python 3.12+ (virtualenv recommended)
- Node.js 20+
- MongoDB reachable at `mongodb://localhost:27017` (or set `PULSE_MONGO_URI`)

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# optional bootstrap admin (created at startup, idempotent)
$env:PULSE_ADMIN_EMAIL = "admin@example.com"
$env:PULSE_ADMIN_PASSWORD = "AdminPass123"

.venv\Scripts\python -m uvicorn main:app --port 8000
# development alternative: --reload
```

Interactive API docs: <http://localhost:8000/docs>

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local   # fill in BACKEND_URL
npm run dev                    # or: npm run build && npm start
```

Open <http://localhost:3000>. Sign in with the bootstrap admin (or register —
new accounts are subscribers; promote them in the admin console).

### Environment variables

**Backend** (all optional; defaults shown)

| Variable                    | Default                          | Purpose |
| --------------------------- | -------------------------------- | ------- |
| `PULSE_MONGO_URI`           | `mongodb://localhost:27017`      | MongoDB connection string |
| `PULSE_MONGO_DB`            | `pulse`                          | Database name |
| `PULSE_JWT_SECRET`          | dev fallback                     | HMAC key for JWTs — set in production |
| `PULSE_TOKEN_MINUTES`       | `720`                            | Access-token lifetime (12h) |
| `PULSE_WEBHOOK_URL`         | `http://localhost:9900`          | Webhook receiver base URL |
| `PULSE_SMTP_HOST` / `PULSE_SMTP_PORT` | `smtp.gmail.com` / `587` | Outgoing mail server (STARTTLS) |
| `PULSE_SMTP_USER`           | unset                            | Gmail address mail is sent **from** |
| `PULSE_SMTP_PASSWORD`       | unset                            | Google **App Password** (16 characters — not the account password); unset = mailer disabled |
| `PULSE_SMTP_FROM`           | = `PULSE_SMTP_USER`              | Override the From address |
| `PULSE_PUBLIC_URL`          | `http://localhost:3000`          | Frontend base URL used in status-page links inside emails |
| `PULSE_FIREBASE_CREDENTIALS`| unset                            | Dormant FCM backend: path to a service-account JSON; unset = pushes disabled |
| `PULSE_ADMIN_EMAIL` / `PULSE_ADMIN_PASSWORD` | unset           | Bootstrap admin created at startup |

To enable notification emails for a Gmail account: turn on 2-Step Verification,
create an **App Password** (Google Account → Security → 2-Step Verification →
App passwords), then set `PULSE_SMTP_USER` to the Gmail address and
`PULSE_SMTP_PASSWORD` to the App Password and restart the backend.

**Frontend** (`.env.local`; see `.env.example`)

| Variable                          | Purpose |
| --------------------------------- | ------- |
| `BACKEND_URL`                     | FastAPI base URL used by the BFF (default `http://localhost:8000`) |

Notification emails are configured entirely on the backend — the frontend
needs no Firebase/mail settings.

The auth cookie is marked `Secure` automatically when the request arrives over
HTTPS (`x-forwarded-proto`), so plain-HTTP local runs and proxied HTTPS both work.

## API overview (backend)

| Area        | Routes |
| ----------- | ------ |
| Health      | `GET /health` |
| Auth        | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Users/admin | `GET /admin/users`, `PATCH /admin/users/{uid}` (role, active), `DELETE /admin/users/{uid}` (soft delete) |
| Catalogue   | `GET|POST /catalogue`, `GET|PATCH|DELETE /catalogue/{service_id}` |
| State cfg   | `GET|PUT /states/{service_id}`, `DELETE /states/{service_id}` (reset) |
| Devices     | `POST|GET /devices` (FCM tokens — dormant channel, masked in responses), `DELETE /devices/{token_id}` |
| Email notifications | `POST|GET|DELETE /email-subscriptions` (subscribe the account email; idempotent) |
| Incidents   | `GET /incidents`, `GET /incidents/{id}`, `PATCH /incidents/{id}/ack`, `POST /incidents/{id}/notes`, `POST /incidents/{id}/resolve` |
| Metrics     | `GET /metrics`, `GET /metrics/{service_id}`, `GET /metrics/{service_id}/checks` |
| Reliability | `GET /reliability`, `GET /reliability/{service_id}` |
| Notifications | `GET /notifications` (webhook delivery history, staff only) |
| Public      | `GET /public/status`, `GET /public/status/{slug}` (sanitized, no auth) |
| Dashboard   | `GET /dashboard` (role-shaped: status view / ops console data / + admin summaries; includes the `email_notifications` summary) |

The frontend mirrors these under its own `/api/*` routes (the browser's only
entry point); logout is handled there by clearing the session cookie.

## Health states & colors

| State    | Meaning                                          | Color           |
| -------- | ------------------------------------------------ | --------------- |
| healthy  | default — nothing tripped                        | green `#22C55E` |
| slow     | responses over the latency threshold             | yellow `#EAB308`|
| flaky    | failure rate over the window exceeds threshold   | maroon `#800000`|
| down     | N consecutive failed/no-response checks          | red `#EF4444`   |

Uptime bars use the same palette (a bucket with mixed outcomes renders as
`flaky`; buckets without checks are neutral gray).

## Design notes

- **UI**: minimal black & white, boxy (square corners, 1px borders, no shadows,
  no pills/badges); the only colors are the four state colors above.
- **Next.js 16 specifics**: `cacheComponents` is on — public pages prerender a
  static shell and stream dynamic data inside `<Suspense>`; auth-gated dashboards
  export `instant = false`; anonymous `/dashboard/*` requests get a real HTTP 307
  to `/auth/login` from `proxy.ts` (Next 16's Middleware); page and route-handler
  `params` are Promises.

## Project structure

```
backend/
  main.py               FastAPI app: lifespan, index bootstrapping, admin bootstrap, scheduler
  core/
    config.py           env-driven settings
    database.py         shared MongoClient + indexes
    dependencies.py     RBAC (CurrentUser / RequireStaff / RequireAdmin)
    jwt.py              token issue/verify
    scheduler.py        APScheduler: health sweep + mail-dispatch jobs (every 10s)
    health_check.py     check execution, state machine, incidents, webhook + FCM fan-out,
                        mail-outbox enqueue (the automated mail trigger)
    analytics.py        metrics, reliability, dashboard summaries, uptime buckets
    fcm.py              Firebase Admin sender (dormant channel: per-device stats, stale-token pruning)
    mailer.py           SMTP sender + durable mail outbox (enqueue on state change,
                        CRON dispatch with retry/backoff, startup flush)
  routers/              one module per API area (see API overview)
  schemas/              Pydantic models per domain (documents + requests/responses)

frontend/
  proxy.ts              edge gate: anonymous /dashboard/* → 307 /auth/login
  lib/
    schemas.ts          Zod schemas (payload + form validation, STATE_COLORS)
    backend.ts          server-only bridge to FastAPI
    auth.ts             httpOnly cookie session
    client.ts           browser fetch helper (relative /api only)
    server-api.ts       server-component fetch (cookie forwarding)
  app/api/              BFF route handlers mirroring the backend API
  app/                  pages: /, /status, /status/[slug], /auth/*, /dashboard/*
  components/           ui primitives + incidents/users/services panels,
                        email-notifications (email subscription), history-bars
```

## Verification

- `smoke_task2.py` (38 checks) and `smoke_task3.py` (19 checks) at the repo root
  cover schemas, RBAC, incident lifecycle, sanitization, metrics/reliability and
  the public pages. `PROGRESS.md` records per-task verification including
  end-to-end runs through the frontend only.

## Known follow-ups

- `npm run lint` reports `react-hooks/set-state-in-effect` errors on the client
  panels' initial data loads (build/runtime unaffected).
- The webhook receiver currently receives incident opened/resolved events;
  acknowledged/note events are modeled but not sent yet.
