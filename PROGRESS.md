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

Next: frontend development (login/register, operator/admin dashboards, status page) with small backend additions as needed.
