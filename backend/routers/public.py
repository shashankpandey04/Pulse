"""Public status page routes — anonymous access, sanitized data.

    GET /public/status           -> PublicStatusResponse
    GET /public/status/{slug}    -> PublicServiceDetail

Only enabled services appear on the list; only ``visibility="public"`` timeline
events are shown. Internal notes and operational details (owners, thresholds)
never leave here.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from core import database
from schemas.catalogue import COLLECTION_SERVICES
from schemas.incidents import COLLECTION_INCIDENTS
from schemas.public import (
    PublicIncident,
    PublicServiceDetail,
    PublicServiceStatus,
    PublicStatusEvent,
    PublicStatusResponse,
)
from schemas.state import STATE_COLORS

router = APIRouter(prefix="/public", tags=["public"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Service not found.")

_UNKNOWN_COLOR = "#6B7280"  # gray fallback; states are a fixed set so this is defensive


def _service_view(service: dict) -> PublicServiceStatus:
    mon = service.get("monitoring", {})
    state = mon.get("current_state", "healthy")
    return PublicServiceStatus(
        service_id=service["service_id"],
        name=service["name"],
        slug=service["slug"],
        description=service.get("description"),
        state=state,
        color=STATE_COLORS.get(state, _UNKNOWN_COLOR),
        last_check_at=mon.get("last_check_at"),
        last_latency_ms=mon.get("last_latency_ms"),
    )


def _public_incident(incident: dict) -> PublicIncident:
    events = [
        PublicStatusEvent(type=e["type"], message=e["message"], at=e["at"])
        for e in incident.get("timeline", [])
        if e.get("visibility") == "public"
    ]
    return PublicIncident(
        incident_id=incident["incident_id"],
        title=incident["title"],
        status=incident["status"],
        current_state=incident["current_state"],
        opened_at=incident["opened_at"],
        resolved_at=incident.get("resolved_at"),
        duration_seconds=incident.get("duration_seconds"),
        events=events,
    )


def build_status_page() -> PublicStatusResponse:
    """Assemble the whole status page payload (also used by the dashboard)."""
    services = database.find_many(COLLECTION_SERVICES, {"enabled": True}, sort=[("name", 1)])
    summary: dict[str, int] = {}
    views = []
    for service in services:
        state = service.get("monitoring", {}).get("current_state", "healthy")
        summary[state] = summary.get(state, 0) + 1
        views.append(_service_view(service))

    active = database.find_many(
        COLLECTION_INCIDENTS,
        {"status": {"$in": ["open", "acknowledged"]}},
        sort=[("opened_at", -1)],
    )
    return PublicStatusResponse(
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        colors=dict(STATE_COLORS),
        services=views,
        active_incidents=[_public_incident(i) for i in active],
    )


@router.get("/status", response_model=PublicStatusResponse)
def status_page() -> PublicStatusResponse:
    """The public status page: all enabled services + active incidents."""
    return build_status_page()


@router.get("/status/{slug}", response_model=PublicServiceDetail)
def service_detail(slug: str) -> PublicServiceDetail:
    """One service with its incident history (public events only)."""
    service = database.find_one(COLLECTION_SERVICES, {"slug": slug})
    if service is None:
        raise _NOT_FOUND
    history = database.find_many(
        COLLECTION_INCIDENTS,
        {"service_id": service["service_id"]},
        sort=[("opened_at", -1)],
        limit=20,
    )
    return PublicServiceDetail(service=_service_view(service), incidents=[_public_incident(i) for i in history])
