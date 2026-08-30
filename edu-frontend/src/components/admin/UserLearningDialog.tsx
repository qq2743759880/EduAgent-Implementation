/**
 * UserLearningDialog — 学习详情弹窗（task60 /admin/users 重构）
 *  - 6 StatCard：报名班次 / 平均进度 / 累计观看 / 作业正确率 / 考试均分 / 收藏
 *  - 最近动态列表（recent_activities）
 *  - 数据源 GET /api/admin/users/{id}/learning（契约⑤用户域，task60 契约定义）
 *  - ⚠ 契约缺口：端点后端当前未注册 → 404 时如实披露缺口 + 渲染字段结构（label + snake_case 字段名 + '—'），
 *    不写 MOCK 假数据；待后端开放后自动渲染真实聚合。其余错误走 ErrorState。
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, CalendarClock, ClipboardCheck, GraduationCap, Heart, Hourglass } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LoadingState } from "@/components/admin/controls";
import { getAdminUserLearning, userDisplayName, userRoleLabel, type AdminUserItem } from "@/lib/api/admin/users";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/** 6 指标字段结构（缺口占位时展示 label + 字段名，非真实值） */
const FIELD_SPECS: Array<{ key: string; label: string; unit: string; icon: LucideIcon; format?: (v: number) => string }> = [
  { key: "active_cohorts_count", label: "报名班次", unit: "班", icon: BookOpen },
  { key: "avg_progress_pct", label: "平均进度", unit: "%", icon: GraduationCap },
  { key: "total_watched_seconds", label: "累计观看", unit: "分", icon: Hourglass, format: (v) => String(Math.round(v / 60)) },
  { key: "homework_accuracy_pct", label: "作业正确率", unit: "%", icon: ClipboardCheck },
  { key: "exam_avg_score", label: "考试均分", unit: "分", icon: CalendarClock },
  { key: "favorite_count", label: "收藏", unit: "件", icon: Heart },
];

export function UserLearningDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const learning = useQuery({
    queryKey: ["admin", "users", user?.user_id, "learning"] as const,
    queryFn: () => getAdminUserLearning(user!.user_id),
    enabled: open && Boolean(user),
    retry: false,
  });

  const isGap = learning.isError && learning.error instanceof ApiError && learning.error.status === 404;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl sm:max-h-[88vh] sm:overflow-y-auto">
        <DialogHeader>
          <DialogTitle>学习详情 · {user ? userDisplayName(user) : ""}</DialogTitle>
          {user && (
            <p className="text-xs text-muted-foreground">
              UID {user.user_id} · 数据源 GET /api/admin/users/{user.user_id}/learning
            </p>
          )}
        </DialogHeader>

        {user && (
          <div className="space-y-4">
            {/* 账号摘要 */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3">
              <Badge className="border-transparent bg-primary-soft text-primary">{userRoleLabel(user.role_code)}</Badge>
              <UserStatusPill status={user.status} yn={user.yn} />
              <span className="text-xs text-muted-foreground">{user.username || user.phone || user.email || "—"}</span>
            </div>

            {learning.isLoading ? (
              <LoadingState label="聚合学习指标…" />
            ) : isGap ? (
              <LearningGap user={user} />
            ) : learning.isError ? (
              <LearnError message={learning.error instanceof Error ? learning.error.message : ""} onRetry={() => learning.refetch()} />
            ) : learning.data ? (
              <>
                {/* 6 指标 */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {FIELD_SPECS.map((f) => {
                    const Icon = f.icon;
                    const raw = learning.data[f.key as keyof typeof learning.data] as number;
                    const value = f.format ? f.format(raw) : String(raw ?? "—");
                    return (
                      <div key={f.key} className="rounded-xl border border-border bg-card p-3">
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Icon className="h-3.5 w-3.5" /> {f.label}
                        </div>
                        <div className="mt-1.5 text-xl font-extrabold text-foreground">
                          {value}
                          <span className="ml-0.5 text-xs font-semibold text-muted-foreground">{f.unit}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {/* 最近动态 */}
                <div>
                  <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                    最近动态
                    <span className="font-mono text-xs font-normal text-muted-foreground">recent_activities[]</span>
                  </div>
                  {learning.data.recent_activities.length === 0 ? (
                    <p className="rounded-xl border border-dashed p-4 text-center text-xs text-muted-foreground">暂无最近动态</p>
                  ) : (
                    <ul className="space-y-2 border-l-2 border-primary-border pl-3">
                      {learning.data.recent_activities.map((a, i) => (
                        <li key={i} className="flex items-baseline gap-2 text-sm">
                          <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                            {formatDate(a.occurred_at)}
                          </span>
                          <span className="text-foreground">{a.detail}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** 契约缺口：端点未接线 → 如实披露 + 渲染字段结构（不造假数据） */
function LearningGap({ user }: { user: AdminUserItem }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-xl border border-candy-orange/30 bg-candy-orange/10 p-3 text-xs leading-relaxed text-foreground">
        <span className="shrink-0">⚠️</span>
        <span>
          <b>契约缺口 · 实披露</b>：<code className="font-mono">GET /api/admin/users/{user.user_id}/learning</code>{" "}
          后端当前<b>未注册</b>（user_admin/router.py 暂无 learning 端点）。下方为 task60 6 指标 + 最近动态的字段结构预览
          （值为占位，非真实聚合，不写 MOCK）；待后端开放后由该端点返回真实数据。
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {FIELD_SPECS.map((f) => {
          const Icon = f.icon;
          return (
            <div key={f.key} className="rounded-xl bg-muted/40 p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Icon className="h-3.5 w-3.5" /> {f.label}
              </div>
              <div className="mt-1.5 text-xl font-extrabold text-muted-foreground">
                —
                <span className="ml-0.5 text-xs">{f.unit}</span>
              </div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{f.key}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function UserStatusPill({ status, yn }: { status: number; yn: number }) {
  const disabled = status === 0 || yn === 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        disabled ? "bg-candy-red/10 text-candy-red" : "bg-candy-green-soft text-primary-deep",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", disabled ? "bg-candy-red" : "bg-candy-green")} />
      {disabled ? "已禁用" : "启用"}
    </span>
  );
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 学习详情加载失败态（非契约缺口；candy 风格，禁用任意字号/灰色系/内联色） */
function LearnError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-candy-red/30 bg-candy-red/10 p-4 text-center">
      <p className="text-sm font-semibold text-candy-red">学习详情加载失败</p>
      <p className="mt-1 break-all font-mono text-xs text-candy-red/80">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
        >
          重试
        </button>
      )}
    </div>
  );
}