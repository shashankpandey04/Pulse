"""Health check execution: one check per service, evaluated against its state config.

Pure evaluation logic lives here plus the side effects it triggers:
store the ``CheckResultDocument``, advance the service's monitoring counters,
open/append/resolve incidents, POST notifications to the webhook receiver
(``http://localhost:9900``) when an incident opens or resolves, and push the
state change to every subscribed device over FCM (``core/fcm.py``).

The scheduler (``core/scheduler.py``) decides *when* each service is checked;
this module decides *what a check means*.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from schemas.catalogue import COLLECTION_SERVICES
from schemas.incidents import COLLECTION_INCIDENTS, IncidentDocument, TimelineEvent
from schemas.metrics import COLLECTION_CHECK_RESULTS, CheckResultDocument
from schemas.notification import COLLECTION_NOTIFICATIONS, NotificationDocument
from schemas.state import COLLECTION_SERVICE_STATES, HealthState, ServiceStateDocument

from . import config, database, fcm, mailer

logger = logging.getLogger("pulse.monitor")

_http: httpx.AsyncClient | None = None
"""Shared async HTTP client (created by the lifespan; lazily created otherwise)."""


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=10.0)
    return _http


def set_http_client(client: httpx.AsyncClient | None) -> None:
    """Inject/replace the shared client (lifespan startup/shutdown)."""
    global _http
    _http = client


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# State evaluation (pure)
# ---------------------------------------------------------------------------


def evaluate_state(
    *,
    previous: HealthState,
    success: bool,
    latency_ms: int | None,
    consecutive_failures: int,
    consecutive_successes: int,
    window_failure_rate: float | None,
    cfg: ServiceStateDocument,
) -> HealthState:
    """Decide the service's health state after one check.

    Precedence: down > recovered-healthy > flaky > slow > (previous state kept).
    A failing check below the ``down`` threshold keeps the previous state — the
    blip is still recorded on the check result. Once
    ``recovery.consecutive_successes`` checks succeed in a row the service is
    healthy again, even while the flaky window still carries older failures.
    """
    if not success and consecutive_failures >= cfg.down.consecutive_failures:
        return "down"
    if success and consecutive_successes >= cfg.recovery.consecutive_successes:
        return "healthy"
    if window_failure_rate is not None and window_failure_rate > cfg.flaky.failure_rate:
        return "flaky"
    if success and latency_ms is not None and latency_ms > cfg.slow.latency_ms:
        return "slow"
    return previous


def load_state_config(service_id: str) -> ServiceStateDocument:
    """The service's stored thresholds, or schema defaults when none is stored."""
    stored = database.find_one(COLLECTION_SERVICE_STATES, {"service_id": service_id})
    return ServiceStateDocument(**stored) if stored else ServiceStateDocument(service_id=service_id)


def window_failure_rate(service_id: str, window: int, *, current_success: bool) -> float | None:
    """Failure share over the last ``window`` checks *including* the current one.

    Reads only ``window - 1`` stored results (the newest ones) because the
    current check completes the window. Returns ``None`` until a full window of
    history exists, so flaky detection never fires on thin history.
    """
    recent = database.find_many(
        COLLECTION_CHECK_RESULTS,
        {"service_id": service_id},
        sort=[("checked_at", -1)],
        limit=window - 1,
    )
    if len(recent) < window - 1:
        return None
    failures = sum(1 for r in recent if not r["success"]) + (0 if current_success else 1)
    return failures / window


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


def _find_open_incident(service_id: str) -> dict | None:
    return database.find_one(
        COLLECTION_INCIDENTS,
        {"service_id": service_id, "status": {"$in": ["open", "acknowledged"]}},
    )


def _append_event(incident_id: str, event: TimelineEvent) -> None:
    database.get_db()[COLLECTION_INCIDENTS].update_one(
        {"incident_id": incident_id},
        {"$push": {"timeline": event.model_dump(mode="json")}, "$set": {"updated_at": utcnow()}},
    )


def _notify(event_type: str, service: dict, incident: dict | None, message: str, extra: dict[str, Any] | None = None) -> None:
    """POST an event to the webhook receiver and record the delivery attempt."""
    payload: dict[str, Any] = {
        "event_type": event_type,
        "service_id": service["service_id"],
        "service_name": service["name"],
        "state": service.get("monitoring", {}).get("current_state"),
        "incident_id": (incident or {}).get("incident_id"),
        "message": message,
        "at": utcnow().isoformat(),
        **(extra or {}),
    }
    doc = NotificationDocument(
        event_type=event_type,  # type: ignore[arg-type]
        service_id=service["service_id"],
        service_name=service["name"],
        incident_id=payload["incident_id"],
        message=message,
        payload=payload,
    )

    async def _post() -> None:
        try:
            r = await _client().post(config.WEBHOOK_URL, json=payload)
            doc.delivered = r.status_code < 300
            if not doc.delivered:
                doc.last_error = f"webhook returned HTTP {r.status_code}"
            else:
                doc.delivered_at = utcnow()
        except Exception as exc:  # webhook down must never break monitoring
            doc.last_error = f"{type(exc).__name__}: {exc}"
        database.insert(COLLECTION_NOTIFICATIONS, doc.model_dump(mode="json"))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. scripted calls outside the app): run inline.
        asyncio.run(_post())
        return
    task = loop.create_task(_post())
    _pending_notify.add(task)
    task.add_done_callback(_pending_notify.discard)


_pending_notify: set[asyncio.Task] = set()
"""Webhook POST tasks awaiting completion; drained by the sweep and on shutdown."""

_pending_push: set[asyncio.Task] = set()
"""FCM fan-out tasks awaiting completion; drained alongside the webhook tasks."""

_pending_mail: set[asyncio.Task] = set()
"""Email fan-out tasks awaiting completion; drained alongside the webhook tasks."""


async def drain_notifications() -> None:
    """Wait for outstanding webhook deliveries, FCM pushes and emails."""
    if _pending_notify or _pending_push or _pending_mail:
        await asyncio.gather(
            *list(_pending_notify), *list(_pending_push), *list(_pending_mail), return_exceptions=True
        )


def _push_state_change(service: dict, previous: HealthState, state: HealthState, incident_id: str | None) -> None:
    """Fan one service state change out to every subscribed device via FCM.

    Follows the same fire-and-forget pattern as the webhook ``_notify``: a task
    per push, tracked so the sweep/shutdown can drain it. Failures are logged,
    never raised — monitoring must not break over notifications.
    """

    async def _run() -> None:
        try:
            outcome = await fcm.send_state_change(
                service["service_id"], service["name"], previous, state, incident_id
            )
            if outcome.get("skipped"):
                logger.debug("fcm push skipped (%s)", outcome["skipped"])
            else:
                logger.info(
                    "fcm push for %s: sent=%s failed=%s pruned=%s",
                    service["name"], outcome.get("sent"), outcome.get("failed"), outcome.get("pruned"),
                )
        except Exception as exc:
            logger.warning("fcm push failed: %s", exc)

    if not fcm.enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. scripted calls outside the app): run inline.
        asyncio.run(_run())
        return
    task = loop.create_task(_run())
    _pending_push.add(task)
    task.add_done_callback(_pending_push.discard)


def _mail_state_change(service: dict, previous: HealthState, state: HealthState, incident_id: str | None) -> None:
    """Email one service state change to every subscribed account (Task 7).

    Same fire-and-forget pattern as the FCM fan-out above: one tracked task,
    failures logged and never raised. Skipped entirely when the SMTP
    credentials are not configured.
    """

    async def _run() -> None:
        try:
            outcome = await mailer.send_state_change(
                service["service_id"], service["name"], service.get("slug", ""), previous, state, incident_id
            )
            if outcome.get("skipped"):
                logger.debug("mail skipped (%s)", outcome["skipped"])
            else:
                logger.info(
                    "mail for %s: sent=%s failed=%s",
                    service["name"], outcome.get("sent"), outcome.get("failed"),
                )
        except Exception as exc:
            logger.warning("mail fan-out failed: %s", exc)

    if not mailer.enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. scripted calls outside the app): run inline.
        asyncio.run(_run())
        return
    task = loop.create_task(_run())
    _pending_mail.add(task)
    task.add_done_callback(_pending_mail.discard)


def open_incident(service: dict, cfg: ServiceStateDocument, state: HealthState, window_rate: float | None) -> dict:
    """Create a new incident for a service that just went ``down``/``flaky``."""
    service_name = service["name"]
    if state == "down":
        title, reason = (
            f"{service_name} is down",
            f"{service['monitoring']['consecutive_failures']} consecutive failed checks",
        )
    else:
        rate = window_rate or 0.0
        title, reason = (
            f"{service_name} is flaky",
            f"failure rate {rate:.0%} over the last {cfg.flaky.window_size} checks "
            f"exceeds the {cfg.flaky.failure_rate:.0%} threshold",
        )
    incident = IncidentDocument(
        service_id=service["service_id"],
        service_name=service_name,
        title=title,
        status="open",
        current_state=state,
        opened_at=utcnow(),
        opened_reason=reason,
        timeline=[TimelineEvent(type="opened", message=reason, at=utcnow())],
    )
    database.insert(COLLECTION_INCIDENTS, incident.model_dump(mode="json"))
    doc = incident.model_dump()
    _notify("incident_opened", service, doc, f"{title} — {reason}", {"status": "open"})
    logger.warning("incident opened: %s (%s)", title, incident.incident_id)
    return doc


def resolve_incident(incident: dict, service: dict, reason: str) -> None:
    """Close an incident because the service recovered."""
    now = utcnow()
    opened_at = incident["opened_at"]
    if isinstance(opened_at, str):  # documents are stored in JSON mode
        opened_at = datetime.fromisoformat(opened_at)
    duration = (now - opened_at).total_seconds()
    updates = {
        "status": "resolved",
        "resolved_at": now,
        "resolved_reason": reason,
        "duration_seconds": duration,
        "updated_at": now,
    }
    database.get_db()[COLLECTION_INCIDENTS].update_one(
        {"incident_id": incident["incident_id"], "status": {"$in": ["open", "acknowledged"]}},
        {"$set": updates, "$push": {"timeline": TimelineEvent(type="resolved", message=reason, at=now).model_dump(mode="json")}},
    )
    incident.update(updates)
    _notify("incident_resolved", service, incident, f"{incident['service_name']} recovered — {reason}")
    logger.info("incident resolved: %s after %.0fs", incident["incident_id"], duration)


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------


async def run_check(service: dict) -> CheckResultDocument | None:
    """Perform one health check for ``service`` and apply all consequences.

    Raises nothing: every failure mode is captured in the stored result. Returns
    the stored ``CheckResultDocument`` (``None`` only on internal errors).
    """
    service_id = service["service_id"]
    cfg = load_state_config(service_id)
    now = utcnow()
    url = str(service["health_url"])

    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    timed_out = False
    success = False
    try:
        response = await _client().get(url, timeout=service["timeout_seconds"])
        status_code = response.status_code
        latency_ms = int(response.elapsed.total_seconds() * 1000)
        success = 200 <= status_code < 300
        if not success:
            error = f"HTTP {status_code}"
    except httpx.TimeoutException:
        timed_out = True
        error = f"timed out after {service['timeout_seconds']}s"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    mon = service.get("monitoring", {})
    previous: HealthState = mon.get("current_state", "healthy")
    if success:
        consecutive_failures = 0
        consecutive_successes = mon.get("consecutive_successes", 0) + 1
    else:
        consecutive_failures = mon.get("consecutive_failures", 0) + 1
        consecutive_successes = 0

    result = CheckResultDocument(
        service_id=service_id,
        checked_at=now,
        success=success,
        state=previous,  # corrected below once evaluated
        status_code=status_code,
        latency_ms=latency_ms,
        error=error,
        timed_out=timed_out,
    )

    rate = window_failure_rate(service_id, cfg.flaky.window_size, current_success=success)
    state = evaluate_state(
        previous=previous,
        success=success,
        latency_ms=latency_ms,
        consecutive_failures=consecutive_failures,
        consecutive_successes=consecutive_successes,
        window_failure_rate=rate,
        cfg=cfg,
    )
    result.state = state
    database.insert(COLLECTION_CHECK_RESULTS, result.model_dump(mode="json"))

    # Advance the service's monitoring counters + claim the next slot on its own schedule.
    database.update_one(
        COLLECTION_SERVICES,
        {"service_id": service_id},
        {
            "monitoring.current_state": state,
            "monitoring.consecutive_failures": consecutive_failures,
            "monitoring.consecutive_successes": consecutive_successes,
            "monitoring.last_check_at": now,
            "monitoring.last_latency_ms": latency_ms,
            "monitoring.last_error": error,
            "monitoring.next_check_at": now + timedelta(seconds=service["check_interval_seconds"]),
        },
    )
    service.setdefault("monitoring", {}).update(
        current_state=state,
        consecutive_failures=consecutive_failures,
        consecutive_successes=consecutive_successes,
    )

    incident = _apply_incident_consequences(service, cfg, previous, state, rate)
    if state != previous:
        # Any state change (healthy->down, down->healthy, flaky<->slow, …) is
        # pushed to every subscribed device and emailed to every subscribed
        # account; the incident id (when one was opened/escalated above) tags
        # the message.
        incident_id = (incident or {}).get("incident_id")
        _push_state_change(service, previous, state, incident_id)
        _mail_state_change(service, previous, state, incident_id)
    logger.info(
        "check %s -> %s (success=%s latency=%s error=%s)", service_id, state, success, latency_ms, error
    )
    return result


def _apply_incident_consequences(
    service: dict,
    cfg: ServiceStateDocument,
    previous: HealthState,
    state: HealthState,
    window_rate: float,
) -> dict | None:
    """Open / annotate / resolve incidents based on the state transition.

    Returns the incident document that was touched (opened, escalated or
    resolved), or ``None`` when nothing changed / there was none to touch.
    """
    if state == previous:
        return None

    incident = _find_open_incident(service["service_id"])

    if state in ("down", "flaky") and incident is None:
        return open_incident(service, cfg, state, window_rate)

    if incident is not None:
        if state == "healthy":
            resolve_incident(
                incident,
                service,
                f"recovered after {service['monitoring']['consecutive_successes']} consecutive successful checks",
            )
        else:
            # Improvement or shift between degraded states (flaky <-> slow, and
            # escalation flaky -> down): reflect the new state on the incident.
            if incident["current_state"] != state:
                database.get_db()[COLLECTION_INCIDENTS].update_one(
                    {"incident_id": incident["incident_id"]},
                    {"$set": {"current_state": state, "title": f"{service['name']} is {state}", "updated_at": utcnow()}},
                )
            _append_event(
                incident["incident_id"],
                TimelineEvent(
                    type="state_changed",
                    message=f"state changed {previous} -> {state}",
                    at=utcnow(),
                ),
            )
        return incident
    return None


async def check_service_by_id(service_id: str) -> CheckResultDocument | None:
    """Re-read the service then run one check (used by tests and manual triggers)."""
    service = database.find_one(COLLECTION_SERVICES, {"service_id": service_id})
    if service is None:
        return None
    return await run_check(service)
