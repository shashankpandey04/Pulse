"""Firebase Cloud Messaging sender: pushes service state changes to subscribers.

Initialized once at startup from ``PULSE_FIREBASE_CREDENTIALS`` (path to a
service-account JSON). Without credentials the sender is *disabled*: device
registrations and the dashboard keep working, state changes are simply not
pushed (same graceful stance as the webhook receiver being offline).

Fan-out rule (Task 5): when the CRON observes a service state change, every
active account's registered device gets one push naming the service and the
``old -> new`` state. Per-device outcomes are recorded on the token document;
tokens Firebase reports as unregistered (device reset, app reinstalled) are
pruned automatically so dead devices never receive further pushes.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from . import config, database
from schemas.auth import COLLECTION_USERS
from schemas.device import COLLECTION_DEVICE_TOKENS

logger = logging.getLogger("pulse.fcm")

_enabled = False
"""True once a service account was loaded and pushes can be delivered."""


def init_firebase() -> bool:
    """Load the service account at startup (idempotent). Returns True when enabled."""
    global _enabled
    path = config.FIREBASE_CREDENTIALS
    if not path:
        logger.info("FCM disabled: PULSE_FIREBASE_CREDENTIALS not set")
        return False
    if not os.path.isfile(path):
        logger.warning("FCM disabled: service-account file not found: %s", path)
        return False
    import firebase_admin
    from firebase_admin import credentials

    try:
        # initialize_app only once per process; a second call raises.
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.Certificate(path))
    _enabled = True
    logger.info("FCM enabled (service account %s)", os.path.basename(path))
    return True


def enabled() -> bool:
    """Whether pushes can actually be delivered."""
    return _enabled


def _active_uids() -> set[str]:
    """uids of accounts that may receive pushes (registered and active)."""
    rows = database.get_db()[COLLECTION_USERS].find({"active": True}, {"uid": 1})
    return {r["uid"] for r in rows}


def _mask(token: str) -> str:
    return f"{token[:6]}…{token[-4:]}" if len(token) > 12 else "…"


def send_state_change_blocking(
    service_id: str,
    service_name: str,
    old_state: str,
    new_state: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Deliver one push per registered device of every active account (sync).

    Runs in a worker thread (``asyncio.to_thread``) because the Firebase Admin
    SDK is synchronous. Returns counters for logging; database/HTTP failures
    never propagate — monitoring must not break over notifications.
    """
    if not _enabled:
        return {"sent": 0, "failed": 0, "skipped": "fcm not configured"}

    from firebase_admin import messaging

    uids = _active_uids()
    if not uids:
        return {"sent": 0, "failed": 0, "skipped": "no active users"}
    devices = list(database.get_db()[COLLECTION_DEVICE_TOKENS].find({"uid": {"$in": list(uids)}}))
    if not devices:
        return {"sent": 0, "failed": 0, "skipped": "no subscribed devices"}

    title = f"{service_name} is {new_state}"
    body = f"State changed from {old_state} to {new_state}."
    if incident_id:
        body += " Incident opened."
    data = {
        "kind": "state_change",
        "service_id": service_id,
        "service_name": service_name,
        "old_state": old_state,
        "new_state": new_state,
        "incident_id": incident_id or "",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data,
            token=device["fcm_token"],
        )
        for device in devices
    ]

    sent = failed = pruned = 0
    now = datetime.now(timezone.utc)
    try:
        # Per-message outcomes land in the batch response; only transport-level
        # trouble (auth/quota/network) raises.
        batch = messaging.send_each(messages)
    except Exception as exc:  # e.g. quota/auth trouble: record on every device
        logger.warning("FCM send_all failed: %s", exc)
        for device in devices:
            database.update_one(
                COLLECTION_DEVICE_TOKENS,
                {"token_id": device["token_id"]},
                {"fail_count": device.get("fail_count", 0) + 1, "last_error": f"{type(exc).__name__}: {exc}"},
            )
        return {"sent": 0, "failed": len(devices), "error": str(exc)}

    for device, response in zip(devices, batch.responses):
        token_id = device["token_id"]
        if response.success:
            sent += 1
            database.update_one(
                COLLECTION_DEVICE_TOKENS,
                {"token_id": token_id},
                {"send_count": device.get("send_count", 0) + 1, "last_sent_at": now, "last_error": None},
            )
        else:
            exception = response.exception
            if isinstance(exception, messaging.UnregisteredError):
                # Stale token (device reset / app uninstalled): unsubscribe it.
                database.delete_one(COLLECTION_DEVICE_TOKENS, {"token_id": token_id})
                pruned += 1
                logger.info("pruned unregistered FCM token %s (%s)", _mask(device["fcm_token"]), token_id)
            else:
                failed += 1
                database.update_one(
                    COLLECTION_DEVICE_TOKENS,
                    {"token_id": token_id},
                    {
                        "fail_count": device.get("fail_count", 0) + 1,
                        "last_error": f"{type(exception).__name__}: {exception}",
                    },
                )
    return {"sent": sent, "failed": failed, "pruned": pruned}


async def send_state_change(
    service_id: str,
    service_name: str,
    old_state: str,
    new_state: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """Async wrapper around the blocking sender (runs it in a thread)."""
    if not _enabled:
        return {"sent": 0, "failed": 0, "skipped": "fcm not configured"}
    return await asyncio.to_thread(
        send_state_change_blocking, service_id, service_name, old_state, new_state, incident_id
    )
