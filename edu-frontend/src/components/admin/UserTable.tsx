/**
 * UserTable — 用户表格（task03）
 *  - 角色切换：NativeSelect → POST /users/{id}/role（后端拒绝最后 1 个 admin 降级 40303 → 全局 toast 提示）
 *  - 启用/禁用：POST /users/{id}/status {status: 0|1}（最后 1 个 admin 禁用被拒同理）
 *  - 查看详情 → UserDetailDialog（列表数据，无 MOCK）
 *  - 写操作 useMutation + invalidateQueries（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, ShieldCheck, ShieldOff } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  USER_ROLE_OPTIONS,
  changeUserRole,
  changeUserStatus,
  userDisplayName,
  userRoleLabel,
  type AdminUserItem,
} from "@/lib/api/admin/users";
import { NativeSelect } from "@/components/admin/controls";
import { StatusPill, UserDetailDialog } from "@/components/admin/UserDetailDialog";

export function UserTable({ users }: { users: AdminUserItem[] }) {
  const queryClient = useQueryClient();
  const [detailUser, setDetailUser] = useState<AdminUserItem | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

  const roleMutation = useMutation({
    mutationFn: ({ userId, targetRole }: { userId: number; targetRole: string }) =>
      changeUserRole(userId, targetRole),
    onSuccess: (_data, vars) => {
      toast.success(`角色已更新 → ${userRoleLabel(vars.targetRole)}`);
      invalidate();
    },
    // 失败（如 40303 最后 1 个 admin 降级被拒）→ 全局 MutationCache onError toast + console.error
  });

  const statusMutation = useMutation({
    mutationFn: ({ userId, status, yn }: { userId: number; status: number; yn?: number }) =>
      changeUserStatus(userId, { status, yn }),
    onSuccess: (_data, vars) => {
      toast.success(vars.status === 0 || vars.yn === 0 ? "已禁用该用户" : "已启用该用户");
      invalidate();
    },
  });

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[720px] text-sm" data-testid="user-table">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
              <th className="px-3 py-2.5 font-medium">用户</th>
              <th className="px-3 py-2.5 font-medium">账号 / 联系方式</th>
              <th className="px-3 py-2.5 font-medium">角色</th>
              <th className="px-3 py-2.5 font-medium">状态</th>
              <th className="px-3 py-2.5 font-medium">注册时间</th>
              <th className="px-3 py-2.5 font-medium">最近登录</th>
              <th className="px-3 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map((u) => {
              const roleBusy = roleMutation.isPending && roleMutation.variables?.userId === u.user_id;
              const statusBusy =
                statusMutation.isPending && statusMutation.variables?.userId === u.user_id;
              return (
                <tr key={u.user_id} className="hover:bg-slate-50/60" data-testid="user-row">
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-slate-800">{userDisplayName(u)}</div>
                    <div className="text-[11px] text-slate-600">ID {u.user_id}</div>
                  </td>
                  <td className="px-3 py-2.5 text-slate-600">
                    <div>{u.username || "—"}</div>
                    <div className="text-[11px] text-slate-600">{u.email || u.phone || ""}</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <NativeSelect
                      className="h-7 w-28 text-xs"
                      value={u.role_code}
                      disabled={roleBusy}
                      aria-label={`${userDisplayName(u)} 的角色`}
                      data-testid={`role-select-${u.user_id}`}
                      onChange={(e) => {
                        if (e.target.value !== u.role_code) {
                          roleMutation.mutate({ userId: u.user_id, targetRole: e.target.value });
                        }
                      }}
                    >
                      {USER_ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </NativeSelect>
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusPill status={u.status} yn={u.yn} />
                  </td>
                  <td className="px-3 py-2.5 text-[13px] text-slate-500">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5 text-[13px] text-slate-500">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDetailUser(u)}
                        data-testid={`detail-${u.user_id}`}
                      >
                        <Eye className="mr-1 h-3.5 w-3.5" /> 详情
                      </Button>
                      {u.status === 1 && u.yn === 1 ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={statusBusy}
                          data-testid={`disable-${u.user_id}`}
                          onClick={() =>
                            statusMutation.mutate({ userId: u.user_id, status: 0, yn: 0 })
                          }
                        >
                          <ShieldOff className="mr-1 h-3.5 w-3.5 text-rose-500" /> 禁用
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={statusBusy}
                          data-testid={`enable-${u.user_id}`}
                          onClick={() =>
                            statusMutation.mutate({ userId: u.user_id, status: 1, yn: 1 })
                          }
                        >
                          <ShieldCheck className="mr-1 h-3.5 w-3.5 text-emerald-600" /> 启用
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <UserDetailInner user={detailUser} open={Boolean(detailUser)} onOpenChange={(o) => !o && setDetailUser(null)} />
    </>
  );
}

function UserDetailInner(props: {
  user: AdminUserItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return <UserDetailDialog {...props} />;
}
