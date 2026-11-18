"""Push-notification device tokens (Firebase Cloud Messaging).

Every account can register one or more devices; each device carries the FCM
registration token the CRON pushes to when a monitored service changes state.

Subscription rules (Task 5):
    - subscribers opt in from their dashboard (optional),
    - operators/admins must keep at least one registered device —
      ``GET /dashboard`` reports ``devices.notifications_required`` until they do.

Database: ``device_tokens`` collection
    - unique index on ``fcm_token`` (one registration per device token)
    - index on ``uid`` (list a user's devices)
    - FCM tokens rotate when devices reset or reinstall; re-registering a token
      that already exists re-assigns it to the calling account (the device
      changed hands) instead of failing with a duplicate error.
    - delivery stats are kept per token: ``send_count``/``fail_count`` and
      ``last_error`` — stale devices (FCM reports the token as unregistered)
      are pruned automatically by the sender.

API routes (wired up in Task 5, in ``routers/devices.py``):
    POST   /devices              DeviceTokenCreateRequest -> DeviceTokenResponse   any signed-in role
        * upsert by token; 201 when a new device is registered, 200 when an
          existing token was re-assigned/updated
    GET    /devices              -> DeviceTokenListResponse  any signed-in role
        * the caller's devices only; full tokens are never returned (whoever
          holds a token can push to that device) — a masked preview is enough
          to tell devices apart
    DELETE /devices/{token_id}   -> MessageResponse          any signed-in role
        * removes one of the caller's own subscriptions (unsubscribe)
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import TimestampedModel, new_uid

COLLECTION_DEVICE_TOKENS = "device_tokens"
"""MongoDB collection that stores ``DeviceTokenDocument`` records."""

DEFAULT_DEVICE_LABEL = "Web browser"
"""Label stored when the client does not name the device."""


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class DeviceTokenDocument(TimestampedModel):
    """One subscribed device — document in the ``device_tokens`` collection."""

    token_id: str = Field(
        default_factory=new_uid,
        description="System generated unique id (used to unsubscribe).",
    )
    uid: str = Field(
        description="``uid`` of the account this device is subscribed for.",
    )
    fcm_token: str = Field(
        min_length=16,
        max_length=4096,
        description="Firebase Cloud Messaging registration token (unique).",
    )
    device_label: str | None = Field(
        default=None,
        max_length=100,
        description="Optional human label, e.g. ``Chrome on Windows``.",
    )
    user_agent: str | None = Field(
        default=None,
        max_length=400,
        description="Browser user agent captured at registration time.",
    )
    send_count: int = Field(
        default=0,
        ge=0,
        description="Pushes successfully delivered to this device.",
    )
    fail_count: int = Field(
        default=0,
        ge=0,
        description="Pushes that failed for this device (excluding pruned tokens).",
    )
    last_sent_at: datetime | None = Field(
        default=None,
        description="When the last push reached this device.",
    )
    last_error: str | None = Field(
        default=None,
        description="Error of the last failed push.",
    )


# ---------------------------------------------------------------------------
# API requests
# ---------------------------------------------------------------------------


class DeviceTokenCreateRequest(BaseModel):
    """``POST /devices`` — register (or refresh) one device subscription."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"fcm_token": "dHkbDd…:APA91b…", "device_label": "Chrome on Windows"}]},
    )

    fcm_token: str = Field(min_length=16, max_length=4096, description="FCM registration token from the browser.")
    device_label: str | None = Field(default=None, max_length=100, description="Optional human-readable device name.")


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class DeviceTokenResponse(BaseModel):
    """A registered device as returned by the API (token masked)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "token_id": "9f3c…",
                    "token_preview": "dHkbDd…b2f1",
                    "device_label": "Chrome on Windows",
                    "user_agent": "Mozilla/5.0 …",
                    "created_at": "2026-11-18T09:00:00Z",
                    "updated_at": "2026-11-18T09:00:00Z",
                    "last_sent_at": None,
                    "send_count": 0,
                    "fail_count": 0,
                    "last_error": None,
                }
            ]
        }
    )

    token_id: str = Field(description="Id used to unsubscribe this device.")
    token_preview: str = Field(description="Masked token (first/last characters) so devices can be told apart.")
    device_label: str | None
    user_agent: str | None
    created_at: datetime
    updated_at: datetime
    last_sent_at: datetime | None
    send_count: int
    fail_count: int
    last_error: str | None


class DeviceTokenListResponse(BaseModel):
    """Response of ``GET /devices`` — the caller's own devices."""

    total: int
    tokens: list[DeviceTokenResponse]


class DevicesSummary(BaseModel):
    """Push-subscription state embedded in the dashboard payload."""

    total: int = Field(description="Devices the caller has subscribed.")
    notifications_required: bool = Field(
        description="True for operators/admins with no device yet: subscribing is mandatory for staff.",
    )
    fcm_enabled: bool = Field(
        description="Whether the backend can actually deliver pushes (service-account configured).",
    )
