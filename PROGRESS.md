# Pulse — Progress

## Task 1 — Schema design (done)

Created `backend/schemas/` (Pydantic v2, for FastAPI + MongoDB/pymongo + bcrypt):

- `common.py` — shared helpers (`utcnow`, `new_uid` uuid4, `TimestampedModel`) and generic responses (`MessageResponse`, `ErrorResponse`).
- `auth.py` — `UserDocument` (`users` collection: uid, email, hashed_password bcrypt, pfp_link, role, active, timestamps) + `RegisterRequest`, `LoginRequest`, `AuthResponse` (bearer token + user), `UserResponse`, `AdminUserUpdateRequest` (admin role/active changes), `UserListResponse`. New accounts are always `subscriber`; role is stored as a plain string literal of `admin | operator | subscriber`; password capped at 72 bytes (bcrypt limit).
- `catalogue.py` — `ServiceDocument` (`services` collection: service_id, name, unique slug, description, health_url, check_interval_seconds, timeout_seconds, owner_uid + owner_email, reliability_target %, enabled) + `ServiceCreateRequest`, `ServiceUpdateRequest` (partial), `ServiceResponse`, `ServiceListResponse`. Validator: `timeout_seconds` must be smaller than `check_interval_seconds`.
- `state.py` — `ServiceStateDocument` (`service_states` collection, one config per service keyed by unique `service_id`) with `DownPolicy` (consecutive no-responses, default 3), `SlowPolicy` (latency_ms, default 2000), `FlakyPolicy` (failure_rate 0..1, default 0.3 = 30%, over a `window_size` window, default 10) and `RecoveryPolicy` (consecutive successes, default 2) + upsert/update/list/response schemas. Colors: healthy `#22C55E` green, down `#EF4444` red, slow `#EAB308` yellow, flaky `#800000` maroon (`STATE_COLORS`).
- `README.md` — collection/index plan, full API route table (who can call what), role rules, state threshold/color table, Mongo implementation notes (`model_dump(mode="json")`, `tz_aware=True`, bcrypt hash/verify).

Validation: throwaway script exercised all 21 models — 33 checks passed (valid payloads, defaults, and rejection of bad emails/short passwords/role smuggling on register/out-of-range flaky rate/timeout >= interval/extra fields).

Next: Task 2 — DB client + routers (auth with bcrypt, catalogue, states) and wiring into a FastAPI app.
