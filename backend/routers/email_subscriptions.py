"""Email-subscription routes (see ``schemas/email_subscription.py`` for the contract).

    POST   /email-subscriptions   -> EmailSubscriptionResponse       any signed-in role
    GET    /email-subscriptions   -> EmailSubscriptionStatusResponse any signed-in role
    DELETE /email-subscriptions   -> 204                             any signed-in role

Subscribing uses the caller's **account email** — no address is accepted from
the request body, so the system can never be used to sign third parties up
(and the mailbox we send from only ever mails registered users). One
subscription per account; re-subscribing is idempotent.
"""

from fastapi import APIRouter, HTTPException, Response, status

from core import database
from core.dependencies import CurrentUser
from schemas.common import utcnow
from schemas.email_subscription import (
    COLLECTION_EMAIL_SUBSCRIPTIONS,
    EmailSubscriptionDocument,
    EmailSubscriptionResponse,
    EmailSubscriptionStatusResponse,
)

router = APIRouter(prefix="/email-subscriptions", tags=["email-subscriptions"])

_NOT_SUBSCRIBED = HTTPException(status.HTTP_404_NOT_FOUND, detail="Not subscribed.")


def _response(doc: dict) -> EmailSubscriptionResponse:
    return EmailSubscriptionResponse.model_validate(doc)


@router.post("", response_model=EmailSubscriptionResponse)
def subscribe(response: Response, user: CurrentUser) -> EmailSubscriptionResponse:
    """Subscribe the caller's account email (idempotent)."""
    existing = database.find_one(COLLECTION_EMAIL_SUBSCRIPTIONS, {"uid": user["uid"]})
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _response(existing)

    doc = EmailSubscriptionDocument(uid=user["uid"], email=str(user["email"]).lower())
    database.insert(COLLECTION_EMAIL_SUBSCRIPTIONS, doc.model_dump(mode="json"))
    response.status_code = status.HTTP_201_CREATED
    return _response(doc.model_dump(mode="json"))


@router.get("", response_model=EmailSubscriptionStatusResponse)
def my_subscription(user: CurrentUser) -> EmailSubscriptionStatusResponse:
    """The caller's subscription, or ``subscription: null`` when not subscribed."""
    doc = database.find_one(COLLECTION_EMAIL_SUBSCRIPTIONS, {"uid": user["uid"]})
    return EmailSubscriptionStatusResponse(subscription=_response(doc) if doc else None)


@router.delete("", response_model=None)
def unsubscribe(user: CurrentUser) -> Response:
    """Unsubscribe the caller's account email."""
    deleted = database.delete_one(COLLECTION_EMAIL_SUBSCRIPTIONS, {"uid": user["uid"]})
    if not deleted:
        raise _NOT_SUBSCRIBED
    return Response(status_code=status.HTTP_204_NO_CONTENT)
