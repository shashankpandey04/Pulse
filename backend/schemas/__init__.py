"""Pydantic schemas for the Pulse backend (Task 1).

Submodules
    common     shared helpers (utcnow, new_uid, TimestampedModel) and generic responses
    auth       accounts: ``users`` document + auth / admin user-management API schemas
    catalogue  service catalogue: ``services`` document + catalogue API schemas
    state      service states: ``service_states`` document + state API schemas

Example:
    from schemas.auth import RegisterRequest, UserDocument
    from schemas.catalogue import ServiceCreateRequest, ServiceResponse
    from schemas.state import StateConfigUpsertRequest, STATE_COLORS
"""

from . import auth, catalogue, common, state

__all__ = ["auth", "catalogue", "common", "state"]
