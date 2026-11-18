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
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from schemas.auth import COLLECTION_USERS
from schemas.email_subscription import COLLECTION_EMAIL_SUBSCRIPTIONS

from . import config, database

logger = logging.getLogger("pulse.mailer")


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
