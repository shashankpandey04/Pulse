"""Service State schemas: per-service state thresholds + API req/res models.

Operators/admins decide *when* a service is considered healthy, down, slow
(degraded) or flaky, and *when it has recovered*. Those decisions are stored as
thresholds per service; the monitor applies them to every check.

The four built-in states and their color codes:

    ====================  ======================================================  =========  =========
    State                 Meaning                                                 Color      Hex
    ====================  ======================================================  =========  =========
    healthy               normal operation — the default when nothing trips       green      #22C55E
    down                  ``consecutive_failures`` failed/no-response checks      red        #EF4444
    slow                  responses slower than ``latency_ms``                    yellow     #EAB308
    flaky                 failure rate over the window exceeds ``failure_rate``   maroon     #800000
    ====================  ======================================================  =========  =========

Recovery: after ``recovery.consecutive_successes`` consecutive successful checks
the service is healthy again.

Database: ``service_states`` collection
    - unique index on ``service_id`` (exactly one configuration per service)
    - this collection stores the *configuration* (thresholds); the live/computed
      state of a service is produced by the monitor and will be tracked with
      incidents in a later task

API routes (wired up in Task 2, in ``routers/state.py``):
    PUT    /states/{service_id}     StateConfigUpsertRequest  -> StateConfigResponse     admin, operator
        * creates or fully replaces the configuration (defaults for omitted
          policies); 404 when the service is not in the catalogue
    PATCH  /states/{service_id}     StateConfigUpdateRequest  -> StateConfigResponse     admin, operator
        * replaces only the provided policies
    GET    /states/{service_id}     -                         -> StateConfigResponse     admin, operator
        * returns the effective configuration (defaults when none is stored)
    GET    /states                  page, page_size (query)   -> StateConfigListResponse admin, operator
    DELETE /states/{service_id}     -                         -> MessageResponse         admin
        * removes the stored configuration, resetting the service to defaults
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import TimestampedModel, new_uid

COLLECTION_SERVICE_STATES = "service_states"
"""MongoDB collection that stores ``ServiceStateDocument`` records."""

HealthState = Literal["healthy", "down", "slow", "flaky"]
"""The state a service can currently be in (computed by the monitor)."""

STATE_COLORS: dict[str, str] = {
    "healthy": "#22C55E",  # green
    "down": "#EF4444",     # red
    "slow": "#EAB308",     # yellow
    "flaky": "#800000",    # maroon
}
"""Color code for every built-in state (Tailwind-friendly greens/reds/yellows)."""


# ---------------------------------------------------------------------------
# Threshold policies
# ---------------------------------------------------------------------------


class DownPolicy(BaseModel):
    """When a service is considered **down** (red)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"consecutive_failures": 3}]},
    )

    consecutive_failures: int = Field(
        default=3,
        ge=1,
        le=1000,
        description="Mark the service Down after this many consecutive failed (no-response) checks.",
    )


class SlowPolicy(BaseModel):
    """When a service is considered **slow / degraded** (yellow)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"latency_ms": 2000}]},
    )

    latency_ms: int = Field(
        default=2000,
        ge=1,
        le=600_000,
        description="A response slower than this many milliseconds counts as Slow; at or under it is acceptable.",
    )


class FlakyPolicy(BaseModel):
    """When a service is considered **flaky** (maroon).

    ``failure_rate`` is the maximum acceptable failure rate, e.g. ``0.3`` means
    30% — anything above it over the recent-check window marks the service flaky.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"failure_rate": 0.3, "window_size": 10}]},
    )

    failure_rate: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable failure rate (0.3 = 30%). Above it the service is Flaky.",
    )
    window_size: int = Field(
        default=10,
        ge=2,
        le=1000,
        description="Number of most-recent checks the failure rate is computed over.",
    )


class RecoveryPolicy(BaseModel):
    """When a service **has recovered** — back to healthy (green)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"consecutive_successes": 2}]},
    )

    consecutive_successes: int = Field(
        default=2,
        ge=1,
        le=1000,
        description="Mark the service Healthy again after this many consecutive successful checks.",
    )


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class ServiceStateDocument(TimestampedModel):
    """State thresholds for one service — document in ``service_states``.

    Keyed by ``service_id`` (unique): one configuration per catalogue service.
    Mongo adds its own ``_id`` (ObjectId) on insert; the models leave it out.
    """

    state_id: str = Field(
        default_factory=new_uid,
        description="System generated unique id of this configuration.",
    )
    service_id: str = Field(
        description="``service_id`` of the catalogue service this configuration belongs to (unique).",
    )
    down: DownPolicy = Field(default_factory=DownPolicy)
    slow: SlowPolicy = Field(default_factory=SlowPolicy)
    flaky: FlakyPolicy = Field(default_factory=FlakyPolicy)
    recovery: RecoveryPolicy = Field(default_factory=RecoveryPolicy)


# ---------------------------------------------------------------------------
# API requests
# ---------------------------------------------------------------------------


class StateConfigUpsertRequest(BaseModel):
    """``PUT /states/{service_id}`` — create or fully replace the configuration.

    ``service_id`` comes from the path. Omitted policies fall back to their
    defaults, so ``{}`` provisions the default configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "down": {"consecutive_failures": 5},
                    "slow": {"latency_ms": 3000},
                    "flaky": {"failure_rate": 0.2, "window_size": 20},
                    "recovery": {"consecutive_successes": 3},
                }
            ]
        },
    )

    down: DownPolicy = Field(default_factory=DownPolicy)
    slow: SlowPolicy = Field(default_factory=SlowPolicy)
    flaky: FlakyPolicy = Field(default_factory=FlakyPolicy)
    recovery: RecoveryPolicy = Field(default_factory=RecoveryPolicy)


class StateConfigUpdateRequest(BaseModel):
    """``PATCH /states/{service_id}`` — replace only the provided policies."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"down": {"consecutive_failures": 10}},
            ]
        },
    )

    down: DownPolicy | None = Field(default=None, description="Omitted policies keep their current value.")
    slow: SlowPolicy | None = None
    flaky: FlakyPolicy | None = None
    recovery: RecoveryPolicy | None = None


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class StateConfigResponse(BaseModel):
    """Effective state configuration of a service, including the color codes.

    ``colors`` is informational and identical on every response — it lets the
    frontend render state badges without hardcoding the palette.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "state_id": "b2a4c6e8-1d3f-4a5b-8c9d-0e1f2a3b4c5d",
                    "service_id": "8c1e7a2b-4d3f-4a5b-9c6d-1e2f3a4b5c6d",
                    "down": {"consecutive_failures": 3},
                    "slow": {"latency_ms": 2000},
                    "flaky": {"failure_rate": 0.3, "window_size": 10},
                    "recovery": {"consecutive_successes": 2},
                    "colors": {"healthy": "#22C55E", "down": "#EF4444", "slow": "#EAB308", "flaky": "#800000"},
                    "created_at": "2026-11-18T09:00:00Z",
                    "updated_at": "2026-11-18T09:00:00Z",
                }
            ]
        },
    )

    state_id: str = Field(description="System generated unique id of this configuration.")
    service_id: str
    down: DownPolicy
    slow: SlowPolicy
    flaky: FlakyPolicy
    recovery: RecoveryPolicy
    colors: dict[str, str] = Field(
        default_factory=lambda: dict(STATE_COLORS),
        description="Color codes for the four states (healthy green, down red, slow yellow, flaky maroon).",
    )
    created_at: datetime
    updated_at: datetime


class StateConfigListResponse(BaseModel):
    """Response of ``GET /states`` — paginated list of configurations."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 7,
                    "page": 1,
                    "page_size": 20,
                    "states": [],
                }
            ]
        },
    )

    total: int = Field(description="Total number of configurations matching the query.")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of configurations per page.")
    states: list[StateConfigResponse] = Field(description="Configurations on this page.")
