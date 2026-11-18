"""Metrics routes (see ``schemas/metrics.py`` for the API contract).

    GET    /metrics                        staff -> MetricsOverviewResponse
    GET    /metrics/{service_id}           staff -> ServiceMetricsResponse
    GET    /metrics/{service_id}/checks    staff -> CheckResultListResponse

All computations are done in ``core/analytics.py`` from the stored check
results and incident history.
"""

from fastapi import APIRouter, HTTPException, Query, status
from typing import Literal

from core import analytics, database
from core.dependencies import RequireStaff
from schemas.catalogue import COLLECTION_SERVICES
from schemas.metrics import (
    COLLECTION_CHECK_RESULTS,
    CheckResultListResponse,
    CheckResultResponse,
    MetricsOverviewResponse,
    ServiceMetricsResponse,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Service not found.")


def _get_service_or_404(service_id: str) -> dict:
    service = database.find_one(COLLECTION_SERVICES, {"service_id": service_id})
    if service is None:
        raise _NOT_FOUND
    return service


@router.get("", response_model=MetricsOverviewResponse)
def metrics_overview(
    _: RequireStaff,
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours."),
) -> MetricsOverviewResponse:
    """Detection/resolution speed + checking performance for every service."""
    return analytics.metrics_overview(window_hours)


@router.get("/{service_id}", response_model=ServiceMetricsResponse)
def service_metrics(service_id: str, _: RequireStaff, window_hours: int = Query(24, ge=1, le=720)) -> ServiceMetricsResponse:
    """Metrics for a single service."""
    return analytics.service_metrics(_get_service_or_404(service_id), window_hours)


@router.get("/{service_id}/checks", response_model=CheckResultListResponse)
def list_checks(
    service_id: str,
    _: RequireStaff,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    success: bool | None = Query(None, description="Filter by check outcome."),
) -> CheckResultListResponse:
    """Raw stored check results for a service, newest first."""
    _get_service_or_404(service_id)
    query: dict = {"service_id": service_id}
    if success is not None:
        query["success"] = success

    total = database.count(COLLECTION_CHECK_RESULTS, query)
    checks = database.find_many(
        COLLECTION_CHECK_RESULTS,
        query,
        sort=[("checked_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return CheckResultListResponse(
        total=total, page=page, page_size=page_size, checks=[CheckResultResponse.model_validate(c) for c in checks]
    )
