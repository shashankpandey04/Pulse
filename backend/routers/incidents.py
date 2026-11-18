"""Incident routes (see ``schemas/incidents.py`` for the API contract).

    GET    /incidents                        staff (admin, operator) -> IncidentListResponse
    GET    /incidents/{incident_id}          staff                   -> IncidentResponse
    PATCH  /incidents/{incident_id}/ack      staff                   -> IncidentResponse
    POST   /incidents/{incident_id}/notes    staff                   -> IncidentResponse
    POST   /incidents/{incident_id}/resolve  staff                   -> IncidentResponse

Incidents are opened/closed automatically by the health-check CRON; this router
lets staff acknowledge them, add timeline notes (public by default; internal
notes stay off the public status page) and resolve them manually. Every action
appends to the incident's embedded timeline.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from typing import Literal

from core import database, health_check
from core.dependencies import RequireStaff
from schemas.common import utcnow
from schemas.incidents import (
    COLLECTION_INCIDENTS,
    AcknowledgeRequest,
    IncidentListResponse,
    IncidentNoteRequest,
    IncidentResolveRequest,
    IncidentResponse,
    TimelineEvent,
)

logger = logging.getLogger("pulse.incidents")
router = APIRouter(prefix="/incidents", tags=["incidents"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Incident not found.")
_ALREADY = HTTPException(status.HTTP_409_CONFLICT, detail="Incident is not in an actionable state.")


def _get_or_404(incident_id: str) -> dict:
    incident = database.find_one(COLLECTION_INCIDENTS, {"incident_id": incident_id})
    if incident is None:
        raise _NOT_FOUND
    return incident


def _to_response(incident: dict) -> IncidentResponse:
    return IncidentResponse.model_validate(incident)


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    _: RequireStaff,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service_id: str | None = Query(None, description="Filter by service."),
    incident_status: Literal["open", "acknowledged", "resolved"] | None = Query(
        None, alias="status", description="Filter by lifecycle status."
    ),
) -> IncidentListResponse:
    """Paginated incident list, newest first."""
    query: dict = {}
    if service_id:
        query["service_id"] = service_id
    if incident_status:
        query["status"] = incident_status

    total = database.count(COLLECTION_INCIDENTS, query)
    incidents = database.find_many(
        COLLECTION_INCIDENTS,
        query,
        sort=[("opened_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return IncidentListResponse(
        total=total, page=page, page_size=page_size, incidents=[_to_response(i) for i in incidents]
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str, _: RequireStaff) -> IncidentResponse:
    """One incident with its full timeline."""
    return _to_response(_get_or_404(incident_id))


@router.patch("/{incident_id}/ack", response_model=IncidentResponse)
def acknowledge_incident(incident_id: str, payload: AcknowledgeRequest, user: RequireStaff) -> IncidentResponse:
    """Acknowledge an open incident (operator is on it). Idempotency: 409 after ack/resolve."""
    incident = _get_or_404(incident_id)
    if incident["status"] != "open":
        raise _ALREADY

    now = utcnow()
    message = payload.note or f"Acknowledged by {user['email']}."
    event = TimelineEvent(type="acknowledged", message=message, at=now, by_uid=user["uid"], by_email=user["email"])
    database.update_push(
        COLLECTION_INCIDENTS,
        {"incident_id": incident_id, "status": "open"},
        {
            "status": "acknowledged",
            "acknowledged_by_uid": user["uid"],
            "acknowledged_by_email": user["email"],
            "acknowledged_at": now,
            "updated_at": now,
        },
        "timeline",
        event.model_dump(mode="json"),
    )
    logger.info("incident %s acknowledged by %s", incident_id, user["email"])
    return _to_response(_get_or_404(incident_id))


@router.post("/{incident_id}/notes", response_model=IncidentResponse)
def add_note(incident_id: str, payload: IncidentNoteRequest, user: RequireStaff) -> IncidentResponse:
    """Append a note to the timeline. Public notes (default) show on the status page."""
    incident = _get_or_404(incident_id)
    event = TimelineEvent(
        type="note",
        message=payload.note,
        at=utcnow(),
        by_uid=user["uid"],
        by_email=user["email"],
        visibility=payload.visibility,
    )
    database.get_db()[COLLECTION_INCIDENTS].update_one(
        {"incident_id": incident_id},
        {"$push": {"timeline": event.model_dump(mode="json")}, "$set": {"updated_at": utcnow()}},
    )
    logger.info("note added to %s by %s (%s)", incident_id, user["email"], payload.visibility)
    return _to_response(_get_or_404(incident_id))


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
def resolve_incident(incident_id: str, payload: IncidentResolveRequest, user: RequireStaff) -> IncidentResponse:
    """Resolve an incident manually (the CRON also resolves on recovery)."""
    incident = _get_or_404(incident_id)
    if incident["status"] == "resolved":
        raise _ALREADY

    reason = payload.note or f"Manually resolved by {user['email']}."
    service = database.find_one("services", {"service_id": incident["service_id"]})
    if service is None:
        # Service was deleted; resolve without monitor context but still notify.
        now = utcnow()
        opened_at = datetime.fromisoformat(incident["opened_at"])
        database.update_push(
            COLLECTION_INCIDENTS,
            {"incident_id": incident_id, "status": {"$in": ["open", "acknowledged"]}},
            {
                "status": "resolved",
                "resolved_at": now,
                "resolved_reason": reason,
                "duration_seconds": (now - opened_at).total_seconds(),
                "updated_at": now,
            },
            "timeline",
            TimelineEvent(type="resolved", message=reason, at=now, by_uid=user["uid"], by_email=user["email"]).model_dump(mode="json"),
        )
    else:
        health_check.resolve_incident(incident, service, reason)
    logger.info("incident %s resolved by %s", incident_id, user["email"])
    return _to_response(_get_or_404(incident_id))
