"""Metrics schemas: raw check results + how quickly problems are detected/resolved.

The CRON stores **every** check result here — successes and failures — which is
the substrate for metrics (detection/resolution speed) and reliability reports.

Database: ``check_results`` collection
    - index ``(service_id, checked_at desc)`` for per-service history
    - TTL-friendly: old results can be pruned later (a separate concern)
    - this collection is append-only; the API never writes it directly

Planned routes (``routers/metrics.py``, later task):
    GET    /metrics                    MetricsOverviewResponse   admin, operator
    GET    /metrics/{service_id}       ServiceMetricsResponse    admin, operator
    GET    /metrics/{service_id}/checks CheckResultListResponse  admin, operator
"""

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.state import HealthState

from .common import TimestampedModel, new_uid

COLLECTION_CHECK_RESULTS = "check_results"
"""MongoDB collection that stores ``CheckResultDocument`` records."""


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class CheckResultDocument(TimestampedModel):
    """The outcome of one health check — document in ``check_results``."""

    check_id: str = Field(default_factory=new_uid)
    service_id: str = Field(description="Catalogue service that was checked.")
    checked_at: datetime = Field(description="When the check ran (UTC).")
    success: bool = Field(description="True when the endpoint returned a 2xx in time.")
    state: HealthState = Field(description="Health state assigned to this check after evaluation.")
    status_code: int | None = Field(default=None, description="HTTP status code; None on transport errors.")
    latency_ms: int | None = Field(default=None, description="Round-trip duration; None when the request never completed.")
    error: str | None = Field(default=None, description="Transport/timeout error message, when failed.")
    timed_out: bool = Field(default=False, description="True when the request exceeded ``timeout_seconds``.")


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class CheckResultResponse(BaseModel):
    """One stored check."""

    check_id: str
    service_id: str
    checked_at: datetime
    success: bool
    state: HealthState
    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    timed_out: bool = False


class CheckResultListResponse(BaseModel):
    """Paginated raw check history for a service."""

    total: int
    page: int
    page_size: int
    checks: list[CheckResultResponse]


class ServiceMetricsResponse(BaseModel):
    """How quickly problems are detected/resolved and how checking performs."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "service_id": "8c1e7a2b-4d3f-4a5b-9c6d-1e2f3a4b5c6d",
                    "service_name": "Checkout API",
                    "window_hours": 24,
                    "total_checks": 1440,
                    "failed_checks": 9,
                    "success_rate": 0.9938,
                    "avg_latency_ms": 187,
                    "p95_latency_ms": 420,
                    "mttd_seconds": 95.0,
                    "mttr_seconds": 612.0,
                    "open_incidents": 0,
                    "last_check_at": "2026-11-18T10:00:00Z",
                    "last_state": "healthy",
                }
            ]
        }
    }

    service_id: str
    service_name: str
    window_hours: int = Field(description="Lookback window the metrics were computed over.")
    total_checks: int
    failed_checks: int
    success_rate: float = Field(description="successful checks / total checks, in [0, 1].")
    avg_latency_ms: float | None = Field(default=None, description="Mean latency of completed checks.")
    p95_latency_ms: float | None = Field(default=None, description="95th-percentile latency of completed checks.")
    mttd_seconds: float | None = Field(
        default=None,
        description="Mean time to detect: opened_at minus the first failed check for resolved incidents.",
    )
    mttr_seconds: float | None = Field(
        default=None,
        description="Mean time to resolve: duration_seconds averaged over resolved incidents.",
    )
    open_incidents: int
    last_check_at: datetime | None = None
    last_state: HealthState | None = None


class MetricsOverviewResponse(BaseModel):
    """All services' metrics in one payload."""

    window_hours: int
    services: list[ServiceMetricsResponse]
