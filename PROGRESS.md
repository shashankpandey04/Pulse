# Pulse — Progress

## Task 1 — Schema design (done)

Created `backend/schemas/` (Pydantic v2, for FastAPI + MongoDB/pymongo + bcrypt):

- `common.py` — shared helpers (`utcnow`, `new_uid` uuid4, `TimestampedModel`) and generic responses (`MessageResponse`, `ErrorResponse`).
- `auth.py` — `UserDocument` (`users` collection: uid, email, hashed_password bcrypt, pfp_link, role, active, timestamps) + `RegisterRequest`, `LoginRequest`, `AuthResponse` (bearer token + user), `UserResponse`, `AdminUserUpdateRequest` (admin role/active changes), `UserListResponse`. New accounts are always `subscriber`; role is stored as a plain string literal of `admin | operator | subscriber`; password capped at 72 bytes (bcrypt limit).
- `catalogue.py` — `ServiceDocument` (`services` collection: service_id, name, unique slug, description, health_url, check_interval_seconds, timeout_seconds, owner_uid + owner_email, reliability_target %, enabled) + `ServiceCreateRequest`, `ServiceUpdateRequest` (partial), `ServiceResponse`, `ServiceListResponse`. Validator: `timeout_seconds` must be smaller than `check_interval_seconds`.
- `state.py` — `ServiceStateDocument` (`service_states` collection, one config per service keyed by unique `service_id`) with `DownPolicy` (consecutive no-responses, default 3), `SlowPolicy` (latency_ms, default 2000), `FlakyPolicy` (failure_rate 0..1, default 0.3 = 30%, over a `window_size` window, default 10) and `RecoveryPolicy` (consecutive successes, default 2) + upsert/update/list/response schemas. Colors: healthy `#22C55E` green, down `#EF4444` red, slow `#EAB308` yellow, flaky `#800000` maroon (`STATE_COLORS`).
- `README.md` — collection/index plan, full API route table (who can call what), role rules, state threshold/color table, Mongo implementation notes (`model_dump(mode="json")`, `tz_aware=True`, bcrypt hash/verify).

Validation: throwaway script exercised all 21 models — 33 checks passed (valid payloads, defaults, and rejection of bad emails/short passwords/role smuggling on register/out-of-range flaky rate/timeout >= interval/extra fields).

## Task 2 — Core, RBAC, routers, health-check CRON (done)

Core (`backend/core/`):
- `config.py` — env-driven settings (mongo uri/db, JWT secret/alg/aud/iss, webhook url).
- `database.py` — shared pymongo client (`tz_aware`), `get_db`, thin helpers (insert/find/count/update/delete), `ensure_indexes` (users/services/service_states + incidents/check_results/notifications), `close_client`.
- `jwt.py` — PyJWT HS256: `create_access_token` (sub=uid, email, role, iat/exp, iss, aud) and `verify_access_token` raising `TokenError`.
- `dependencies.py` — central RBAC: `get_current_user` (JWT -> live user, rejects deactivated), `require_roles(*roles)` factory, ready-made `CurrentUser` / `RequireStaff` (admin+operator) / `RequireAdmin`, plus soft `OptionalUser` for public endpoints.
- `health_check.py` — one check per service via shared httpx client: stores `CheckResultDocument` (every result), evaluates state (`evaluate_state`: down > recovered-healthy > flaky (full-window failure rate incl. current check) > slow > keep previous), advances `services.monitoring.*`, auto-opens incidents on down/flaky (with timeline), escalates flaky->down on the open incident, auto-resolves on recovery, POSTs webhook notifications (recorded in `notifications` with delivered/error status).
- `scheduler.py` — APScheduler `AsyncIOScheduler` + 10s sweep job: atomically claims due services (`monitoring.next_check_at`) and runs each check as an independent asyncio task (per-check timeout, no service blocks others); drains pending webhook posts.

Routers:
- `routers/auth.py` — register (bcrypt, role forced subscriber, 409 dup email), login (401 generic), `/auth/me`, admin: list (filters+pagination), PATCH role/active (self-demotion/self-deactivation guarded), DELETE (soft delete). First admin bootstrapped from `PULSE_ADMIN_EMAIL/PASSWORD` env at startup.
- `routers/catalogue.py` — full CRUD (admin writes, staff reads), slug auto-derive, owner email -> uid resolution (404 unknown), duplicate 409, PATCH re-validates merged doc (timeout < interval), delete also removes state config; service creation provisions default state config.
- `routers/state.py` — PUT upsert / PATCH partial / GET effective (defaults when unstored) / list / DELETE reset (admin only); one config per service keyed by `service_id`.

App: `main.py` — FastAPI with lifespan (indexes -> httpx client -> scheduler start -> admin bootstrap; shutdown: scheduler stop, drain notifications, close client). Schemas added: `incidents.py` (IncidentDocument w/ embedded timeline, ack/note/resolve requests, responses), `metrics.py` (CheckResultDocument + ServiceMetricsResponse MTTD/MTTR), `reliability.py` (availability vs target + error budget), `notification.py` (webhook delivery records).

Verification: `D:\Pulse\smoke_task2.py` against real local Mongo (test db `pulse_test`) + local fixture HTTP server — 38 checks passed: auth/RBAC flows (401/403/409/404 paths), catalogue & states CRUD, and the CRON: down after 3 failed checks -> incident auto-opened + webhook recorded; recovery after 2 successes -> incident auto-resolved + webhook recorded; flaky detection with tight window; second service scheduled independently; tampered token rejected; OpenAPI paths sane.

## Task 3 — Incidents/Metrics/Reliability/Public/Notification/Dashboard routers (done)

- `schemas/public.py` — sanitized status-page payloads (public events only, no owner emails): `PublicStatusResponse` (summary/colors/services/active incidents), `PublicServiceDetail`.
- `schemas/dashboard.py` — role-shaped `DashboardResponse` + `IncidentSummary`, `UsersSummary`, `NotificationsSummary`.
- `core/analytics.py` — computations shared by routers: `service_metrics` (success rate, avg/p95 latency, MTTD from first failed check of the episode, MTTR from resolved durations), `service_reliability` (availability vs catalogue target, error budget allowed/consumed/remaining), `incidents_summary`, `users_summary`, `notifications_summary`. Storage convention documented: `resolved_at`/`acknowledged_at`/`monitoring.*` are BSON dates; `opened_at`/`checked_at`/timeline `at` are ISO strings — range queries use the matching type.
- `routers/incidents.py` (staff) — list (filters: service_id, status; paged), get, `PATCH /{id}/ack` (409 unless open; timeline event + acknowledged_by), `POST /{id}/notes` (public default / internal), `POST /{id}/resolve` (manual; notifies webhook via `health_check.resolve_incident`; 409 if resolved).
- `routers/metrics.py` (staff) — `/metrics` overview (window_hours 1-720, default 24), `/metrics/{service_id}`, `/metrics/{service_id}/checks` (raw results, success filter, paged).
- `routers/reliability.py` (staff) — `/reliability` overview + per-service (window_days 1-90, default 30).
- `routers/public.py` (no auth) — `/public/status` (enabled services + state colors + active incidents), `/public/status/{slug}` (service detail + incident history, public events only); `build_status_page()` reused by dashboard.
- `routers/notification.py` (staff) — `/notifications` delivery history (filters: service_id, event_type, delivered).
- `routers/dashboard.py` — `GET /dashboard` for any signed-in role: subscriber -> `status` (public view); operator -> `services` + `incidents_summary` + `metrics` + `reliability`; admin -> adds `users_summary` + `notifications_summary`.
- `main.py` wired with all new routers; `database.update_push` helper added ($set + $push atomic).

Verification: `D:\Pulse\smoke_task3.py` — 19 checks passed: RBAC (subscriber 403 on ops routers, anonymous dashboard 401), incident ack/notes/resolve lifecycle incl. 409s, internal notes hidden from public page (and no owner-email leak), metrics MTTD/MTTR/success-rate, reliability vs target + error budget, public status page + 404s, dashboard shapes for all three roles. Task 2 suite re-run: still 38/38.

## Task 4 — Frontend: Next.js BFF + minimal black & white UI (done)

Stack: Next.js 16.4.6 (App Router, TypeScript, Tailwind 4) + Zod. Design rules honored: minimal black & white only, boxy (`border-radius: 0` everywhere, plain 1px borders, no shadows), no badges/pills; the only colors are the backend's state palette (`#22C55E/#EF4444/#EAB308/#800000`, mirrored as `STATE_COLORS`).

Architecture — pages never call the FastAPI backend directly; a self-hosted BFF layer sits in between:

- `lib/schemas.ts` — Zod schemas mirroring every backend payload (users, auth envelope, catalogue, states, incidents, metrics, reliability, notifications, public status, role-shaped dashboard) + shared `STATE_COLORS`. Used both to validate backend responses server-side and to validate form input client-side.
- `lib/backend.ts` — server-only bridge to the backend (`BACKEND_URL`, default `http://localhost:8000`); forwards the bearer token, normalizes FastAPI `detail` errors, never imported by client code.
- `lib/auth.ts` — session cookie `pulse_token`: httpOnly, sameSite=lax, path=/, 12h max-age (matches backend token expiry); `secure` derived from `x-forwarded-proto` (not `NODE_ENV`) so login works on plain-HTTP self-hosted deployments and behind HTTPS proxies.
- `lib/client.ts` — browser fetch helper; components only ever call relative `/api/...` routes (cookie attached by the browser).
- `lib/server-api.ts` — server-component helper that calls our own `/api` routes with the auth cookie forwarded and validates responses with Zod (`PageApiError` carries the status for 401/404 handling).

17 route handlers under `app/api/` (all validate bodies with Zod, validate backend responses with Zod, map errors):

- `auth/register`, `auth/login` (set the httpOnly cookie; token never reaches JS), `auth/logout` (clears), `auth/me`.
- `dashboard` — role-shaped payload.
- `public/status`, `public/status/[slug]` — no-auth proxy of the sanitized status page.
- `admin/users`, `admin/users/[uid]` (PATCH role/active, DELETE soft delete).
- `catalogue`, `catalogue/[serviceId]` (GET/PATCH/DELETE).
- `states`, `states/[serviceId]` (GET/PUT/DELETE reset).
- `incidents`, `incidents/[incidentId]`, `.../ack` (PATCH), `.../notes` (POST), `.../resolve` (POST).
- `metrics`, `metrics/[serviceId]`, `metrics/[serviceId]/checks`; `reliability`, `reliability/[serviceId]`; `notifications`.

Pages:

- `/` — landing (Monitor / Incidents / Reliability panels), `/status` — public status table + active incidents, `/status/[slug]` — per-service state + incident history (streams `notFound()` as 200 + `noindex`, per Cache Components behavior).
- `/auth/login`, `/auth/register` — Zod-validated forms; register auto-signs in and lands on `/dashboard`.
- `/dashboard` — role router: subscriber sees the status summary (counts per state + service list); operator/admin redirected to their consoles.
- `/dashboard/operator` — operations console: incidents panel (status filter, timeline, acknowledge, resolve with optional note, add public/internal note), 24h metrics table (checks, success %, avg/p95 latency, MTTD, MTTR), 30d reliability table (availability vs target, error budget, downtime used), service catalogue table.
- `/dashboard/admin` — admin console: users/role/webhook stats, users panel (role select, deactivate/reactivate, soft delete; own row protected), services panel (register form with interval/timeout/target validation, pause/resume, delete, link to thresholds), webhook delivery history.
- `/dashboard/services/[serviceId]` — state-thresholds editor (down consecutive-failures, slow latency ms, flaky rate+window, recovery successes; admin can reset to defaults). Staff-level, so operators reach it too.

Components: `ui.tsx` (Panel/Stat/StateLabel/Field/buttons/inputs — all square, bordered), `site-header` (+ `HeaderFallback` static shell), `logout-button`, `incidents-panel`, `users-panel`, `services-panel`, `state-config-form`, `access-panel`.

Next.js 16 specifics (read from bundled `node_modules/next/dist/docs` — this version differs from training data): Middleware is now **Proxy** (`proxy.ts` at project root); route-handler and page `params` are Promises; `cacheComponents: true` is on, so: request-time data must sit inside `<Suspense>` (public pages prerender a static shell with `HeaderFallback`), auth-gated pages that intentionally block export `instant = false`, and anonymous users hitting `/dashboard/*` get a real HTTP 307 to `/auth/login` from `proxy.ts` (cookie-presence check only — pages still validate the session against the backend; in-page role gates render an `AccessPanel` instead of a client-only redirect).

Removed the scaffold's unused Firebase stub (`lib/firebase*`, `hooks/useFCM`, `.env.local` Firebase keys, `firebase` dependency) — auth and notifications come from the Pulse backend.

Verification: production build green (`next build`, 25 routes + Proxy, correct rendering modes: public pages partial-prerendered, dashboards dynamic). End-to-end suite against the real backend (`uvicorn :8000`, Mongo db `pulse_e2e`, dropped afterwards) through the frontend only: 38 checks passed — register/login + httpOnly cookie, `/api/auth/me`, role-shaped dashboards for all three roles, RBAC (subscriber 403 on admin users, anonymous 401, proxy 307 with `Location: /auth/login`), service + state-config creation via the frontend API, public pages listing the service with correct colors, unknown slug → not-found + `noindex`, subscriber bounced to access panels on staff pages, role upgrade mid-session, CRON auto-opening an incident on a dead health URL (down after 2 failures), ack → internal+public notes → resolve with 409 on re-ack — all via the frontend API — notifications recorded (opened+resolved), metrics (0% success) and reliability below target, public page shows the public note but never the internal note or the owner email, admin console/thresholds pages render, logout clears the session. (One suite line "failed" only because my regex expected a relative redirect URL; curl confirmed the correct `307 → /auth/login`.)

Known follow-ups: `npm run lint` reports 4 errors from the new `react-hooks` compiler rules (`set-state-in-effect`: the four client panels kick off their initial fetch with `void load()` inside `useEffect`) plus minor unused-import warnings. Options: restructure the loads (start via event/interval callbacks) or scope-disable the rule per file. Build and runtime behavior are unaffected.

Next: decide on the lint follow-up; then remaining backend bits if still wanted (acknowledged/note webhook events, `OptionalUser` wiring).

## Task 5 — Public uptime history bars + Firebase push notifications (done)

### Uptime history bars (public status pages)

- `schemas/public.py` — new `UptimeBucket` (start, total/failed checks, success_rate, avg_latency_ms, precomputed `color`); `PublicServiceStatus.history` (hourly bars, last 24 hours) and `PublicServiceDetail.daily_history` (daily bars, last 30 days).
- `core/analytics.py` — `uptime_history()`: one Mongo aggregation over `check_results` buckets every service's checks by ISO-prefix (hour or day — lexicographic == chronological for our uniform UTC strings), filling fixed-size bucket lists (oldest first) with a neutral gray `#D4D4D4` for buckets where no check ran. Bucket color mirrors the live-state semantics: no failures → healthy green (or slow yellow when the bucket's mean latency exceeds the service's slow threshold), all failures → down red, partial → flaky maroon.
- `routers/public.py` attaches the histories; the status-page payload stays sanitized (no owner/threshold data — only counts, rates and colors).
- Frontend: `components/history-bars.tsx` (`HistoryBars` — one square div per bucket, colored inline by the backend, with a per-bar `title` tooltip showing % ok / checks / avg latency; `HistoryLegend`), integrated into `/status` (a "Last 24 hours" column), `/status/[slug]` (24-hour strip in the current-state panel + a 30-day panel), and the subscriber dashboard reuses the same `/api/dashboard` payload.

### Firebase Cloud Messaging notifications

- Database (`schemas/device.py`, collection `device_tokens`): one document per subscribed device — `token_id` (app uid), `uid`, unique-indexed `fcm_token`, optional `device_label` + captured `user_agent`, and per-device delivery stats (`send_count`, `fail_count`, `last_sent_at`, `last_error`). Indexes: unique `fcm_token`, `(uid, created_at desc)`.
- Rules implemented: subscribers opt in from their dashboard; operators/admins must keep at least one device — `GET /dashboard` now returns a `devices` summary for every role with `notifications_required` (true for staff with zero devices), `total`, and `fcm_enabled`. A user can register any number of devices.
- Backend API (`routers/devices.py`, wired in `main.py`): `POST /devices` (201 create / 200 upsert — re-registering an existing token re-assigns it to the calling account, since the device changed hands), `GET /devices` (caller's devices, tokens masked to `first6…last4` — full tokens are never returned, whoever holds a token can push to that device), `DELETE /devices/{token_id}` (404 for other users' devices).
- Sender (`core/fcm.py`): Firebase Admin SDK 7.8 initialized at startup from `PULSE_FIREBASE_CREDENTIALS` (service-account JSON path); without it the sender is disabled but registrations still work (`fcm_enabled: false`), mirroring the graceful webhook stance. On every service state change (`core/health_check.py` now calls `_push_state_change` after the incident consequences) it fans out one push per registered device of every active account via `messaging.send_each` (the 7.x API; `send_all` was removed), with `notification` (title "X is down", body old→new) + `data` payload (service ids/states/incident id) for deep-linking. Per-device outcomes are written back to the token doc; `UnregisteredError` responses (device reset / app uninstalled) are pruned automatically. Failures never break monitoring — pushes run as fire-and-forget tasks drained by the sweep/shutdown alongside webhook deliveries.
- Frontend: `lib/firebase.ts` (Web SDK, dynamically imported so SSR never touches it), `public/firebase-messaging-sw.js` (background handler: one notification per service via `tag`, click → `/status`; foreground messages are surfaced inside the panel by `onMessage`), `components/notification-setup.tsx` (permission request → service worker → `getToken` with the VAPID key → `POST /api/devices`; device table with masked tokens, push stats and per-device unsubscribe; current device tracked in `sessionStorage`), mounted on all three dashboards (`required` for operator/admin). BFF routes `app/api/devices[/tokenId]` proxy with Zod validation; `firebase` dependency restored, `.env.local` (gitignored) holds the scaffold's public Firebase keys, `.env.example` documents all `NEXT_PUBLIC_FIREBASE_*` vars.
- Note: the push-notification subscription flow's browser side (permission popup, FCM token issuance) needs a real browser to exercise; the API, storage, fan-out and stats paths were verified over HTTP. Lint unchanged in kind: the new panel follows the same load pattern as the others, so `npm run lint` now reports 5 `set-state-in-effect` errors (was 4).

Verification (fresh DB `pulse_t5`, dropped afterwards; throwaway helper scripts removed): devices API 16 checks (masked 201 register, list, multiple devices per user, role-shaped dashboard summaries — subscriber optional/staff mandatory, upsert re-assignment, cross-user delete 404, own unsubscribe 204, short-token 422, anonymous 401); FCM wiring: with a locally generated service account the sender enabled, a real CRON `healthy→down` transition fanned out to all registered devices, Google rejected the fake credential and every device's `fail_count`/`last_error` recorded it (backend stayed healthy); uptime bars via the real endpoints: 24 hourly + 30 daily buckets, pure-failure bucket red `#EF4444`, pure-success green `#22C55E` (avg latency correct), mixed bucket maroon `#800000`, no-data gray `#D4D4D4`; frontend production build green (now 27 routes + Proxy), status page renders the bars + legend + colors, detail page renders the 30-day panel, BFF devices routes (register/list/unsubscribe/422/401), dashboards surface the subscription panel with the "required for staff" notice for operators and the optional variant for subscribers. Default `down` threshold observed as 3 consecutive failures (Task 4's suite had configured 2 explicitly).

Next: the lint follow-up (restructure the panels' initial fetch or scope-disable `set-state-in-effect`), then optional backend bits (acknowledged/note webhook events, `OptionalUser` wiring).

## Task 6 — Native notification permission flow (pending)

Problem (user report): clicking **Subscribe this device** answered with the generic "Notification permission was not granted — subscriptions need it to deliver pushes." Diagnosis: browsers resolve `requestPermission()` instantly with `denied` or `default` when the site is hard-blocked or the prompt is silenced (Chrome/Edge "quieter permission UI" shows a bell icon instead of the prompt) — in those states no prompt is displayed at all, and the old code answered every outcome with one misleading message.

Implemented so far in `components/notification-setup.tsx`:

- `askNotificationPermission()` — a single JS call covering both the promise form and Safari's legacy callback form (no double prompt), invoked directly in the click handler so the browser treats it as a user gesture.
- Outcome-specific handling: already `granted` → skip the ask and go straight to service worker registration → FCM `getToken` → `POST /api/devices`; `denied` → guidance to re-enable notifications in the browser's site settings (a blocked site is never re-prompted by the browser); `default` (dismissed or silenced) → guidance pointing at the bell icon in the address bar and to click Subscribe again. The browser's live `Notification.permission` is re-read after the ask and trusted over the resolved value (some browsers resolve `default` even after the user answers).
- Firebase `getToken` rejections wrapped in a clearer message (the raw SDK wording, e.g. "Registration failed - permission denied" while the header showed "permission granted", is replaced by an explanation that incognito windows and some managed browsers block push entirely).

Verified in a real (embedded) browser: the blocked-site guidance path, the granted path reaching the FCM token step, no console errors; production build green. The embedded test browser runs incognito (Chrome disables the Push API there) and denies notifications at profile level, so a true end-to-end granted flow (prompt → Allow → token stored → device row) could not be completed in it.

Pending:

- User-side confirmation: the prompt still resolves `default` in the user's browser (now answered with the silenced/dismissed guidance). Most likely cause: the site was hard-blocked by an earlier denial — resetting it in site settings restores the ask-on-click behavior; then one Subscribe click should show the native prompt and complete the flow (token saved, device row appears).
- If quiet-prompting persists on the user's browser, add an in-page pre-prompt explanation (e.g. "you will be asked to allow notifications") before the ask, a known mitigation for silenced prompts.

Next: resolve the pending user-side confirmation; on success, record the full granted-path verification and close out Task 6.

## Task 7 — Replace Firebase notifications with email (SMTP) (done)

Firebase Cloud Messaging is **removed from the frontend only** and replaced by an email notification system backed by the user's Gmail account via a Google **App Password**. The backend FCM machinery (`core/fcm.py`, `routers/devices.py`, `device_tokens`) stays in place but dormant — nothing calls it from the UI and pushes only happen when a service account is configured.

### Backend

- Config (`core/config.py`): `PULSE_SMTP_HOST` (default `smtp.gmail.com`), `PULSE_SMTP_PORT` (587, STARTTLS), `PULSE_SMTP_USER` (Gmail address to send from), `PULSE_SMTP_PASSWORD` (the 16-character **App Password** — not the account password), `PULSE_SMTP_FROM` (defaults to the user), `PULSE_PUBLIC_URL` (for status-page links inside emails). Without user+password the mailer is disabled and subscriptions still work (same graceful stance as webhook/FCM).
- New collection `email_subscriptions` (`schemas/email_subscription.py`): one document per subscribed account — `subscription_id`, `uid`, `email` (the **account's own email**, enforced server-side), plus per-address delivery stats (`send_count`, `fail_count`, `last_sent_at`, `last_error`). Indexes: unique `uid`, unique `email`. Stored separately from the FCM `device_tokens` as requested.
- New router (`routers/email_subscriptions.py`, wired in `main.py`): `POST /email-subscriptions` subscribes the caller's account email (idempotent: 201 created / 200 already-subscribed; the request body is ignored — the address always comes from the authenticated user, so third parties can't be signed up), `GET /email-subscriptions` returns the caller's subscription or `null`, `DELETE /email-subscriptions` unsubscribes (404 when not subscribed).
- Mailer (`core/mailer.py`): `smtplib` + `EmailMessage` over STARTTLS; one SMTP connection per fan-out, **one individual email per subscribed active account** (recipients never see each other). Subject `[Pulse] <service> is <state>`, body with the `old -> new` transition, incident notice when one opened, and a link to the public status page (`{PUBLIC_URL}/status/{slug}`). Per-address outcomes update the subscription stats; connection/login-level failures record on every subscriber. Runs as a fire-and-forget task drained by the sweep/shutdown (never breaks monitoring).
- `core/health_check.py`: on every state change the fan-out now does webhook + (dormant) FCM + **email**.
- `GET /dashboard` now returns `email_notifications` for every role: `subscribed`, `email`, `notifications_required` (true for operators/admins who are not subscribed — the Task 5 staff-mandatory rule carried over to email).

### Frontend

- New panel `components/email-notifications.tsx` ("Subscribe by email" / Unsubscribe, address shown from the dashboard payload, send/fail stats displayed): no permission prompts, no service workers, no tokens — subscription is one click that stores the account email server-side. Mounted on all three dashboards (`required` for staff via `dashboard.email_notifications`).
- BFF route `app/api/email-subscriptions` (GET/POST/DELETE proxy with Zod validation).
- **Firebase removed visually**: `notification-setup.tsx`, `lib/firebase.ts`, `public/firebase-messaging-sw.js`, `app/api/devices[/tokenId]`, the `firebase` npm dependency and all `NEXT_PUBLIC_FIREBASE_*` env keys (.env.local reset to BACKEND_URL only; `.env.example` documents the backend SMTP setup instead). Zod device schemas dropped; `DashboardSchema` gained required `email_notifications` and lost `devices`.
- Lint hygiene: removed the now-unused `redirect`/`UserResponseSchema` imports (leftovers from the Task 4 AccessPanel swap) — `npm run lint` is back to only the 4 pre-existing `set-state-in-effect` panel errors.

### Verification & manual testing

Verified so far over HTTP: subscription API (account-email subscription, idempotent re-subscribe, status endpoint, anonymous 401), staff `notifications_required` flag before/after subscribing, dashboard payload wiring, frontend production build green with Firebase fully absent. The SMTP fan-out fired on a real CRON state change and correctly recorded per-address failures when the test SMTP sink was unreachable (`fail_count` + `last_error`), and subscribed/unsubscribed addressing logic is exercised by the wave design. Automated end-to-end delivery verification was **stopped early at the user's request** (test-script bugs produced false failures; the local SMTP sink was flaky under `Start-Process`), so real delivery is to be confirmed manually.

Manual test with a real Gmail App Password (backend env, then restart uvicorn):

```
PULSE_SMTP_USER=<gmail address>
PULSE_SMTP_PASSWORD=<16-char App Password>   # Google Account → Security → 2-Step Verification → App passwords
# PULSE_SMTP_HOST / PULSE_SMTP_PORT default to smtp.gmail.com / 587
# PULSE_SMTP_FROM defaults to PULSE_SMTP_USER; PULSE_PUBLIC_URL defaults to http://localhost:3000
```

Then: sign in on the dashboard → Subscribe by email → flip a service's state (e.g. point its health_url at a dead port, wait for the down transition) → each subscribed account should receive one individual email from the Gmail address.

Next: user's manual mail-delivery test with real credentials; then the lint follow-up (restructure the panels' initial fetch or scope-disable `set-state-in-effect`) and optional backend bits (acknowledged/note webhook events, `OptionalUser` wiring).

## Task 8 — Automated CRON trigger for status mails (done)

The Task 7 fan-out fired inside the check task — a restart or an SMTP hiccup at that moment silently lost the notification. The automated trigger is now a **durable outbox pipeline** end to end inside the CRON:

```
health check (CRON sweep) ──▶ enqueue mail_outbox row (fast insert, never fails the check)
                                       │
mail dispatch (CRON job, every sweep) ─┘ delivers due rows → SMTP fan-out
                                failure → retry with backoff (5 attempts, 60s × attempt)
                                exhausted → status "failed" (kept, with last_error)
                                no audience at send time → "skipped"
```

- `schemas/mail_outbox.py` — `MailOutboxDocument` (`mail_id`, service id/name/slug, old/new state, incident id) with lifecycle `pending → sent | failed | skipped` and `attempts`/`next_attempt_at` for the retry schedule. Indexes: `(status, next_attempt_at)` for the dispatcher query, `created_at` for FIFO.
- `core/mailer.py` — `enqueue_state_change()` (called in the check path; a single fast insert) and `process_outbox()` (the dispatcher: picks due pending rows oldest-first, fans each out through the Task 7 sender, classifies the outcome — `sent` when any recipient got mail, `skipped` when there was no audience, retry with backoff otherwise; `last_error` recorded on every attempt). When SMTP is unconfigured the dispatcher is a no-op and rows simply wait — deliveries start automatically once credentials are set.
- `core/health_check.py` — `_mail_state_change` now enqueues instead of firing a background task (the fire-and-forget `_pending_mail` set is gone; webhook + FCM fan-outs unchanged).
- `core/scheduler.py` — second APScheduler job `mail-dispatch` alongside `health-sweep` (same 10s cadence, `max_instances=1`, `coalesce`), so delivery latency is at most one sweep and retries happen automatically.
- `main.py` — startup flush: `process_outbox()` runs once at boot so anything queued while the process was down goes out immediately.
- Frontend: the subscribed panel gained a "Refresh delivery stats" button (GET `/api/email-subscriptions`) so per-address `send_count`/`last_error` can be watched during manual testing.

Verification: import + scheduler wiring (both jobs registered), and a logic self-check of the outbox state machine against a scratch DB with the sender stubbed — enqueue → dispatch (sent/partial-sent/skipped/retry classifications correct, `next_attempt_at` backed off, retry blocked until due, budget exhaustion marks `failed` with attempts == 5), dispatcher idle when the mailer is disabled (rows stay `pending`). Automated end-to-end SMTP delivery remains with the user's manual test (per the Task 7 arrangement — real Gmail App Password credentials are needed); note the last frontend production build was interrupted, so run `npm run build` before `next start` if serving the production bundle.

Next: user's manual mail-delivery test with real credentials; then the lint follow-up (restructure the panels' initial fetch or scope-disable `set-state-in-effect`) and optional backend bits (acknowledged/note webhook events, `OptionalUser` wiring).
