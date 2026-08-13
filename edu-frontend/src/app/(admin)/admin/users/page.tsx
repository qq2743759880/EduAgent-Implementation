/**
 * 管理端 · 用户管理（/admin/users，task03）
 *  - 用户列表：GET /api/admin/users（role/keyword/status 过滤 + 分页）
 *  - UserTable：角色切换 + 启用/禁用 + 详情弹窗
 *  - 写操作 useMutation + invalidateQueries（L3）；失败全局 toast（R-7）
 *    最后 1 个 admin 降级/禁用被后端 40303 拒绝 → toast 明确提示「至少保留 1 名可用管理员账号」
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Users as UsersIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { UserTable } from "@/components/admin/UserTable";
import { ErrorState, EmptyState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { USER_ROLE_OPTIONS, USER_STATUS_OPTIONS, listUsers } from "@/lib/api/admin/users";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

const PAGE_SIZE = 10;

export default function AdminUsersPage() {
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  // perf F1：关键词 300ms 防抖后进 queryKey（applied 快照），空串归一 undefined 减少无效 key 变体
  const appliedKeyword = useDebouncedValue(keyword, 300);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "users", { role, status, keyword: appliedKeyword || undefined, page }] as const,
    async queryFn() {
      return listUsers({
        role_code: role,
        status: status === "" ? undefined : Number(status),
        keyword: appliedKeyword || undefined,
        page,
        page_size: PAGE_SIZE,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">用户管理</h1>
          <p className="text-sm text-slate-500">
            共 {data?.total ?? "—"} 位用户 · 角色切换与禁用受后端 RBAC 保护
          </p>
        </div>
      </div>

      {/* 过滤栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="w-full sm:w-36">
          <label htmlFor="filter-role" className="mb-1 block text-xs text-slate-500">角色</label>
          <NativeSelect id="filter-role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
            <option value="">全部角色</option>
            {USER_ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-32">
          <label htmlFor="filter-status" className="mb-1 block text-xs text-slate-500">状态</label>
          <NativeSelect id="filter-status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">全部</option>
            {USER_STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="min-w-0 flex-1">
          <label htmlFor="filter-user-keyword" className="mb-1 block text-xs text-slate-500">关键词</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              id="filter-user-keyword"
              className="pl-8"
              value={keyword}
              placeholder="账号 / 姓名 / 手机 / 邮箱"
              onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
            />
          </div>
        </div>
        <Button variant="outline" onClick={() => { setRole(""); setStatus(""); setKeyword(""); setPage(1); }}>
          重置
        </Button>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载用户…" />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : "用户加载失败"} onRetry={() => refetch()} />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState
          message="没有匹配的用户"
          hint="调整筛选条件后重试"
        />
      ) : (
        <>
          <UserTable users={data!.items} />
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                <UsersIcon className="h-3.5 w-3.5" /> 共 {data!.total} 位用户
              </span>
              <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
