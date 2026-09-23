/**
 * useChatStream
 *
 * 对 chatStream() API 的 React 状态化封装：
 *   - 维护一条"正在生成的 assistant 消息"（immutable，setMessages 追加）
 *   - 每收到 delta/sources/tool_calls 事件，增量更新到该 pending 消息的 refs
 *   - **揭示节奏与网络到达解耦（打字机队列）**：只控制"何时显示已到达的增量"，
 *     不改内容、不改 SSE 解析契约（TA1 定因见 REPORT-TA1-3）
 *   - abort() → 停止生成但保留已接收内容（作为"被用户中断的回复"）
 *
 * [TA1 定因/修复] 为什么需要节拍器而不是"到达即渲染"：
 *   CDP 实测（同机 9988 直连 + 上游 api.deepseek.com 裸 socket）——
 *   上游 LLM 吞吐 400~620 字/秒，整段 token 窗口仅 0.24~1.3s；旧实现按 80ms 节流 1:1 渲染，
 *   一次 354~640 字的回答只出 20 个中间态、可见窗口约 1.25s，肉眼等同"转圈后整段弹出"。
 *   现按固定节拍揭示 acc.slice(0, shown)：最小 90 字/秒（保证逐字可见），
 *   剩余缓冲越多越快（尾部至多 REVEAL_TAIL_MS），并有 REVEAL_FORCE_MS 硬兜底。
 *
 * task40 对齐：ChatMessage 主键 = message_id（后端契约），流式占位消息
 * 以 message_id 对齐；工具调用以 call_id 键控（MCPToolCall 契约字段）。
 *
 * 调用方用法：
 *   const { messages, isStreaming, send, stop, pendingAssistantMsgId } = useChatStream({
 *     onFirstMessage: () => ensureSession(),
 *   });
 *   send("什么是勾股定理？", { sessionId });
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  chatStream,
  type ChatMessage,
  type ChatSendOptions,
  type MCPToolCall,
  type RetrievedDoc,
} from "@/lib/api/chat";

/* [TA1] 揭示节拍参数（与 edu-frontend/public/chat.html 的 openStream 保持同构语义） */
const REVEAL_TICK_MS = 30;
const REVEAL_MIN_CPS = 90; // 最小揭示速度（字/秒）
const REVEAL_TAIL_MS = 2200; // 剩余缓冲至多再花这么久排空
const REVEAL_FORCE_MS = 20000; // 硬兜底：揭示最长 20s，超时立即全量

export interface UseChatStreamOptions {
  /** 发送第一条消息前的钩子，可用于懒创建会话并返回 sessionId */
  onFirstMessage?: () => Promise<string | null | undefined> | string | null | undefined;
  /** 任意错误回调（组件通常直接 toast 展示） */
  onError?: (err: Error) => void;
  /** 流完成回调（含契约⑬ done 内嵌壳透出的 degraded_reason / latency / retrieved_count） */
  onFinalMessage?: (finalMessage: ChatMessage) => void;
}

export interface UseChatStreamHandle {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  isStreaming: boolean;
  pendingAssistantMsgId: string | null;
  send: (
    text: string,
    opts?: Omit<ChatSendOptions, "onDelta" | "onSources" | "onToolStart" | "onToolProgress" | "onToolResult" | "onDone" | "onError">,
  ) => Promise<void>;
  stop: () => void;
}

/** 流式过程中的占位消息构造：非契约字段置空，视图层只读 content/sources/tool_calls/streaming */
function makeStreamingMessage(
  messageId: string,
  sessionId: string | null,
  role: "user" | "assistant",
  content: string,
): ChatMessage {
  return {
    message_id: messageId,
    session_id: sessionId ?? "",
    user_id: 0,
    role,
    content,
    rag_query_rewrite: null,
    rag_retrieved_count: null,
    rag_final_count: null,
    rag_docs_json: null,
    rag_error: null,
    latency_ms: null,
    mcp_tool_calls_json: null,
    mcp_called_count: null,
    created_at: new Date().toISOString(),
    sources: null,
    tool_calls: null,
    streaming: role === "assistant",
  };
}

export function useChatStream(options: UseChatStreamOptions = {}): UseChatStreamHandle {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingAssistantMsgId, setPendingAssistantMsgId] = useState<string | null>(null);

  const acRef = useRef<AbortController | null>(null);
  // 当前正在生成的消息的草稿（refs 存储增量；content = 已到达全量（事实源），shown = 已揭示长度）
  const draftRef = useRef<{
    messageId: string;
    content: string;
    shown: number;
    sources: RetrievedDoc[] | null;
    tools: Record<string, MCPToolCall>;
    sessionId: string | null;
  } | null>(null);
  const isStreamingRef = useRef(false);
  /* [TA1] 揭示节拍器状态 */
  const pacerRef = useRef<number | null>(null);
  const streamDoneRef = useRef(false); // 已收到 done 帧（此后仅等揭示排空）
  const revealStartRef = useRef(0);
  const finishedRef = useRef(false);

  /** 把「已揭示」的可见前缀写入 React 状态（不写全量，否则打字机效果被一次性覆盖） */
  const flush = useCallback(() => {
    if (!draftRef.current) return;
    const d = draftRef.current;
    const visible = d.content.slice(0, d.shown);
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.message_id === d.messageId);
      const next: ChatMessage = {
        ...makeStreamingMessage(d.messageId, d.sessionId, "assistant", visible),
        sources: d.sources && d.sources.length ? d.sources : null,
        tool_calls: Object.values(d.tools).length ? Object.values(d.tools) : null,
      };
      if (idx < 0) return [...prev, next];
      const clone = prev.slice();
      clone[idx] = next;
      return clone;
    });
  }, []);

  const stopPacer = useCallback(() => {
    if (pacerRef.current !== null) {
      window.clearInterval(pacerRef.current);
      pacerRef.current = null;
    }
  }, []);

  const finalizePending = useCallback(() => {
    stopPacer();
    if (!draftRef.current) return;
    const d = draftRef.current;
    d.shown = d.content.length; // 收尾一次性补齐（揭示排空后的正常路径：这里无额外变化）
    flush();
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.message_id === d.messageId);
      if (idx < 0) return prev;
      const clone = prev.slice();
      clone[idx] = { ...clone[idx], streaming: false };
      return clone;
    });
    draftRef.current = null;
    finishedRef.current = true;
    setPendingAssistantMsgId(null);
    setIsStreaming(false);
    isStreamingRef.current = false;
  }, [flush, stopPacer]);

  /** done 帧到达且揭示已排空 → 才真正收尾（否则 done 一到就整段弹出，打字机等于没有） */
  const maybeFinalize = useCallback(() => {
    if (finishedRef.current) return true;
    const d = draftRef.current;
    if (!d) return false;
    if (!streamDoneRef.current || d.shown < d.content.length) return false;
    finalizePending();
    return true;
  }, [finalizePending]);

  /** 揭示一步：速率随剩余缓冲自适应（越大越快），保证既可见又不拖尾 */
  const revealTick = useCallback(() => {
    const d = draftRef.current;
    if (!d || finishedRef.current) {
      stopPacer();
      return;
    }
    const remain = d.content.length - d.shown;
    if (remain > 0) {
      const cps = Math.max(REVEAL_MIN_CPS, remain / (REVEAL_TAIL_MS / 1000));
      const step = Math.max(1, Math.round((cps * REVEAL_TICK_MS) / 1000));
      d.shown = Math.min(d.content.length, d.shown + step);
      flush();
    }
    if (
      revealStartRef.current > 0 &&
      Date.now() - revealStartRef.current > REVEAL_FORCE_MS &&
      d.shown < d.content.length
    ) {
      d.shown = d.content.length;
      flush();
    }
    if (d.shown >= d.content.length) maybeFinalize();
  }, [flush, maybeFinalize, stopPacer]);

  const ensurePacer = useCallback(() => {
    if (pacerRef.current !== null || finishedRef.current || !draftRef.current) return;
    if (!revealStartRef.current) revealStartRef.current = Date.now();
    pacerRef.current = window.setInterval(revealTick, REVEAL_TICK_MS);
  }, [revealTick]);

  const stop = useCallback(() => {
    if (acRef.current) {
      acRef.current.abort();
      acRef.current = null;
    }
    finalizePending();
  }, [finalizePending]);

  const send = useCallback<UseChatStreamHandle["send"]>(async (text, opts) => {
    if (isStreamingRef.current) return;
    const trimmed = text.trim();
    if (!trimmed) return;

    // 用户消息先入队
    const userMsgId = `u_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const userMsg = makeStreamingMessage(userMsgId, opts?.sessionId ?? null, "user", trimmed);
    setMessages((prev) => [...prev, userMsg]);

    // 准备 pending assistant 消息
    const pendingId = `a_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    draftRef.current = {
      messageId: pendingId,
      content: "",
      shown: 0,
      sources: null,
      tools: {},
      sessionId: opts?.sessionId ?? null,
    };
    /* [TA1] 重置揭示节拍状态（上一轮的 timer/标志不得串到本轮） */
    stopPacer();
    streamDoneRef.current = false;
    revealStartRef.current = 0;
    finishedRef.current = false;
    setPendingAssistantMsgId(pendingId);
    setIsStreaming(true);
    isStreamingRef.current = true;
    // 先占个空位置，避免消息列表抖动
    setMessages((prev) => [
      ...prev,
      makeStreamingMessage(pendingId, opts?.sessionId ?? null, "assistant", ""),
    ]);

    let sessionId = opts?.sessionId ?? null;
    if (!sessionId && typeof options.onFirstMessage === "function") {
      try {
        const resolved = await options.onFirstMessage();
        if (resolved != null) sessionId = resolved;
        if (draftRef.current) draftRef.current.sessionId = sessionId;
      } catch (e) {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.message_id === pendingId);
          if (idx < 0) return prev;
          const clone = prev.slice();
          clone[idx] = {
            ...clone[idx],
            role: "system",
            content: `创建会话失败：${e instanceof Error ? e.message : String(e)}`,
            streaming: false,
          };
          return clone;
        });
        setIsStreaming(false);
        isStreamingRef.current = false;
        setPendingAssistantMsgId(null);
        draftRef.current = null;
        options.onError?.(e instanceof Error ? e : new Error(String(e)));
        return;
      }
    }

    const ac = chatStream(trimmed, {
      ...opts,
      sessionId,
      onDelta: (chunk) => {
        if (!draftRef.current) return;
        draftRef.current.content += chunk;
        ensurePacer();
      },
      onSources: (sources) => {
        if (!draftRef.current) return;
        draftRef.current.sources = sources;
        ensurePacer();
      },
      onToolStart: (call) => {
        if (!draftRef.current) return;
        draftRef.current.tools[call.call_id] = call;
        ensurePacer();
      },
      onToolProgress: (update) => {
        if (!draftRef.current) return;
        const prev = draftRef.current.tools[update.call_id] ?? {
          call_id: update.call_id, tool_name: update.tool_name ?? "mcp.tool", status: "running",
        };
        draftRef.current.tools[update.call_id] = { ...prev, ...update, status: "running" };
        ensurePacer();
      },
      onToolResult: (update) => {
        if (!draftRef.current) return;
        const prev = draftRef.current.tools[update.call_id] ?? {
          call_id: update.call_id, tool_name: update.tool_name ?? "mcp.tool", status: "success",
        };
        draftRef.current.tools[update.call_id] = { ...prev, ...update };
        ensurePacer();
      },
      onDone: (finalMessage) => {
        if (acRef.current === ac) acRef.current = null;
        /* [TA1] done = "服务端生成完毕"，不等于"用户已看完"：
           置 streamDoneRef 后交给节拍器——揭示排空才 finalize，
           避免 token 突发（0.24~1.3s）一结束就整段弹出。 */
        streamDoneRef.current = true;
        if (!maybeFinalize()) ensurePacer();
        options.onFinalMessage?.(finalMessage);
      },
      onError: (err) => {
        if (acRef.current === ac) acRef.current = null;
        stopPacer();
        finishedRef.current = true;
        if (draftRef.current) {
          const d = draftRef.current;
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.message_id === d.messageId);
            if (idx < 0) return prev;
            const clone = prev.slice();
            clone[idx] = {
              ...clone[idx],
              role: "system",
              content: err.message || "生成失败，请稍后重试",
              streaming: false,
            };
            return clone;
          });
        }
        setIsStreaming(false);
        isStreamingRef.current = false;
        setPendingAssistantMsgId(null);
        draftRef.current = null;
        options.onError?.(err);
      },
    });
    acRef.current = ac;
  }, [options, maybeFinalize, ensurePacer, stopPacer]);

  useEffect(() => () => {
    if (pacerRef.current !== null) window.clearInterval(pacerRef.current);
    acRef.current?.abort();
  }, []);

  return { messages, setMessages, isStreaming, pendingAssistantMsgId, send, stop };
}
