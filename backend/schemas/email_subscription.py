"""Email notification subscriptions (the mail replacement for FCM pushes).

Every account can subscribe with **its own account email**; on each service
state change the backend emails every subscribed, active user individually
(recipient addresses are never shared between subscribers). This lives in its
own collection, separate from the FCM ``device_tokens`` — the Firebase system
stays in the backend (dormant) but is no longer the user-facing channel.

Database: ``email_subscriptions`` collection
    - unique index on ``uid`` (one subscription per account — the account
      email *is* the subscription address)
    - unique index on ``email`` (defensive)
    - delivery stats per subscription, same pattern as FCM device tokens:
      ``send_count``/``fail_count`` and ``last_sent_at``/``last_error``.

API routes (``routers/email_subscriptions.py``):
    POST   /email-subscriptions   -> EmailSubscriptionResponse       any signed-in role
        * subscribes the caller's account email; 201 when newly created,
          200 when the account was already subscribed
    GET    /email-subscriptions   -> EmailSubscriptionStatusResponse
        * the caller's subscription, or ``subscription: null``
    DELETE /email-subscriptions   -> 204
        * unsubscribe (404 when not subscribed)
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from .common import TimestampedModel, new_uid

COLLECTION_EMAIL_SUBSCRIPTIONS = "email_subscriptions"
"""MongoDB collection that stores ``EmailSubscriptionDocument`` records."""


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class EmailSubscriptionDocument(TimestampedModel):
    """One email subscription — document in ``email_subscriptions``."""

    subscription_id: str = Field(
        default_factory=new_uid,
        description="System generated unique id.",
    )
    uid: str = Field(
        description="``uid`` of the subscribed account.",
    )
    email: EmailStr = Field(
        description="The account's email address — the subscription address.",
    )
    send_count: int = Field(
        default=0,
        ge=0,
        description="State-change emails delivered to this address.",
    )
    fail_count: int = Field(
        default=0,
        ge=0,
        description="State-change emails that failed for this address.",
    )
    last_sent_at: datetime | None = Field(
        default=None,
        description="When the last email reached this address.",
    )
    last_error: str | None = Field(
        default=None,
        description="Error of the last failed delivery.",
    )


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class EmailSubscriptionResponse(BaseModel):
    """A subscription as returned by the API."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "subscription_id": "9f3c…",
                    "email": "viewer@example.com",
                    "created_at": "2026-11-18T09:00:00Z",
                    "updated_at": "2026-11-18T09:00:00Z",
                    "send_count": 0,
                    "fail_count": 0,
                    "last_sent_at": None,
                    "last_error": None,
                }
            ]
        }
    }

    subscription_id: str
    email: str
    created_at: datetime
    updated_at: datetime
    send_count: int
    fail_count: int
    last_sent_at: datetime | None
    last_error: str | None


class EmailSubscriptionStatusResponse(BaseModel):
    """Response of ``GET /email-subscriptions``."""

    subscription: EmailSubscriptionResponse | None


class EmailNotificationsSummary(BaseModel):
    """Email-subscription state embedded in the dashboard payload."""

    subscribed: bool = Field(description="Whether the caller is subscribed via email.")
    email: str | None = Field(default=None, description="The subscribed address (when subscribed).")
    notifications_required: bool = Field(
        description="True for operators/admins with no subscription: subscribing is mandatory for staff.",
    )
