"""Dashboard route — one endpoint, shaped by the caller's role.

    GET /dashboard    any signed-in role -> DashboardResponse

    subscriber -> ``status`` (the public status page view)
    operator   -> ``services`` + ``incidents_summary`` + ``metrics`` + ``reliability``
    admin      -> operator's sections + ``users_summary`` + ``notifications_summary``
"""

import logging

from fastapi import APIRouter

from core import analytics, database
from core.dependencies import CurrentUser
from routers.public import build_status_page
from schemas.catalogue import COLLECTION_SERVICES, ServiceResponse
from schemas.dashboard import DashboardResponse

logger = logging.getLogger("pulse.dashboard")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(user: CurrentUser) -> DashboardResponse:
    """Everything the caller's role is allowed to see, in one payload."""
    role = user["role"]
    response = DashboardResponse(role=role, generated_at=analytics.utcnow())

    if role == "subscriber":
        response.status = build_status_page()
        return response

    # Operator and admin share the operational view.
    response.services = [
        ServiceResponse.model_validate(s) for s in database.find_many(COLLECTION_SERVICES, sort=[("name", 1)])
    ]
    response.incidents_summary = analytics.incidents_summary()
    response.metrics = analytics.metrics_overview(window_hours=24)
    response.reliability = analytics.reliability_overview(window_days=30)

    if role == "admin":
        response.users_summary = analytics.users_summary()
        response.notifications_summary = analytics.notifications_summary()

    return response
