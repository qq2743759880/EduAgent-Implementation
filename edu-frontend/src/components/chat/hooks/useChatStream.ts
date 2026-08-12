/**
 * useChatStream
 *
 * 对 chatStream() API 的 React 状态化封装：
 *   - 维护一条"正在生成的 assistant 消息"（immutable，setMessages 追加）
 *   - 每收到 delta/sources/tool_calls 事件，增量更新到该 pending 消息的 refs
 *   - 节流 setState（每 80ms 刷一次），避免每字一帧的 React re-render 风暴
 *   - abort() → 停止生成但保留已接收内容（作为"被用户中断的回复"）
 *
 * 调用方用法：
 *   const { messages, isStreaming, send, stop, pendingAssistantMsgId } = useChatStream({
 *     onFirstMessage: () => ensureSession(),
 *   });
 *   send("什么是勾股定理？", { subject_code: "math" });
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  chatStream,
  type ChatMessage,
  type ChatSendOptions,
  type MCPToolCall,
  type RagDoc,
} from "@/lib/api/chat";

const FLUSH_MS = 80;

export interface UseChatStreamOptions {
  /** 发送第一条消息前的钩子，可用于懒创建会话并返回 sessionId */
  onFirstMessage?: () => Promise<string | number | null | undefined> | string | number | null | undefined;
  /** 任意错误回调（组件通常直接 toast 展示） */
  onError?: (err: Error) => void;
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

export function useChatStream(options: UseChatStreamOptions = {}): UseChatStreamHandle {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingAssistantMsgId, setPendingAssistantMsgId] = useState<string | null>(null);

  const acRef = useRef<AbortController | null>(null);
  const flushTimerRef = useRef<number | null>(null);
  // 当前正在生成的消息的草稿（refs 存储增量，定期 flush 到 React 状态）
  const draftRef = useRef<{
    id: string;
    content: string;
    sources: RagDoc[] | null;
    tools: Record<string, MCPToolCall>;
    sessionId: string | number | null;
  } | null>(null);
  const isStreamingRef = useRef(false);

  const flush = useCallback(() => {
    flushTimerRef.current = null;
    if (!draftRef.current) return;
    const d = draftRef.current;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === d.id);
      const next: ChatMessage = {
        id: d.id,
        session_id: d.sessionId,
        role: "assistant",
        content: d.content,
        sources: d.sources && d.sources.length ? d.sources : null,
        tool_calls: Object.values(d.tools).length ? Object.values(d.tools) : null,
        streaming: true,
        created_at: new Date().toISOString(),
      };
      if (idx < 0) return [...prev, next];
      const clone = prev.slice();
      clone[idx] = next;
      return clone;
    });
  }, []);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current !== null) return;
    flushTimerRef.current = window.setTimeout(flush, FLUSH_MS);
  }, [flush]);

  const finalizePending = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
      flush();
    }
    if (!draftRef.current) return;
    const d = draftRef.current;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === d.id);
      if (idx < 0) return prev;
      const clone = prev.slice();
      clone[idx] = { ...clone[idx], streaming: false };
      return clone;
    });
    draftRef.current = null;
    setPendingAssistantMsgId(null);
    setIsStreaming(false);
    isStreamingRef.current = false;
  }, [flush]);

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
    const userMsg: ChatMessage = {
      id: userMsgId,
      session_id: opts?.sessionId ?? null,
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // 准备 pending assistant 消息
    const pendingId = `a_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    draftRef.current = {
      id: pendingId,
      content: "",
      sources: null,
      tools: {},
      sessionId: opts?.sessionId ?? null,
    };
    setPendingAssistantMsgId(pendingId);
    setIsStreaming(true);
    isStreamingRef.current = true;
    // 先占个空位置，避免消息列表抖动
    setMessages((prev) => [
      ...prev,
      {
        id: pendingId,
        session_id: opts?.sessionId ?? null,
        role: "assistant",
        content: "",
        streaming: true,
        sources: null,
        tool_calls: null,
        created_at: new Date().toISOString(),
      },
    ]);

    let sessionId = opts?.sessionId ?? null;
    if (!sessionId && typeof options.onFirstMessage === "function") {
      try {
        const resolved = await options.onFirstMessage();
        if (resolved != null) sessionId = resolved;
        if (draftRef.current) draftRef.current.sessionId = sessionId;
      } catch (e) {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === pendingId);
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
        scheduleFlush();
      },
      onSources: (sources) => {
        if (!draftRef.current) return;
        draftRef.current.sources = sources;
        scheduleFlush();
      },
      onToolStart: (call) => {
        if (!draftRef.current) return;
        draftRef.current.tools[call.id] = call;
        scheduleFlush();
      },
      onToolProgress: (update) => {
        if (!draftRef.current) return;
        const prev = draftRef.current.tools[update.id] ?? {
          id: update.id, tool_name: update.tool_name ?? "mcp.tool", status: "running",
        };
        draftRef.current.tools[update.id] = { ...prev, ...update, status: "running" };
        scheduleFlush();
      },
      onToolResult: (update) => {
        if (!draftRef.current) return;
        const prev = draftRef.current.tools[update.id] ?? {
          id: update.id, tool_name: update.tool_name ?? "mcp.tool", status: "success",
        };
        draftRef.current.tools[update.id] = { ...prev, ...update };
        scheduleFlush();
      },
      onDone: () => {
        if (acRef.current === ac) acRef.current = null;
        finalizePending();
      },
      onError: (err) => {
        if (acRef.current === ac) acRef.current = null;
        if (draftRef.current) {
          draftRef.current.content = draftRef.current.content || "（生成失败）";
          const d = draftRef.current;
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === d.id);
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
  }, [options, finalizePending, scheduleFlush]);

  useEffect(() => () => {
    if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
    acRef.current?.abort();
  }, []);

  return { messages, setMessages, isStreaming, pendingAssistantMsgId, send, stop };
}
