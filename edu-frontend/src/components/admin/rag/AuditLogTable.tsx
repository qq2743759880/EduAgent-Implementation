/**
 * AuditLogTable — RAG 审计日志表格（task04）
 *  - 过滤栏：user_id（数字）/ role / created_after（datetime-local）
 *  - 分页：GET /api/admin/rag/audit-log?page&page_size&user_id&role&created_after
 *  - 表格列：时间/用户/角色/问题/召回数/最终数/模型/延迟/降级
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FilterX, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { EmptyState, ErrorState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { listRagAuditLog } from "@/lib/api/admin/rag";

const PAGE_SIZE = 10;

const ROLE_OPTIONS = [
  { value: "student", label: "学员" },
  { value: "admin", label: "管理员" },
  { value: "teacher", label: "教师" },
  { value: "manager", label: "运营" },
] as const;

export function AuditLogTable() {
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [applied, setApplied] = useState({ userId: "", role: "", createdAfter: "" });
  const [page, setPage] = useState(1);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "rag", "audit-log", applied, page] as const,
    async queryFn() {
      return listRagAuditLog({
        page,
        page_size: PAGE_SIZE,
        user_id: applied.userId === "" ? undefined : Number(applied.userId),
        role: applied.role,
        created_after: applied.createdAfter || undefined,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 10_000,
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  function applyFilters() {
    setApplied({ userId: userId.trim(), role, createdAfter });
    setPage(1);
  }

  function resetFilters() {
    setUserId("");
    setRole("");
    setCreatedAfter("");
    setApplied({ userId: "", role: "", createdAfter: "" });
    setPage(1);
  }

  return (
    <div className="space-y-3">
      {/* 过滤栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="w-full sm:w-36">
          <label htmlFor="audit-user-id" className="mb-1 block text-xs text-slate-600">用户 ID</label>
          <Input
            id="audit-user-id"
            type="number"
            min={1}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="如 841"
            data-testid="audit-user-id"
          />
        </div>
        <div className="w-full sm:w-32">
          <label htmlFor="audit-role" className="mb-1 block text-xs text-slate-600">发起角色</label>
          <NativeSelect id="audit-role" value={role} onChange={(e) => setRole(e.target.value)} data-testid="audit-role">
            <option value="">全部角色</option>
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-56">
          <label htmlFor="audit-created-after" className="mb-1 block text-xs text-slate-600">创建时间之后（created_after）</label>
          <Input
            id="audit-created-after"
            type="datetime-local"
            value={createdAfter}
            onChange={(e) => setCreatedAfter(e.target.value)}
            data-testid="audit-created-after"
          />
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={applyFilters} data-testid="audit-apply">
            <Search className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 查询
          </Button>
          <Button size="sm" variant="outline" onClick={resetFilters} data-testid="audit-reset">
            <FilterX className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 重置
          </Button>
        </div>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载审计日志…" />
      ) : isError ? (
        <ErrorState
          message={error instanceof Error ? error.message : "审计日志加载失败"}
          onRetry={() => refetch()}
        />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="没有匹配的审计记录" hint="调整过滤条件后重试" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[900px] text-sm" data-testid="audit-log-table">
              <caption className="sr-only">RAG 审计日志列表（时间 / 用户 / 角色 / 问题 / 召回 / 模型 / 延迟 / 降级）</caption>
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
                  <th scope="col" className="px-3 py-2.5 font-medium">时间</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">用户</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">角色</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">问题（query）</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">召回/最终</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">模型</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">延迟</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">降级</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data!.items.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/60" data-testid="audit-log-row">
                    <td className="whitespace-nowrap px-3 py-2.5 text-[13px] text-slate-500">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="font-medium text-slate-700">#{entry.user_id}</span>
                      {entry.session_id && (
                        <div className="font-mono text-[11px] text-slate-600">sid {entry.session_id}</div>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge variant="outline" className="border-slate-200 text-slate-600">
                        {entry.role}
                      </Badge>
                    </td>
                    <td className="max-w-[280px] px-3 py-2.5">
                      <div className="truncate text-[13px] text-slate-700" title={entry.query}>
                        {entry.query || "—"}
                      </div>
                      <div className="font-mono text-[11px] text-slate-600">{entry.audit_id}</div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[13px] text-slate-600">
                      {entry.retrieved_count ?? "—"} / {entry.final_count ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[13px] text-slate-500">
                      {entry.llm_model ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[13px] text-slate-600">
                      {entry.latency_ms}ms
                    </td>
                    <td className="px-3 py-2.5">
                      {entry.degraded_reason ? (
                        <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700" data-testid="degraded-badge">
                          {entry.degraded_reason}
                        </Badge>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />
        </>
      )}
    </div>
  );
}
