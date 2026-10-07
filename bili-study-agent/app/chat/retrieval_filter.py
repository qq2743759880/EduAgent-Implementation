"""W5-v1 retrieval filters and safe Milvus expression compilation.

The W5-v1 fields remain compatible; ``study_scope`` adds server-authorized
course/video criteria. ``visibility`` compilation is gated until producer,
Milvus persistence and round-trip tests have been verified by integration.
``security_scope`` is propagated metadata, not a W5-v1 filter field.

This module is pure: it does not import Milvus or inspect the live schema. The
integration layer remains responsible for startup schema introspection and for
applying the same compiled expression to dense and sparse ANN requests.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from app.auth.schemas import UserRole
from app.knowledge.models import ContentType


class RetrievalCaller(str, Enum):
    SIXNODE = "sixnode"
    GRAPH_SUBAGENT = "graph_subagent"
    RAG_ADMIN = "rag_admin"
    MCP_SEARCH_KNOWLEDGE = "mcp_search_knowledge"
    FLOWS_AGENT_LEGACY = "flows_agent_legacy"


class RetrievalFilterField(str, Enum):
    TENANT_SCOPE = "tenant_scope"
    INTERNAL = "internal"
    CONTENT_TYPES = "content_types"
    VISIBILITY = "visibility"


W5_V1_REGISTERED_FIELDS = frozenset(field.value for field in RetrievalFilterField)
_SHARED_TENANTS = ("_default", "course_public")
_TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_VISIBILITIES = frozenset({"public", "private"})
_CONTENT_TYPES = frozenset(item.value for item in ContentType)
_ROLES_WITH_INTERNAL = frozenset({UserRole.ADMIN, UserRole.MANAGER})
_COURSE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
NON_VIDEO_EXPRESSION = '((not exists video_id) or video_id <= 0)'


def is_non_video_knowledge(doc: object) -> bool:
    # A positive video identity is never ordinary knowledge, even if a forged
    # producer relabels its content_type as "question".
    return not getattr(doc, "video_id", None)


@dataclass(frozen=True)
class StudyRetrievalScope:
    """Scope derived from an authorized StudyContext, never from request filters.

    A playable lesson admits a READY video version plus non-video knowledge
    bound to its course. Without a READY identity only non-video knowledge is
    admitted. Existing text-only lessons retain course-level non-video retrieval.
    Milvus's historical ``series_codes`` is CSV, not an ARRAY field.
    """

    series_id: int
    series_code: str
    session_id: int | None = None
    video_id: int | None = None
    generation: str | None = None
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.series_id is None:
            raise ValueError("series_id must be a positive integer")
        for name in ("series_id", "session_id", "video_id"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.series_code, str) or not _COURSE_CODE_RE.fullmatch(self.series_code):
            raise ValueError("series_code must be a safe course identifier")
        if (self.session_id is None) != (self.video_id is None):
            raise ValueError("video scope requires both session_id and video_id")
        if (self.generation is None) != (self.artifact_sha256 is None):
            raise ValueError("publication scope requires both generation and artifact SHA")
        if self.generation is not None and (self.video_id is None or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in (self.generation, self.artifact_sha256)
        )):
            raise ValueError("publication scope requires a video and valid immutable digests")

    @property
    def course_codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.series_code, str(self.series_id))))

    def matches(self, doc: object) -> bool:
        """Defense in depth against missing or incorrectly assembled result metadata."""
        codes = getattr(doc, "series_codes", ()) or ()
        if isinstance(codes, str):
            codes = codes.split(",")
        course_match = str(getattr(doc, "series_code", "") or "") in self.course_codes or any(
            code in self.course_codes for code in codes
        )
        if is_non_video_knowledge(doc):
            return course_match
        return (
            self.generation is not None
            and self.video_id is not None
            and getattr(doc, "tenant_id", None) == "course_public"
            and getattr(doc, "content_type", None) in _CONTENT_TYPES - {"question"}
            and getattr(doc, "series_id", None) == self.series_id
            and getattr(doc, "session_id", None) == self.session_id
            and getattr(doc, "video_id", None) == self.video_id
            and getattr(doc, "generation", None) == self.generation
            and getattr(doc, "distill_artifact_sha256", None) == self.artifact_sha256
        )


def _study_scope_expression(scope: StudyRetrievalScope) -> str:
    membership = [_in_expr("series_code", scope.course_codes)]
    for code in scope.course_codes:
        escaped = code.replace("_", r"\_")
        membership.append(f"series_codes == {json.dumps(code)}")
        for pattern in (f"{escaped},%", f"%,{escaped},%", f"%,{escaped}"):
            # JSON escaping supplies the doubled backslash required by Milvus 2.x.
            membership.append(f"series_codes like {json.dumps(pattern)}")
    course = "(" + " or ".join(membership) + ")"
    # Old course/question rows do not have the dynamic video_id key. EXISTS is
    # essential: missing metadata must remain compatible, while video vectors
    # must never enter this branch merely because their course binding matches.
    ordinary = f'({course} and {NON_VIDEO_EXPRESSION})'
    if scope.generation is None:
        return ordinary
    video = (
        f'(tenant_id == "course_public" and content_type != "question" '
        f"and series_id == {scope.series_id} and session_id == {scope.session_id} "
        f"and video_id == {scope.video_id})"
    )
    if scope.generation is not None:
        # MySQL READY publication chooses the sole student generation before
        # ANN/topK. Previous/pending vectors remain stored and cannot crowd out
        # the active learning version. Shared course question rules stay intact.
        video = video[:-1] + (
            f" and generation == {json.dumps(scope.generation)}"
            f" and distill_artifact_sha256 == {json.dumps(scope.artifact_sha256)})"
        )
    return f'({video} or {ordinary})'


def _as_values(field: str, value: Iterable[str] | str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        values = (value,)
    else:
        try:
            values = tuple(value)
        except TypeError as exc:
            raise ValueError(f"{field} must be a string or iterable of strings") from exc
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{field} values must be non-empty strings")
    # Preserve caller order while making output deterministic and duplicate-free.
    return tuple(dict.fromkeys(item.strip() for item in values))


@dataclass(frozen=True, init=False)
class RetrievalFilter:
    """Typed legacy criteria plus an optional server-issued study scope."""

    tenant_scope: tuple[str, ...] | None
    internal: bool | None
    content_types: tuple[str, ...] | None
    visibility: tuple[str, ...] | None
    study_scope: StudyRetrievalScope | None

    def __init__(
        self,
        tenant_scope: Iterable[str] | str | None = None,
        internal: bool | None = None,
        content_types: Iterable[str] | str | None = None,
        visibility: Iterable[str] | str | None = None,
        study_scope: StudyRetrievalScope | None = None,
        **unknown_fields: object,
    ) -> None:
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ValueError(f"unregistered retrieval filter field(s): {unknown}")
        if internal is not None and not isinstance(internal, bool):
            raise ValueError("internal must be bool or None")
        if study_scope is not None and not isinstance(study_scope, StudyRetrievalScope):
            raise ValueError("study_scope must be a StudyRetrievalScope")

        tenants = _as_values("tenant_scope", tenant_scope)
        if tenants is not None and any(not _TENANT_RE.fullmatch(item) for item in tenants):
            raise ValueError("tenant_scope contains an unsafe tenant identifier")

        types = _as_values("content_types", content_types)
        if types is not None and any(item not in _CONTENT_TYPES for item in types):
            raise ValueError("content_types contains an unregistered content type")

        visibilities = _as_values("visibility", visibility)
        if visibilities is not None and any(item.lower() not in _VISIBILITIES for item in visibilities):
            raise ValueError("visibility values must be public/private")
        if visibilities is not None:
            visibilities = tuple(dict.fromkeys(item.lower() for item in visibilities))

        object.__setattr__(self, "tenant_scope", tenants)
        object.__setattr__(self, "internal", internal)
        object.__setattr__(self, "content_types", types)
        object.__setattr__(self, "visibility", visibilities)
        object.__setattr__(self, "study_scope", study_scope)


@dataclass(frozen=True)
class RetrievalCapabilities:
    """Verified producer/persistence/test gates for conditionally admitted fields."""

    visibility_ready: bool = False


@dataclass(frozen=True)
class CompiledMilvusFilter:
    expression: str | None
    partition_names: tuple[str, ...] | None
    no_results: bool = False


def _coerce_caller(caller: RetrievalCaller | str) -> RetrievalCaller:
    if isinstance(caller, RetrievalCaller):
        return caller
    if not isinstance(caller, str):
        raise ValueError("caller must be a registered RetrievalCaller")
    try:
        return RetrievalCaller(caller)
    except ValueError as exc:
        raise ValueError(f"unregistered retrieval caller: {caller!r}") from exc


def _coerce_role(role: UserRole | str | None) -> UserRole:
    # Existing retriever contract: missing role is treated as STUDENT, never as
    # unrestricted access (especially for the MCP agent caller).
    if role is None:
        return UserRole.STUDENT
    if isinstance(role, UserRole):
        return role
    if isinstance(role, str):
        try:
            return UserRole(role.strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown retrieval role: {role!r}") from exc
    raise ValueError("role must be a UserRole, role string, or None")


def _partition_name(tenant_id: str) -> str:
    """Mirror loader._get_partition_name without importing its I/O dependencies."""
    if tenant_id in _SHARED_TENANTS:
        return tenant_id
    safe_id = tenant_id.replace("-", "_")
    if not safe_id.startswith("user_"):
        safe_id = f"user_{safe_id}"
    return safe_id


def _in_expr(field_name: str, values: tuple[str, ...]) -> str:
    # field_name is always a literal owned by this module; values have passed
    # the per-field registry/grammar validation above.
    literals = ", ".join(json.dumps(value, ensure_ascii=True) for value in values)
    return f"{field_name} in [{literals}]"


def compile_retrieval_filter(
    retrieval_filter: RetrievalFilter,
    *,
    caller: RetrievalCaller | str,
    user_id: int,
    role: UserRole | str | None,
    capabilities: RetrievalCapabilities = RetrievalCapabilities(),
) -> CompiledMilvusFilter:
    """Compile a W5-v1 filter into one ANN expression and partition selection.

    Non-admin requested tenants must be a subset of their documented scope:
    ``_default``, ``course_public`` and ``user_{user_id}``. ``internal=True``
    cannot widen student/teacher access. The RAG admin caller is admin-only.
    """
    resolved_caller = _coerce_caller(caller)
    if not isinstance(retrieval_filter, RetrievalFilter):
        raise ValueError("retrieval_filter must be a RetrievalFilter instance")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    if not isinstance(capabilities, RetrievalCapabilities):
        raise ValueError("capabilities must be RetrievalCapabilities")

    resolved_role = _coerce_role(role)
    if resolved_caller is RetrievalCaller.RAG_ADMIN and resolved_role is not UserRole.ADMIN:
        raise PermissionError("rag_admin caller requires admin role")

    all_tenants = resolved_role is UserRole.ADMIN
    permitted_tenants = set(_SHARED_TENANTS)
    permitted_tenants.add(f"user_{user_id}")
    requested_tenants = retrieval_filter.tenant_scope
    if requested_tenants is None:
        selected_tenants = None if all_tenants else tuple(sorted(permitted_tenants))
    else:
        if not all_tenants and not set(requested_tenants).issubset(permitted_tenants):
            raise PermissionError("tenant_scope exceeds caller's authorized tenant scope")
        selected_tenants = requested_tenants

    if retrieval_filter.visibility is not None and not capabilities.visibility_ready:
        raise ValueError(
            "visibility filter is not enabled until producer, persistence and round-trip tests pass"
        )

    include_internal = (
        retrieval_filter.internal
        if retrieval_filter.internal is not None
        else resolved_role in _ROLES_WITH_INTERNAL
    )
    if include_internal and resolved_role not in _ROLES_WITH_INTERNAL:
        raise PermissionError("student/teacher caller cannot include internal records")

    if selected_tenants == () or retrieval_filter.content_types == () or retrieval_filter.visibility == ():
        return CompiledMilvusFilter(expression=None, partition_names=(), no_results=True)

    clauses: list[str] = []
    partitions: tuple[str, ...] | None
    if selected_tenants is None:
        partitions = None
    else:
        partitions = tuple(dict.fromkeys(_partition_name(item) for item in selected_tenants))
        # Keep the scalar tenant check in addition to Milvus partition selection.
        clauses.append(_in_expr("tenant_id", selected_tenants))

    if not include_internal:
        clauses.append("internal != true")
    if retrieval_filter.content_types is not None:
        clauses.append(_in_expr("content_type", retrieval_filter.content_types))
    if retrieval_filter.visibility is not None:
        clauses.append(_in_expr("visibility", retrieval_filter.visibility))
    if retrieval_filter.study_scope is not None:
        clauses.append(_study_scope_expression(retrieval_filter.study_scope))

    expression = " and ".join(f"({clause})" for clause in clauses) or None
    return CompiledMilvusFilter(expression=expression, partition_names=partitions)
