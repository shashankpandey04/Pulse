"""Shared helpers and generic API schemas used across every Pulse domain."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Current time in UTC.

    Timezone-aware on purpose: datetimes are stored as UTC in Mongo (connect the
    client with ``MongoClient(..., tz_aware=True)`` so reads come back aware).
    """
    return datetime.now(timezone.utc)


def new_uid() -> str:
    """System generated unique id (uuid4) used as the public identifier of a record.

    Mongo's ``_id`` (ObjectId) stays internal; every record additionally carries an
    app-level id — ``uid`` for accounts, ``service_id``/``state_id`` for the
    catalogue and state configuration.
    """
    return str(uuid4())


class TimestampedModel(BaseModel):
    """Mixin for database documents: creation and last-update timestamps."""

    created_at: datetime = Field(
        default_factory=utcnow,
        description="UTC time the record was created.",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        description="UTC time the record was last updated.",
    )


class MessageResponse(BaseModel):
    """Acknowledgement body for action endpoints (e.g. DELETE)."""

    message: str = Field(examples=["Service deleted."])


class ErrorResponse(BaseModel):
    """Error body returned on failures (matches FastAPI's ``HTTPException`` shape)."""

    detail: str = Field(examples=["Service not found."])
