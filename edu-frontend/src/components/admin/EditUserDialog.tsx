/**
 * EditUserDialog — 用户编辑弹窗（task60 /admin/users 重构）
 *  - 角色切换   POST /api/admin/users/{id}/role   body {target_role, reason}
 *  - 状态切换   POST /api/admin/users/{id}/status body {status:0|1, yn, reason}
 *  - 变更原因 reason（选填，≤255，操作留痕）
 *  - 最后 1 个可用 admin 红线（GWT③）：
 *      lastAdmin=true → 前端禁用「降级」「禁用」「保存」+ 红线条幅提示；
 *      后端仍拒绝兜底（40303「至少保留 1 名可用管理员账号」）。
 *  - 错误提示：401/403 与其余状态码统一走全局 MutationCache onError → toast（task37 差异单②），
 *     本组件不再做任何 onError 补偿，避免双弹。
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/admin/controls";
import { changeUserRole, changeUserStatus, userDisplayName, userRoleLabel, USER_ROLE_OPTIONS, type AdminUserItem } from "@/lib/api/admin/users";
import { cn } from "@/lib/utils";

export function EditUserDialog({
  user,
  lastAdmin,
  open,
  onOpenChange,
}: {
  user: AdminUserItem | null;
  lastAdmin: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [role, setRole] = useState(user?.role_code ?? "");
  const [status, setStatus] = useState<number>(user?.status ?? 1);
  const [reason, setReason] = useState("");

  // 编辑态随选中用户复位：由 UserTable 以 key={user_id} remount 本组件（对齐 SeriesForm 技法），
  // 避免在 effect 中同步 setState（React Compiler 专项优化，防止级联渲染）。

  const roleMutation = useMutation({
    mutationFn: (targetRole: string) => changeUserRole(user!.user_id, targetRole, reason.trim() || undefined),
  });
  const statusMutation = useMutation({
    mutationFn: (nextStatus: number) =>
      changeUserStatus(user!.user_id, {
        status: nextStatus,
        yn: nextStatus === 0 ? 0 : 1,
        reason: reason.trim() || undefined,
      }),
  });

  const guard = lastAdmin;
  const busy = roleMutation.isPending || statusMutation.isPending;
  const roleChanged = user ? role !== user.role_code : false;
  const statusChanged = user ? status !== user.status : false;
  const canSave = !guard && (roleChanged || statusChanged) && !busy;

  function closeAndInvalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    onOpenChange(false);
  }

  function handleSave() {
    if (!user || guard || busy || (!roleChanged && !statusChanged)) return;
    if (roleChanged) {
      const roleOnSuccess = () => {
        toast.success(`角色已更新 → ${userRoleLabel(role)}`);
        if (statusChanged) {
          statusMutation.mutate(status, {
            onSuccess: () => {
              toast.success(status === 0 ? "已禁用该用户" : "已启用该用户");
              closeAndInvalidate();
            },
          });
        } else {
          closeAndInvalidate();
        }
      };
      roleMutation.mutate(role, { onSuccess: roleOnSuccess });
      return;
    }
    statusMutation.mutate(status, {
      onSuccess: () => {
        toast.success(status === 0 ? "已禁用该用户" : "已启用该用户");
        closeAndInvalidate();
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>编辑用户 · {user ? userDisplayName(user) : ""}</DialogTitle>
        </DialogHeader>

        {user && (
          <div className="space-y-4">
            <div className="text-xs text-muted-foreground">
              UID {user.user_id} · 校验线 <code className="font-mono">POST /api/admin/users/{user.user_id}/role | /status</code>
            </div>

            {/* 红线条幅：最后 1 个可用 admin */}
            {guard && (
              <div className="flex items-start gap-2 rounded-xl border border-candy-red/30 bg-candy-red/10 p-3 text-xs leading-relaxed text-foreground">
                <Ban className="mt-0.5 h-4 w-4 shrink-0 text-candy-red" />
                <span>
                  <b>红线保护</b>：该用户是<b>唯一可用 admin</b>。禁用（status=0）或降级（≠admin）
                  将导致无人能进入管理端——前端已禁用操作；后端同样拒绝（40303「至少保留 1 名可用管理员账号」）。
                </span>
              </div>
            )}

            <div className="space-y-1.5">
              <label htmlFor="edit-role" className="text-xs font-medium text-muted-foreground">
                角色 <code className="font-mono">target_role</code>
              </label>
              <NativeSelect
                id="edit-role"
                value={role}
                disabled={guard}
                aria-label="角色"
                data-testid="edit-role"
                title={guard ? "最后 1 个可用 admin：禁止降级" : undefined}
                onChange={(e) => setRole(e.target.value)}
              >
                {USER_ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </NativeSelect>
              {guard && (
                <p className="text-xs text-candy-red">角色选择已锁定（最后 1 个可用 admin）</p>
              )}
            </div>

            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground">状态</span>
              <div className="inline-flex overflow-hidden rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setStatus(1)}
                  aria-pressed={status === 1}
                  className={cn(
                    "px-4 py-2 text-sm font-semibold transition-colors",
                    status === 1 ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:bg-primary-soft",
                  )}
                >
                  启用
                </button>
                <button
                  type="button"
                  onClick={() => setStatus(0)}
                  disabled={guard}
                  aria-pressed={status === 0}
                  title={guard ? "最后 1 个可用 admin：禁止禁用" : undefined}
                  className={cn(
                    "px-4 py-2 text-sm font-semibold transition-colors",
                    status === 0 ? "bg-candy-red text-white" : "bg-card text-muted-foreground hover:bg-primary-soft",
                    guard && "cursor-not-allowed opacity-50",
                  )}
                >
                  禁用
                </button>
              </div>
              <p className="text-xs text-muted-foreground">
                状态切换 <code className="font-mono">status+yn（禁用 0 / 启用 1）</code>
              </p>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="edit-reason" className="text-xs font-medium text-muted-foreground">
                变更原因（选填，reason ≤255）
              </label>
              <textarea
                id="edit-reason"
                value={reason}
                maxLength={255}
                onChange={(e) => setReason(e.target.value)}
                placeholder="操作留痕，选填"
                className="min-h-16 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                data-testid="edit-reason"
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button disabled={!canSave} onClick={handleSave} data-testid="edit-save">
                {busy ? "保存中…" : "保存变更"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}