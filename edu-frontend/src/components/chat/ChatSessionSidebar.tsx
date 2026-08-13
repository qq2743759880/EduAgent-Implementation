/**
 * ChatSessionSidebar
 *   - 两种模式：side=固定侧栏（全屏聊天页）/ drawer=抽屉（浮动 ChatPanel 的会话切换）
 *   - 日期分组：今天 / 昨天 / 7 天内 / 更早（updated_at 判定，无则回退 created_at）
 *   - 新建会话：顶部"+ 新对话"按钮（Drawer 模式下也保留）
 *   - 删除：会话项 hover 显示 Trash2，点击二次确认 Dialog；删除后软切换到临近会话
 *   - 选中：整行高亮，点击立即 select 并（drawer 模式）触发 onClose()
 *   - 空态：MessageSquare + Sparkles + CTA 按钮「开启第一个对话」
 */
"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  CalendarDays,
  Loader2,
  MessageSquare,
  Plus,
  ScrollText,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/api/chat";
import { useChatSessions } from "./hooks/useChatSessions";

export type ChatSidebarMode = "side" | "drawer";

export interface ChatSessionSidebarProps {
  mode?: ChatSidebarMode;
  /** drawer 模式下关闭按钮回调 */
  onClose?: () => void;
  /** 当用户选中一个会话（或创建新会话）后调用，可用于 drawer 自动收起 */
  onPicked?: (sessionId: string | number | null) => void;
  /** 初始选中 id（优先级最高，覆盖 localStorage） */
  initialSessionId?: string | number | null;
  className?: string;
  /** 禁用查询（未登录） */
  enabled?: boolean;
}

type BucketKey = "today" | "yesterday" | "last7" | "earlier";
const BUCKET_LABEL: Record<BucketKey, string> = {
  today: "今天",
  yesterday: "昨天",
  last7: "过去 7 天",
  earlier: "更早",
};
const BUCKET_ORDER: BucketKey[] = ["today", "yesterday", "last7", "earlier"];

function bucketOf(iso: string | null | undefined): BucketKey {
  if (!iso) return "earlier";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "earlier";
  const now = new Date();
  const d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const diffDay = (d0 - t) / 86400000;
  if (diffDay < 1) return "today"; // <= 今天内
  if (diffDay < 2) return "yesterday"; // 昨天
  if (diffDay < 8) return "last7";
  return "earlier";
}

function displayPreview(s: ChatSession): string {
  const p = s.preview;
  if (typeof p === "string" && p.trim()) return p.trim();
  return `${s.messages_count ?? 0} 条消息`;
}

function displayTitle(s: ChatSession): string {
  const t = s.title?.trim();
  return t && t.length ? t : "未命名对话";
}

export function ChatSessionSidebar({
  mode = "side",
  onClose,
  onPicked,
  initialSessionId,
  className,
  enabled,
}: ChatSessionSidebarProps) {
  const {
    sessions,
    sessionsLoading,
    sessionsError,
    selectedId: storeSelected,
    selectSession,
    createAndSelect,
    deleteSession,
    refetch,
  } = useChatSessions({ initialSessionId, enabled });

  // 组件本地复制一份 selectedId 保证 react 响应式（useChatSessions 里用 ref 管理 + onPicked 回调，但侧栏 UI 需要渲染高亮）
  const [selected, setSelected] = React.useState<string | number | null>(initialSessionId ?? storeSelected ?? null);
  React.useEffect(() => {
    setSelected(initialSessionId ?? storeSelected ?? null);
    void sessions;
  }, [initialSessionId, storeSelected, sessions]);

  const [creating, setCreating] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState<ChatSession | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const groups = React.useMemo(() => {
    const g: Record<BucketKey, ChatSession[]> = {
      today: [], yesterday: [], last7: [], earlier: [],
    };
    for (const s of sessions) {
      const key = bucketOf(s.updated_at ?? s.created_at);
      g[key].push(s);
    }
    // 按更新时间倒序
    for (const k of BUCKET_ORDER) {
      g[k].sort((a, b) => {
        const ta = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
        const tb = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
        return tb - ta;
      });
    }
    return g;
  }, [sessions]);

  const totalCount = sessions.length;

  /* =========== handlers =========== */

  const handleNew = async () => {
    setCreating(true);
    try {
      const created = await createAndSelect({ title: "" });
      setSelected(created.id);
      onPicked?.(created.id);
    } catch (e) {
      toast.error("创建对话失败", {
        description: e instanceof Error ? e.message : undefined,
      });
    } finally {
      setCreating(false);
    }
  };

  const handlePick = (s: ChatSession) => {
    selectSession(s.id);
    setSelected(s.id);
    onPicked?.(s.id);
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      // 删除后自动切换临近的 session
      const idx = sessions.findIndex((s) => String(s.id) === String(confirmDelete.id));
      const neighbor = sessions[idx + 1] ?? sessions[idx - 1] ?? null;
      await deleteSession(confirmDelete.id, neighbor?.id ?? null);
      setSelected(neighbor?.id ?? null);
      if (String(selected) === String(confirmDelete.id)) {
        onPicked?.(neighbor?.id ?? null);
      }
      toast.success("对话已删除");
      setConfirmDelete(null);
    } catch (e) {
      toast.error("删除失败", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setDeleting(false);
    }
  };

  const isDrawer = mode === "drawer";

  /* =========== 渲染 =========== */

  return (
    <aside
      className={cn(
        "flex h-full w-full flex-col bg-background",
        isDrawer ? "min-w-[280px]" : "",
        className,
      )}
      aria-label="历史会话"
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center gap-2",
          isDrawer ? "px-3 pt-3 pb-2" : "px-4 pt-4 pb-3",
        )}
      >
        <div className="flex items-center gap-2">
          <span className="inline-flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ScrollText className="size-4" aria-hidden />
          </span>
          <div>
            <div className="text-sm font-semibold leading-tight text-foreground">
              历史对话
            </div>
            <div className="text-3xs text-muted-foreground tabular-nums">
              共 {totalCount} 个会话
            </div>
          </div>
        </div>
        {isDrawer && onClose ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="关闭会话列表"
            className="ml-auto"
          >
            <X className="size-4" />
          </Button>
        ) : null}
      </div>

      {/* New + 搜索占位 */}
      <div className={cn("px-3 pb-2 space-y-2", isDrawer ? "px-3" : "px-4")}>
        <Button
          type="button"
          variant="default"
          size={isDrawer ? "sm" : "default"}
          onClick={handleNew}
          disabled={creating || sessionsLoading || sessionsError !== null}
          className="w-full"
        >
          {creating ? (
            <Loader2 className="mr-1.5 size-4 animate-spin" />
          ) : (
            <Plus className="mr-1.5 size-4" />
          )}
          新对话
        </Button>
      </div>

      <Separator className="my-1" />

      {/* List / Loading / Empty */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {sessionsLoading ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" aria-hidden />
            <span className="text-xs">加载对话中…</span>
          </div>
        ) : sessionsError ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-10">
            <div className="text-xs text-destructive">加载失败</div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => refetch()}
            >
              重新加载
            </Button>
          </div>
        ) : totalCount === 0 ? (
          <EmptyCTA onNew={handleNew} creating={creating} />
        ) : (
          <ul className="mt-1 space-y-4 px-1 py-1">
            {BUCKET_ORDER.map((bk) =>
              groups[bk].length === 0 ? null : (
                <li key={bk}>
                  <div className="flex items-center gap-1.5 px-2 py-1 text-3xs uppercase tracking-wide text-muted-foreground/80">
                    <CalendarDays className="size-3 opacity-80" aria-hidden />
                    {BUCKET_LABEL[bk]}
                    <span className="ml-auto tabular-nums opacity-70">{groups[bk].length}</span>
                  </div>
                  <ul className="space-y-0.5">
                    {groups[bk].map((s, i) => (
                      <SessionRow
                        key={s.id ?? `sr-${i}`}
                        session={s}
                        selected={String(selected) === String(s.id)}
                        onPick={() => handlePick(s)}
                        onDelete={() => setConfirmDelete(s)}
                      />
                    ))}
                  </ul>
                </li>
              ),
            )}
          </ul>
        )}
      </div>

      {/* 删除确认 */}
      <Dialog open={!!confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除对话</DialogTitle>
            <DialogDescription>
              确定要删除「{confirmDelete ? displayTitle(confirmDelete) : ""}」吗？
              删除后将无法恢复，历史消息和引用来源都会被清除。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirmDelete(null)}
              disabled={deleting}
            >
              取消
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="text-destructive-foreground"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? (
                <>
                  <Loader2 className="mr-1.5 size-4 animate-spin" /> 删除中
                </>
              ) : (
                <>确认删除</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}

/* =========== 会话行 =========== */

function SessionRow({
  session,
  selected,
  onPick,
  onDelete,
}: {
  session: ChatSession;
  selected: boolean;
  onPick: () => void;
  onDelete: () => void;
}) {
  const [hovered, setHovered] = React.useState(false);
  return (
    <li>
      <div
        className={cn(
          "group relative flex items-center gap-2 rounded-lg px-2 py-2 cursor-pointer transition-colors",
          selected
            ? "bg-primary/10 ring-1 ring-primary/20"
            : "hover:bg-muted/70",
        )}
        onClick={onPick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <span
          className={cn(
            "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md",
            selected ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          <MessageSquare className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div
            className={cn(
              "text-sm-table font-medium leading-5 text-foreground line-clamp-1 break-words",
              selected ? "text-primary-foreground/95 *:text-primary-foreground/95" : "",
            )}
            style={
              selected
                ? ({ color: "var(--foreground)" } as React.CSSProperties)
                : undefined
            }
          >
            {displayTitle(session)}
          </div>
          <div
            className={cn(
              "text-3xs leading-4 text-muted-foreground line-clamp-1 break-words",
            )}
          >
            {displayPreview(session)}
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-1">
          {session.messages_count ? (
            <Badge
              variant="outline"
              className={cn(
                "hidden h-5 px-1.5 text-4xs tabular-nums group-hover:inline-flex",
                selected ? "bg-background/60" : "",
              )}
            >
              {session.messages_count}
            </Badge>
          ) : null}
          <button
            type="button"
            aria-label={`删除对话 ${displayTitle(session)}`}
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition",
              hovered || selected ? "opacity-100" : "opacity-0 pointer-events-none",
              "hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100",
            )}
          >
            <Trash2 className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </li>
  );
}

/* =========== 空态 =========== */

function EmptyCTA({ onNew, creating }: { onNew: () => void; creating: boolean }) {
  return (
    <div className="mx-2 mt-6 flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border/70 bg-muted/20 px-5 py-10 text-center">
      <div className="relative">
        {/* fe-task07：空态渐变 → 主色渐变；在线点 → bg-success */}
        <span className="inline-flex size-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep to-primary text-primary-foreground shadow-lg shadow-primary/20">
          <MessageSquare className="size-5" aria-hidden />
        </span>
        <span className="absolute -right-1 -top-1 inline-flex size-4 items-center justify-center rounded-full bg-success text-white ring-2 ring-background">
          <Sparkles className="size-2.5" aria-hidden />
        </span>
      </div>
      <div className="space-y-1">
        <div className="text-sm font-semibold text-foreground">开启第一个对话</div>
        <div className="text-2xs leading-5 text-muted-foreground">
          随时向 AI 提问：学科知识点、错题讲解、学习规划、或调用工具为你查询报告。
        </div>
      </div>
      <Button type="button" variant="default" size="sm" onClick={onNew} disabled={creating}>
        {creating ? <Loader2 className="mr-1.5 size-4 animate-spin" /> : <Plus className="mr-1.5 size-4" />}
        开启第一个对话
      </Button>
    </div>
  );
}

export default ChatSessionSidebar;
