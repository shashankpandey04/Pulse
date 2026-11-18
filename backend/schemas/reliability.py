"""Reliability schemas: each service's availability over time against its target.

Availability is computed from stored check results (``check_results``); the
target comes from the catalogue (``reliability_target``). The report also shows
the error budget — how much failure the service is still allowed before it
breaches its target.

Database: none of its own — reports are computed on read from
``check_results`` + ``incidents`` + ``services``.

Planned routes (``routers/reliability.py``, later task):
    GET    /reliability                   ReliabilityListResponse   admin, operator
    GET    /reliability/{service_id}      ReliabilityResponse       admin, operator
"""

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.state import HealthState


class ReliabilityResponse(BaseModel):
    """Availability over a lookback window, judged against the target."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "service_id": "8c1e7a2b-4d3f-4a5b-9c6d-1e2f3a4b5c6d",
                    "service_name": "Checkout API",
                    "window_days": 30,
                    "target_pct": 99.9,
                    "availability_pct": 99.86,
                    "meeting_target": False,
                    "error_budget_pct": 0.1,
                    "error_budget_remaining_pct": 60.0,
                    "allowed_downtime_minutes": 43.2,
                    "consumed_downtime_minutes": 17.3,
                    "total_checks": 43200,
                    "failed_checks": 6,
                    "incident_count": 1,
                    "last_state": "healthy",
                    "computed_at": "2026-11-18T10:00:00Z",
                }
            ]
        }
    }

    service_id: str
    service_name: str
    window_days: int = Field(description="Lookback window in days.")
    target_pct: float = Field(description="Reliability target from the catalogue (e.g. 99.9).")
    availability_pct: float = Field(description="Measured availability percentage over the window.")
    meeting_target: bool = Field(description="True when availability_pct >= target_pct.")
    error_budget_pct: float = Field(description="Allowed failure percentage: 100 - target (e.g. 0.1).")
    error_budget_remaining_pct: float = Field(
        description="Share of the error budget still unspent (0-100); negative means the budget is blown.",
    )
    allowed_downtime_minutes: float = Field(description="Total budget expressed as downtime minutes over the window.")
    consumed_downtime_minutes: float = Field(description="Downtime actually consumed over the window.")
    total_checks: int
    failed_checks: int
    incident_count: int = Field(description="Incidents opened during the window.")
    last_state: HealthState | None = None
    computed_at: datetime


class ReliabilityListResponse(BaseModel):
    """All services' reliability reports in one payload."""

    window_days: int
    services: list[ReliabilityResponse]
