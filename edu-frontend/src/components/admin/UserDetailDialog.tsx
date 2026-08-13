/**
 * UserDetailDialog — 用户详情弹窗（task03）
 *  - 展示真实列表数据（AdminUserItem，来自 GET /api/admin/users，无 MOCK）
 *  - 包含账号信息 / 角色 / 状态 / 注册与最近登录时间
 */
"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  formatDateTime,
  userDisplayName,
  userRoleLabel,
  type AdminUserItem,
} from "@/lib/api/admin/users";
import { cn } from "@/lib/utils";

export function UserDetailDialog({
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
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>用户详情 · {user ? userDisplayName(user) : ""}</DialogTitle>
        </DialogHeader>

        {user && (
          <dl className="space-y-3 text-sm">
            <InfoRow label="用户 ID">
              <code className="font-mono text-xs">{user.user_id}</code>
            </InfoRow>
            <InfoRow label="登录账号">{user.username || "—"}</InfoRow>
            <InfoRow label="真实姓名">{user.real_name || "—"}</InfoRow>
            <InfoRow label="手机号">{user.phone || "—"}</InfoRow>
            <InfoRow label="邮箱">{user.email || "—"}</InfoRow>
            <InfoRow label="角色">
              <span className="inline-flex items-center gap-2">
                <Badge variant="outline">{userRoleLabel(user.role_code)}</Badge>
                <code className="font-mono text-[11px] text-slate-600">{user.role_code}</code>
              </span>
            </InfoRow>
            <InfoRow label="账号状态">
              <StatusPill status={user.status} yn={user.yn} />
            </InfoRow>
            <InfoRow label="注册时间">{formatDateTime(user.created_at)}</InfoRow>
            <InfoRow label="最近登录">
              {user.last_login_at ? formatDateTime(user.last_login_at) : "从未登录"}
            </InfoRow>
            <InfoRow label="最后更新">{formatDateTime(user.updated_at)}</InfoRow>
          </dl>
        )}
      </DialogContent>
    </Dialog>
  );
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 text-right text-slate-800">{children}</dd>
    </div>
  );
}

export function StatusPill({ status, yn }: { status: number; yn: number }) {
  const disabled = status === 0 || yn === 0;
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-medium",
        disabled ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700",
      )}
    >
      {disabled ? "已禁用" : "正常"}
    </span>
  );
}
