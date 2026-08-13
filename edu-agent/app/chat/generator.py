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
from app.config import settings


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

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

    def _model_name(self, model: str) -> str:
        return settings.LLM_MODEL_STRONG if model == "strong" else settings.LLM_MODEL_FAST

    def call_chat(self, *, messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float = 60.0):
        body = {
            "model": self._model_name(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        resp = self._session.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"LLM 响应结构异常：{data}") from e

    def call_chat_stream(self, *, messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float = 180.0):
        """生成器：每次 yield 一个增量 token 字符串。"""
        body = {
            "model": self._model_name(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with self._session.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"LLM stream HTTP {resp.status_code}: {resp.text[:400]}")
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
                    return
                try:
                    obj = json.loads(raw_line)
                except Exception:
                    continue
                try:
                    delta = obj["choices"][0]["delta"]["content"]
                except (KeyError, IndexError, TypeError):
                    continue
                if delta:
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
) -> list[dict]:
    """把组件拼起来形成最终 messages（给单元测/路由都能用）。
    mcp_context 非空时，会拼到 system prompt 末尾（P8：工具结果注入）。"""
    from app.chat.tool_calling import inject_mcp_into_system_prompt
    system_prompt_base = RAG_SYSTEM_PROMPT.format(
        context_str=format_docs_for_prompt(docs),
        graph_str=format_graph_for_prompt(graph_entities),
        platform_rule=platform_rule,
    )
    system_prompt = inject_mcp_into_system_prompt(system_prompt_base, mcp_context)
    user_prompt = RAG_USER_PROMPT.format(
        history_str=format_history_for_prompt(history_turns),
        query=query,
    )
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
) -> tuple[str, str | None]:
    """
    非流式：返回 (answer_text, extra_degraded)。
    任何 LLM 异常都捕获 → 回退 _local_rule_answer。
    """
    t0 = time.perf_counter()
    messages = build_messages(
        query=query, docs=docs, graph_entities=graph_entities, history_turns=history_turns,
        mcp_context=mcp_context,
    )
    # 开发环境里 Key 不对时，LLM_API_KEY 占位但真实会 401/403。这里把这些当正常失败捕获。
    try:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None,
            lambda: client.call_chat(
                messages=messages,
                model=model,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            ),
        )
        cost_ms = int((time.perf_counter() - t0) * 1000)
        logger.debug(f"[P2 generate] LLM 非流式 OK，cost={cost_ms}ms，len={len(answer)}")
        return answer, degraded_reason
    except Exception as e:
        logger.warning(f"[P2 generate] LLM 非流式失败，降级规则答案：{type(e).__name__}: {e}")
        rule_ans, rule_deg = _local_rule_answer(query, docs, degraded_reason)
        merged_deg = "；".join([x for x in [degraded_reason, f"LLM 调用失败({type(e).__name__})", rule_deg] if x])
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
) -> AsyncGenerator[str, None]:
    """
    流式：逐个增量 token。LLM 失败/流式抛错 → 直接回退到规则答案按 chunk 流式输出。
    """
    messages = build_messages(
        query=query, docs=docs, graph_entities=graph_entities, history_turns=history_turns,
        mcp_context=mcp_context,
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
                for token in client.call_chat_stream(
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
                # 修复（2026-08-10 根因#4）：真实 api.a6api.com 非流式 TTLB ≈ 10s，
                # 流式首包 TTFT 通常 6~12s。原 5s 增量超时会 100% 误杀正常请求，
                # 每一次都触发 TimeoutError → 回退规则兜底（正文出现 "当前处于开发降级模式"）。
                # 放宽到 30s：给冷启动 + 长 prompt prefill 留足余量，但仍避免真正挂死。
                item = await loop.run_in_executor(None, q.get, True, 30.0)
            except queue.Empty:
                raise TimeoutError("LLM stream 30s 无增量，超时降级")
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    except Exception as e:
        logger.warning(f"[P2 generate_stream] LLM 流式失败，降级规则答案：{type(e).__name__}: {e}")
        merged_deg = "；".join([x for x in [degraded_reason, f"LLM 流式失败({type(e).__name__})"] if x])
        rule_ans, _rule_deg = _local_rule_answer(query, docs, merged_deg)
        stream_fallback_text = _append_mcp_context(rule_ans, mcp_context)

    if stream_fallback_text is not None:
        # 每 1~2 个字吐一次，模拟流式体感
        step = 2
        for i in range(0, len(stream_fallback_text), step):
            yield stream_fallback_text[i : i + step]
            await asyncio.sleep(0.01)
