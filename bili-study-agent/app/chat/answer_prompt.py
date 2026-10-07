"""Shared answer-prompt assembly for legacy and SixNode answer paths.

The builder keeps each path's GENERAL_LEARNING wording intact while making
policy selection and prompt assembly a single callable seam.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PromptPolicy(str, Enum):
    GENERAL_LEARNING = "GENERAL_LEARNING"
    ENTERPRISE_GROUNDED = "ENTERPRISE_GROUNDED"


@dataclass(frozen=True)
class BuiltAnswerPrompt:
    messages: list[dict[str, str]]
    policy: PromptPolicy
    fallback_answer: str | None
    system_prompt_fingerprint: str
    trusted_context: bool


class PromptPolicyResolver:
    """Resolve an answer policy from the caller's route and trusted context mode."""

    @staticmethod
    def resolve(
        route: str | None,
        role: Any,
        retrieval_mode: str | None,
        flag: bool | str | None,
        *,
        requested_policy: PromptPolicy | str | None = None,
    ) -> PromptPolicy:
        if requested_policy is not None:
            try:
                return PromptPolicy(str(getattr(requested_policy, "value", requested_policy)))
            except ValueError as exc:
                raise ValueError(f"unknown answer prompt policy: {requested_policy!r}") from exc

        enabled = flag if isinstance(flag, bool) else str(flag or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        role_name = str(getattr(role, "value", role) or "").strip().lower()
        route_name = str(route or "").strip().lower()
        mode_name = str(retrieval_mode or "").strip().lower()
        enterprise_routes = {"enterprise", "enterprise_grounded", "admin_enterprise", "knowledge", "learning"}
        grounded_modes = {"grounded", "enterprise_grounded", "rag"}

        if enabled and role_name in {"admin", "manager"} and route_name in enterprise_routes and mode_name in grounded_modes:
            return PromptPolicy.ENTERPRISE_GROUNDED
        return PromptPolicy.GENERAL_LEARNING


class AnswerPromptBuilder:
    """Build the exact message shape consumed by an answer generator."""

    ENTERPRISE_RAG_SYSTEM_PROMPT = """你是 EduAgent 的企业知识助手。

## 回答规则
1）只依据下方可信参考材料回答事实性问题，并标注材料来源。
2）材料没有支持答案时，不要用通用知识补全或猜测；说明没有找到相关资料，并建议联系配置的负责人。
3）不把问题中的假设当作事实。

## 图谱
{graph_str}

## 可信参考材料
{context_str}

## 工具使用纪律
{internal_param_rule}

{platform_rule}
""".strip()

    ENTERPRISE_SIXNODE_SYSTEM_PROMPT = """你是 EduAgent 的企业知识助手。
只依据下方可信综合上下文回答事实性问题。上下文没有支持答案时，不得猜测或使用通用知识补全；应说明没有找到相关资料，并建议联系配置的负责人。""".strip()

    @staticmethod
    def enterprise_grounded_enabled() -> bool:
        """Read the opt-in flag without adding an application config dependency."""
        return os.getenv("ENTERPRISE_GROUNDED_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def no_context_answer(contact: str | None = None) -> str:
        contact_name = str(contact if contact is not None else os.getenv("ENTERPRISE_GROUNDED_CONTACT") or "").strip()
        if not contact_name:
            contact_name = "课程管理员"
        return f"未找到相关资料，请咨询{contact_name}。"

    @staticmethod
    def _fingerprint(system_prompt: str) -> str:
        return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()

    @classmethod
    def build_generator(
        cls,
        *,
        query: str,
        docs: list[Any],
        graph_entities: list[Any],
        context_str: str,
        graph_str: str,
        history_str: str,
        platform_rule: str,
        internal_param_rule: str,
        mcp_context: str = "",
        strict_rag: bool = True,
        role: Any = None,
        route: str = "chat",
        retrieval_mode: str | None = None,
        enterprise_grounded_enabled: bool | str | None = None,
        policy: PromptPolicy | str | None = None,
        contact: str | None = None,
    ) -> BuiltAnswerPrompt:
        from app.chat.prompts import (
            CHAT_SYSTEM_PROMPT,
            CHAT_USER_PROMPT,
            RAG_SYSTEM_PROMPT,
            RAG_USER_PROMPT,
        )
        from app.chat.tool_calling import inject_mcp_into_system_prompt

        trusted_context = any(str(getattr(doc, "content", "") or "").strip() for doc in docs)
        flag = enterprise_grounded_enabled
        if flag is None:
            flag = cls.enterprise_grounded_enabled()
        mode = retrieval_mode or ("grounded" if strict_rag else "general")
        resolved = PromptPolicyResolver.resolve(route, role, mode, flag, requested_policy=policy)

        if resolved is PromptPolicy.ENTERPRISE_GROUNDED:
            if not trusted_context:
                fallback = cls.no_context_answer(contact)
                return BuiltAnswerPrompt(
                    messages=[], policy=resolved, fallback_answer=fallback,
                    system_prompt_fingerprint=cls._fingerprint(cls.ENTERPRISE_RAG_SYSTEM_PROMPT),
                    trusted_context=False,
                )
            system_prompt_base = cls.ENTERPRISE_RAG_SYSTEM_PROMPT.format(
                context_str=context_str,
                graph_str=graph_str,
                internal_param_rule=internal_param_rule,
                platform_rule=platform_rule,
            )
            user_prompt = RAG_USER_PROMPT.format(history_str=history_str, query=query)
        elif strict_rag:
            system_prompt_base = RAG_SYSTEM_PROMPT.format(
                context_str=context_str,
                graph_str=graph_str,
                platform_rule=platform_rule,
                internal_param_rule=internal_param_rule,
            )
            user_prompt = RAG_USER_PROMPT.format(history_str=history_str, query=query)
        else:
            system_prompt_base = CHAT_SYSTEM_PROMPT.format(
                platform_rule=platform_rule,
                internal_param_rule=internal_param_rule,
            )
            user_prompt = CHAT_USER_PROMPT.format(history_str=history_str, query=query)

        system_prompt = inject_mcp_into_system_prompt(system_prompt_base, mcp_context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return BuiltAnswerPrompt(
            messages=messages, policy=resolved, fallback_answer=None,
            system_prompt_fingerprint=cls._fingerprint(system_prompt),
            trusted_context=trusted_context,
        )

    @classmethod
    def build_sixnode(
        cls,
        *,
        query: str,
        context: str,
        skill_context: str,
        general_system_prompt: str,
        trusted_context: bool,
        role: Any = None,
        route: str = "chat",
        retrieval_mode: str = "general",
        enterprise_grounded_enabled: bool | str | None = None,
        policy: PromptPolicy | str | None = None,
        contact: str | None = None,
    ) -> BuiltAnswerPrompt:
        trusted_context = bool(trusted_context and context.strip())
        flag = enterprise_grounded_enabled
        if flag is None:
            flag = cls.enterprise_grounded_enabled()
        resolved = PromptPolicyResolver.resolve(
            route, role, retrieval_mode, flag, requested_policy=policy,
        )

        if resolved is PromptPolicy.ENTERPRISE_GROUNDED:
            if not trusted_context:
                fallback = cls.no_context_answer(contact)
                return BuiltAnswerPrompt(
                    messages=[], policy=resolved, fallback_answer=fallback,
                    system_prompt_fingerprint=cls._fingerprint(cls.ENTERPRISE_SIXNODE_SYSTEM_PROMPT),
                    trusted_context=False,
                )
            system_prompt = cls.ENTERPRISE_SIXNODE_SYSTEM_PROMPT
        else:
            # Preserve SixNode's established GENERAL_LEARNING prompt byte-for-byte.
            system_prompt = general_system_prompt

        system_prompt += "\n\n## 综合上下文\n" + (context or "（无）")
        if skill_context:
            system_prompt += "\n\n## 相关 skill 指引\n" + skill_context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        return BuiltAnswerPrompt(
            messages=messages, policy=resolved, fallback_answer=None,
            system_prompt_fingerprint=cls._fingerprint(system_prompt),
            trusted_context=trusted_context,
        )
