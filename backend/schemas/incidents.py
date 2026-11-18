"""Incident schemas: database document + API request/response models.

The health-check CRON opens an incident automatically when a service goes down
and closes it when it recovers. Operators can acknowledge incidents and add
notes; every action lands on the incident's embedded timeline. Notes default to
``public`` — public notes are visible on the public status page.

Database: ``incidents`` collection
    - unique partial index: one *open* incident per service
      ``{service_id: 1, status: 1}, unique=True, partialFilterExpression={"status": {"$in": ["open", "acknowledged"]}}``
    - ``timeline`` is embedded (bounded: an incident's history is small)
    - only the CRON creates/resolves incidents automatically; acknowledging and
      notes are operator/admin actions (routers in a later task)

Planned routes (``routers/incidents.py``, later task):
    GET    /incidents                         IncidentListResponse   admin, operator
    GET    /incidents/{incident_id}           IncidentResponse       admin, operator
    PATCH  /incidents/{incident_id}/ack       AcknowledgeRequest     admin, operator
    POST   /incidents/{incident_id}/notes     IncidentNoteRequest    admin, operator
    POST   /incidents/{incident_id}/resolve   IncidentResolveRequest admin, operator
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.state import HealthState

from .common import TimestampedModel, new_uid

COLLECTION_INCIDENTS = "incidents"
"""MongoDB collection that stores ``IncidentDocument`` records."""

IncidentStatus = Literal["open", "acknowledged", "resolved"]
"""Lifecycle: open -> acknowledged -> resolved (CRON resolves on recovery)."""

TimelineEventType = Literal["opened", "state_changed", "acknowledged", "note", "resolved"]
Visibility = Literal["public", "internal"]


# ---------------------------------------------------------------------------
# Database documents
# ---------------------------------------------------------------------------


class TimelineEvent(BaseModel):
    """One entry on an incident's timeline (embedded in the incident)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "event_id": "e-8f1a2b3c",
                    "type": "note",
                    "message": "Rolling restart in progress.",
                    "at": "2026-11-18T09:12:30Z",
                    "by_uid": "3f9d2f4e-6a1b-4c7e-9f0a-2b3c4d5e6f70",
                    "by_email": "op@example.com",
                    "visibility": "public",
                }
            ]
        },
    )

    event_id: str = Field(default_factory=new_uid)
    type: TimelineEventType
    message: str = Field(description="What happened; note events render on the status page when public.")
    at: datetime = Field(description="When the event happened (UTC).")
    by_uid: str | None = Field(default=None, description="Acting account (None for CRON-created events).")
    by_email: str | None = None
    visibility: Visibility = Field(
        default="public",
        description="``public`` events (notes) also appear on the public status page.",
    )


class IncidentDocument(TimestampedModel):
    """An incident — document in the ``incidents`` collection."""

    incident_id: str = Field(
        default_factory=new_uid,
        description="System generated unique incident id.",
    )
    service_id: str = Field(description="Catalogue service this incident belongs to.")
    service_name: str = Field(description="Denormalized for display on the status page.")
    title: str = Field(description="Human summary, e.g. ``Checkout API is down``.")
    status: IncidentStatus = Field(
        default="open",
        description="open -> acknowledged -> resolved.",
    )
    current_state: HealthState = Field(
        default="down",
        description="Health state that triggered the incident (down or flaky).",
    )
    opened_at: datetime = Field(description="When the CRON opened the incident.")
    opened_reason: str = Field(description="Why the incident was opened, e.g. ``3 consecutive failed checks``.")
    acknowledged_by_uid: str | None = Field(default=None)
    acknowledged_by_email: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = Field(default=None, description="Set when the service recovered.")
    resolved_reason: str | None = None
    duration_seconds: float | None = Field(
        default=None,
        description="resolved_at - opened_at; None until resolved.",
    )
    timeline: list[TimelineEvent] = Field(
        default_factory=list,
        description="Chronological events; first entry is the automatic 'opened' event.",
    )


# ---------------------------------------------------------------------------
# API requests (routes wired in a later task)
# ---------------------------------------------------------------------------


class AcknowledgeRequest(BaseModel):
    """``PATCH /incidents/{incident_id}/ack`` — an operator claims an incident."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500, description="Optional public note added when acknowledging.")


class IncidentNoteRequest(BaseModel):
    """``POST /incidents/{incident_id}/notes`` — add a note to the timeline.

    Notes are public by default; ``visibility="internal"`` keeps them off the
    public status page.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"note": "We are investigating.", "visibility": "public"}]},
    )

    note: str = Field(min_length=1, max_length=2000)
    visibility: Visibility = Field(default="public", description="public (default) or internal.")


class IncidentResolveRequest(BaseModel):
    """``POST /incidents/{incident_id}/resolve`` — close the incident manually."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: str | None = Field(default=None, max_length=2000, description="Optional public resolution note.")


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class IncidentResponse(BaseModel):
    """An incident with its full timeline."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "incident_id": "d4e5f6a7-8b9c-4d0e-9f1a-2b3c4d5e6f70",
                    "service_id": "8c1e7a2b-4d3f-4a5b-9c6d-1e2f3a4b5c6d",
                    "service_name": "Checkout API",
                    "title": "Checkout API is down",
                    "status": "acknowledged",
                    "current_state": "down",
                    "opened_at": "2026-11-18T09:05:00Z",
                    "opened_reason": "3 consecutive failed checks",
                    "acknowledged_by_uid": "3f9d2f4e-6a1b-4c7e-9f0a-2b3c4d5e6f70",
                    "acknowledged_by_email": "op@example.com",
                    "acknowledged_at": "2026-11-18T09:07:00Z",
                    "resolved_at": None,
                    "resolved_reason": None,
                    "duration_seconds": None,
                    "timeline": [],
                    "created_at": "2026-11-18T09:05:00Z",
                    "updated_at": "2026-11-18T09:07:00Z",
                }
            ]
        },
    )

    incident_id: str
    service_id: str
    service_name: str
    title: str
    status: IncidentStatus
    current_state: HealthState
    opened_at: datetime
    opened_reason: str
    acknowledged_by_uid: str | None = None
    acknowledged_by_email: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_reason: str | None = None
    duration_seconds: float | None = None
    timeline: list[TimelineEvent]
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    """Paginated incident list."""

    total: int
    page: int
    page_size: int
    incidents: list[IncidentResponse]
