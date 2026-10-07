"""Fail-closed access decisions for one retrieved knowledge record.

``security_scope`` is carried through ingestion as metadata, but is not part of
the W5-v1 filter registry and has no user-grant source.  It is intentionally not
used for authorization here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.auth.schemas import UserRole


COURSE_PUBLIC_TENANT = "course_public"
SHARED_TENANTS = frozenset({"_default", COURSE_PUBLIC_TENANT})


class AccessReason(str, Enum):
    ALLOWED = "allowed"
    MISSING_PRINCIPAL = "missing_principal"
    INVALID_PRINCIPAL = "invalid_principal"
    MISSING_TENANT = "missing_tenant"
    CROSS_TENANT = "cross_tenant"
    MISSING_INTERNAL_CLASSIFICATION = "missing_internal_classification"
    INTERNAL_FORBIDDEN = "internal_forbidden"
    MISSING_VISIBILITY = "missing_visibility"
    INVALID_VISIBILITY = "invalid_visibility"
    PRIVATE_OWNER_UNKNOWN = "private_owner_unknown"
    PRIVATE_OWNER_MISMATCH = "private_owner_mismatch"


@dataclass(frozen=True)
class RetrievalPrincipal:
    user_id: int | None
    role: UserRole | str | None


@dataclass(frozen=True)
class RetrievalResource:
    tenant_id: str | None
    visibility: str | None
    owner_id: int | None
    internal: bool | None
    # Propagated metadata only; deliberately not part of W5-v1 authorization.
    security_scope: str | None = None


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: AccessReason


def _role_value(role: UserRole | str | None) -> UserRole | None:
    if isinstance(role, UserRole):
        return role
    if not isinstance(role, str) or not role.strip():
        return None
    try:
        return UserRole(role.strip().lower())
    except ValueError:
        return None


def _tenant_allowed(principal: RetrievalPrincipal, role: UserRole, tenant_id: str) -> bool:
    if role is UserRole.ADMIN:
        return True
    return tenant_id in SHARED_TENANTS or tenant_id == f"user_{principal.user_id}"


def evaluate_retrieval_access(
    principal: RetrievalPrincipal | None,
    resource: RetrievalResource,
) -> AccessDecision:
    """Check tenant, internal, visibility and private-owner constraints.

    Callers should apply this to each candidate before exposing its content.
    ANN pre-filters are an earlier narrowing step, not a replacement for this
    authorization check.
    """
    if principal is None:
        return AccessDecision(False, AccessReason.MISSING_PRINCIPAL)

    role = _role_value(principal.role)
    if principal.user_id is None or principal.user_id <= 0 or role is None:
        return AccessDecision(False, AccessReason.INVALID_PRINCIPAL)

    tenant_id = resource.tenant_id.strip() if isinstance(resource.tenant_id, str) else ""
    if not tenant_id:
        return AccessDecision(False, AccessReason.MISSING_TENANT)
    if not _tenant_allowed(principal, role, tenant_id):
        return AccessDecision(False, AccessReason.CROSS_TENANT)

    if not isinstance(resource.internal, bool):
        return AccessDecision(False, AccessReason.MISSING_INTERNAL_CLASSIFICATION)
    if resource.internal and role not in (UserRole.ADMIN, UserRole.MANAGER):
        return AccessDecision(False, AccessReason.INTERNAL_FORBIDDEN)

    visibility = resource.visibility.strip().lower() if isinstance(resource.visibility, str) else ""
    if not visibility:
        return AccessDecision(False, AccessReason.MISSING_VISIBILITY)
    if visibility not in ("public", "private"):
        return AccessDecision(False, AccessReason.INVALID_VISIBILITY)

    if visibility == "private":
        if resource.owner_id is None or resource.owner_id <= 0:
            return AccessDecision(False, AccessReason.PRIVATE_OWNER_UNKNOWN)
        if resource.owner_id != principal.user_id:
            return AccessDecision(False, AccessReason.PRIVATE_OWNER_MISMATCH)

    return AccessDecision(True, AccessReason.ALLOWED)
