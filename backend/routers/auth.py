"""Auth & user-management routes (see ``schemas/auth.py`` for the API contract).

    POST   /auth/register          public    -> AuthResponse   (role forced to subscriber)
    POST   /auth/login             public    -> AuthResponse   (401 on bad creds / deactivated)
    GET    /auth/me                any role  -> UserResponse
    GET    /admin/users            admin     -> UserListResponse
    PATCH  /admin/users/{uid}      admin     -> UserResponse   (upgrade/downgrade roles, activate)
    DELETE /admin/users/{uid}      admin     -> MessageResponse (soft delete: active=False)
"""

import logging

import bcrypt
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from core.dependencies import CurrentUser, RequireAdmin
from core.jwt import create_access_token
from schemas.auth import (
    COLLECTION_USERS,
    AdminUserUpdateRequest,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserDocument,
    UserListResponse,
    UserResponse,
)

from core import database
from schemas.common import MessageResponse, utcnow

logger = logging.getLogger("pulse.auth")
router = APIRouter(tags=["auth"])

_ERROR = {
    "email_taken": HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists."),
    "bad_credentials": HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."),
    "not_found": HTTPException(status.HTTP_404_NOT_FOUND, detail="Account not found."),
}


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _to_response(user: dict) -> UserResponse:
    return UserResponse.model_validate(user)


def _issue_token(user: dict) -> AuthResponse:
    token = create_access_token(uid=user["uid"], email=user["email"], role=user["role"])
    return AuthResponse(access_token=token, user=_to_response(user))


# ---------------------------------------------------------------------------
# Public: register / login
# ---------------------------------------------------------------------------


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> AuthResponse:
    """Create an account. New accounts are always ``subscriber`` + ``active``."""
    document = UserDocument(
        email=payload.email,
        hashed_password=_hash_password(payload.password),
        pfp_link=payload.pfp_link,
    )
    try:
        database.insert(COLLECTION_USERS, document.model_dump(mode="json"))
    except DuplicateKeyError:
        raise _ERROR["email_taken"]
    except ValueError:
        # bcrypt >= 5 raises for >72-byte passwords; the schema caps length, so
        # this is just a safety net mapped to a clean 422-style rejection.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password too long.")
    logger.info("registered new account uid=%s", document.uid)
    return _issue_token(document.model_dump())


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    """Exchange credentials for a bearer token."""
    user = database.find_one(COLLECTION_USERS, {"email": payload.email})
    if user is None or not _verify_password(payload.password, user.get("hashed_password", "")):
        # Same error for unknown email and wrong password (no account enumeration).
        raise _ERROR["bad_credentials"]
    if not user.get("active", False):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="This account has been deactivated.")
    return _issue_token(user)


# ---------------------------------------------------------------------------
# Authenticated: profile
# ---------------------------------------------------------------------------


@router.get("/auth/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """The signed-in account (from the bearer token)."""
    return _to_response(user)


# ---------------------------------------------------------------------------
# Admin: manage users
# ---------------------------------------------------------------------------


@router.get("/admin/users", response_model=UserListResponse)
def list_users(
    _: RequireAdmin,
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = Query(None, pattern="^(admin|operator|subscriber)$", description="Filter by role."),
    active: bool | None = Query(None, description="Filter by activation state."),
    search: str | None = Query(None, min_length=1, max_length=120, description="Case-insensitive email substring."),
) -> UserListResponse:
    """Paginated list of accounts with optional filters."""
    query: dict = {}
    if role is not None:
        query["role"] = role
    if active is not None:
        query["active"] = active
    if search:
        query["email"] = {"$regex": search, "$options": "i"}

    total = database.count(COLLECTION_USERS, query)
    users = database.find_many(
        COLLECTION_USERS,
        query,
        sort=[("created_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return UserListResponse(total=total, page=page, page_size=page_size, users=[_to_response(u) for u in users])


@router.patch("/admin/users/{uid}", response_model=UserResponse)
def admin_update_user(uid: str, payload: AdminUserUpdateRequest, admin: RequireAdmin) -> UserResponse:
    """Upgrade/downgrade a role and/or activate/deactivate an account.

    An admin cannot demote or deactivate their own account (prevents locking
    yourself out of user management).
    """
    user = database.find_one(COLLECTION_USERS, {"uid": uid})
    if user is None:
        raise _ERROR["not_found"]

    is_self = user["uid"] == admin["uid"]
    changes: dict = {}
    if payload.role is not None:
        if is_self and payload.role != "admin":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="You cannot change your own role.")
        changes["role"] = payload.role
    if payload.active is not None:
        if is_self and not payload.active:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="You cannot deactivate your own account.")
        changes["active"] = payload.active

    if changes:
        changes["updated_at"] = utcnow()
        database.update_one(COLLECTION_USERS, {"uid": uid}, changes)
        user = database.find_one(COLLECTION_USERS, {"uid": uid})
    logger.info("admin %s updated user uid=%s fields=%s", admin["uid"], uid, list(changes))
    return _to_response(user)


@router.delete("/admin/users/{uid}", response_model=MessageResponse)
def admin_deactivate_user(uid: str, admin: RequireAdmin) -> MessageResponse:
    """Soft delete: the account is deactivated and its history is preserved."""
    if uid == admin["uid"]:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You cannot deactivate your own account.")
    changes = {"active": False, "updated_at": utcnow()}
    if not database.update_one(COLLECTION_USERS, {"uid": uid}, changes):
        raise _ERROR["not_found"]
    return MessageResponse(message=f"Account {uid} deactivated.")
