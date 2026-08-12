/**
 * ChatFullScreenClient - /chat full screen AI Q&A page (client component)
 *
 *  Layout:
 *   - lg+: 3 columns
 *       Left w-[280px]: ChatSessionSidebar (mode=side) session history
 *       Center flex-1: ChatPanel (floating=false) messages + input
 *       Right w-[340px] hidden xl:block: latest assistant sources + tool calls
 *   - <lg: single column + top hamburger opens MobileDrawer for sessions
 *
 *  Data:
 *   - useChatSessions for sessions list / current selection
 *   - useChatStream for messages / SSE stream / stop
 *   - ?sid=<id> search param supports deep link to specific session
 *   - Switching session triggers getChatHistory fetch + merge
 *
 *  Auth: wrapped with <ProtectedRoute>, unauthed redirects to /login?redirect=/chat
 */
"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Menu, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ProtectedRoute } from "@/lib/protected-route";
import { useAuthStore } from "@/lib/auth-client";
import type { ChatMessage, ChatSession, RagDoc, MCPToolCall } from "@/lib/api/chat";
import { getChatHistory } from "@/lib/api/chat";

import { useChatSessions } from "@/components/chat/hooks/useChatSessions";
import { useChatStream } from "@/components/chat/hooks/useChatStream";
import { ChatSessionSidebar } from "@/components/chat/ChatSessionSidebar";
import { ChatPanel, type ChatPanelHandle } from "@/components/chat/ChatPanel";
import { SourceCardList } from "@/components/chat/SourceCardList";
import { ToolCallList } from "@/components/chat/ToolCallVisualizer";

/* Mobile left-slide session drawer */

function MobileDrawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const dialogRef = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      try { dlg.showModal(); } catch { /* noop */ }
    } else if (!open && dlg.open) {
      dlg.close();
    }
  }, [open]);

  React.useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const onCancel = (e: Event) => { e.preventDefault(); onClose(); };
    dlg.addEventListener("cancel", onCancel);
    return () => dlg.removeEventListener("cancel", onCancel);
  }, [onClose]);

  return (
    <>
      <div
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
          "left-0 top-0 backdrop:bg-transparent",
          open ? "translate-x-0 opacity-100" : "-translate-x-full opacity-0",
          "transition-transform duration-200 ease-out",
        )}
      >
        <form method="dialog" className="hidden"><button type="submit" aria-hidden /></form>
        <div className="h-full w-full">{children}</div>
      </dialog>
    </>
  );
}

/* Right column: sources + tool calls aggregate for the latest assistant message */

function ExtraInfoPanel({
  latestAssistant,
}: {
  latestAssistant: ChatMessage | null;
}) {
  if (!latestAssistant) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 px-6 text-center text-muted-foreground">
        <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 p-5 text-xs leading-5">
          Ask a question on the left.<br />Knowledge references and MCP tool calls<br />
          will appear here for quick inspection.
        </div>
      </div>
    );
  }

  const sources: RagDoc[] = (latestAssistant.sources ?? []) as RagDoc[];
  const tools: MCPToolCall[] = (latestAssistant.tool_calls ?? []) as MCPToolCall[];

  return (
    <div className="flex h-full w-full flex-col">
      <header className="flex items-center gap-2 border-b border-border/80 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-7 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-300">
            <MessageSquarePlus className="size-4" aria-hidden />
          </span>
          <div>
            <div className="text-[13.5px] font-semibold leading-tight">Context</div>
            <div className="text-[11px] text-muted-foreground">
              Sources {sources.length} - Tools {tools.length}
            </div>
          </div>
        </div>
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
        {sources.length > 0 ? (
          <SourceCardList
            sources={sources}
            max={8}
            compact={false}
            className="max-w-full"
          />
        ) : null}
        {tools.length > 0 ? (
          <ToolCallList calls={tools} compact={false} className="max-w-full" />
        ) : null}
        {sources.length === 0 && tools.length === 0 ? (
          <div className="rounded-xl border border-border/60 bg-muted/20 px-3 py-4 text-[12px] leading-5 text-muted-foreground">
            This answer has no cited sources or tool calls.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* Main component */

export function ChatFullScreenClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const sidParam = sp.get("sid");
  const ready = useAuthStore((s) => s.ready);
  const isAuthedFn = useAuthStore((s) => s.isAuthenticated);
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);

  const authed = ready && isAuthedFn();

  const initialSid = React.useMemo<string | number | null>(() => {
    if (sidParam) {
      const n = Number(sidParam);
      return Number.isFinite(n) ? n : sidParam;
    }
    return null;
  }, [sidParam]);

  const {
    sessions,
    selectedId,
    createAndSelect,
    deleteSession,
    ensureSession,
    selectSession,
    refetch: refetchSessions,
  } = useChatSessions({ enabled: authed, initialSessionId: initialSid ?? undefined });
  void deleteSession;

  const currentSession: ChatSession | null = React.useMemo(() => {
    if (!authed) return null;
    return sessions.find((s) => String(s.id) === String(selectedId)) ?? null;
  }, [sessions, selectedId, authed]);

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
      if (typeof window !== "undefined" && sid != null) {
        const url = new URL(window.location.href);
        url.searchParams.set("sid", String(sid));
        window.history.replaceState({}, "", url.toString());
      }
      return sid;
    },
    onError(err) {
      const m = err.message || String(err);
      if (/401|403|Unauthorized/i.test(m) && authed) {
        toast.error("Login expired, please sign in again", { description: m });
        try { logout?.({ silent: true }); } catch { /* ignore */ }
        const from = encodeURIComponent("/chat");
        router.replace(`/login?redirect=${from}`);
        return;
      }
      toast.error("AI generation failed", { description: m });
    },
  });

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
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("sid", String(selectedId));
      window.history.replaceState({}, "", url.toString());
    }
    let cancelled = false;
    void (async () => {
      try {
        const history = await getChatHistory(selectedId);
        if (cancelled) return;
        setMessages((prev) => {
          if (prev.length === 0) return history as ChatMessage[];
          const seen = new Set(prev.map((m) => m.id));
          const extra = (history as ChatMessage[]).filter((h) => !seen.has(h.id));
          return [...extra, ...prev];
        });
      } catch (e) {
        if (!cancelled) {
          toast.error("Failed to load history", {
            description: e instanceof Error ? e.message : undefined,
          });
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, authed]);

  const panelHandleRef = React.useRef<ChatPanelHandle | null>(null);
  const [mobileDrawerOpen, setMobileDrawerOpen] = React.useState(false);

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
    window.setTimeout(() => panelHandleRef.current?.focusInput(), 60);
  };

  const handlePickedSide = (sid: string | number | null) => {
    if (sid != null) selectSession(sid);
    setMobileDrawerOpen(false);
    window.setTimeout(() => panelHandleRef.current?.focusInput(), 80);
  };

  const lastAssistant = React.useMemo<ChatMessage | null>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i] as ChatMessage;
      if (m.role === "assistant") return m;
    }
    return null;
  }, [messages]);

  const nickname = me?.nickname?.trim() || (me?.username as string | undefined) || "me";
  const avatar = (me?.avatar as string | null | undefined) ?? null;

  if (!ready) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background text-muted-foreground">
        <div className="animate-pulse text-sm">Loading AI assistant...</div>
      </div>
    );
  }

  return (
    <ProtectedRoute>
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto flex min-h-screen w-full max-w-[1440px] gap-0 lg:gap-4 px-0 lg:px-4 py-0 lg:py-4">
          {/* Left: session sidebar (lg+ persistent) */}
          <aside className="hidden lg:flex w-[280px] shrink-0 flex-col rounded-2xl border border-border/70 bg-background shadow-sm overflow-hidden">
            <ChatSessionSidebar
              mode="side"
              onPicked={handlePickedSide}
              initialSessionId={initialSid ?? undefined}
              enabled={authed}
            />
          </aside>

          {/* Center: chat main area */}
          <main className="relative flex min-w-0 flex-1 flex-col rounded-none lg:rounded-2xl border-0 lg:border lg:border-border/70 bg-background shadow-none lg:shadow-sm overflow-hidden">
            {/* Mobile header (visible <lg) */}
            <div className="lg:hidden flex items-center gap-2 border-b border-border/70 px-3 py-2.5">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => setMobileDrawerOpen(true)}
                aria-label="Open sessions"
              >
                <Menu className="size-4" />
              </Button>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-semibold leading-tight">
                  AI Study Assistant
                </div>
                <div className="truncate text-[11px] text-muted-foreground">
                  {currentSession?.title?.trim() || "Start a new conversation"}
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={handleNewSession}
                aria-label="New conversation"
              >
                <MessageSquarePlus className="size-4" />
              </Button>
            </div>

            <div className="min-h-0 flex-1">
              <ChatPanel
                floating={false}
                session={currentSession}
                messages={messages as ChatMessage[]}
                isStreaming={isStreaming}
                onSend={handleSend}
                onStop={handleStop}
                onNewSession={handleNewSession}
                userNickname={nickname}
                userAvatar={avatar}
                compactSources={false}
                panelRef={panelHandleRef}
                hideSessionsButton
                sessionsPanelOpen
              />
            </div>
          </main>

          {/* Right: context inspector (xl+ visible) */}
          <aside className="hidden xl:flex w-[340px] shrink-0 flex-col rounded-2xl border border-border/70 bg-background shadow-sm overflow-hidden">
            <ExtraInfoPanel latestAssistant={lastAssistant} />
          </aside>
        </div>

        {/* Mobile session drawer */}
        <MobileDrawer open={mobileDrawerOpen} onClose={() => setMobileDrawerOpen(false)}>
          <ChatSessionSidebar
            mode="drawer"
            onClose={() => setMobileDrawerOpen(false)}
            onPicked={handlePickedSide}
            initialSessionId={initialSid ?? undefined}
            enabled={authed}
          />
        </MobileDrawer>
      </div>
    </ProtectedRoute>
  );
}

export default ChatFullScreenClient;
