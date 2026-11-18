"""JWT issuing/verification for the frontend client (PyJWT, HS256).

Tokens carry the user's ``uid``, ``email`` and ``role`` so RBAC decisions never
need a DB hit for the role itself; the account's live ``active`` flag is still
checked by the auth dependency.
"""

from datetime import datetime, timedelta, timezone

import jwt

from . import config


class TokenError(Exception):
    """Raised when a token is invalid, expired or untrusted."""


def create_access_token(
    *,
    uid: str,
    email: str,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """Issue a signed bearer token for an authenticated account."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or config.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": uid,
        "email": email,
        "role": role,
        "iat": now,
        "exp": expire,
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict:
    """Decode + validate a token and return its claims.

    Raises ``TokenError`` on bad signature, expiry, audience/issuer mismatch or
    any structural problem — callers turn that into a 401.
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
            audience=config.JWT_AUDIENCE,
            issuer=config.JWT_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    if not isinstance(payload.get("sub"), str) or not payload.get("sub"):
        raise TokenError("Invalid token: missing subject.")
    return payload
