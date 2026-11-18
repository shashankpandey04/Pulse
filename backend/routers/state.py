"""Service State routes (see ``schemas/state.py`` for the API contract).

    PUT    /states/{service_id}      admin, operator  -> StateConfigResponse      (upsert)
    PATCH  /states/{service_id}      admin, operator  -> StateConfigResponse      (partial)
    GET    /states/{service_id}      admin, operator  -> StateConfigResponse      (effective config)
    GET    /states                   admin, operator  -> StateConfigListResponse
    DELETE /states/{service_id}      admin            -> MessageResponse          (reset to defaults)

One configuration per catalogue service, keyed by unique ``service_id``. The
health-check CRON reads these thresholds to decide healthy/down/slow/flaky and
when a service has recovered.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from core import database
from core.dependencies import RequireAdmin, RequireStaff
from schemas.common import MessageResponse, utcnow
from schemas.catalogue import COLLECTION_SERVICES
from schemas.state import (
    COLLECTION_SERVICE_STATES,
    ServiceStateDocument,
    StateConfigListResponse,
    StateConfigResponse,
    StateConfigUpdateRequest,
    StateConfigUpsertRequest,
)

logger = logging.getLogger("pulse.state")
router = APIRouter(prefix="/states", tags=["states"])

_NOT_FOUND_SERVICE = HTTPException(status.HTTP_404_NOT_FOUND, detail="Service not found in the catalogue.")
_NOT_FOUND_CONFIG = HTTPException(status.HTTP_404_NOT_FOUND, detail="No state configuration stored for this service.")


def _service_exists(service_id: str) -> None:
    if not database.find_one(COLLECTION_SERVICES, {"service_id": service_id}):
        raise _NOT_FOUND_SERVICE


def _to_response(doc: dict) -> StateConfigResponse:
    return StateConfigResponse.model_validate(doc)


def _get_config_or_none(service_id: str) -> dict | None:
    return database.find_one(COLLECTION_SERVICE_STATES, {"service_id": service_id})


def _effective_config(service_id: str) -> dict:
    """Stored config, or an in-memory default when none has been stored yet."""
    stored = _get_config_or_none(service_id)
    if stored is not None:
        return stored
    return ServiceStateDocument(service_id=service_id).model_dump(mode="json")


def _store_config(doc: dict) -> dict:
    """Insert or replace a config document (keeps the original ``state_id``)."""
    existing = _get_config_or_none(doc["service_id"])
    if existing is None:
        try:
            database.insert(COLLECTION_SERVICE_STATES, doc)
        except DuplicateKeyError:
            existing = _get_config_or_none(doc["service_id"])
            if existing is None:  # pragma: no cover - defensive
                raise
    if existing is not None:
        # Full replace but keep the original state_id + created_at.
        update = {k: v for k, v in doc.items() if k not in {"state_id", "created_at", "updated_at"}}
        update["updated_at"] = utcnow()
        database.update_one(COLLECTION_SERVICE_STATES, {"service_id": doc["service_id"]}, update)
    return _get_config_or_none(doc["service_id"])  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Write endpoints (operator/admin)
# ---------------------------------------------------------------------------


@router.put("/{service_id}", response_model=StateConfigResponse)
def upsert_config(service_id: str, payload: StateConfigUpsertRequest, _: RequireStaff) -> StateConfigResponse:
    """Create or fully replace the configuration (omitted policies -> defaults)."""
    _service_exists(service_id)
    doc = ServiceStateDocument(service_id=service_id, **payload.model_dump())
    stored = _store_config(doc.model_dump(mode="json"))
    logger.info("upserted state config for %s", service_id)
    return _to_response(stored)


@router.patch("/{service_id}", response_model=StateConfigResponse)
def update_config(service_id: str, payload: StateConfigUpdateRequest, _: RequireStaff) -> StateConfigResponse:
    """Replace only the provided policies; the rest keep their current value."""
    _service_exists(service_id)
    merged = ServiceStateDocument(**_effective_config(service_id))
    changes = payload.model_dump(exclude_unset=True)
    data = merged.model_dump(mode="json")
    data.update(changes)
    stored = _store_config(data)
    logger.info("patched state config for %s fields=%s", service_id, list(changes))
    return _to_response(stored)


@router.delete("/{service_id}", response_model=MessageResponse)
def reset_config(service_id: str, _: RequireAdmin) -> MessageResponse:
    """Remove the stored configuration; the service falls back to defaults."""
    if not database.delete_one(COLLECTION_SERVICE_STATES, {"service_id": service_id}):
        raise _NOT_FOUND_CONFIG
    logger.info("reset state config for %s", service_id)
    return MessageResponse(message=f"State configuration for {service_id} removed; defaults restored.")


# ---------------------------------------------------------------------------
# Read endpoints (operator/admin)
# ---------------------------------------------------------------------------


@router.get("", response_model=StateConfigListResponse)
def list_configs(
    _: RequireStaff,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> StateConfigListResponse:
    """Paginated list of stored configurations."""
    total = database.count(COLLECTION_SERVICE_STATES)
    docs = database.find_many(
        COLLECTION_SERVICE_STATES,
        sort=[("created_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return StateConfigListResponse(total=total, page=page, page_size=page_size, states=[_to_response(d) for d in docs])


@router.get("/{service_id}", response_model=StateConfigResponse)
def get_config(service_id: str, _: RequireStaff) -> StateConfigResponse:
    """Effective configuration for a service (defaults when none is stored)."""
    _service_exists(service_id)
    return _to_response(_effective_config(service_id))
