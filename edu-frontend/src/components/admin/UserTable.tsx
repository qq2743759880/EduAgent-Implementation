/**
 * UserTable — 用户表格（task60 /admin/users 重构）
 *  - 行：头像 + 姓名(+「最后admin」徽章) + UID / 手机账号 / 角色徽章 / 状态 / 注册 / 最近登录
 *  - 操作：
 *      「查看」→ UserLearningDialog（学习详情 6 指标 + 最近动态，GET /{id}/learning 契约缺口如实披露）
 *      「编辑」→ EditUserDialog（角色/状态/reason + 最后 admin 前端红线）
 *  - 最后 1 个可用 admin 判定：当前列表内 role=admin 且 status=1 且 yn=1 的用户仅此 1 个
 *    （前端 best-effort，后端 40303 仍兜底拒绝）
 *  - 写操作集中在 EditUserDialog；401/403 与其余状态码一律走全局 MutationCache onError → toast
 *    （task37 差异单②，组件级不再补偿，避免双弹）
 */
"use client";

import { useState } from "react";
import { BookOpen, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EditUserDialog } from "@/components/admin/EditUserDialog";
import { UserLearningDialog, UserStatusPill } from "@/components/admin/UserLearningDialog";
import { userDisplayName, userRoleLabel, type AdminUserItem } from "@/lib/api/admin/users";
import { cn } from "@/lib/utils";

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-primary-soft text-primary",
  manager: "bg-candy-purple/10 text-candy-purple",
  teacher: "bg-candy-blue/10 text-candy-blue",
  student: "bg-muted text-muted-foreground",
};

const AVATAR_GRADS = [
  "from-primary to-candy-purple",
  "from-candy-blue to-candy-green",
  "from-candy-orange to-candy-pink",
  "from-candy-purple to-candy-pink",
  "from-candy-green to-candy-blue",
];

const COLUMNS = ["用户", "手机 / 账号", "角色", "状态", "注册时间", "最近登录"] as const;

export function UserTable({ users }: { users: AdminUserItem[] }) {
  const [learningUser, setLearningUser] = useState<AdminUserItem | null>(null);
  const [editingUser, setEditingUser] = useState<AdminUserItem | null>(null);

  // 红线程：有效 admin 仅此 1 个 → lastAdmin
  const activeAdminIds = users
    .filter((u) => u.role_code === "admin" && u.status === 1 && u.yn === 1)
    .map((u) => u.user_id);
  const lastAdminIds = new Set(activeAdminIds.length <= 1 ? activeAdminIds : []);

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full min-w-[780px] text-sm" data-testid="user-table">
          <thead>
            <tr className="border-b border-border bg-primary-soft/40 text-left text-xs text-muted-foreground">
              {COLUMNS.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2.5 font-medium">
                  {c}
                </th>
              ))}
              <th className="px-3 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((u, i) => {
              const lastAdmin = lastAdminIds.has(u.user_id);
              return (
                <tr key={u.user_id} className="hover:bg-primary-soft/40" data-testid="user-row">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={cn(
                          "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-sm font-bold text-white",
                          AVATAR_GRADS[i % AVATAR_GRADS.length],
                        )}
                      >
                        {userDisplayName(u).slice(0, 1)}
                      </span>
                      <div className="min-w-0">
                        <div className="font-medium text-foreground">
                          {userDisplayName(u)}
                          {lastAdmin && (
                            <span className="ml-1.5 inline-flex items-center gap-0.5 rounded-full border border-candy-red/30 bg-candy-red/10 px-1.5 py-0.5 text-xs font-semibold text-candy-red">
                              最后admin
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">{u.username || "—"} · UID {u.user_id}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{u.phone || u.email || "—"}</td>
                  <td className="px-3 py-2.5">
                    <RoleBadge role={u.role_code} />
                  </td>
                  <td className="px-3 py-2.5">
                    <UserStatusPill status={u.status} yn={u.yn} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted-foreground">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "从未登录"}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setLearningUser(u)} data-testid={`view-${u.user_id}`}>
                        <BookOpen className="mr-1 h-3.5 w-3.5" /> 查看
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setEditingUser(u)} data-testid={`edit-${u.user_id}`}>
                        <Pencil className="mr-1 h-3.5 w-3.5" /> 编辑
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <UserLearningDialog
        key={learningUser?.user_id ?? "none"}
        user={learningUser}
        open={Boolean(learningUser)}
        onOpenChange={(o) => !o && setLearningUser(null)}
      />
      <EditUserDialog
        key={editingUser?.user_id ?? "none"}
        user={editingUser}
        lastAdmin={editingUser ? lastAdminIds.has(editingUser.user_id) : false}
        open={Boolean(editingUser)}
        onOpenChange={(o) => !o && setEditingUser(null)}
      />
    </>
  );
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        ROLE_BADGE[role] ?? "bg-muted text-muted-foreground",
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {userRoleLabel(role)}
    </span>
  );
}