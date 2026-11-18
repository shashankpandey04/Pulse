"""Service Catalogue schemas: database document + API request/response models.

The catalogue is the registry of services Pulse watches. Each entry carries its
health URL, how often to check it, its owner and its reliability target.

Database: ``services`` collection
    - unique index on ``service_id`` (app-level id) and on ``slug``
    - ``name`` should also be indexed (unique) to avoid duplicate entries
    - ``HttpUrl``/``EmailStr`` values are stored as strings — dump documents with
      ``model_dump(mode="json")`` before inserting into Mongo
    - creating a service should provision a default state configuration for it
      in the ``service_states`` collection (see ``schemas/state.py``)

API routes (wired up in Task 2, in ``routers/catalogue.py``):
    POST   /catalogue               ServiceCreateRequest   -> ServiceResponse      admin
        * 409 when ``name``/``slug`` already exist; 404 when ``owner_email`` is
          not a registered account
    GET    /catalogue               page, page_size (query) -> ServiceListResponse admin, operator
    GET    /catalogue/{service_id}  -                      -> ServiceResponse      admin, operator
    PATCH  /catalogue/{service_id}  ServiceUpdateRequest   -> ServiceResponse      admin
    DELETE /catalogue/{service_id}  -                      -> MessageResponse      admin
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

from schemas.state import HealthState

from .common import TimestampedModel, new_uid

COLLECTION_SERVICES = "services"
"""MongoDB collection that stores ``ServiceDocument`` records."""

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
"""URL-friendly slug: lowercase words separated by single dashes (``checkout-api``)."""


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class ServiceMonitoring(BaseModel):
    """Live monitoring counters for one service — written only by the CRON.

    Embedded in ``ServiceDocument.monitoring``; the catalogue API never sets
    these fields directly.
    """

    current_state: HealthState = Field(
        default="healthy",
        description="Last evaluated health state (healthy/down/slow/flaky).",
    )
    consecutive_failures: int = Field(default=0, description="Failed checks in a row right now.")
    consecutive_successes: int = Field(default=0, description="Successful checks in a row right now.")
    last_check_at: datetime | None = Field(default=None, description="When the last check ran.")
    last_latency_ms: int | None = Field(default=None, description="Latency of the last completed check.")
    last_error: str | None = Field(default=None, description="Error message of the last failed check.")
    next_check_at: datetime | None = Field(
        default=None,
        description="When this service is next due for a check (its own schedule).",
    )


class ServiceDocument(TimestampedModel):
    """A registered service — document in the ``services`` collection.

    Mongo adds its own ``_id`` (ObjectId) on insert; the models leave it out and
    treat it as internal (extra fields are ignored on read).
    """

    service_id: str = Field(
        default_factory=new_uid,
        description="System generated unique id of the service.",
    )
    name: str = Field(
        min_length=1,
        max_length=120,
        description="Human readable name, e.g. ``Checkout API`` (unique).",
    )
    slug: str = Field(
        pattern=SLUG_PATTERN.pattern,
        description="URL-friendly unique identifier used on the public status page, e.g. ``checkout-api``.",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Short description shown on the status page.",
    )
    health_url: HttpUrl = Field(
        description="Health endpoint URL that the monitor requests on every check.",
    )
    check_interval_seconds: int = Field(
        default=60,
        ge=5,
        le=86_400,
        description="How often the health URL is checked, in seconds.",
    )
    timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Per-check request timeout; a check that exceeds it counts as a no-response.",
    )
    owner_uid: str = Field(
        description="``uid`` of the account that owns this service.",
    )
    owner_email: EmailStr = Field(
        description="Email of the owner, denormalized for display on the status page.",
    )
    reliability_target: float = Field(
        default=99.9,
        gt=0.0,
        le=100.0,
        description="Target uptime percentage (e.g. 99.9); reliability is reported against it.",
    )
    enabled: bool = Field(
        default=True,
        description="When False the monitor pauses checks for this service.",
    )
    monitoring: ServiceMonitoring = Field(
        default_factory=ServiceMonitoring,
        description="Live check counters maintained by the health-check CRON.",
    )

    @model_validator(mode="after")
    def timeout_must_be_shorter_than_interval(self) -> "ServiceDocument":
        """A single check must time out well before the next check is due."""
        if self.timeout_seconds >= self.check_interval_seconds:
            raise ValueError("timeout_seconds must be smaller than check_interval_seconds")
        return self


# ---------------------------------------------------------------------------
# API requests
# ---------------------------------------------------------------------------


class ServiceCreateRequest(BaseModel):
    """``POST /catalogue`` — registers a service to watch (admin only).

    ``slug`` is derived from ``name`` when omitted. ``owner_email`` must belong
    to an existing account; the router resolves it to ``owner_uid``.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "Checkout API",
                    "slug": "checkout-api",
                    "description": "Handles cart checkout and payments.",
                    "health_url": "https://api.example.com/health",
                    "check_interval_seconds": 60,
                    "timeout_seconds": 10,
                    "owner_email": "team-payments@example.com",
                    "reliability_target": 99.9,
                    "enabled": True,
                }
            ]
        },
    )

    name: str = Field(min_length=1, max_length=120, description="Human readable service name (unique).")
    slug: str | None = Field(
        default=None,
        pattern=SLUG_PATTERN.pattern,
        description="URL-friendly unique identifier; derived from ``name`` when omitted.",
    )
    description: str | None = Field(default=None, max_length=500)
    health_url: HttpUrl = Field(description="Health endpoint URL to monitor.")
    check_interval_seconds: int = Field(default=60, ge=5, le=86_400, description="Seconds between health checks.")
    timeout_seconds: int = Field(default=10, ge=1, le=60, description="Per-check request timeout in seconds.")
    owner_email: EmailStr = Field(description="Email of the owning account (resolved to ``owner_uid``).")
    reliability_target: float = Field(default=99.9, gt=0.0, le=100.0, description="Target uptime percentage.")
    enabled: bool = Field(default=True, description="Start monitoring immediately (default) or paused.")

    @model_validator(mode="after")
    def timeout_must_be_shorter_than_interval(self) -> "ServiceCreateRequest":
        """A single check must time out well before the next check is due."""
        if self.timeout_seconds >= self.check_interval_seconds:
            raise ValueError("timeout_seconds must be smaller than check_interval_seconds")
        return self


class ServiceUpdateRequest(BaseModel):
    """``PATCH /catalogue/{service_id}`` — partial update (admin only).

    Only the provided fields are changed; omitted fields keep their current
    value. Cross-field validation (e.g. timeout vs interval) is done in the
    router against the merged document.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "check_interval_seconds": 30,
                    "reliability_target": 99.95,
                }
            ]
        },
    )

    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN.pattern)
    description: str | None = Field(default=None, max_length=500)
    health_url: HttpUrl | None = Field(default=None)
    check_interval_seconds: int | None = Field(default=None, ge=5, le=86_400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    owner_email: EmailStr | None = Field(default=None, description="Reassign ownership to this account.")
    reliability_target: float | None = Field(default=None, gt=0.0, le=100.0)
    enabled: bool | None = Field(default=None)


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class ServiceResponse(BaseModel):
    """A catalogue entry as returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "service_id": "8c1e7a2b-4d3f-4a5b-9c6d-1e2f3a4b5c6d",
                    "name": "Checkout API",
                    "slug": "checkout-api",
                    "description": "Handles cart checkout and payments.",
                    "health_url": "https://api.example.com/health",
                    "check_interval_seconds": 60,
                    "timeout_seconds": 10,
                    "owner_uid": "3f9d2f4e-6a1b-4c7e-9f0a-2b3c4d5e6f70",
                    "owner_email": "team-payments@example.com",
                    "reliability_target": 99.9,
                    "enabled": True,
                    "created_at": "2026-11-18T09:00:00Z",
                    "updated_at": "2026-11-18T09:00:00Z",
                }
            ]
        },
    )

    service_id: str = Field(description="System generated unique service id.")
    name: str
    slug: str
    description: str | None = None
    health_url: HttpUrl
    check_interval_seconds: int
    timeout_seconds: int
    owner_uid: str
    owner_email: EmailStr
    reliability_target: float
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ServiceListResponse(BaseModel):
    """Response of ``GET /catalogue`` — paginated list of services."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 7,
                    "page": 1,
                    "page_size": 20,
                    "services": [],
                }
            ]
        },
    )

    total: int = Field(description="Total number of services matching the query.")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of services per page.")
    services: list[ServiceResponse] = Field(description="Services on this page.")
