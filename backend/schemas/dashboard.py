"""Dashboard schemas — one endpoint, role-shaped responses.

``GET /dashboard`` (any signed-in role) returns a ``DashboardResponse`` whose
sections depend on the caller's role:

    subscriber -> ``status``           the public status page view
    operator   -> ``services`` + ``incidents_summary`` + ``metrics`` + ``reliability``
    admin      -> everything above plus ``users_summary`` and ``notifications_summary``

Unrequested sections are ``None``.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .auth import Role
from .catalogue import ServiceResponse
from .device import DevicesSummary
from .email_subscription import EmailNotificationsSummary
from .metrics import MetricsOverviewResponse
from .public import PublicStatusResponse
from .reliability import ReliabilityListResponse


class IncidentSummary(BaseModel):
    """Incident counters for the dashboard header."""

    open: int
    acknowledged: int
    resolved_24h: int


class UsersSummary(BaseModel):
    """Manage-Users snapshot for admins."""

    total: int
    by_role: dict[str, int] = Field(description="Account count per role.")
    active: int
    deactivated: int


class NotificationsSummary(BaseModel):
    """Webhook delivery health for admins."""

    total: int
    delivered: int
    failed: int


class DashboardResponse(BaseModel):
    """Role-shaped dashboard payload."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "operator",
                    "generated_at": "2026-11-18T10:00:00Z",
                    "status": None,
                    "services": [],
                    "incidents_summary": {"open": 1, "acknowledged": 0, "resolved_24h": 2},
                    "metrics": None,
                    "reliability": None,
                    "users_summary": None,
                    "notifications_summary": None,
                }
            ]
        }
    }

    role: Role
    generated_at: datetime
    status: PublicStatusResponse | None = Field(
        default=None,
        description="Subscriber only: the public status page view.",
    )
    services: list[ServiceResponse] | None = Field(
        default=None,
        description="Operator/admin: the full service catalogue.",
    )
    incidents_summary: IncidentSummary | None = None
    metrics: MetricsOverviewResponse | None = Field(
        default=None,
        description="Operator/admin: 24h metrics overview.",
    )
    reliability: ReliabilityListResponse | None = Field(
        default=None,
        description="Operator/admin: 30d reliability overview.",
    )
    users_summary: UsersSummary | None = Field(
        default=None,
        description="Admin only: account totals per role/activation.",
    )
    notifications_summary: NotificationsSummary | None = Field(
        default=None,
        description="Admin only: webhook delivery totals.",
    )
    devices: DevicesSummary | None = Field(
        default=None,
        description="The caller's push-subscription state (``notifications_required`` "
        "is True for operators/admins who have no device registered yet).",
    )
    email_notifications: EmailNotificationsSummary = Field(
        default_factory=lambda: EmailNotificationsSummary(subscribed=False, email=None, notifications_required=False),
        description="The caller's email-subscription state (the user-facing notification "
        "channel; ``notifications_required`` is True for staff who are not subscribed).",
    )
