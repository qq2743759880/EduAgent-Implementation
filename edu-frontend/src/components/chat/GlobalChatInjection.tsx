/**
 * GlobalChatInjection
 *
 * 注入到根 Providers 下（全局所有用户端 & 登录/注册页 & 首页都能看到浮动聊天按钮）：
 *   - 未登录：按钮灰显 + tooltip 提示登录，不渲染 ChatPanel（避免 API 401 toast 风暴）
 *   - 登录后：
 *       • useAuthStore.me 取 nickname + avatar
 *       • useChatSessions({ enabled: authed }) 拉会话列表（enabled 控制未登录不请求）
 *       • useChatStream 管消息 / 流式 / stop / send
 *       • ChatSessionSidebar 作为 drawer 模式 + Dialog 包一层（会话切换面板）
 *       • ChatPanel floating=true 模式（右下角 380×560 卡片）
 *       • onSend: 首条消息懒 ensureSession（见 useChatStream.onFirstMessage 钩子），之后复用已选中会话
 *       • onNewSession: createAndSelect 并 setMessages([]) 清空当前屏幕
 *
 *   Dialog（会话列表抽屉）这里使用原生 dialog 替代 shadcn Dialog（为了侧边抽屉效果 + 更轻量），
 *   shadcn Dialog 是居中模态，不适合左滑抽屉。
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth-client";
import type { ChatMessage, ChatSession } from "@/lib/api/chat";
import { getChatHistory } from "@/lib/api/chat";

import { useChatSessions } from "@/components/chat/hooks/useChatSessions";
import { useChatStream } from "@/components/chat/hooks/useChatStream";

import { ChatFloatingButton } from "@/components/chat/ChatFloatingButton";
import { ChatPanel, type ChatPanelHandle } from "@/components/chat/ChatPanel";
import { ChatSessionSidebar } from "@/components/chat/ChatSessionSidebar";

/* ================== Dialog Drawer（原生） ================== */

function DrawerDialog({
  open,
  onClose,
  children,
}: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const backdropRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      try {
        dlg.showModal();
      } catch { /* dialog already open */ }
    } else if (!open && dlg.open) {
      dlg.close();
    }
  }, [open]);

  // ESC 关闭（原生 dialog 自带 cancel 事件）
  React.useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const onCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    dlg.addEventListener("cancel", onCancel);
    return () => dlg.removeEventListener("cancel", onCancel);
  }, [onClose]);

  return (
    <>
      {/* Backdrop（点击关闭） */}
      <div
        ref={backdropRef}
        onClick={onClose}
        className={cn(
          "fixed inset-0 z-[70] bg-black/30 transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        aria-hidden
      />
      <dialog
        ref={dialogRef}
        className={cn(
          "fixed z-[80] m-0 h-full w-[300px] max-w-[88vw] border-r border-border bg-background p-0 shadow-2xl",
          // 左滑入
          "left-0 top-0",
          // 覆盖原生 dialog backdrop 样式（我们自己用 backdrop div）
          "backdrop:bg-transparent",
          open ? "translate-x-0 opacity-100" : "-translate-x-full opacity-0",
          "transition-transform duration-200 ease-out",
        )}
      >
        <form method="dialog" className="hidden">
          <button type="submit" aria-hidden />
        </form>
        <div className="h-full w-full">{children}</div>
      </dialog>
    </>
  );
}

/* ================== 主组件 ================== */

export function GlobalChatInjection() {
  const router = useRouter();
  const ready = useAuthStore((s) => s.ready);
  const isAuthedFn = useAuthStore((s) => s.isAuthenticated);
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);

  const authed = ready && isAuthedFn();

  // ====== 浮动面板 UI 状态 ======
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const panelHandleRef = React.useRef<ChatPanelHandle | null>(null);

  // ====== 会话管理 ======
  const {
    sessions,
    selectedId,
    createAndSelect,
    deleteSession,
    ensureSession,
    selectSession,
    refetch: refetchSessions,
  } = useChatSessions({ enabled: authed });
  void deleteSession;

  const currentSession: ChatSession | null = React.useMemo(() => {
    if (!authed) return null;
    return sessions.find((s) => String(s.id) === String(selectedId)) ?? null;
  }, [sessions, selectedId, authed]);

  // ====== 消息流 ======
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
        router.replace(`/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`);
        return;
      }
      toast.error("AI 生成失败", { description: m });
    },
  });

  // 选中会话变化时拉历史
  const hydratedIdRef = React.useRef<string | number | null>("__none__");
  React.useEffect(() => {
    if (!authed) return;
    if (selectedId == null) {
      setMessages([]);
      hydratedIdRef.current = null;
      return;
    }
    if (String(hydratedIdRef.current) === String(selectedId)) return;
    hydratedIdRef.current = selectedId;
    let cancelled = false;
    void (async () => {
      try {
        const history = await getChatHistory(selectedId);
        if (cancelled) return;
        // 仅当当前用户未发送新消息时才覆盖；否则把历史合并放前面
        setMessages((prev) => {
          if (prev.length === 0) return history;
          const seen = new Set(prev.map((m) => m.id));
          const extra = history.filter((h) => !seen.has(h.id));
          return [...extra, ...prev];
        });
      } catch (e) {
        if (!cancelled) {
          toast.error("加载历史消息失败", { description: e instanceof Error ? e.message : undefined });
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, authed]);

  // ====== 操作回调 ======

  const handleToggleOpen = () => setPanelOpen((v) => !v);
  const handleClose = () => setPanelOpen(false);

  const handleSend = async (text: string) => {
    await send(text, { sessionId: selectedId ?? undefined });
    refetchSessions();
  };
  const handleStop = () => stop();

  const handleNewSession = async () => {
    const created = await createAndSelect({ title: "" });
    hydratedIdRef.current = created.id;
    setMessages([]);
    refetchSessions();
  };

  const handleRequestSessionsPanel = () => {
    setDrawerOpen(true);
  };

  const handlePicked = (sid: string | number | null) => {
    if (sid != null) selectSession(sid);
    setDrawerOpen(false);
    // 给用户视觉焦点反馈
    window.setTimeout(() => panelHandleRef.current?.focusInput(), 80);
  };

  /* ================== 渲染 ================== */

  // 未 ready：不渲染（避免 SSR / hydrate 时按钮闪烁）
  if (!ready) return null;

  const nickname = me?.nickname?.trim() || (me?.username as string | undefined) || "我";
  const avatar = (me?.avatar as string | null | undefined) ?? null;

  return (
    <>
      {/* 浮动按钮：所有状态下都渲染，未登录也能看到品牌入口 + tooltip 引导登录 */}
      <ChatFloatingButton
        open={panelOpen}
        onToggle={handleToggleOpen}
        unreadCount={isStreaming ? 1 : 0}
      />

      {/* ChatPanel：仅登录后展示，避免未登录下 UI 打开 + 触发无意义 API 请求 */}
      {authed ? (
        <ChatPanel
          floating
          open={panelOpen}
          onClose={handleClose}
          onRequestSessionsPanel={handleRequestSessionsPanel}
          session={currentSession}
          messages={messages as ChatMessage[]}
          isStreaming={isStreaming}
          onSend={handleSend}
          onStop={handleStop}
          onNewSession={handleNewSession}
          userNickname={nickname}
          userAvatar={avatar}
          compactSources
          panelRef={panelHandleRef}
        />
      ) : null}

      {/* Drawer：会话列表 */}
      {authed ? (
        <DrawerDialog open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          <ChatSessionSidebar
            mode="drawer"
            onClose={() => setDrawerOpen(false)}
            onPicked={handlePicked}
            initialSessionId={selectedId ?? undefined}
          />
        </DrawerDialog>
      ) : null}
    </>
  );
}

export default GlobalChatInjection;
