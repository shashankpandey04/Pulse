# Pulse — Backend Schemas (Task 1)

Pydantic v2 models for the three domains designed in Task 1: **Auth**, **Service
Catalogue** and **Service States**. Each module holds the database document
(what is stored in MongoDB) plus the API request/response models (what crosses
the HTTP boundary). Response models never contain secrets (e.g. password hashes).

## Collections & indexes

| Collection        | Document                | Module       | Indexes                                   |
| ----------------- | ----------------------- | ------------ | ----------------------------------------- |
| `users`           | `UserDocument`          | `auth.py`    | `email` (unique)                          |
| `services`        | `ServiceDocument`       | `catalogue.py` | `service_id`, `slug`, `name` (all unique) |
| `service_states`  | `ServiceStateDocument`  | `state.py`   | `service_id` (unique — one config per service) |

Every record also carries an app-level id (`uid`, `service_id`, `state_id`,
uuid4) as its public identifier; Mongo's `_id` (ObjectId) stays internal.

## API surface (routes are wired in Task 2)

| Domain     | Route                       | Request                 | Response                  | Who            |
| ---------- | --------------------------- | ----------------------- | ------------------------- | -------------- |
| Auth       | `POST /auth/register`       | `RegisterRequest`       | `AuthResponse`            | public         |
| Auth       | `POST /auth/login`          | `LoginRequest`          | `AuthResponse`            | public         |
| Auth       | `GET /auth/me`              | —                       | `UserResponse`            | signed-in      |
| Auth       | `GET /admin/users`          | page/page_size (query)  | `UserListResponse`        | admin          |
| Auth       | `PATCH /admin/users/{uid}`  | `AdminUserUpdateRequest`| `UserResponse`            | admin          |
| Auth       | `DELETE /admin/users/{uid}` | —                       | `MessageResponse`         | admin (soft)   |
| Catalogue  | `POST /catalogue`           | `ServiceCreateRequest`  | `ServiceResponse`         | admin          |
| Catalogue  | `GET /catalogue`            | page/page_size (query)  | `ServiceListResponse`     | admin, operator|
| Catalogue  | `GET /catalogue/{id}`       | —                       | `ServiceResponse`         | admin, operator|
| Catalogue  | `PATCH /catalogue/{id}`     | `ServiceUpdateRequest`  | `ServiceResponse`         | admin          |
| Catalogue  | `DELETE /catalogue/{id}`    | —                       | `MessageResponse`         | admin          |
| States     | `PUT /states/{service_id}`  | `StateConfigUpsertRequest`  | `StateConfigResponse` | admin, operator|
| States     | `PATCH /states/{service_id}`| `StateConfigUpdateRequest`  | `StateConfigResponse` | admin, operator|
| States     | `GET /states/{service_id}`  | —                       | `StateConfigResponse`     | admin, operator|
| States     | `GET /states`               | page/page_size (query)  | `StateConfigListResponse` | admin, operator|
| States     | `DELETE /states/{service_id}`| —                      | `MessageResponse`         | admin          |

Errors use FastAPI's `HTTPException` shape (see `common.ErrorResponse`).

## Role rules

- New accounts are **always** `subscriber` with `active=True`; `RegisterRequest`
  deliberately has no `role` field.
- Only admins change `role` / `active` via `PATCH /admin/users/{uid}`.
- Operators write incidents and read metrics/reliability; subscribers get the
  public status page.

## Service states (thresholds per service)

| State     | Color   | Hex       | Trigger                                                       |
| --------- | ------- | --------- | ------------------------------------------------------------- |
| `healthy` | green   | `#22C55E` | default — nothing trips and recovery conditions are met        |
| `down`    | red     | `#EF4444` | `down.consecutive_failures` consecutive failed checks          |
| `slow`    | yellow  | `#EAB308` | responses slower than `slow.latency_ms`                        |
| `flaky`   | maroon  | `#800000` | failure rate over `flaky.window_size` checks exceeds `flaky.failure_rate` (e.g. `0.3` = 30%) |
| recovery  | green   | —         | `recovery.consecutive_successes` consecutive successful checks |

Notes for implementation (Task 2):

- Dump documents with `model_dump(mode="json")` before `insert_one` so
  `HttpUrl`/`EmailStr`/`datetime` serialize for Mongo; connect the client with
  `tz_aware=True`.
- Store passwords with `bcrypt.hashpw(...)` and verify with `bcrypt.checkpw(...)`.
  `RegisterRequest.password` is capped at 72 bytes because bcrypt only reads the
  first 72 bytes.
- Creating a service should provision a default `ServiceStateDocument` for it.
