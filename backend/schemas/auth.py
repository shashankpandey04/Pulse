"""Auth (accounts) schemas: database document + API request/response models.

Every account has: email, password (stored as a bcrypt hash), pfp_link, a system
generated uid, a role and an active flag.

Database: ``users`` collection
    - unique index on ``email``
    - ``hashed_password`` holds a bcrypt hash; raw passwords are never stored
    - every new account starts as ``role="subscriber"``, ``active=True``
    - only admins change ``role``/``active`` (Manage Users)

API routes (wired up in Task 2, in ``routers/auth.py``):
    POST   /auth/register         RegisterRequest         -> AuthResponse      public
        * role is always forced to ``subscriber`` (the request carries no role)
        * 409 when the email is already registered
    POST   /auth/login            LoginRequest            -> AuthResponse      public
        * 401 on bad credentials or a deactivated (``active=False``) account
    GET    /auth/me               -                       -> UserResponse      any signed-in role
    GET    /admin/users           page, page_size (query) -> UserListResponse  admin
    PATCH  /admin/users/{uid}     AdminUserUpdateRequest  -> UserResponse      admin
        * upgrade/downgrade the role and/or activate/deactivate the account
    DELETE /admin/users/{uid}     -                       -> MessageResponse   admin
        * soft delete: the account is deactivated, history is preserved
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .common import TimestampedModel, new_uid

Role = Literal["admin", "operator", "subscriber"]
"""Account role, stored as a plain string holding exactly one of the three roles."""

DEFAULT_ROLE: Role = "subscriber"
"""Every new account is created as a subscriber; only an admin can change it."""

COLLECTION_USERS = "users"
"""MongoDB collection that stores ``UserDocument`` records."""

MAX_PASSWORD_BYTES = 72
"""bcrypt only reads the first 72 bytes of a password."""


# ---------------------------------------------------------------------------
# Database document
# ---------------------------------------------------------------------------


class UserDocument(TimestampedModel):
    """A user account — document in the ``users`` collection.

    Mongo adds its own ``_id`` (ObjectId) on insert; the models leave it out and
    treat it as internal (extra fields are ignored on read).
    """

    uid: str = Field(
        default_factory=new_uid,
        description="System generated unique user id exposed by the API.",
    )
    email: EmailStr = Field(
        description="Unique sign-in email address.",
    )
    hashed_password: str = Field(
        description="Bcrypt hash of the password. Never returned by any API response.",
        examples=["$2b$12$KIXQxQ9Z3nq0u7Xe1Yv1ou5S5wW9oXk1mQ0eJw2b8dCqYvZ6yG7Oa"],
    )
    pfp_link: HttpUrl | None = Field(
        default=None,
        description="Profile picture URL.",
    )
    role: Role = Field(
        default=DEFAULT_ROLE,
        description="One of admin, operator, subscriber. New accounts are always subscriber.",
    )
    active: bool = Field(
        default=True,
        description="False means the account is deactivated and cannot sign in.",
    )


# ---------------------------------------------------------------------------
# API requests
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """``POST /auth/register`` — creates a new account.

    The role is not part of the payload on purpose: every new account is a
    subscriber. Upgrades to operator/admin are done by an admin via
    ``PATCH /admin/users/{uid}``.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "email": "jane@example.com",
                    "password": "S3curePass!",
                    "pfp_link": "https://cdn.example.com/avatars/jane.png",
                }
            ]
        },
    )

    email: EmailStr = Field(description="Email address of the new account (must be unique).")
    password: str = Field(
        min_length=8,
        max_length=MAX_PASSWORD_BYTES,
        description="Plain password (8-72 chars; bcrypt only reads the first 72 bytes).",
    )
    pfp_link: HttpUrl | None = Field(default=None, description="Optional profile picture URL.")


class LoginRequest(BaseModel):
    """``POST /auth/login`` — exchanges credentials for a bearer token."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "email": "jane@example.com",
                    "password": "S3curePass!",
                }
            ]
        },
    )

    email: EmailStr = Field(description="Email address of the account.")
    password: str = Field(description="Plain password as entered by the user.")


class AdminUserUpdateRequest(BaseModel):
    """``PATCH /admin/users/{uid}`` — Manage Users (admin only).

    Only the provided fields are changed; omitted fields keep their current
    value. Used to upgrade/downgrade roles and to activate/deactivate accounts.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"role": "operator"},
                {"active": False},
            ]
        },
    )

    role: Role | None = Field(default=None, description="New role for the account.")
    active: bool | None = Field(default=None, description="Deactivate (False) or reactivate (True) the account.")


# ---------------------------------------------------------------------------
# API responses
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public view of an account — never includes the password hash."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "uid": "3f9d2f4e-6a1b-4c7e-9f0a-2b3c4d5e6f70",
                    "email": "jane@example.com",
                    "pfp_link": "https://cdn.example.com/avatars/jane.png",
                    "role": "subscriber",
                    "active": True,
                    "created_at": "2026-11-18T09:00:00Z",
                    "updated_at": "2026-11-18T09:00:00Z",
                }
            ]
        },
    )

    uid: str = Field(description="System generated unique user id.")
    email: EmailStr
    pfp_link: HttpUrl | None = None
    role: Role
    active: bool
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    """Response of ``POST /auth/register`` and ``POST /auth/login``.

    ``access_token`` is the bearer token to send as
    ``Authorization: Bearer <token>`` (issuance — JWT or DB-backed session
    token — is implemented together with the routers in Task 2).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "user": {
                        "uid": "3f9d2f4e-6a1b-4c7e-9f0a-2b3c4d5e6f70",
                        "email": "jane@example.com",
                        "pfp_link": "https://cdn.example.com/avatars/jane.png",
                        "role": "subscriber",
                        "active": True,
                        "created_at": "2026-11-18T09:00:00Z",
                        "updated_at": "2026-11-18T09:00:00Z",
                    },
                }
            ]
        },
    )

    access_token: str = Field(description="Bearer token for authenticated requests.")
    token_type: str = Field(default="bearer", description="Always ``bearer``.")
    user: UserResponse = Field(description="The authenticated account.")


class UserListResponse(BaseModel):
    """Response of ``GET /admin/users`` — paginated list of accounts."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 42,
                    "page": 1,
                    "page_size": 20,
                    "users": [],
                }
            ]
        },
    )

    total: int = Field(description="Total number of accounts matching the query.")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of accounts per page.")
    users: list[UserResponse] = Field(description="Accounts on this page.")
