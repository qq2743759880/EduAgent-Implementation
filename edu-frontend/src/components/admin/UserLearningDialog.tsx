/**
 * UserLearningDialog — 学习详情弹窗（task60 /admin/users 重构）
 *  - 账号摘要（角色/状态/账号名）
 *  - 6 指标字段结构预览（报名班次 / 平均进度 / 累计观看 / 作业正确率 / 考试均分 / 收藏）
 *  - ⚠ 契约缺口 · 实披露（W-NEXT-FEBE-SCAN-002 死调用删除）：数据源
 *    GET /api/admin/users/{id}/learning 后端从未注册（user_admin/router.py 暂无
 *    learning 端点，OpenAPI 实测确认）。原实现每次打开弹窗都发起必 404 的死请求，
 *    现已删除该调用，直接渲染缺口占位（label + snake_case 字段名 + '—'，不写 MOCK
 *    假数据）；待后端开放该端点后由变更单恢复封装（lib/api/admin/users.ts）与真实聚合渲染。
 */
"use client";

import { BookOpen, CalendarClock, ClipboardCheck, GraduationCap, Heart, Hourglass } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { userDisplayName, userRoleLabel, type AdminUserItem } from "@/lib/api/admin/users";
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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl sm:max-h-[88vh] sm:overflow-y-auto">
        <DialogHeader>
          <DialogTitle>学习详情 · {user ? userDisplayName(user) : ""}</DialogTitle>
          {user && (
            <p className="text-xs text-muted-foreground">
              UID {user.user_id} · 数据源 GET /api/admin/users/{user.user_id}/learning（后端未注册 · 缺口披露）
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

            <LearningGap user={user} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** 契约缺口：端点未接线 → 如实披露 + 渲染字段结构（不造假数据，不发必 404 的死请求） */
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
