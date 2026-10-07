"""Fail-fast validation for the answer prompt templates used by both callers.

Runtime templates use Python ``str.format``. The validator keeps a reviewed
placeholder allowlist and rejects Jinja/Shell-style placeholders that would
otherwise silently survive or be emitted as literal text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from string import Formatter
from typing import Mapping


class PromptTemplateValidationError(ValueError):
    """Raised when a prompt's placeholder syntax or allowlist is invalid."""


@dataclass(frozen=True)
class PromptTemplateSpec:
    template: str
    allowed_placeholders: frozenset[str]


_DOLLAR_PLACEHOLDER = re.compile(r"\$\{\s*[^{}]+\s*}")
_MUSTACHE_PLACEHOLDER = re.compile(r"(?<!{){{\s*[A-Za-z_][A-Za-z0-9_.]*\s*}}(?!})")


def _extract_format_placeholders(name: str, template: str) -> set[str]:
    formatter = Formatter()
    fields: set[str] = set()
    try:
        for _literal, field_name, format_spec, conversion in formatter.parse(template):
            if field_name is None:
                continue
            if not field_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name):
                raise PromptTemplateValidationError(
                    f"{name}: unsupported placeholder expression {{{field_name}}}"
                )
            if format_spec or conversion:
                raise PromptTemplateValidationError(
                    f"{name}: format specs and conversions are not allowed for {{{field_name}}}"
                )
            fields.add(field_name)
    except ValueError as exc:
        if isinstance(exc, PromptTemplateValidationError):
            raise
        raise PromptTemplateValidationError(f"{name}: malformed str.format template: {exc}") from exc
    return fields


def validate_prompt_template(
    name: str,
    template: str,
    allowed_placeholders: set[str] | frozenset[str],
) -> frozenset[str]:
    """Validate one ``str.format`` template and return its placeholders."""
    format_fields = _extract_format_placeholders(name, template)
    uses_dollar = bool(_DOLLAR_PLACEHOLDER.search(template))
    uses_mustache = bool(_MUSTACHE_PLACEHOLDER.search(template))

    if uses_dollar and uses_mustache:
        raise PromptTemplateValidationError(f"{name}: mixed ${{...}} and {{{{...}}}} placeholder syntax")
    if (uses_dollar or uses_mustache) and format_fields:
        raise PromptTemplateValidationError(
            f"{name}: mixed str.format and alternate placeholder syntax"
        )
    if uses_dollar or uses_mustache:
        syntax = "${...}" if uses_dollar else "{{...}}"
        raise PromptTemplateValidationError(f"{name}: unsupported {syntax} syntax; use str.format placeholders")

    allowed = frozenset(allowed_placeholders)
    unknown = format_fields - allowed
    if unknown:
        raise PromptTemplateValidationError(
            f"{name}: unknown placeholder(s): {', '.join(sorted(unknown))}"
        )
    return frozenset(format_fields)


def validate_prompt_templates(
    templates: Mapping[str, PromptTemplateSpec | tuple[str, set[str] | frozenset[str]]],
) -> dict[str, frozenset[str]]:
    """Validate a named collection of templates against explicit allowlists."""
    validated: dict[str, frozenset[str]] = {}
    for name, spec in templates.items():
        if isinstance(spec, PromptTemplateSpec):
            template, allowed = spec.template, spec.allowed_placeholders
        else:
            template, allowed = spec
        validated[name] = validate_prompt_template(name, template, allowed)
    return validated


def validate_registered_answer_prompts() -> dict[str, frozenset[str]]:
    """Validate every answer template owned by the shared prompt builder.

    This function has no startup side effect so the same check can run in tests,
    CI, and an application lifespan hook without importing heavyweight runtime
    dependencies until explicitly invoked.
    """
    from app.ai.graph import ANSWER_SYSTEM_PROMPT
    from app.chat.answer_prompt import AnswerPromptBuilder
    from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT, RAG_SYSTEM_PROMPT, RAG_USER_PROMPT

    return validate_prompt_templates({
        "rag_system": PromptTemplateSpec(
            RAG_SYSTEM_PROMPT,
            frozenset({"context_str", "graph_str", "platform_rule", "internal_param_rule"}),
        ),
        "rag_user": PromptTemplateSpec(RAG_USER_PROMPT, frozenset({"history_str", "query"})),
        "chat_system": PromptTemplateSpec(CHAT_SYSTEM_PROMPT, frozenset({"platform_rule", "internal_param_rule"})),
        "chat_user": PromptTemplateSpec(CHAT_USER_PROMPT, frozenset({"history_str", "query"})),
        "sixnode_system": PromptTemplateSpec(ANSWER_SYSTEM_PROMPT, frozenset()),
        "enterprise_rag_system": PromptTemplateSpec(
            AnswerPromptBuilder.ENTERPRISE_RAG_SYSTEM_PROMPT,
            frozenset({"context_str", "graph_str", "internal_param_rule", "platform_rule"}),
        ),
        "enterprise_sixnode_system": PromptTemplateSpec(
            AnswerPromptBuilder.ENTERPRISE_SIXNODE_SYSTEM_PROMPT,
            frozenset(),
        ),
    })
