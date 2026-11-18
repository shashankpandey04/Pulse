"""Push-device routes (see ``schemas/device.py`` for the API contract).

    POST   /devices              DeviceTokenCreateRequest -> DeviceTokenResponse   any signed-in role
    GET    /devices              -> DeviceTokenListResponse  any signed-in role
    DELETE /devices/{token_id}   -> MessageResponse          any signed-in role

Registering an FCM token *subscribes* that device for service state-change
pushes. Subscribers opt in from their dashboard; operators/admins are required
to keep at least one device (``GET /dashboard`` reports it via
``devices.notifications_required``). Upsert semantics: a token already stored
is re-assigned to the caller (the device changed hands) instead of erroring.
Full tokens are never returned — only a masked preview.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from core import database
from core.dependencies import CurrentUser
from schemas.common import utcnow
from schemas.device import (
    COLLECTION_DEVICE_TOKENS,
    DEFAULT_DEVICE_LABEL,
    DeviceTokenCreateRequest,
    DeviceTokenDocument,
    DeviceTokenListResponse,
    DeviceTokenResponse,
)

router = APIRouter(prefix="/devices", tags=["devices"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Device not found.")

_MAX_USER_AGENT = 400


def _preview(token: str) -> str:
    return f"{token[:6]}…{token[-4:]}" if len(token) > 12 else "…"


def _response(doc: dict) -> DeviceTokenResponse:
    payload = {k: v for k, v in doc.items() if k != "fcm_token"}
    payload["token_preview"] = _preview(doc["fcm_token"])
    return DeviceTokenResponse.model_validate(payload)


@router.post("", response_model=DeviceTokenResponse)
def register_device(
    body: DeviceTokenCreateRequest,
    response: Response,
    request: Request,
    user: CurrentUser,
) -> DeviceTokenResponse:
    """Subscribe one device: creates, re-labels or re-assigns the token."""
    existing = database.find_one(COLLECTION_DEVICE_TOKENS, {"fcm_token": body.fcm_token})
    now = utcnow()
    user_agent = (request.headers.get("user-agent") or None)
    if user_agent:
        user_agent = user_agent[:_MAX_USER_AGENT]

    if existing is None:
        doc = DeviceTokenDocument(
            uid=user["uid"],
            fcm_token=body.fcm_token,
            device_label=body.device_label or DEFAULT_DEVICE_LABEL,
            user_agent=user_agent,
        )
        database.insert(COLLECTION_DEVICE_TOKENS, doc.model_dump(mode="json"))
        response.status_code = status.HTTP_201_CREATED
        return _response(doc.model_dump(mode="json"))

    # Upsert: same device re-registering (possibly under a new account).
    sets: dict = {"uid": user["uid"], "updated_at": now}
    if body.device_label is not None:
        sets["device_label"] = body.device_label
    database.update_one(COLLECTION_DEVICE_TOKENS, {"fcm_token": body.fcm_token}, sets)
    response.status_code = status.HTTP_200_OK
    return _response({**existing, **sets})


@router.get("", response_model=DeviceTokenListResponse)
def list_devices(user: CurrentUser) -> DeviceTokenListResponse:
    """The caller's own devices, newest first (tokens masked)."""
    docs = database.find_many(
        COLLECTION_DEVICE_TOKENS,
        {"uid": user["uid"]},
        sort=[("created_at", -1)],
    )
    return DeviceTokenListResponse(total=len(docs), tokens=[_response(d) for d in docs])


@router.delete("/{token_id}", response_model=None)
def delete_device(token_id: str, user: CurrentUser) -> Response:
    """Unsubscribe one of the caller's devices."""
    deleted = database.delete_one(COLLECTION_DEVICE_TOKENS, {"token_id": token_id, "uid": user["uid"]})
    if not deleted:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
