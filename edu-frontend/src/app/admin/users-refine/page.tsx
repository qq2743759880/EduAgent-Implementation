/** admin-users Refine 版（B3-impl，/admin/users-refine）——admin-users.html(642 行) 的 Refine v5 headless 实现，C15 选型证伪件（判据 ≤214 行，不含 import/类型声明）。
 * 数据层=B2 refine-layer（EduRefineProvider+共享 queryClient 单例+dataProvider），零手写客户端（C17）；与 task60 版 /admin/users 并存，回滚=删本目录+还原接线（见 B3 报告）。
 * 权限口径（D-H3/GWT③）：manager=只读横幅+不发列表请求（请求前复查 auth/me，H2a/P1-9）；ADMIN=列表+搜索防抖 400ms+筛选+窗口化分页+启停二次确认+编辑 diff（40303 红线）。 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useList } from "@refinedev/core";
import { toast } from "sonner";
import { EduRefineProvider, http, tokenStore } from "@edu/refine-layer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { EmptyState, ErrorState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { USER_ROLE_OPTIONS, USER_STATUS_OPTIONS, formatDateTime, userDisplayName, userRoleLabel, type AdminUserItem } from "@/lib/api/admin/users";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import { EditDiffDialog, StatusConfirmDialog, apiErrInfo } from "./dialogs";

const PAGE_SIZE = 10;
const LOGIN_REDIRECT = "/login?redirect=%2Fadmin%2Fusers-refine";
type MeShape = { role?: string | null; role_code?: string | null; roles?: string[] | null };
type MetricsShape = { role_breakdown?: Record<string, number>; total_user_count?: number };

/** 三段守卫（教训10）：无 token→跳登录（不发请求）；有 token→复查 auth/me；me 失败仍跳登录（防 DEBUG 降级绕过） */
function useRefineGate(): "checking" | "manager" | "admin" {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null); // null=首帧未定（SSR/CSR 一致）
  const me = useQuery({ queryKey: ["refine-gate", "me"], queryFn: () => http.get<MeShape>("/api/auth/me"), enabled: !!token, retry: false });
  const role = String(me.data?.role || me.data?.role_code || me.data?.roles?.[0] || "").toLowerCase();
  useEffect(() => {
    const t = tokenStore.getToken();
    setToken(t);
    if (!t) { toast.warning("请先登录"); router.replace(LOGIN_REDIRECT); }
  }, [router]);
  useEffect(() => {
    if (!token) return;
    if (me.isError) { toast.error("登录态校验失败，请重新登录"); router.replace(LOGIN_REDIRECT); }
    else if (me.isSuccess && role !== "admin" && role !== "manager") router.replace("/dashboard");
  }, [token, me.isError, me.isSuccess, role, router]);
  if (!token || !me.isSuccess) return "checking";
  return role === "admin" ? "admin" : "manager";
}

export default function UsersRefinePage() {
  const gate = useRefineGate();
  return (
    <div className="mx-auto w-full max-w-6xl p-4 md:p-6">
      {gate === "checking" && <LoadingState label="正在校验权限…" />}
      {gate === "manager" && <ManagerBanner />}
      {gate === "admin" && <EduRefineProvider resources={[{ name: "admin/users", list: "/admin/users-refine" }]}><AdminUsersRefine /></EduRefineProvider>}
    </div>
  );
}

/** S1 manager 视角态：只读横幅 + 诚实空态（列表请求前置拦截，不发必 403 的请求） */
function ManagerBanner() {
  const router = useRouter();
  return (
    <div className="space-y-4">
      <div role="alert" data-testid="refine-manager-banner" className="flex flex-wrap items-center justify-center gap-3 rounded-xl bg-rose-400 px-4 py-3.5 text-sm font-bold text-white">
        <span>该模块仅 ADMIN 可用（后端权限口径 require_role([ADMIN])；当前角色 manager）</span>
        <button type="button" onClick={() => router.push("/admin/dashboard")} className="rounded-full bg-white px-3.5 py-1 text-xs font-bold text-rose-700">返回仪表盘</button>
      </div>
      <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground"><p><b className="font-semibold text-foreground">该模块仅 ADMIN 可用（后端权限口径）</b>——当前登录角色 manager，无权读取用户列表；列表区为诚实空态，未发起必 403 的列表请求</p></div>
    </div>
  );
}

/** S2~S7 ADMIN 视角态全量 */
function AdminUsersRefine() {
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminUserItem | null>(null);
  const [toggling, setToggling] = useState<AdminUserItem | null>(null);
  const applied = useDebouncedValue(keyword, 400); // GWT① 防抖 400ms
  const metrics = useQuery({ queryKey: ["refine", "users-metrics"], queryFn: () => http.get<MetricsShape>("/api/admin/users/dashboard/metrics"), retry: false, staleTime: 60_000 });
  const filters = useMemo(() => [
    ...(applied.trim() ? [{ field: "keyword", operator: "contains" as const, value: applied.trim() }] : []),
    ...(role ? [{ field: "role_code", operator: "eq" as const, value: role }] : []),
    ...(status !== "" ? [{ field: "status", operator: "eq" as const, value: Number(status) }] : []),
  ], [applied, role, status]);
  // v5 形状（B2 实测）：数据在 result={data,total}；query 为底层观测句柄（refetch/isError 用）
  const { query, result } = useList<AdminUserItem>({ resource: "admin/users", pagination: { currentPage: page, pageSize: PAGE_SIZE, mode: "server" }, filters, queryOptions: { placeholderData: (prev) => prev, staleTime: 15_000 } });
  const items = result?.data ?? [], total = result?.total ?? 0, totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const adminCount = metrics.data?.role_breakdown?.admin; // 红线尽力提示源；undefined=不拦截（后端 40303 权威兜底）
  const listErr = query.error ? apiErrInfo(query.error) : null;
  const refresh = () => { query.refetch(); metrics.refetch(); };
  const foot = (<div className="flex items-center justify-between text-xs text-muted-foreground"><span data-testid="refine-total">共 {total} 条 · 第 {page}/{totalPages} 页</span>{totalPages > 1 && <PaginationBar page={page} total_pages={totalPages} onChange={setPage} className="py-0" />}</div>);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">用户管理（Refine 版）</h1>
        <p className="mt-1 text-sm text-muted-foreground">共 {metrics.data?.total_user_count ?? "—"} 位用户 · 最后 1 个可用 admin 的禁用/降级 前端禁用 + 后端 40303 拒绝 ·<a className="ml-1 text-primary hover:underline" href="/admin/users">返回现有版</a></p>
      </div>
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-card p-3" data-testid="refine-filterbar">
        <label className="w-36 space-y-1"><span className="block text-xs text-muted-foreground">角色</span>
          <NativeSelect value={role} aria-label="按角色筛选" onChange={(e) => { setRole(e.target.value); setPage(1); }}><option value="">全部角色</option>{USER_ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</NativeSelect></label>
        <label className="w-32 space-y-1"><span className="block text-xs text-muted-foreground">状态</span>
          <NativeSelect value={status} aria-label="按状态筛选" onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">全部状态</option>{USER_STATUS_OPTIONS.map((s) => <option key={s.value} value={String(s.value)}>{s.label}</option>)}</NativeSelect></label>
        <label className="min-w-0 flex-1 space-y-1"><span className="block text-xs text-muted-foreground">关键词（防抖 400ms）</span>
          <Input value={keyword} aria-label="关键词搜索" placeholder="账号 / 姓名 / 手机 / 邮箱（LIKE 组合查询）" onChange={(e) => { setKeyword(e.target.value); setPage(1); }} /></label>
        <Button variant="outline" data-testid="refine-reset" onClick={() => { setRole(""); setStatus(""); setKeyword(""); setPage(1); }}>重置</Button>
      </div>
      {/* 三态：S3 骨架 / S5 403 兜底（正常路径请求前已拦截）/ S4 空态 / S2 正常表 */}
      {query.isLoading && !result ? <LoadingState label="加载用户…" />
        : listErr ? (
          <div data-testid="refine-error">
            <ErrorState message={"用户列表加载失败：" + listErr.message} onRetry={() => query.refetch()} />
            <p className="mx-auto mt-2 max-w-2xl break-all rounded-lg bg-rose-50 px-3 py-2 text-center font-mono text-xs text-rose-700">HTTP {listErr.status || "—"} · code {listErr.code || "—"}</p>
          </div>
        ) : items.length === 0 ? (
          <><EmptyState message="未匹配到用户（组合查询为空/调整筛选）" />{foot}</>
        ) : (
          <>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <table className="w-full border-collapse text-sm">
                <thead><tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">{["用户", "手机", "角色", "状态", "注册时间", "最近登录", "操作"].map((h, i) => <th key={h} className={"px-3 py-2.5 font-semibold" + (i === 6 ? " text-right" : "")}>{h}</th>)}</tr></thead>
                <tbody>
                  {items.map((u) => (
                    <tr key={u.user_id} data-testid="refine-user-row" className="border-b border-border last:border-0">
                      <td className="px-3 py-2.5"><div className="font-medium text-foreground">{userDisplayName(u)}</div><div className="font-mono text-xs text-muted-foreground">{u.username} · UID {u.user_id}</div></td>
                      <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{u.phone || "—"}</td>
                      <td className="px-3 py-2.5">{userRoleLabel(u.role_code)}</td>
                      <td className="px-3 py-2.5"><span className={"rounded-full px-2.5 py-0.5 text-xs font-semibold " + (u.status === 1 ? "bg-emerald-50 text-emerald-700" : "bg-muted text-muted-foreground")}>{u.status === 1 ? "启用" : "禁用"}</span></td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{formatDateTime(u.created_at)}</td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{u.last_login_at ? formatDateTime(u.last_login_at) : "—"}</td>
                      <td className="px-3 py-2.5"><div className="flex justify-end gap-1.5"><Button variant="ghost" size="sm" onClick={() => setEditing(u)}>编辑</Button><Button variant="outline" size="sm" className={u.status === 1 ? "text-rose-600" : ""} onClick={() => setToggling(u)}>{u.status === 1 ? "禁用" : "启用"}</Button></div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {foot}
          </>
        )}
      {toggling && <StatusConfirmDialog user={toggling} open onOpenChange={() => setToggling(null)} onDone={refresh} />}
      {editing && <EditDiffDialog user={editing} open onOpenChange={() => setEditing(null)} onDone={refresh} adminCount={adminCount} />}
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800">缺口诚实披露：「查看/学习详情」依赖 GET /api/admin/users/{'{id}'}/learning，后端未注册（2026-09-12 实测 HTTP 404 · code 40400），学习指标暂无法展示——不造假指标；后端开放后补实现。</p>
    </div>
  );
}
