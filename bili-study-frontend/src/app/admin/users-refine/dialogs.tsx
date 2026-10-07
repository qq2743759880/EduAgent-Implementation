/** B3-impl 对话框（S6 启停二次确认 / S7 编辑 diff + 40303 红线）。写路径契约 2026-09-12 curl 实测：
 * POST /api/admin/users/{id}/status body{status:0|1,yn,reason?}→200{updated,user_id,status,yn}；POST /api/admin/users/{id}/role body{target_role,reason?}→200{updated,user_id,target_role}。
 * 40303「至少保留 1 名可用管理员账号」经 HTTP 403 + code "40303" 返回（后端权威兜底）；前端以 metrics.role_breakdown.admin 尽力提示（adminCount≤1→禁用保存），不据此放行真实操作。 */
"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, http } from "@edu/refine-layer";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/admin/controls";
import { Textarea } from "@/components/ui/textarea";
import { USER_ROLE_OPTIONS, userDisplayName, userRoleLabel, type AdminUserItem } from "@/lib/api/admin/users";

export interface UserDialogProps { user: AdminUserItem; open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void; }

/** ApiError→{status,code,message}（错误码为字符串，如 "40300"/"40303"，取自壳 body.code） */
export function apiErrInfo(e: unknown): { status: number; code: string; message: string } {
  const a = e instanceof ApiError ? e : null, body = (a?.body ?? null) as { code?: unknown } | null;
  return { status: a?.status ?? 0, code: body && body.code != null ? String(body.code) : "", message: (e instanceof Error && e.message) || "请求失败" };
}

const Redline = ({ children }: { children: React.ReactNode }) => <p data-testid="refine-redline" className="rounded-lg bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-700">{children}</p>;

const ReasonField = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
  <label className="block space-y-1"><span className="block text-xs text-muted-foreground">变更原因（可选，≤255，操作留痕）</span><Textarea rows={2} maxLength={255} value={value} onChange={(e) => onChange(e.target.value)} placeholder="操作留痕，选填" /></label>
);

/** S7 diff 行：未变更=灰 / 变更=绿 / 被红线拦截=红 */
const DiffRow = ({ k, oldText, newText, changed, blocked }: { k: string; oldText: string; newText: string; changed: boolean; blocked: boolean }) => (
  <div className={"flex items-center gap-2.5 px-3 py-2.5 text-sm " + (changed ? "border-t " + (blocked ? "border-rose-200 bg-rose-50" : "border-emerald-200 bg-emerald-50") : "")}><span className="w-8 shrink-0 text-xs font-bold text-muted-foreground">{k}</span>
    {changed ? <><span className="text-muted-foreground line-through">{oldText}</span><span className="text-muted-foreground">→</span><span className={"font-bold " + (blocked ? "text-rose-700" : "text-emerald-700")}>{newText}</span></> : <span className="text-xs text-muted-foreground">{newText}（未变更）</span>}
  </div>
);

/** S6 启停二次确认：POST /{id}/status（yn 约定：禁用 0 / 启用 1，与 task60 版一致） */
export function StatusConfirmDialog({ user, open, onOpenChange, onDone }: UserDialogProps) {
  const [reason, setReason] = useState(""), disabling = user.status === 1;
  const m = useMutation({
    mutationFn: () => http.post<{ updated: boolean }>(`/api/admin/users/${user.user_id}/status`, { status: disabling ? 0 : 1, yn: disabling ? 0 : 1, reason: reason.trim() || undefined }),
    onSuccess: () => { toast.success(disabling ? "已禁用该用户" : "已启用该用户"); onDone(); },
    onError: (e) => toast.error(apiErrInfo(e).message),
  });
  const err = m.error ? apiErrInfo(m.error) : null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-md">
      <DialogHeader><DialogTitle>{disabling ? "确认禁用该账号？" : "确认启用该账号？"}</DialogTitle></DialogHeader>
      <p className="text-sm">{userDisplayName(user)}（UID {user.user_id}）——{disabling ? "禁用后该用户将无法登录。" : "启用后恢复登录。"}</p>
      <p className="font-mono text-xs text-muted-foreground">{"POST /api/admin/users/" + user.user_id + "/status · body {status: " + (disabling ? 0 : 1) + "}"}</p>
      {err?.code === "40303" && <Redline>红线保护：{err.message}（后端权威兜底：至少保留 1 名可用管理员账号）</Redline>}
      <ReasonField value={reason} onChange={setReason} />
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button><Button data-testid="refine-confirm-status" disabled={m.isPending} onClick={() => m.mutate()}>确认{disabling ? "禁用" : "启用"}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

/** S7 编辑 diff 弹窗：保存=先 POST /{id}/role 再 POST /{id}/status（仅提交变更项）；40303/唯一可用 admin→保存禁用+红线 */
export function EditDiffDialog({ user, open, onOpenChange, onDone, adminCount }: UserDialogProps & { adminCount?: number }) {
  const [role, setRole] = useState(user.role_code), [status, setStatus] = useState(user.status), [reason, setReason] = useState("");
  const roleChanged = role !== user.role_code, statusChanged = status !== user.status;
  // 唯一可用 admin 的禁用/降级（尽力提示；metrics 缺失时不拦截，后端 40303 权威兜底）
  const lastAdminRisk = user.role_code === "admin" && user.status === 1 && adminCount !== undefined && adminCount <= 1 && (role !== "admin" || status === 0);
  const m = useMutation({
    mutationFn: async () => {
      if (roleChanged) await http.post(`/api/admin/users/${user.user_id}/role`, { target_role: role, reason: reason.trim() || undefined });
      if (statusChanged) await http.post(`/api/admin/users/${user.user_id}/status`, { status, yn: status === 0 ? 0 : 1, reason: reason.trim() || undefined });
    },
    onSuccess: () => { toast.success("已保存变更"); onDone(); },
    onError: (e) => toast.error(apiErrInfo(e).message),
  });
  const err = m.error ? apiErrInfo(m.error) : null, blocked = lastAdminRisk || err?.code === "40303";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-lg">
      <DialogHeader><DialogTitle>编辑用户 {userDisplayName(user)}（UID {user.user_id}）</DialogTitle></DialogHeader>
      <div className="overflow-hidden rounded-xl border border-border">
        <DiffRow k="角色" oldText={userRoleLabel(user.role_code) + " " + user.role_code} newText={userRoleLabel(role) + " " + role} changed={roleChanged} blocked={blocked} />
        <DiffRow k="状态" oldText={user.status === 1 ? "启用 1" : "禁用 0"} newText={status === 1 ? "启用 1" : "禁用 0"} changed={statusChanged} blocked={blocked} />
      </div>
      <div className="flex flex-wrap gap-2">
        <label className="min-w-36 flex-1 space-y-1"><span className="block text-xs text-muted-foreground">角色</span>
          <NativeSelect aria-label="编辑角色" value={role} onChange={(e) => { setRole(e.target.value); m.reset(); }}>{USER_ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</NativeSelect></label>
        <label className="min-w-32 flex-1 space-y-1"><span className="block text-xs text-muted-foreground">状态</span>
          <NativeSelect aria-label="编辑状态" value={String(status)} onChange={(e) => { setStatus(Number(e.target.value)); m.reset(); }}><option value="1">启用</option><option value="0">禁用</option></NativeSelect></label>
      </div>
      {blocked && <Redline>红线保护：{lastAdminRisk ? "该用户是唯一可用 admin（metrics.role_breakdown.admin=" + adminCount + "），禁用（状态=0）或降级（≠admin）将导致无人能进入管理端，前端已禁用保存；" : ""}后端同样拒绝（40303「至少保留 1 名可用管理员账号」，权威兜底）。</Redline>}
      <ReasonField value={reason} onChange={setReason} />
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button><Button data-testid="refine-save-edit" disabled={m.isPending || blocked || (!roleChanged && !statusChanged)} onClick={() => m.mutate()}>保存变更</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
