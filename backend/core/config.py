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

Kept for the dormant FCM backend machinery; the user-facing notification
channel is now email (see SMTP_* below). When unset the push sender stays
disabled — exactly like before.
"""

SMTP_HOST: str = os.getenv("PULSE_SMTP_HOST", "smtp.gmail.com")
"""Outgoing SMTP server (Gmail for the Google App Password flow)."""

SMTP_PORT: int = int(os.getenv("PULSE_SMTP_PORT", "587"))
"""SMTP port; 587 uses STARTTLS, 465 would use implicit SSL."""

SMTP_USER: str | None = os.getenv("PULSE_SMTP_USER")
"""Login user — the Gmail address mail is sent from."""

SMTP_PASSWORD: str | None = os.getenv("PULSE_SMTP_PASSWORD")
"""Login password — for Gmail a 16-character **App Password** (not the
account password). When user+password are unset the mailer is disabled and
subscriptions keep working without deliveries, mirroring the FCM stance."""

SMTP_FROM: str | None = os.getenv("PULSE_SMTP_FROM")
"""From address; defaults to ``SMTP_USER`` when unset."""

PUBLIC_URL: str = os.getenv("PULSE_PUBLIC_URL", "http://localhost:3000")
"""Base URL of the frontend, used for the status-page links in emails."""

HEALTH_CHECK_JITTER_SECONDS: float = 0.0
"""Optional random delay added per check; keep 0 for deterministic tests."""
