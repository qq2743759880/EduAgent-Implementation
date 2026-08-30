/**
 * ChatCandyClient — /chat AI 问答页（task50 糖果单栏，candy-playful frozen）
 * 单栏结构：顶部智能问答头部 / 中部消息区（消息气泡滚动）/ 底部 sticky 输入区。
 * 状态机：
 *   - 空态   ：无会话无消息 → EmptyState 引导 + 建议提问 chips
 *   - 历史加载失败：ErrorState（C8）+ 锁定输入
 *   - 流式   ：useChatStream 逐字渲染 + streaming 光标；首包前显示「AI 正在思考…」排队 pill
 *   - 降级   ：onFinalMessage 透出 done 内嵌壳 degraded_reason → 琥珀 degrade banner
 * 上下文携带：?context=session:{id} 深链到指定会话，展示「来自 · {会话标题}」徽标。
 * 复用：components/chat/* hooks + api（chat.ts SSE），C7/C8 状态组件。
 */
"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { ProtectedRoute } from "@/lib/protected-route";
import { useAuthStore } from "@/lib/auth-client";
import type { ChatMessage } from "@/lib/api/chat";
import { getChatHistory } from "@/lib/api/chat";

import { useChatSessions } from "@/components/chat/hooks/useChatSessions";
import { useChatStream } from "@/components/chat/hooks/useChatStream";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ChatBubble } from "@/components/feature/chat/ChatBubble";
import { ChatSessionList } from "@/components/feature/chat/ChatSessionList";
import {
  MessageComposer,
  type DegradeInfo,
  type MessageComposerHandle,
} from "@/components/feature/chat/MessageComposer";

const SUGGESTIONS = ["什么是反向传播？", "帮我整理第三章重点", "这道题怎么做？", "制定一周学习计划"];

interface ParsedContext {
  sessionId: string | null;
  /** URL 中是否存在 context 参数（用于上下文徽标） */
  active: boolean;
}

function parseContext(raw: string | null): ParsedContext {
  if (!raw) return { sessionId: null, active: false };
  const m = raw.match(/session:([A-Za-z0-9_-]+)/);
  return { sessionId: m?.[1] ?? null, active: true };
}

function getRetrievedCount(msg: ChatMessage): number {
  return msg.rag_retrieved_count ?? msg.sources?.length ?? 0;
}

export default function ChatCandyClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const ctx = React.useMemo(() => parseContext(sp.get("context")), [sp]);

  const ready = useAuthStore((s) => s.ready);
  const token = useAuthStore((s) => s.token);
  const logout = useAuthStore((s) => s.logout);
  const authed = ready && !!token;

  const {
    sessions,
    selectedId,
    createAndSelect,
    ensureSession,
    selectSession,
    deleteSession,
    sessionsLoading,
    refetch: refetchSessions,
  } = useChatSessions({ enabled: authed, initialSessionId: ctx.sessionId ?? undefined });

  const currentSession = React.useMemo(
    () => sessions.find((s) => s.session_id === selectedId) ?? null,
    [sessions, selectedId],
  );

  const [historyError, setHistoryError] = React.useState<string | null>(null);
  const [degrade, setDegrade] = React.useState<DegradeInfo | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  const {
    messages,
    setMessages,
    isStreaming,
    send,
    stop,
  } = useChatStream({
    async onFirstMessage() {
      const sid = await ensureSession();
      if (sid != null) refetchSessions();
      return sid;
    },
    onError(err) {
      const m = err.message || String(err);
      if (/401|403|Unauthorized/i.test(m) && authed) {
        toast.error("登录已过期，请重新登录", { description: m });
        try { logout?.({ silent: true }); } catch { /* ignore */ }
        router.replace(`/login?redirect=${encodeURIComponent("/chat")}`);
        return;
      }
      toast.error("AI 生成失败", { description: m });
    },
    onFinalMessage(finalMessage) {
      // 契约⑬ done 事件内嵌壳 data.degraded_reason 透出为降级 banner
      setDegrade(
        finalMessage.rag_error
          ? { title: "排队人数较多，已为你降级回答：", detail: finalMessage.rag_error }
          : null,
      );
    },
  });

  /* 会话切换 → 加载历史（并行：逐字渲染态互不干扰） */
  const hydratedIdRef = React.useRef<string | null>("__none__");
  React.useEffect(() => {
    if (!authed) return;
    if (selectedId == null) {
      setMessages([]);
      hydratedIdRef.current = null;
      return;
    }
    if (hydratedIdRef.current === selectedId) return;
    hydratedIdRef.current = selectedId;
    setDegrade(null);
    let cancelled = false;
    void (async () => {
      if (cancelled) return;
      setHistoryError(null);
      try {
        const history = await getChatHistory(selectedId);
        if (cancelled) return;
        setHistoryError(null);
        setMessages((prev) => {
          if (prev.length === 0) return history;
          const seen = new Set(prev.map((m) => m.message_id));
          const extra = history.filter((h) => !seen.has(h.message_id));
          return [...extra, ...prev];
        });
      } catch (e) {
        if (!cancelled) setHistoryError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, authed]);

  const handleSend = async (text: string) => {
    setDegrade(null);
    await send(text, { sessionId: selectedId ?? undefined });
    refetchSessions();
  };
  const handleStop = () => stop();

  const handleNewSession = async () => {
    // 中止进行中的流，避免旧会话的生成写回新会话空列表（幽灵消息）
    if (isStreaming) stop();
    const created = await createAndSelect({ title: "" });
    hydratedIdRef.current = created.session_id;
    setMessages([]);
    setHistoryError(null);
    setDegrade(null);
    refetchSessions();
    window.setTimeout(() => composerRef.current?.focusInput(), 60);
  };

  const handleSuggestion = async (text: string) => {
    await handleSend(text);
    composerRef.current?.focusInput();
  };

  /* 点选会话：中止进行中流（防幽灵消息）→ 清空当前消息 → 切换到目标会话（历史副作用按 selectedId 重载） */
  const handleSelectSession = (id: string) => {
    if (id === selectedId) {
      setDrawerOpen(false);
      return;
    }
    if (isStreaming) stop();
    setMessages([]);
    setHistoryError(null);
    setDegrade(null);
    selectSession(id);
    setDrawerOpen(false);
  };

  /* 删除会话：删的是当前项则先中止流并清空消息，让 deleteChatSession 选切邻居后历史副作用替换内容 */
  const handleDeleteSession = (id: string) => {
    if (id === selectedId) {
      if (isStreaming) stop();
      setMessages([]);
      setHistoryError(null);
      setDegrade(null);
    }
    deleteSession(id);
  };

  const sessionListEl = (
    <ChatSessionList
      sessions={sessions}
      activeId={selectedId}
      loading={sessionsLoading}
      onSelect={handleSelectSession}
      onNew={handleNewSession}
      onDelete={handleDeleteSession}
    />
  );

  /* 自动滚动到底部（新消息 / 流式增量） */
  const stageRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, historyError]);

  const composerRef = React.useRef<MessageComposerHandle | null>(null);

  // 首包前排队提示：流式中且当前 pending 消息尚无内容
  const pendingMsg = React.useMemo(
    () => messages.find((m) => m.streaming) ?? null,
    [messages],
  );
  const queueing = isStreaming && (pendingMsg ? (pendingMsg.content as string).length === 0 : true);

  const contextTag =
    ctx.active && currentSession
      ? `来自 · ${currentSession.title.trim() || "课程上下文"}`
      : ctx.active
        ? "来自 · 课程上下文"
        : null;

  if (!ready) {
    return (
      <div className="flex h-[calc(100dvh-64px)] w-full items-center justify-center bg-background text-muted-foreground">
        <div className="animate-pulse text-sm">正在加载 AI 助手…</div>
      </div>
    );
  }

  const stageContent = historyError ? (
    <ErrorState
      title="历史消息加载失败"
      message={historyError}
      retry={undefined}
      className="rounded-3xl border-0"
    />
  ) : messages.length === 0 ? (
    <EmptyState
      icon={<span aria-hidden="true" className="text-4xl">🦊</span>}
      title="开始你的 AI 学习助手"
      description={
        <>
          我可以基于<b className="font-bold">课程知识库</b>回答你的问题：课程大纲、知识点讲解、题目解析、学习计划……在下方输入即可。
        </>
      }
      action={
        <div className="flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleSuggestion(s)}
              className="rounded-full border-2 border-candy-purple bg-background px-3 py-1.5 text-xs font-bold text-candy-purple transition-colors hover:bg-candy-purple-soft"
            >
              {s}
            </button>
          ))}
        </div>
      }
      className="rounded-3xl border-2 border-dashed border-candy-purple/30"
    />
  ) : (
    messages.map((m) => (
      <ChatBubble
        key={m.message_id}
        role={m.role}
        content={m.content ?? ""}
        streaming={!!m.streaming}
        time={m.created_at}
        retrievedCount={getRetrievedCount(m)}
      />
    ))
  );

  return (
    <ProtectedRoute>
      <div
        data-slot="chat-candy-page"
        className="mx-auto flex h-[calc(100dvh-64px)] w-full max-w-[1240px] gap-3 bg-candy-bg px-2 py-3 sm:px-4"
      >
        {/* 主区 */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* 头部 */}
          <header className="mb-2 flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="打开会话列表"
              data-slot="chat-drawer-trigger"
              className="grid size-9 shrink-0 place-items-center rounded-xl border-2 border-foreground bg-background text-base shadow-[0_3px_0_color-mix(in_oklch,var(--foreground),transparent_82%)] md:hidden"
            >
              <span aria-hidden="true">☰</span>
            </button>
            <span aria-hidden="true" className="animate-[candy-float_3.4s_ease-in-out_infinite] text-3xl">
              🦊
            </span>
            <div className="min-w-0">
              <h1 className="text-xl font-extrabold leading-tight tracking-tight">智能问答</h1>
              <p className="text-xs text-muted-foreground">基于课程知识库，随时问我</p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleNewSession}
              className="ml-auto"
            >
              ＋ 新会话
            </Button>
          </header>

          {/* 消息区 */}
          <div
            ref={stageRef}
            data-slot="chat-stage"
            className="flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto py-2"
          >
            {stageContent}
          </div>

          {/* 输入区 */}
          <div className="pt-2">
            <MessageComposer
              ref={composerRef}
              onSend={handleSend}
              onStop={handleStop}
              streaming={isStreaming}
              disabled={!!historyError || !authed}
              contextTag={contextTag}
              queueing={queueing}
              degrade={degrade}
            />
          </div>
        </div>

        {/* 会话列表侧栏（桌面 ≥md，固定在右侧） */}
        <aside
          data-slot="chat-sidebar"
          className="hidden w-[224px] shrink-0 flex-col rounded-2xl border-[3px] border-foreground bg-background p-2.5 shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)] md:flex lg:w-[252px]"
        >
          {sessionListEl}
        </aside>
      </div>

      {/* 移动端会话列表抽屉 + 遮罩（<md） */}
      <div
        aria-hidden={!drawerOpen}
        data-slot="chat-drawer-scrim"
        onClick={() => setDrawerOpen(false)}
        className={cn(
          "fixed inset-0 z-[70] bg-black/40 transition-opacity md:hidden",
          drawerOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />
      <aside
        data-slot="chat-drawer"
        aria-hidden={!drawerOpen}
        className={cn(
          "fixed inset-y-0 right-0 z-[80] flex w-[min(300px,86vw)] flex-col gap-3 bg-candy-bg p-4 pt-3 transition-transform md:hidden",
          drawerOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex shrink-0 items-center justify-between">
          <span className="text-sm font-extrabold tracking-tight">会话列表</span>
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            aria-label="关闭会话列表"
            data-slot="chat-drawer-close"
            className="grid size-8 place-items-center rounded-lg border-2 border-foreground bg-background text-sm font-extrabold"
          >
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 rounded-2xl border-[3px] border-foreground bg-background p-2.5">
          {sessionListEl}
        </div>
      </aside>
    </ProtectedRoute>
  );
}
