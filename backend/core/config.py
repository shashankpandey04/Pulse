"""Environment-driven settings for the Pulse backend (plain module, no extra deps)."""

import os

MONGO_URI: str = os.getenv("PULSE_MONGO_URI", "mongodb://localhost:27017")
"""Connection string for MongoDB."""

MONGO_DB: str = os.getenv("PULSE_MONGO_DB", "pulse")
"""Database name."""

JWT_SECRET: str = os.getenv("PULSE_JWT_SECRET", "pulse-dev-secret-change-me-0123456789abcdef0123456789abcdef")
"""HMAC signing key for JWTs. Override in production via PULSE_JWT_SECRET."""

JWT_ALGORITHM: str = "HS256"
JWT_AUDIENCE: str = "pulse-frontend"
JWT_ISSUER: str = "pulse-backend"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("PULSE_TOKEN_MINUTES", "720"))

WEBHOOK_URL: str = os.getenv("PULSE_WEBHOOK_URL", "http://localhost:9900")
"""Webhook receiver that stands in for chat/email/paging (base URL)."""

FIREBASE_CREDENTIALS: str | None = os.getenv("PULSE_FIREBASE_CREDENTIALS")
"""Path to a Firebase service-account JSON used by the FCM push sender.

When unset (or the file is missing) the sender is disabled: device
registrations and the dashboard keep working, but state changes are not
pushed — mirroring how the webhook receiver may simply not be running.
"""

HEALTH_CHECK_JITTER_SECONDS: float = 0.0
"""Optional random delay added per check; keep 0 for deterministic tests."""
