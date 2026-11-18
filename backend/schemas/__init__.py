"""Pydantic schemas for the Pulse backend (Task 1).

Submodules
    common       shared helpers (utcnow, new_uid, TimestampedModel) and generic responses
    auth         accounts: ``users`` document + auth / admin user-management API schemas
    catalogue    service catalogue: ``services`` document + catalogue API schemas
    state        service states: ``service_states`` document + state API schemas
    incidents    incidents: ``incidents`` document (embedded timeline) + API schemas
    metrics      check results: ``check_results`` document + metrics API schemas
    reliability  reliability reports (computed on read, no dedicated collection)
    notification webhook deliveries: ``notifications`` document + API schemas
    public       public status page payloads (sanitized, no auth)
    dashboard    role-shaped dashboard payloads

Example:
    from schemas.auth import RegisterRequest, UserDocument
    from schemas.catalogue import ServiceCreateRequest, ServiceResponse
    from schemas.state import StateConfigUpsertRequest, STATE_COLORS
"""

from . import (
    auth,
    catalogue,
    common,
    dashboard,
    incidents,
    metrics,
    notification,
    public,
    reliability,
    state,
)

__all__ = [
    "auth",
    "catalogue",
    "common",
    "dashboard",
    "incidents",
    "metrics",
    "notification",
    "public",
    "reliability",
    "state",
]
