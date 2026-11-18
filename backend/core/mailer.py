"""SMTP mailer: emails service state changes to every subscribed user.

The user-facing notification channel (replacing FCM pushes in the UI): every
account subscribes with its account email (``email_subscriptions`` collection)
and, when the CRON observes a state change, each subscriber receives an
individual email — one message per recipient so addresses are never shared.

Credentials come from the environment; for the Gmail flow the user supplies
their address (``PULSE_SMTP_USER``) and a Google **App Password**
(``PULSE_SMTP_PASSWORD``), sent over STARTTLS on ``smtp.gmail.com:587``.
Without credentials the mailer is disabled: subscriptions keep working, state
changes are simply not emailed (same graceful stance as FCM/webhook).

Like ``core/fcm.py`` the sender is synchronous (``smtplib``) and runs in a
worker thread; per-subscriber outcomes are recorded on the subscription
documents and failures never break monitoring.
"""

import asyncio
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from schemas.auth import COLLECTION_USERS
from schemas.email_subscription import COLLECTION_EMAIL_SUBSCRIPTIONS
from schemas.mail_outbox import COLLECTION_MAIL_OUTBOX, MailOutboxDocument, OutboxProcessingResult

from . import config, database

logger = logging.getLogger("pulse.mailer")

OUTBOX_MAX_ATTEMPTS = 5
"""Retry budget per queued mail before it is marked ``failed``."""

OUTBOX_RETRY_SECONDS = 60
"""Backoff base: attempt N is retried N * OUTBOX_RETRY_SECONDS after the failure."""


def enabled() -> bool:
    """Whether emails can actually be sent (credentials configured)."""
    return bool(config.SMTP_USER and config.SMTP_PASSWORD)


def _active_uids() -> set[str]:
    """uids of accounts that may receive mail (registered and active)."""
    rows = database.get_db()[COLLECTION_USERS].find({"active": True}, {"uid": 1})
    return {r["uid"] for r in rows}


def send_state_change_blocking(
    service_id: str,
    service_name: str,
    slug: str,
    old_state: str,
    new_state: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Email one message per subscribed, active account (sync).

    Reuses a single SMTP connection for the whole fan-out. Returns counters
    for logging; SMTP/database failures never propagate — monitoring must not
    break over notifications.
    """
    if not enabled():
        return {"sent": 0, "failed": 0, "skipped": "smtp not configured"}

    uids = _active_uids()
    if not uids:
        return {"sent": 0, "failed": 0, "skipped": "no active users"}
    subscriptions = list(
        database.find_many(COLLECTION_EMAIL_SUBSCRIPTIONS, {"uid": {"$in": list(uids)}})
    )
    if not subscriptions:
        return {"sent": 0, "failed": 0, "skipped": "no subscribers"}

    now = datetime.now(timezone.utc)
    subject = f"[Pulse] {service_name} is {new_state}"
    body = (
        f"{service_name} changed state from {old_state} to {new_state} at {now.isoformat()}.\n"
        + ("An incident was opened.\n" if incident_id else "")
        + f"\nView the status page: {config.PUBLIC_URL.rstrip('/')}/status/{slug}\n"
    )

    sent = failed = 0
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            for sub in subscriptions:
                message = EmailMessage()
                message["From"] = config.SMTP_FROM or config.SMTP_USER
                message["To"] = sub["email"]
                message["Subject"] = subject
                message.set_content(body)
                try:
                    server.send_message(message)
                    sent += 1
                    database.update_one(
                        COLLECTION_EMAIL_SUBSCRIPTIONS,
                        {"subscription_id": sub["subscription_id"]},
                        {"send_count": sub.get("send_count", 0) + 1, "last_sent_at": now, "last_error": None},
                    )
                except Exception as exc:  # per-recipient failure: keep going
                    failed += 1
                    logger.warning("mail to %s failed: %s", sub["email"], exc)
                    database.update_one(
                        COLLECTION_EMAIL_SUBSCRIPTIONS,
                        {"subscription_id": sub["subscription_id"]},
                        {
                            "fail_count": sub.get("fail_count", 0) + 1,
                            "last_error": f"{type(exc).__name__}: {exc}",
                        },
                    )
    except Exception as exc:  # connection/login-level failure: nobody got mail
        logger.warning("mail fan-out failed: %s", exc)
        for sub in subscriptions:
            database.update_one(
                COLLECTION_EMAIL_SUBSCRIPTIONS,
                {"subscription_id": sub["subscription_id"]},
                {
                    "fail_count": sub.get("fail_count", 0) + 1,
                    "last_error": f"{type(exc).__name__}: {exc}",
                },
            )
        return {"sent": 0, "failed": len(subscriptions), "error": str(exc)}

    return {"sent": sent, "failed": failed}


async def send_state_change(
    service_id: str,
    service_name: str,
    slug: str,
    old_state: str,
    new_state: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Async wrapper around the blocking sender (runs it in a thread)."""
    if not enabled():
        return {"sent": 0, "failed": 0, "skipped": "smtp not configured"}
    return await asyncio.to_thread(
        send_state_change_blocking, service_id, service_name, slug, old_state, new_state, incident_id
    )


# ---------------------------------------------------------------------------
# Durable outbox (Task 8): enqueue on state change, CRON job delivers
# ---------------------------------------------------------------------------


def enqueue_state_change(
    service_id: str,
    service_name: str,
    slug: str,
    old_state: str,
    new_state: str,
    incident_id: str | None = None,
) -> None:
    """Queue one state-change mail — the durable automated trigger.

    Called in the health-check path (inside the CRON sweep). A single fast
    insert; delivery happens on the mail job's sweep, so an SMTP outage or a
    process restart never loses a notification.
    """
    doc = MailOutboxDocument(
        service_id=service_id,
        service_name=service_name,
        slug=slug,
        old_state=old_state,
        new_state=new_state,
        incident_id=incident_id,
    )
    database.insert(COLLECTION_MAIL_OUTBOX, doc.model_dump(mode="json"))
    logger.info(
        "mail queued: %s %s -> %s (mail_id=%s)", service_name, old_state, new_state, doc.mail_id
    )


def _classify_outcome(outcome: dict[str, Any]) -> str:
    """Map a fan-out outcome onto an outbox disposition.

        "skipped" in outcome            -> skipped   (no audience at send time)
        "error" in outcome              -> retry     (connection/login-level failure)
        sent == 0 and failed > 0        -> retry     (every recipient failed individually)
        otherwise                       -> sent      (per-recipient stats already recorded)
    """
    if outcome.get("skipped"):
        return "skipped"
    if outcome.get("error"):
        return "retry"
    if outcome.get("sent", 0) == 0 and outcome.get("failed", 0) > 0:
        return "retry"
    return "sent"


def process_outbox_blocking(limit: int = 50) -> OutboxProcessingResult:
    """Deliver due pending mails and update their rows (sync; the CRON job).

    One row = one state-change event; the fan-out inside
    ``send_state_change_blocking`` emails every current subscriber. Retryable
    failures go back to ``pending`` with ``next_attempt_at`` backed off until
    ``OUTBOX_MAX_ATTEMPTS`` is exhausted.
    """
    result = OutboxProcessingResult()
    if not enabled():
        # Credentials not configured (yet): leave everything pending — rows
        # send automatically once SMTP is set up.
        return result

    now = datetime.now(timezone.utc)
    rows = database.find_many(
        COLLECTION_MAIL_OUTBOX,
        {
            "status": "pending",
            "$or": [{"next_attempt_at": None}, {"next_attempt_at": {"$lte": now}}],
        },
        sort=[("created_at", 1)],
        limit=limit,
    )
    for row in rows:
        result.processed += 1
        try:
            outcome = send_state_change_blocking(
                row["service_id"],
                row["service_name"],
                row.get("slug", ""),
                row["old_state"],
                row["new_state"],
                row.get("incident_id"),
            )
        except Exception as exc:  # defensive: the sender normally swallows errors
            outcome = {"sent": 0, "failed": 0, "error": f"{type(exc).__name__}: {exc}"}

        disposition = _classify_outcome(outcome)
        if disposition == "sent":
            result.sent += 1
            database.update_one(
                COLLECTION_MAIL_OUTBOX,
                {"mail_id": row["mail_id"]},
                {"status": "sent", "sent_at": now, "last_error": None, "updated_at": now},
            )
        elif disposition == "skipped":
            result.skipped += 1
            database.update_one(
                COLLECTION_MAIL_OUTBOX,
                {"mail_id": row["mail_id"]},
                {"status": "skipped", "updated_at": now},
            )
        else:
            attempts = int(row.get("attempts", 0)) + 1
            error = outcome.get("error") or f"{outcome.get('failed', 0)} of {outcome.get('failed', 0) + outcome.get('sent', 0)} recipients failed"
            if attempts >= OUTBOX_MAX_ATTEMPTS:
                result.failed += 1
                database.update_one(
                    COLLECTION_MAIL_OUTBOX,
                    {"mail_id": row["mail_id"]},
                    {"status": "failed", "attempts": attempts, "last_error": error, "updated_at": now},
                )
                logger.warning("mail %s failed after %d attempts: %s", row["mail_id"], attempts, error)
            else:
                result.retried += 1
                retry_at = now + timedelta(seconds=OUTBOX_RETRY_SECONDS * attempts)
                database.update_one(
                    COLLECTION_MAIL_OUTBOX,
                    {"mail_id": row["mail_id"]},
                    {
                        "attempts": attempts,
                        "next_attempt_at": retry_at,
                        "last_error": error,
                        "updated_at": now,
                    },
                )
    if result.processed:
        logger.info(
            "mail outbox: processed=%d sent=%d retried=%d failed=%d skipped=%d",
            result.processed, result.sent, result.retried, result.failed, result.skipped,
        )
    return result


async def process_outbox(limit: int = 50) -> OutboxProcessingResult:
    """Async wrapper around the blocking outbox processor (runs it in a thread)."""
    if not enabled():
        return OutboxProcessingResult()
    return await asyncio.to_thread(process_outbox_blocking, limit)
