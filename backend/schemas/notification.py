"""Notification schemas: what was sent to the webhook receiver, and whether it got there.

Every incident open/resolve is POSTed to the webhook receiver (``http://localhost:9900``),
which stands in for chat/email/paging. Each attempt is recorded here so the team
can audit deliveries.

Database: ``notifications`` collection
    - index ``(created_at desc)``; append-only

Planned routes (``routers/notification.py``, later task):
    GET    /notifications         NotificationListResponse   admin, operator
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .common import TimestampedModel, new_uid

COLLECTION_NOTIFICATIONS = "notifications"
"""MongoDB collection that stores ``NotificationDocument`` records."""

NotificationEvent = Literal["incident_opened", "incident_resolved", "incident_acknowledged", "note_added"]


class NotificationDocument(TimestampedModel):
    """One webhook delivery attempt — document in ``notifications``."""

    notification_id: str = Field(default_factory=new_uid)
    event_type: NotificationEvent = Field(description="What happened.")
    service_id: str
    service_name: str = Field(description="Denormalized for quick scanning.")
    incident_id: str | None = Field(default=None, description="Related incident, when applicable.")
    message: str = Field(description="Human summary that was delivered.")
    payload: dict[str, Any] = Field(description="The JSON body POSTed to the webhook receiver.")
    delivered: bool = Field(default=False, description="True when the webhook accepted the POST (2xx).")
    attempts: int = Field(default=1, description="Delivery attempts so far.")
    last_error: str | None = Field(default=None, description="Last delivery error, when not delivered.")
    delivered_at: datetime | None = None


class NotificationResponse(BaseModel):
    """A notification delivery record as returned by the API."""

    notification_id: str
    event_type: NotificationEvent
    service_id: str
    service_name: str
    incident_id: str | None = None
    message: str
    payload: dict[str, Any]
    delivered: bool
    attempts: int
    last_error: str | None = None
    delivered_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated notification history."""

    total: int
    page: int
    page_size: int
    notifications: list[NotificationResponse]
