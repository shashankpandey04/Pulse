"""Durable mail outbox: state-change emails queued by the CRON, sent by the CRON.

The health-check CRON detects state changes, but SMTP can be slow, down or
simply not configured yet at that moment. Instead of firing mail inside the
check task — where any failure or a restart would silently lose it — the
change is **enqueued** in the same request path as one pending row here, and a
CRON job (``core.scheduler``'s mail dispatch, every sweep) drains the queue:

    health check ──▶ insert pending row ──▶ mail CRON job ──▶ SMTP fan-out
                                                 │ failure → retry with backoff
                                                 │ exhausted → ``failed`` (kept for inspection)

Database: ``mail_outbox`` collection
    - index ``(status, next_attempt_at)`` for the dispatcher query
    - rows are kept after delivery (``sent`` / ``failed`` / ``skipped``) for
      observability; per-recipient stats live on the ``email_subscriptions``
      documents.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import TimestampedModel, new_uid

COLLECTION_MAIL_OUTBOX = "mail_outbox"
"""MongoDB collection that stores ``MailOutboxDocument`` records."""

MailOutboxStatus = Literal["pending", "sent", "failed", "skipped"]
"""
    pending  — waiting for the mail CRON job (or its next retry)
    sent     — fanned out to the subscribers (per-recipient stats on subscriptions)
    failed   — retry budget exhausted; ``last_error`` says why
    skipped  — nothing to do at send time (no subscribers / no active users)
"""


class MailOutboxDocument(TimestampedModel):
    """One service state change awaiting email delivery."""

    mail_id: str = Field(default_factory=new_uid)
    service_id: str
    service_name: str
    slug: str = Field(description="Service slug for the status-page link in the mail body.")
    old_state: str
    new_state: str
    incident_id: str | None = None
    status: MailOutboxStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    next_attempt_at: datetime | None = Field(
        default=None,
        description="Earliest time the mail job may retry; null = immediately.",
    )
    sent_at: datetime | None = None
    last_error: str | None = None


class OutboxProcessingResult(BaseModel):
    """Counters returned by one mail-job run."""

    processed: int = Field(default=0, description="Rows examined.")
    sent: int = Field(default=0, description="Rows delivered to subscribers.")
    retried: int = Field(default=0, description="Rows that failed and will be retried.")
    failed: int = Field(default=0, description="Rows that exhausted the retry budget.")
    skipped: int = Field(default=0, description="Rows with no audience at send time.")
