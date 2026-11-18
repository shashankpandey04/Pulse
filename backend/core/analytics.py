"""Analytics computations for metrics, reliability and dashboard summaries.

Reads from ``check_results`` / ``incidents`` / ``services`` / ``users`` /
``notifications`` — never writes. Used by the metrics, reliability, public and
dashboard routers.

Storage note: documents in ``check_results``/``incidents`` are stored in JSON
mode, so their datetime fields are ISO-8601 strings; ``services.monitoring.*``
holds real BSON dates. Range queries against string fields pass ISO strings
(lexicographic order == chronological order for our uniform ``+00:00`` UTC
format); ``as_dt`` normalizes values of either kind for arithmetic.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from schemas.dashboard import IncidentSummary, NotificationsSummary, UsersSummary
from schemas.incidents import COLLECTION_INCIDENTS
from schemas.metrics import (
    COLLECTION_CHECK_RESULTS,
    MetricsOverviewResponse,
    ServiceMetricsResponse,
)
from schemas.notification import COLLECTION_NOTIFICATIONS
from schemas.catalogue import COLLECTION_SERVICES
from schemas.auth import COLLECTION_USERS
from schemas.reliability import ReliabilityListResponse, ReliabilityResponse

from . import database


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_dt(value: Any) -> datetime:
    """Normalize an ISO string or BSON datetime to an aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _p95(latencies: list[int]) -> float | None:
    """95th percentile (nearest-rank) of the given latencies."""
    if not latencies:
        return None
    ordered = sorted(latencies)
    index = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def _hours_ago_iso(hours: int) -> str:
    return (utcnow() - timedelta(hours=hours)).isoformat()


def _days_ago_iso(days: int) -> str:
    return (utcnow() - timedelta(days=days)).isoformat()


def _hours_ago_dt(hours: int) -> datetime:
    return utcnow() - timedelta(hours=hours)


# Storage-type conventions (see module docstring): ``resolved_at``/``acknowledged_at``
# and ``services.monitoring.*`` hold BSON dates; ``opened_at``/``checked_at``/
# ``timeline[].at`` hold ISO strings. Range queries must use the matching type.


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _mean_time_to_detect(service_id: str, incident: dict) -> float | None:
    """Opened_at minus the first failed check of the incident's episode (seconds).

    The episode starts at the first failed check after the last successful one
    before the incident opened. Returns None when the episode can't be located
    (e.g. no checks stored yet).
    """
    opened_at = as_dt(incident["opened_at"])
    opened_iso = opened_at.isoformat()
    # Newest successful check before the incident opened bounds the episode.
    successes = database.find_many(
        COLLECTION_CHECK_RESULTS,
        {"service_id": service_id, "success": True, "checked_at": {"$lte": opened_iso}},
        sort=[("checked_at", -1)],
        limit=1,
    )
    lower_bound = successes[0]["checked_at"] if successes else None

    episode_query: dict[str, Any] = {
        "service_id": service_id,
        "success": False,
        "checked_at": {"$lte": opened_iso},
    }
    if lower_bound is not None:
        episode_query["checked_at"]["$gt"] = lower_bound if isinstance(lower_bound, str) else as_dt(lower_bound).isoformat()

    first_failure = database.find_many(COLLECTION_CHECK_RESULTS, episode_query, sort=[("checked_at", 1)], limit=1)
    if not first_failure:
        return None
    return (opened_at - as_dt(first_failure[0]["checked_at"])).total_seconds()


def service_metrics(service: dict, window_hours: int) -> ServiceMetricsResponse:
    """Detection/resolution speed and checking performance for one service."""
    service_id = service["service_id"]
    start_iso = _hours_ago_iso(window_hours)
    window_query = {"service_id": service_id, "checked_at": {"$gte": start_iso}}

    total = database.count(COLLECTION_CHECK_RESULTS, window_query)
    failed = database.count(COLLECTION_CHECK_RESULTS, {**window_query, "success": False})
    checked = database.find_many(
        COLLECTION_CHECK_RESULTS,
        {**window_query, "latency_ms": {"$ne": None}},
        sort=[("checked_at", -1)],
        limit=1000,
    )
    latencies = [c["latency_ms"] for c in checked]

    resolved = database.find_many(
        COLLECTION_INCIDENTS,
        # resolved_at is stored as a BSON date -> query with a datetime.
        {"service_id": service_id, "status": "resolved", "resolved_at": {"$gte": _hours_ago_dt(window_hours)}},
    )
    durations = [i["duration_seconds"] for i in resolved if i.get("duration_seconds") is not None]
    detections = [m for m in (_mean_time_to_detect(service_id, i) for i in resolved) if m is not None]

    mon = service.get("monitoring", {})
    return ServiceMetricsResponse(
        service_id=service_id,
        service_name=service["name"],
        window_hours=window_hours,
        total_checks=total,
        failed_checks=failed,
        success_rate=(total - failed) / total if total else 1.0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else None,
        p95_latency_ms=_p95(latencies),
        mttd_seconds=sum(detections) / len(detections) if detections else None,
        mttr_seconds=sum(durations) / len(durations) if durations else None,
        open_incidents=database.count(
            COLLECTION_INCIDENTS, {"service_id": service_id, "status": {"$in": ["open", "acknowledged"]}}
        ),
        last_check_at=mon.get("last_check_at"),
        last_state=mon.get("current_state"),
    )


def metrics_overview(window_hours: int) -> MetricsOverviewResponse:
    services = database.find_many(COLLECTION_SERVICES, sort=[("name", 1)])
    return MetricsOverviewResponse(
        window_hours=window_hours,
        services=[service_metrics(s, window_hours) for s in services],
    )


# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------


def service_reliability(service: dict, window_days: int) -> ReliabilityResponse:
    """Availability over the window judged against the catalogue target."""
    service_id = service["service_id"]
    start_iso = _days_ago_iso(window_days)
    window_query = {"service_id": service_id, "checked_at": {"$gte": start_iso}}

    total = database.count(COLLECTION_CHECK_RESULTS, window_query)
    failed = database.count(COLLECTION_CHECK_RESULTS, {**window_query, "success": False})

    target = service["reliability_target"]
    availability = (total - failed) / total * 100 if total else 100.0

    window_minutes = window_days * 24 * 60
    allowed_minutes = (100 - target) / 100 * window_minutes
    consumed_minutes = failed / total * window_minutes if total else 0.0
    if allowed_minutes > 0:
        budget_remaining = (allowed_minutes - consumed_minutes) / allowed_minutes * 100
    else:
        # Target of 100% leaves no budget: unspent unless anything failed.
        budget_remaining = 100.0 if consumed_minutes <= 0 else 0.0

    mon = service.get("monitoring", {})
    return ReliabilityResponse(
        service_id=service_id,
        service_name=service["name"],
        window_days=window_days,
        target_pct=target,
        availability_pct=round(availability, 4),
        meeting_target=availability >= target,
        error_budget_pct=round(100 - target, 4),
        error_budget_remaining_pct=round(budget_remaining, 2),
        allowed_downtime_minutes=round(allowed_minutes, 2),
        consumed_downtime_minutes=round(consumed_minutes, 2),
        total_checks=total,
        failed_checks=failed,
        incident_count=database.count(COLLECTION_INCIDENTS, {"service_id": service_id, "opened_at": {"$gte": start_iso}}),
        last_state=mon.get("current_state"),
        computed_at=utcnow(),
    )


def reliability_overview(window_days: int) -> ReliabilityListResponse:
    services = database.find_many(COLLECTION_SERVICES, sort=[("name", 1)])
    return ReliabilityListResponse(
        window_days=window_days,
        services=[service_reliability(s, window_days) for s in services],
    )


# ---------------------------------------------------------------------------
# Dashboard summaries
# ---------------------------------------------------------------------------


def incidents_summary() -> IncidentSummary:
    return IncidentSummary(
        open=database.count(COLLECTION_INCIDENTS, {"status": "open"}),
        acknowledged=database.count(COLLECTION_INCIDENTS, {"status": "acknowledged"}),
        # resolved_at is stored as a BSON date -> query with a datetime.
        resolved_24h=database.count(
            COLLECTION_INCIDENTS, {"status": "resolved", "resolved_at": {"$gte": _hours_ago_dt(24)}}
        ),
    )


def users_summary() -> UsersSummary:
    total = database.count(COLLECTION_USERS)
    active = database.count(COLLECTION_USERS, {"active": True})
    return UsersSummary(
        total=total,
        by_role={role: database.count(COLLECTION_USERS, {"role": role}) for role in ("admin", "operator", "subscriber")},
        active=active,
        deactivated=total - active,
    )


def notifications_summary() -> NotificationsSummary:
    total = database.count(COLLECTION_NOTIFICATIONS)
    delivered = database.count(COLLECTION_NOTIFICATIONS, {"delivered": True})
    return NotificationsSummary(total=total, delivered=delivered, failed=total - delivered)
