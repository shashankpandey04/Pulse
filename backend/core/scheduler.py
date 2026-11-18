"""APScheduler wiring: the health-check CRON on FastAPI's asyncio event loop.

An ``AsyncIOScheduler`` is started inside the FastAPI lifespan (startup) and
shut down on exit. Two jobs run every ``SWEEP_INTERVAL_SECONDS``:

    health sweep   for each enabled service whose ``monitoring.next_check_at``
                   is due: claim it atomically and run its check as an
                   independent asyncio task

    mail dispatch  deliver the due ``mail_outbox`` rows (state-change emails
                   queued by the checks) — retries with backoff, survives
                   restarts

Consequences of this design:
    - every service runs on **its own schedule** (``check_interval_seconds``),
      not on a global cadence;
    - one slow/hanging service never holds up the others — checks run
      concurrently, each with its own per-check timeout, so the sweep itself
      returns immediately after dispatching.

New, edited or deleted services are picked up by the next sweep automatically;
no restart is needed when the catalogue changes.
"""

import asyncio
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from schemas.catalogue import COLLECTION_SERVICES

from . import database, mailer
from .health_check import drain_notifications, run_check, utcnow

logger = logging.getLogger("pulse.scheduler")

SWEEP_INTERVAL_SECONDS = 10
"""How often the sweep looks for services due for a check."""

MISFIRE_GRACE_SECONDS = 30
"""How long a missed sweep (event loop busy) may fire late before being dropped."""


async def run_sweep() -> None:
    """Dispatch due checks concurrently; never blocks on any single service."""
    now = utcnow()
    services = database.find_many(COLLECTION_SERVICES, {"enabled": True})
    tasks: list[asyncio.Task] = []

    for service in services:
        interval = service["check_interval_seconds"]
        # Atomic claim: the first sweep to win sets the next slot, so overlapping
        # sweeps (or a slow previous check) never double-run the same service.
        # ``next_check_at`` may be null/missing right after registration.
        claimed = database.get_db()[COLLECTION_SERVICES].update_one(
            {
                "service_id": service["service_id"],
                "$or": [
                    {"monitoring.next_check_at": None},
                    {"monitoring.next_check_at": {"$exists": False}},
                    {"monitoring.next_check_at": {"$lte": now}},
                ],
            },
            {"$set": {"monitoring.next_check_at": now + timedelta(seconds=interval)}},
        )
        if claimed.modified_count:
            tasks.append(asyncio.create_task(_check_isolated(service), name=f"check:{service['service_id']}"))

    if tasks:
        logger.info("sweep dispatched %d check(s)", len(tasks))
        # Independent tasks: gather with return_exceptions so one crash never
        # cancels the others.
        await asyncio.gather(*tasks, return_exceptions=True)
        await drain_notifications()  # let webhook POSTs finish before returning


async def _check_isolated(service: dict) -> None:
    """Run one service's check, converting any crash into a log entry."""
    try:
        await run_check(service)
    except Exception:
        logger.exception("health check crashed for service %s", service["service_id"])


async def run_mail_dispatch() -> None:
    """Deliver due state-change mails queued by the checks (Task 8).

    A no-op unless the outbox has due rows and SMTP is configured; rows that
    cannot be delivered go back to ``pending`` with a backed-off
    ``next_attempt_at`` until the retry budget is exhausted.
    """
    try:
        await mailer.process_outbox()
    except Exception:
        logger.exception("mail dispatch crashed")


def build_scheduler() -> AsyncIOScheduler:
    """The scheduler with the sweep + mail dispatch jobs (not yet started)."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_sweep,
        trigger=IntervalTrigger(seconds=SWEEP_INTERVAL_SECONDS),
        id="health-sweep",
        name="Health check sweep",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    scheduler.add_job(
        run_mail_dispatch,
        trigger=IntervalTrigger(seconds=SWEEP_INTERVAL_SECONDS),
        id="mail-dispatch",
        name="Mail outbox dispatch",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    return scheduler
