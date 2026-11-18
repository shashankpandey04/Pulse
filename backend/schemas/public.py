"""Public status page schemas — the anonymous, customer-facing view.

Everything here is sanitized: internal timeline events (``visibility="internal"``)
are filtered out, owner emails and other operational details are never included.
The state colors come from ``schemas.state.STATE_COLORS``.

Routes (``routers/public.py``):
    GET /public/status            -> PublicStatusResponse   (no auth)
    GET /public/status/{slug}     -> PublicServiceDetail    (no auth)
"""

from datetime import datetime

from pydantic import BaseModel, Field


class PublicStatusEvent(BaseModel):
    """A public timeline event rendered on the status page."""

    type: str = Field(description="Event type (opened/state_changed/acknowledged/note/resolved).")
    message: str
    at: datetime


class PublicIncident(BaseModel):
    """An incident as shown on the public status page (public events only)."""

    incident_id: str
    title: str
    status: str
    current_state: str
    opened_at: datetime
    resolved_at: datetime | None = None
    duration_seconds: float | None = None
    events: list[PublicStatusEvent] = Field(
        description="Chronological public events only; internal notes are excluded.",
    )


class PublicServiceStatus(BaseModel):
    """A service as shown on the status page list."""

    service_id: str
    name: str
    slug: str
    description: str | None = None
    state: str = Field(description="Current health state (healthy/down/slow/flaky).")
    color: str = Field(description="Hex color for the state badge.")
    last_check_at: datetime | None = None
    last_latency_ms: int | None = None


class PublicStatusResponse(BaseModel):
    """``GET /public/status`` — the whole status page in one payload."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "generated_at": "2026-11-18T10:00:00Z",
                    "summary": {"healthy": 4, "down": 1, "slow": 0, "flaky": 0},
                    "colors": {"healthy": "#22C55E", "down": "#EF4444", "slow": "#EAB308", "flaky": "#800000"},
                    "services": [],
                    "active_incidents": [],
                }
            ]
        }
    }

    generated_at: datetime
    summary: dict[str, int] = Field(description="Count of services per state.")
    colors: dict[str, str] = Field(description="Color codes for the four states.")
    services: list[PublicServiceStatus] = Field(description="All enabled services.")
    active_incidents: list[PublicIncident] = Field(description="Open/acknowledged incidents, newest first.")


class PublicServiceDetail(BaseModel):
    """``GET /public/status/{slug}`` — one service with its incident history."""

    service: PublicServiceStatus
    incidents: list[PublicIncident] = Field(description="Recent incidents (public events only), newest first.")
