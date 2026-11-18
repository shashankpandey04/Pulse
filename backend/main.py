"""Pulse backend — FastAPI application entrypoint.

Run with:  uvicorn main:app --reload   (from the ``backend`` folder)

Startup/shutdown resources are managed by the lifespan context manager (not the
deprecated ``@app.on_event``): MongoDB indexes, the shared HTTP client for the
monitor, and the APScheduler ``AsyncIOScheduler`` that runs the health-check
CRON directly on this process's asyncio event loop.
"""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from core import database, fcm, health_check, mailer
from core import config
from core.health_check import drain_notifications
from core.scheduler import build_scheduler
from routers import (
    auth,
    catalogue,
    dashboard,
    devices,
    email_subscriptions,
    incidents,
    metrics,
    notification,
    public,
    reliability,
    state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pulse.main")


def _bootstrap_admin() -> None:
    """Create the first admin account from env vars (idempotent).

    Registration always creates subscribers, so ops provision the first admin by
    setting PULSE_ADMIN_EMAIL / PULSE_ADMIN_PASSWORD before starting the server.
    Skipped when an admin already exists.
    """
    import bcrypt

    from schemas.auth import COLLECTION_USERS, UserDocument

    email = os.getenv("PULSE_ADMIN_EMAIL")
    password = os.getenv("PULSE_ADMIN_PASSWORD")
    if not email or not password:
        return
    if database.find_one(COLLECTION_USERS, {"role": "admin"}):
        return
    admin = UserDocument(
        email=email,
        hashed_password=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role="admin",
    )
    try:
        database.insert(COLLECTION_USERS, admin.model_dump(mode="json"))
        logger.info("bootstrapped admin account uid=%s", admin.uid)
    except Exception:
        logger.warning("admin bootstrap skipped (%s already exists?)", email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup -------------------------------------------------------------
    database.ensure_indexes()
    _bootstrap_admin()
    fcm.init_firebase()

    http_client = httpx.AsyncClient(timeout=10.0)
    health_check.set_http_client(http_client)

    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Pulse backend started (mongo=%s db=%s)", config.MONGO_URI, config.MONGO_DB)

    yield

    # --- shutdown ------------------------------------------------------------
    scheduler.shutdown(wait=False)
    await drain_notifications()
    await http_client.aclose()
    health_check.set_http_client(None)
    database.close_client()
    logger.info("Pulse backend stopped")


app = FastAPI(
    title="Pulse",
    description="Status & incident hub: continuous health checks, incident tracking, "
    "reliability against targets, and a public status page.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(catalogue.router)
app.include_router(state.router)
app.include_router(devices.router)
app.include_router(email_subscriptions.router)
app.include_router(incidents.router)
app.include_router(metrics.router)
app.include_router(reliability.router)
app.include_router(public.router)
app.include_router(notification.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe for the Pulse backend itself."""
    return {"status": "ok", "service": "pulse"}

if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")    