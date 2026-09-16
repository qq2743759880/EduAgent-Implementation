"""
P2 答案生成器：
- 优先使用 settings.LLM_BASE_URL（OpenAI-compatible，DashScope 默认就是这个）+ API_KEY
- 支持非流式 generate() 与流式 generate_stream()（async generator）
- 全链路降级：LLM 调用失败 → 返回规则化模板（FALLBACK_NO_DOCS / 本地简易回答），保证问答永远不 500
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator

from loguru import logger

from app.chat.prompts import (
    FALLBACK_NO_DOCS,
    HISTORY_TURN_TEMPLATE,
    RAG_SYSTEM_PROMPT,
    RAG_USER_PROMPT,
)
from app.chat.schemas import GraphEntity, RetrievedDoc
from app.middleware.auth_middleware import get_trace_id
from app.config import settings
from app.monitoring import metrics as _metrics


# ============================================================
# 1. 格式化上下文：docs → doc[1] ... doc[N] 编号；graph → bullet
# ============================================================
def _summarize(text: str, limit: int = 160) -> str:
    s = (text or "").strip().replace("\r", "").replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 1] + "…"


def format_docs_for_prompt(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "（暂无匹配的参考材料，以下内容为空）"
    blocks: list[str] = []
    for idx, d in enumerate(docs, start=1):
        meta_bits: list[str] = []
        if d.series_code:
            meta_bits.append(f"系列={d.series_code}")
        if d.series_name:
            meta_bits.append(f"系列名={d.series_name}")
        if d.module_codes:
            meta_bits.append(f"模块={','.join(d.module_codes)}")
        if d.source_file:
            meta_bits.append(f"来源={d.source_file}")
        meta = f"[{', '.join(meta_bits)}]" if meta_bits else ""
        content_block = (d.content or "").strip()
        if len(content_block) > 1200:
            content_block = content_block[:1199] + "…"
        blocks.append(
            f"doc[{idx}] {meta}\n{content_block}\n"
        )
    return "\n".join(blocks).strip()


def format_graph_for_prompt(graph_entities: list[GraphEntity]) -> str:
    if not graph_entities:
        return "（暂无图谱扩展上下文）"
    lines: list[str] = []
    for g in graph_entities:
        rels = "、".join(g.related[:6])
        lines.append(f"- [{g.entity_type}] {g.entity_name}（相关：{rels or '无'}）")
    return "\n".join(lines).strip()


def format_history_for_prompt(history_turns: list[tuple[str, str]]) -> str:
    """history_turns: 按时间正序 [(role, content), ...]，这里倒取 N 轮再正序输出。"""
    if not history_turns:
        return ""
    lines = ["## 历史对话（用于指代承接，不要编造历史里不存在的信息）"]
    for role, content in history_turns:
        lines.append(
            HISTORY_TURN_TEMPLATE.format(role=role, content_summary=_summarize(content, limit=220))
        )
    return "\n".join(lines).strip()


# ============================================================
# 2. 本地兜底答案生成（完全离线，给打靶用）：规则生成，避免 500
# ============================================================
def _append_mcp_context(answer: str, mcp_context: str) -> str:
    """规则兜底场景：把 MCP 工具执行结果明确写进答案（避免只有 mcp_tool_calls 但正文没数字的问题）。"""
    if not mcp_context:
        return answer
    block = mcp_context.strip()
    if not block:
        return answer
    header = "---\n\n#### 工具计算结果（MCP）\n"
    if header.strip() in answer:
        return answer
    return (answer.rstrip() + "\n\n" + header + block + "\n")


def _local_rule_answer(query: str, docs: list[RetrievedDoc], degraded: str | None) -> tuple[str, str | None]:
    """
    返回 (answer, extra_degraded_reason)
    简单策略：
    - 若有 docs：拼接 doc[1]/doc[2] 的摘要 + 引用；
    - 无 docs：给 FALLBACK_NO_DOCS
    """
    extra: list[str] = []
    if degraded:
        extra.append(f"当前处于开发降级模式：{degraded}")
    if docs:
        head = docs[: min(3, len(docs))]
        points = []
        for idx, d in enumerate(head, start=1):
            snippet = _summarize(d.content, limit=260)
            points.append(f"{idx}. 参考片段（相关度 {d.score:.3f}）：{snippet}")
        refs = "引用：" + "；".join(
            f"doc[{i+1}] {_summarize(d.content, limit=48)}" for i, d in enumerate(head)
        )
        body = (
            "以下是基于当前知识库匹配的要点摘要（开发环境：LLM 调用失败后回退到规则版）：\n"
            + "\n".join(points)
            + "\n\n" + refs
        )
        if extra:
            body += "\n\n提示：" + "；".join(extra)
        return body, ("LLM 未启用（本地规则兜底）" if not degraded else None)
    return FALLBACK_NO_DOCS + ("\n\n提示：" + "；".join(extra) if extra else ""), "无检索结果 + LLM 未启用（本地规则兜底）"


# ============================================================
# 3. LLM 客户端封装（OpenAI-compatible 同步 HTTP → 包装为 async 跑在线程池）
# ============================================================
def _retry_after_from(resp) -> float | None:
    """从 LLM 响应头解析 ``Retry-After``（秒），供重试退避覆盖默认指数/线性。
    对标 OpenAI/Anthropic 官方 SDK：429/503 响应携带 Retry-After 时应以服务方指令为准。
    解析失败/缺头 → 返回 None（回退 core/retry 默认退避）。"""
    try:
        raw = resp.headers.get("Retry-After") if getattr(resp, "headers", None) else None
        if raw is None:
            return None
        raw = str(raw).strip()
        if not raw:
            return None
        # 仅支持秒级数值（HTTP-date 形式极少见，遇则按 None 处理交给默认退避）
        return float(raw)
    except (TypeError, ValueError):
        return None


class _ChatClient:
    """兼容 DashScope compatible-mode 与任何 OpenAI 协议服务；单例懒加载。

    关键修复（2026-08-10 根因#3）：
      - requests 库在 Windows 下会自动从「系统注册表（IE 代理设置）/ 环境变量」读取 HTTP/HTTPS 代理，
        若本机存在 127.0.0.1:7993 这类本地代理劫持（甚至只是注册表残留），会直接导致：
            SSLEOFError / ReadTimeout 从而所有 LLM 请求失败。
        修复方式：创建 requests.Session 并设置 session.trust_env = False，
        彻底禁用"从 env / 系统代理 / netrc 自动读取代理与凭证"，强制直连 LLM_BASE_URL。
    """

    _instance: "_ChatClient | None" = None

    def __init__(self) -> None:
        # 延迟导入保证 import 本模块不抛；真实环境里 requests 已存在（knowledge_hit 用到）
        import requests as _requests_mod
        self._requests = _requests_mod
        # 用 Session 复用连接 + 禁用系统/环境代理（根治 127.0.0.1 代理劫持导致的 SSLEOF 与 ReadTimeout）
        self._session = self._requests.Session()
        self._session.trust_env = False

    @classmethod
    def get(cls) -> "_ChatClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _headers(self, model: str = "fast") -> dict:
        # 双源（2026-08-22 用户裁定）：FAST=火山引擎 ark plan/v3；STRONG=DeepSeek 官方。
        # 配置了 LLM_FAST/STRONG_* 专属 base/key 时按档位选择；否则回退同源。
        if model == "strong" and settings.LLM_STRONG_BASE_URL and settings.LLM_STRONG_API_KEY:
            api_key = settings.LLM_STRONG_API_KEY
        elif model != "strong" and settings.LLM_FAST_BASE_URL and settings.LLM_FAST_API_KEY:
            api_key = settings.LLM_FAST_API_KEY
        else:
            api_key = settings.LLM_API_KEY
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _base_url(self, model: str) -> str:
        # 双源 base；留空回退 LLM_BASE_URL（同源）
        if model == "strong" and settings.LLM_STRONG_BASE_URL:
            return settings.LLM_STRONG_BASE_URL
        if model != "strong" and settings.LLM_FAST_BASE_URL:
            return settings.LLM_FAST_BASE_URL
        return settings.LLM_BASE_URL

    def _model_name(self, model: str) -> str:
        return settings.LLM_MODEL_STRONG if model == "strong" else settings.LLM_MODEL_FAST

    def call_chat_with_retry(self, *, messages: list[dict], model: str, temperature: float,
                             max_tokens: int, timeout: float = 60.0) -> str:
        """task-G1-①：智能重试退避（按错误类型动态，对齐 core/retry.py）。

        - 限流(429/RateLimit) → 指数退避 2^n 秒（封顶 30s）；
        - 超时(Timeout) → 线性退避 1s/次；
        - 模型错误(invalid_request/model_error) → 立即切 FAST↔STRONG 重试一次（同模型不重试）。
        超过该类型上限仍失败 → 抛出异常，由调用方落规则兜底（不破坏既有降级链）。
        """
        from app.core import retry as _retry

        current = model
        attempt = 1
        while True:
            try:
                return self.call_chat(
                    messages=messages, model=current, temperature=temperature,
                    max_tokens=max_tokens, timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001
                cat = _retry.classify_error(exc)
                # 模型错误：立即切换备用模型源（FAST↔STRONG）并重试一次
                if _retry.should_switch_model(cat):
                    other = _retry.switch_model_source(current)
                    logger.warning(
                        f"[LLM] 模型错误({type(exc).__name__}) → 切换模型源 {current}→{other} 重试",
                        trace_id=get_trace_id(),
                    )
                    current = other
                    try:
                        return self.call_chat(
                            messages=messages, model=current, temperature=temperature,
                            max_tokens=max_tokens, timeout=timeout,
                        )
                    except Exception as exc2:  # noqa: BLE001
                        logger.warning(f"[LLM] 切换模型源后仍失败：{type(exc2).__name__}: {exc2}")
                        raise
                if not _retry.should_retry(cat, attempt):
                    raise
                wait = _retry.next_backoff(cat, attempt, retry_after=getattr(exc, "retry_after", None))
                if wait > 0:
                    time.sleep(wait)
                attempt += 1

    def call_chat_stream_with_retry(self, *, messages: list[dict], model: str, temperature: float,
                                    max_tokens: int, timeout: float = 180.0):
        """task-G1-①：流式版智能重试（仅在尚未吐出任何 token 时重试，避免重复输出）。"""
        from app.core import retry as _retry

        current = model
        attempt = 1
        while True:
            yielded = False
            try:
                for tok in self.call_chat_stream(
                    messages=messages, model=current, temperature=temperature,
                    max_tokens=max_tokens, timeout=timeout,
                ):
                    yielded = True
                    yield tok
                return
            except Exception as exc:  # noqa: BLE001
                if yielded:
                    raise  # 已吐出 token，不再重试（防重复）
                cat = _retry.classify_error(exc)
                if _retry.should_switch_model(cat):
                    current = _retry.switch_model_source(current)
                    continue
                if not _retry.should_retry(cat, attempt):
                    raise
                wait = _retry.next_backoff(cat, attempt, retry_after=getattr(exc, "retry_after", None))
                if wait > 0:
                    time.sleep(wait)
                attempt += 1

    def call_chat(self, *, messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float = 60.0):
        body = {
            "model": self._model_name(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        import time as _time

        _t0 = _time.perf_counter()
        _ok = False
        try:
            resp = self._session.post(
                f"{self._base_url(model)}/chat/completions",
                headers=self._headers(model),
                json=body,
                timeout=timeout,
            )
            _ok = resp.status_code == 200
        finally:
            _latency = (_time.perf_counter() - _t0) * 1000
            try:
                from app.monitoring.metrics import llm_duration_seconds, llm_requests_total
                llm_requests_total.labels(
                    model=self._model_name(model), stream="false",
                    status="ok" if _ok else "error",
                ).inc()
                llm_duration_seconds.labels(
                    model=self._model_name(model), stream="false",
                ).observe(_latency / 1000)
            except Exception:
                pass
            # 慢 LLM 告警（P1-1 可观测性）：单次 >20s 打 WARNING，正常打 DEBUG
            if _latency > 20_000:
                logger.warning(
                    f"[LLM] 慢响应 {_latency:.0f}ms > 20s 阈值 (model={self._model_name(model)}, non-stream)",
                    trace_id=get_trace_id(), llm_model=self._model_name(model),
                    llm_latency_ms=round(_latency, 1), slow_llm=True,
                )
            else:
                logger.debug(
                    f"[LLM] {_latency:.0f}ms (model={self._model_name(model)}, non-stream)",
                    trace_id=get_trace_id(), llm_model=self._model_name(model),
                    llm_latency_ms=round(_latency, 1),
                )
        if resp.status_code != 200:
            exc = RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:400]}")

            # critique round4（对标 OpenAI SDK）：429/503 携带 Retry-After 时，
            # 附加到异常供重试退避覆盖默认指数/线性（尊重服务方退避指令）。
            ra = _retry_after_from(resp)
            if ra is not None:
                exc.retry_after = ra
            raise exc
        data = resp.json()
        # task97 R5 缓存监控：上报 cache_read/creation token（真实多轮对话观测命中率）
        self._report_cache_usage(data, model)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"LLM 响应结构异常：{data}") from e

    def _report_cache_usage(self, data: dict, model: str) -> None:
        """解析 usage.prompt_tokens_details.cache_read/creation_input_tokens，上报 CacheMonitor。

        兼容 OpenAI-compatible / DeepSeek / 火山 ark 的 usage 字段（缺失则安全跳过）。
        模型切换（同 tier 内模型名变化）→ 自动记录 model_switch 失效（命中率骤降根因）。
        同步入口（record_llm_call_sync）：本方法在线程池（run_in_executor）中调用，无事件循环。
        """
        usage = (data or {}).get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        cache_read = int(details.get("cache_read_input_tokens") or 0)
        cache_creation = int(details.get("cache_creation_input_tokens") or 0)
        prompt_total = int(usage.get("prompt_tokens") or 0)
        if cache_read == 0 and cache_creation == 0 and prompt_total == 0:
            return  # 无缓存用量信息（如本地规则兜底 / 网关未回 usage）→ 不上报
        try:
            from app.ai.cache_monitor import get_cache_monitor

            get_cache_monitor().record_llm_call_sync(
                cache_read=cache_read, cache_creation=cache_creation,
                prompt_total=prompt_total, model=self._model_name(model), tier=model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[cache_monitor] 上报失败（忽略）: {exc}")

        # task-O1 AC2：同步上报 OTel 缓存命中事件，供 5 维指标 CacheHitRate 消费
        # （与 task97 CacheMonitor 各司其职：此处产出可溯源的结构化 cache_event）。
        try:
            from app.otel.exporter import get_otel_exporter

            get_otel_exporter().record_cache_event(
                cache_read=cache_read,
                cache_miss=max(0, prompt_total - cache_read - cache_creation),
                model=self._model_name(model),
                layer="project",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[otel] 缓存事件上报失败（忽略）: {exc}")

    def call_chat_stream(self, *, messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float = 180.0):
        """生成器：每次 yield 一个增量 token 字符串。"""
        body = {
            "model": self._model_name(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        import time as _time

        _t0 = _time.perf_counter()
        _first_token_logged = False
        _total_tokens = 0
        with self._session.post(
            f"{self._base_url(model)}/chat/completions",
            headers=self._headers(model),
            json=body,
            timeout=timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                exc = RuntimeError(f"LLM stream HTTP {resp.status_code}: {resp.text[:400]}")

                # critique round4（对标 OpenAI SDK）：429/503 携带 Retry-After 时附加到异常。
                ra = _retry_after_from(resp)
                if ra is not None:
                    exc.retry_after = ra
                raise exc
            # 关键修复（2026-08-12 根因）：LLM 网关返回 content-type: application/json 无 charset，
            # requests 对响应流推断 encoding=ISO-8859-1，iter_lines(decode_unicode=True) 会把 UTF-8 中文
            # 误解码成 mojibake（如 "你好世界" → "ä½ å¥½"）。resp.json() 有特殊修正不受影响，但流式必须显式指定。
            resp.encoding = "utf-8"
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if raw_line.startswith("data:"):
                    raw_line = raw_line[5:].lstrip()
                if raw_line == "[DONE]":
                    # 流结束：记录总耗时
                    _total_ms = (_time.perf_counter() - _t0) * 1000
                    logger.debug(
                        f"[LLM-stream] 完成 {_total_ms:.0f}ms, {_total_tokens} tokens (model={self._model_name(model)})",
                        trace_id=get_trace_id(), llm_model=self._model_name(model),
                        llm_stream_total_ms=round(_total_ms, 1), llm_tokens=_total_tokens,
                    )
                    return
                try:
                    obj = json.loads(raw_line)
                except Exception:
                    continue
                # task97 R5：流式最后一帧带 usage（stream_options.include_usage=True）→ 上报缓存命中
                if "usage" in obj and obj.get("usage") is not None:
                    self._report_cache_usage(obj, model)
                try:
                    delta = obj["choices"][0]["delta"]["content"]
                except (KeyError, IndexError, TypeError):
                    continue
                if delta:
                    # 首个 token：记录首 token 延迟（TTFT）
                    if not _first_token_logged:
                        _first_token_logged = True
                        _ttft_ms = (_time.perf_counter() - _t0) * 1000
                        try:
                            from app.monitoring.metrics import llm_requests_total, llm_ttft_seconds
                            llm_requests_total.labels(
                                model=self._model_name(model), stream="true", status="ok",
                            ).inc()
                            llm_ttft_seconds.labels(model=self._model_name(model)).observe(_ttft_ms / 1000)
                        except Exception:
                            pass
                        logger.debug(
                            f"[LLM-stream] 首 token {_ttft_ms:.0f}ms (model={self._model_name(model)})",
                            trace_id=get_trace_id(), llm_model=self._model_name(model),
                            llm_ttft_ms=round(_ttft_ms, 1),
                        )
                    _total_tokens += 1
                    yield delta


# ============================================================
# 4. 对外：非流式 & 流式
# ============================================================
def build_messages(
    *,
    query: str,
    docs: list[RetrievedDoc],
    graph_entities: list[GraphEntity],
    history_turns: list[tuple[str, str]],
    platform_rule: str = "当前版本支持英语/考研数学/编程入门三类知识库；其他学科内容将陆续补充。",
    mcp_context: str = "",
    strict_rag: bool = True,
) -> list[dict]:
    """把组件拼起来形成最终 messages（给单元测/路由都能用）。
    mcp_context 非空时，会拼到 system prompt 末尾（P8：工具结果注入）。
    strict_rag=False：用普通对话 prompt（Agent 决策无需检索时，避免闲聊被 RAG 规则拒答）。"""
    from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT
    from app.chat.tool_calling import inject_mcp_into_system_prompt

    if strict_rag:
        system_prompt_base = RAG_SYSTEM_PROMPT.format(
            context_str=format_docs_for_prompt(docs),
            graph_str=format_graph_for_prompt(graph_entities),
            platform_rule=platform_rule,
        )
        user_prompt = RAG_USER_PROMPT.format(
            history_str=format_history_for_prompt(history_turns),
            query=query,
        )
    else:
        system_prompt_base = CHAT_SYSTEM_PROMPT.format(platform_rule=platform_rule)
        user_prompt = CHAT_USER_PROMPT.format(
            history_str=format_history_for_prompt(history_turns),
            query=query,
        )
    system_prompt = inject_mcp_into_system_prompt(system_prompt_base, mcp_context)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def generate_answer(
    *,
    query: str,
    docs: list[RetrievedDoc],
    graph_entities: list[GraphEntity],
    history_turns: list[tuple[str, str]],
    model: str = "fast",
    degraded_reason: str | None,
    mcp_context: str = "",
    strict_rag: bool = True,
) -> tuple[str, str | None]:
    """
    非流式：返回 (answer_text, extra_degraded)。
    任何 LLM 异常都捕获 → 回退 _local_rule_answer。
    """
    t0 = time.perf_counter()
    messages = build_messages(
        query=query, docs=docs, graph_entities=graph_entities, history_turns=history_turns,
        mcp_context=mcp_context, strict_rag=strict_rag,
    )
    # 开发环境里 Key 不对时，LLM_API_KEY 占位但真实会 401/403。这里把这些当正常失败捕获。
    try:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None,
            lambda: client.call_chat_with_retry(
                messages=messages,
                model=model,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            ),
        )
        cost_ms = int((time.perf_counter() - t0) * 1000)
        logger.debug(f"[P2 generate] LLM 非流式 OK，cost={cost_ms}ms，len={len(answer)}")
        _metrics.clear_degraded("llm")
        return answer, degraded_reason
    except Exception as e:
        logger.warning(f"[P2 generate] LLM 非流式失败，降级规则答案：{type(e).__name__}: {e}")
        # task39 GWT②：LLM 宕机 → 规则兜底答案（§6.4 矩阵行），指标可见
        _metrics.record_degraded("llm", f"generate:{type(e).__name__}")
        rule_ans, rule_deg = _local_rule_answer(query, docs, degraded_reason)
        merged_deg = "；".join([x for x in [degraded_reason, "LLM 调用失败，已降级规则答案（详见服务端日志）", rule_deg] if x])
        final_ans = _append_mcp_context(rule_ans, mcp_context)
        return final_ans, (merged_deg or None)


async def generate_stream(
    *,
    query: str,
    docs: list[RetrievedDoc],
    graph_entities: list[GraphEntity],
    history_turns: list[tuple[str, str]],
    model: str = "fast",
    degraded_reason: str | None,
    mcp_context: str = "",
    strict_rag: bool = True,
) -> AsyncGenerator[str, None]:
    """
    流式：逐个增量 token。LLM 失败/流式抛错 → 直接回退到规则答案按 chunk 流式输出。
    """
    messages = build_messages(
        query=query, docs=docs, graph_entities=graph_entities, history_turns=history_turns,
        mcp_context=mcp_context, strict_rag=strict_rag,
    )
    stream_fallback_text: str | None = None

    try:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        # 流式是阻塞生成器 → 放到线程池里消费：用 queue 跨线程桥接
        import queue
        import threading

        q: queue.Queue[str | BaseException | None] = queue.Queue()

        def _worker():
            try:
                for token in client.call_chat_stream_with_retry(
                    messages=messages,
                    model=model,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                ):
                    q.put(token)
                q.put(None)
            except BaseException as e:  # noqa: BLE001
                q.put(e)

        th = threading.Thread(target=_worker, daemon=True)
        th.start()

        while True:
            try:
                # 根因 #4：a6api 中转 DeepSeek 首包 TTFT 波动大，冷启动/长 prompt 可达 30~50s。
                # 30s 经常误杀 → 回退规则兜底 → 用户看到 "当前处于开发降级模式"。
                # 放宽到 60s：覆盖 a6api 99% 正常响应窗口，同时仍避免真正挂死。
                item = await loop.run_in_executor(None, q.get, True, 60.0)
            except queue.Empty:
                raise TimeoutError("LLM stream 60s 无增量，超时降级")
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    except Exception as e:
        logger.warning(f"[P2 generate_stream] LLM 流式失败，降级规则答案：{type(e).__name__}: {e}")
        # task39 GWT②：流式 LLM 宕机降级，同非流式口径计入 edu_degraded_total{component="llm"}
        _metrics.record_degraded("llm", f"generate_stream:{type(e).__name__}")
        merged_deg = "；".join([x for x in [degraded_reason, "LLM 流式失败，已降级规则答案（详见服务端日志）"] if x])
        rule_ans, _rule_deg = _local_rule_answer(query, docs, merged_deg)
        stream_fallback_text = _append_mcp_context(rule_ans, mcp_context)

    if stream_fallback_text is not None:
        # 每 1~2 个字吐一次，模拟流式体感
        step = 2
        for i in range(0, len(stream_fallback_text), step):
            yield stream_fallback_text[i : i + step]
            await asyncio.sleep(0.01)
