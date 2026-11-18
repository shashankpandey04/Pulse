"""MongoDB access via pymongo — a single shared client for the whole app."""

import logging
from typing import Any

import pymongo
from pymongo.database import Database

from schemas.auth import COLLECTION_USERS
from schemas.catalogue import COLLECTION_SERVICES
from schemas.incidents import COLLECTION_INCIDENTS
from schemas.metrics import COLLECTION_CHECK_RESULTS
from schemas.notification import COLLECTION_NOTIFICATIONS
from schemas.state import COLLECTION_SERVICE_STATES

from . import config

logger = logging.getLogger("pulse.database")

_client: pymongo.MongoClient | None = None


def get_client() -> pymongo.MongoClient:
    """The process-wide MongoClient (tz_aware so reads return aware datetimes)."""
    global _client
    if _client is None:
        _client = pymongo.MongoClient(config.MONGO_URI, tz_aware=True)
    return _client


def get_db() -> Database:
    """The ``pulse`` database handle."""
    return get_client()[config.MONGO_DB]


def close_client() -> None:
    """Flush and release the client (called from the FastAPI lifespan on shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def ensure_indexes() -> None:
    """Create the unique indexes that back the schemas in ``backend/schemas/README.md``.

    Safe to call on every startup. A duplicate-key violation (409) at write time
    is how uniqueness is enforced for email/slug/service_id.
    """
    db = get_db()
    db[COLLECTION_USERS].create_index("email", unique=True)
    db[COLLECTION_USERS].create_index("uid", unique=True)
    db[COLLECTION_SERVICES].create_index("service_id", unique=True)
    db[COLLECTION_SERVICES].create_index("slug", unique=True)
    db[COLLECTION_SERVICES].create_index("name", unique=True)
    db[COLLECTION_SERVICE_STATES].create_index("service_id", unique=True)
    db[COLLECTION_SERVICE_STATES].create_index("state_id", unique=True)
    # Monitoring-side collections (incidents, check results, notifications).
    db[COLLECTION_INCIDENTS].create_index("incident_id", unique=True)
    # At most one open/acknowledged incident per service (resolved ones excluded).
    db[COLLECTION_INCIDENTS].create_index(
        [("service_id", 1), ("status", 1)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["open", "acknowledged"]}},
    )
    db[COLLECTION_INCIDENTS].create_index([("status", 1), ("opened_at", -1)])
    db[COLLECTION_CHECK_RESULTS].create_index([("service_id", 1), ("checked_at", -1)])
    db[COLLECTION_NOTIFICATIONS].create_index([("created_at", -1)])
    logger.info("database indexes ensured")


def insert(collection: str, document: dict[str, Any]) -> None:
    """Insert one document; raises on duplicate key so callers can map to 409."""
    get_db()[collection].insert_one(dict(document))


def find_one(collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
    return get_db()[collection].find_one(query)


def find_many(
    collection: str,
    query: dict[str, Any] | None = None,
    sort: list[tuple[str, int]] | None = None,
    skip: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cursor = get_db()[collection].find(dict(query or {}))
    if sort:
        cursor = cursor.sort(sort)
    if skip:
        cursor = cursor.skip(skip)
    if limit is not None:
        cursor = cursor.limit(limit)
    return list(cursor)


def count(collection: str, query: dict[str, Any] | None = None) -> int:
    return get_db()[collection].count_documents(dict(query or {}))


def update_one(collection: str, query: dict[str, Any], sets: dict[str, Any]) -> bool:
    """``$set`` update; returns True when a document matched."""
    result = get_db()[collection].update_one(query, {"$set": sets})
    return result.matched_count > 0


def delete_one(collection: str, query: dict[str, Any]) -> bool:
    result = get_db()[collection].delete_one(query)
    return result.deleted_count > 0
