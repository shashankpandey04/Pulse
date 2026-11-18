"""Reliability routes (see ``schemas/reliability.py`` for the API contract).

    GET    /reliability                   staff -> ReliabilityListResponse
    GET    /reliability/{service_id}      staff -> ReliabilityResponse

Availability over the window vs the service's catalogue target, with the error
budget (allowed/consumed downtime, remaining budget). Computed in
``core/analytics.py``.
"""

from fastapi import APIRouter, HTTPException, Query, status

from core import analytics, database
from core.dependencies import RequireStaff
from schemas.catalogue import COLLECTION_SERVICES
from schemas.reliability import ReliabilityListResponse, ReliabilityResponse

router = APIRouter(prefix="/reliability", tags=["reliability"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Service not found.")


@router.get("", response_model=ReliabilityListResponse)
def reliability_overview(
    _: RequireStaff,
    window_days: int = Query(30, ge=1, le=90, description="Lookback window in days."),
) -> ReliabilityListResponse:
    """Every service's availability against its target."""
    return analytics.reliability_overview(window_days)


@router.get("/{service_id}", response_model=ReliabilityResponse)
def service_reliability(
    service_id: str,
    _: RequireStaff,
    window_days: int = Query(30, ge=1, le=90),
) -> ReliabilityResponse:
    """Reliability report for a single service."""
    service = database.find_one(COLLECTION_SERVICES, {"service_id": service_id})
    if service is None:
        raise _NOT_FOUND
    return analytics.service_reliability(service, window_days)
