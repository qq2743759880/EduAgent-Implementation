/**
 * 管理端 · 用户管理（/admin/users，task60 重构）
 *  - 用户列表：GET /api/admin/users（keyword + role_code + status 组合查询 + 分页，page_size 10）
 *  - 关键词搜索防抖 400ms（GWT①）；角色/状态切换即查；重置清空并回第 1 页
 *  - 列表三态：Loading / Error / Empty（controls 共享）；无 MOCK
 *  - 行内操作：查看（学习详情 Dialog）/ 编辑（角色/状态 + 最后 admin 红线）→ UserTable
 *  - 最后 1 个可用 admin 的禁用/降级由前端禁用 + 后端 40303 兜底
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { UserTable } from "@/components/admin/UserTable";
import { EmptyState, ErrorState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { USER_ROLE_OPTIONS, USER_STATUS_OPTIONS, listUsers } from "@/lib/api/admin/users";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

const PAGE_SIZE = 10;
/** GWT①：关键词搜索防抖 400ms */
const KEYWORD_DEBOUNCE_MS = 400;

export default function AdminUsersPage() {
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  // 关键词 400ms 防抖后进 queryKey（applied 快照），空串归一 undefined 减少无效 key 变体
  const appliedKeyword = useDebouncedValue(keyword, KEYWORD_DEBOUNCE_MS);

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

  const resetFilter = () => {
    setRole("");
    setStatus("");
    setKeyword("");
    setPage(1);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">用户管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {data?.total ?? "—"} 位用户 · 角色切换与禁用受后端 RBAC 保护，最后 1 个可用 admin 前端禁用 + 后端 40303 拒绝
          </p>
        </div>
      </div>

      {/* 过滤栏：搜索防抖 400ms + 角色/状态组合查询 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-card p-3">
        <div className="w-full sm:w-36">
          <label htmlFor="filter-role" className="mb-1 block text-xs text-muted-foreground">角色</label>
          <NativeSelect
            id="filter-role"
            value={role}
            aria-label="按角色筛选"
            onChange={(e) => {
              setRole(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部角色</option>
            {USER_ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-32">
          <label htmlFor="filter-status" className="mb-1 block text-xs text-muted-foreground">状态</label>
          <NativeSelect
            id="filter-status"
            value={status}
            aria-label="按状态筛选"
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部</option>
            {USER_STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="min-w-0 flex-1">
          <label htmlFor="filter-user-keyword" className="mb-1 block text-xs text-muted-foreground">
            关键词 <span className="text-muted-foreground/70">（防抖 400ms）</span>
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="filter-user-keyword"
              className="pl-8"
              value={keyword}
              placeholder="账号 / 姓名 / 手机 / 邮箱（LIKE 组合查询）"
              onChange={(e) => {
                setKeyword(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <Button variant="outline" onClick={resetFilter} data-testid="users-reset">
          重置
        </Button>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载用户…" />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : "用户加载失败"} onRetry={() => refetch()} />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="没有匹配的用户" hint="调整筛选条件后重试" />
      ) : (
        <>
          <UserTable users={data!.items} />
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                共 {data!.total} 位用户
              </span>
              <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}