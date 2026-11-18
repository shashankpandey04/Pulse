"""Service Catalogue routes (see ``schemas/catalogue.py`` for the API contract).

    POST   /catalogue               admin              -> ServiceResponse
    GET    /catalogue               admin, operator    -> ServiceListResponse
    GET    /catalogue/{service_id}  admin, operator    -> ServiceResponse
    PATCH  /catalogue/{service_id}  admin              -> ServiceResponse
    DELETE /catalogue/{service_id}  admin              -> MessageResponse

Creating a service also provisions its default state configuration
(``ServiceStateDocument``), so the health-check CRON can evaluate it right away.
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from core import database
from core.dependencies import RequireAdmin, RequireStaff
from schemas.catalogue import (
    COLLECTION_SERVICES,
    ServiceCreateRequest,
    ServiceDocument,
    ServiceListResponse,
    ServiceResponse,
    ServiceUpdateRequest,
)
from schemas.common import MessageResponse, utcnow
from schemas.state import COLLECTION_SERVICE_STATES, ServiceStateDocument

logger = logging.getLogger("pulse.catalogue")
router = APIRouter(prefix="/catalogue", tags=["catalogue"])

_ERROR = {
    "not_found": HTTPException(status.HTTP_404_NOT_FOUND, detail="Service not found."),
    "duplicate": HTTPException(status.HTTP_409_CONFLICT, detail="A service with this name or slug already exists."),
    "owner_missing": HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner email does not belong to any account."),
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "service"


def _resolve_owner(email: str) -> dict:
    owner = database.find_one("users", {"email": email})
    if owner is None:
        raise _ERROR["owner_missing"]
    return owner


def _to_response(service: dict) -> ServiceResponse:
    return ServiceResponse.model_validate(service)


def _get_service_or_404(service_id: str) -> dict:
    service = database.find_one(COLLECTION_SERVICES, {"service_id": service_id})
    if service is None:
        raise _ERROR["not_found"]
    return service


def _provision_default_state(service_id: str) -> None:
    """Best-effort creation of the per-service state config (defaults)."""
    state_doc = ServiceStateDocument(service_id=service_id)
    try:
        database.insert(COLLECTION_SERVICE_STATES, state_doc.model_dump(mode="json"))
    except DuplicateKeyError:
        pass  # a config already exists — leave it untouched


# ---------------------------------------------------------------------------
# Write endpoints (admin)
# ---------------------------------------------------------------------------


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreateRequest, _: RequireAdmin) -> ServiceResponse:
    """Register a service to watch. Owner email must be an existing account."""
    owner = _resolve_owner(payload.owner_email)
    slug = payload.slug or _slugify(payload.name)

    document = ServiceDocument(
        name=payload.name,
        slug=slug,
        description=payload.description,
        health_url=payload.health_url,
        check_interval_seconds=payload.check_interval_seconds,
        timeout_seconds=payload.timeout_seconds,
        owner_uid=owner["uid"],
        owner_email=owner["email"],
        reliability_target=payload.reliability_target,
        enabled=payload.enabled,
    )
    try:
        database.insert(COLLECTION_SERVICES, document.model_dump(mode="json"))
    except DuplicateKeyError:
        raise _ERROR["duplicate"]

    _provision_default_state(document.service_id)
    logger.info("created service %s (%s)", document.name, document.service_id)
    return _to_response(document.model_dump())


@router.patch("/{service_id}", response_model=ServiceResponse)
def update_service(service_id: str, payload: ServiceUpdateRequest, _: RequireAdmin) -> ServiceResponse:
    """Partial update. Cross-field rules are re-validated on the merged document."""
    current = _get_service_or_404(service_id)
    merged = dict(current)

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if "owner_email" in changes:
        owner = _resolve_owner(changes.pop("owner_email"))
        changes["owner_uid"] = owner["uid"]
        changes["owner_email"] = owner["email"]

    merged.update(changes)

    try:
        # Re-validate everything (ranges + timeout < interval) in one go.
        ServiceDocument.model_validate(merged)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    changes["updated_at"] = utcnow()
    try:
        database.update_one(COLLECTION_SERVICES, {"service_id": service_id}, changes)
    except DuplicateKeyError:
        raise _ERROR["duplicate"]

    updated = _get_service_or_404(service_id)
    logger.info("updated service %s fields=%s", service_id, list(changes))
    return _to_response(updated)


@router.delete("/{service_id}", response_model=MessageResponse)
def delete_service(service_id: str, _: RequireAdmin) -> MessageResponse:
    """Remove a service from the catalogue (and its state configuration)."""
    if not database.delete_one(COLLECTION_SERVICES, {"service_id": service_id}):
        raise _ERROR["not_found"]
    database.delete_one(COLLECTION_SERVICE_STATES, {"service_id": service_id})
    logger.info("deleted service %s", service_id)
    return MessageResponse(message=f"Service {service_id} deleted.")


# ---------------------------------------------------------------------------
# Read endpoints (admin + operator)
# ---------------------------------------------------------------------------


@router.get("", response_model=ServiceListResponse)
def list_services(
    _: RequireStaff,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=120, description="Case-insensitive name substring."),
    enabled: bool | None = Query(None, description="Filter by monitoring-enabled flag."),
) -> ServiceListResponse:
    """Paginated catalogue of services."""
    query: dict = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if enabled is not None:
        query["enabled"] = enabled

    total = database.count(COLLECTION_SERVICES, query)
    services = database.find_many(
        COLLECTION_SERVICES,
        query,
        sort=[("created_at", -1)],
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return ServiceListResponse(
        total=total, page=page, page_size=page_size, services=[_to_response(s) for s in services]
    )


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(service_id: str, _: RequireStaff) -> ServiceResponse:
    """One catalogue entry."""
    return _to_response(_get_service_or_404(service_id))
