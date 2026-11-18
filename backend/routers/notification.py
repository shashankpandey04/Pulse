"""Notification routes (see ``schemas/notification.py`` for the API contract).

    GET /notifications    staff -> NotificationListResponse

Delivery history for the webhook receiver (chat/email/paging stand-in). The
CRON records one row per attempted delivery; nothing here writes.
"""

from fastapi import APIRouter, Query
from typing import Literal

from core import database
from core.dependencies import RequireStaff
from schemas.notification import (
    COLLECTION_NOTIFICATIONS,
    NotificationListResponse,
    NotificationResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    _: RequireStaff,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service_id: str | None = Query(None, description="Filter by service."),
    event_type: Literal["incident_opened", "incident_resolved", "incident_acknowledged", "note_added"] | None = None,
    delivered: bool | None = Query(None, description="Filter by delivery outcome."),
) -> NotificationListResponse:
    """Paginated webhook delivery history, newest first."""
    query: dict = {}
    if service_id:
        query["service_id"] = service_id
    if event_type:
        query["event_type"] = event_type
    if delivered is not None:
        query["delivered"] = delivered

    total = database.count(COLLECTION_NOTIFICATIONS, query)
    docs = database.find_many(
        COLLECTION_NOTIFICATIONS,
        query,
        sort=[("created_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return NotificationListResponse(
        total=total, page=page, page_size=page_size, notifications=[NotificationResponse.model_validate(d) for d in docs]
    )
