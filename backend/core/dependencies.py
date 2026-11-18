"""Central role-based access control (RBAC) for Pulse.

One place to authenticate (JWT) and one place to authorize (roles). Routers
declare what they need via ``Depends(...)``:

    from core.dependencies import (
        CurrentUser,
        require_authenticated,
        require_staff,      # admin OR operator
        require_admin,      # admin only
    )

    @router.get("/me")
    def me(user: CurrentUser) -> ...:                     # any signed-in role
        ...

    @router.post("/catalogue")
    def create(..., _: RequireAdmin) -> ...:              # admin only

    @router.patch("/states/{service_id}")
    def upsert(..., _: RequireStaff) -> ...:              # operator or admin

Roles (schemas.auth.Role): ``admin`` > ``operator`` > ``subscriber``.
"""

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from schemas.auth import COLLECTION_USERS

from . import database
from .jwt import verify_access_token

_bearer = HTTPBearer(auto_error=False, description="JWT access token from /auth/login or /auth/register.")

_FORBIDDEN = HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")
_CREDENTIALS = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Auth dependency: verifies the JWT and loads the live account.

    Returns the ``users`` document (minus the password hash). 401 on a missing,
    malformed, expired or invalid token — and when the account was deactivated
    after the token was issued.
    """
    if credentials is None:
        raise _CREDENTIALS
    try:
        claims = verify_access_token(credentials.credentials)
    except Exception:
        raise _CREDENTIALS

    user = database.find_one(COLLECTION_USERS, {"uid": claims["sub"]})
    if user is None or not user.get("active", False):
        # Deactivated or deleted accounts are rejected even with a valid token.
        raise _CREDENTIALS
    return {k: v for k, v in user.items() if k != "hashed_password"}


def require_roles(*allowed: str) -> Callable[[dict], dict]:
    """Build a dependency that only lets through users with one of ``allowed`` roles.

    Raises 403 when the role doesn't match (authentication itself is already
    handled by ``get_current_user``). Usage:

        _: Annotated[dict, Depends(require_roles("admin", "operator"))]
    """

    def dependency(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if user.get("role") not in allowed:
            raise _FORBIDDEN
        return user

    dependency.__doc__ = f"RBAC dependency allowing roles: {', '.join(sorted(allowed))}."
    return dependency


# --- Ready-made guards -------------------------------------------------------
# CurrentUser:             any signed-in account (admin, operator, subscriber)
# RequireStaff:            operator or admin — can write incidents, read metrics/reliability
# RequireAdmin:            admin — manage users, catalogue, states
CurrentUser = Annotated[dict, Depends(get_current_user)]
RequireStaff = Annotated[dict, Depends(require_roles("admin", "operator"))]
RequireAdmin = Annotated[dict, Depends(require_roles("admin"))]


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict | None:
    """Soft auth dependency: the user when a valid token is present, else ``None``.

    Unlike ``get_current_user`` this never raises — useful for public endpoints
    (status page) that can personalize for signed-in visitors but must work for
    anonymous ones.
    """
    if credentials is None:
        return None
    try:
        claims = verify_access_token(credentials.credentials)
    except Exception:
        return None
    user = database.find_one(COLLECTION_USERS, {"uid": claims["sub"]})
    if user is None or not user.get("active", False):
        return None
    return {k: v for k, v in user.items() if k != "hashed_password"}


OptionalUser = Annotated[dict | None, Depends(get_optional_user)]
