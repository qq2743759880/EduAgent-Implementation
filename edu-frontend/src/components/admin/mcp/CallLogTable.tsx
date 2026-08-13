/**
 * CallLogTable — MCP 工具调用日志表格（task04）
 *  - 过滤：server_id / tool_name / status / user_id
 *  - 分页：GET /api/mcp/call-log?page&page_size&...
 *  - 列：时间 / server / tool / status / latency / user / trace_id / error
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
import {
  listMcpCallLog,
  mcpCallStatusLabel,
  type McpCallLogItem,
} from "@/lib/api/admin/mcp";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

const STATUS_OPTIONS = [
  { value: "SUCCESS", label: "成功" },
  { value: "ERROR", label: "失败" },
  { value: "TIMEOUT", label: "超时" },
  { value: "SKIPPED", label: "跳过" },
] as const;

export function CallLogTable({ defaultServerId }: { defaultServerId?: number }) {
  const [serverId, setServerId] = useState(defaultServerId ? String(defaultServerId) : "");
  const [toolName, setToolName] = useState("");
  const [status, setStatus] = useState("");
  const [userId, setUserId] = useState("");
  const [applied, setApplied] = useState({ serverId: serverId, toolName: "", status: "", userId: "" });
  const [page, setPage] = useState(1);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "mcp", "call-log", applied, page] as const,
    async queryFn() {
      return listMcpCallLog({
        page,
        page_size: PAGE_SIZE,
        server_id: applied.serverId === "" ? undefined : Number(applied.serverId),
        tool_name: applied.toolName || undefined,
        status: applied.status || undefined,
        user_id: applied.userId === "" ? undefined : Number(applied.userId),
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 10_000,
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  function applyFilters() {
    setApplied({ serverId: serverId.trim(), toolName: toolName.trim(), status, userId: userId.trim() });
    setPage(1);
  }

  function resetFilters() {
    setServerId("");
    setToolName("");
    setStatus("");
    setUserId("");
    setApplied({ serverId: "", toolName: "", status: "", userId: "" });
    setPage(1);
  }

  return (
    <div className="space-y-3">
      {/* 过滤栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="w-full sm:w-28">
          <label htmlFor="log-server-id" className="mb-1 block text-xs text-slate-600">Server ID</label>
          <Input
            id="log-server-id"
            type="number"
            min={1}
            value={serverId}
            onChange={(e) => setServerId(e.target.value)}
            placeholder="如 1"
            data-testid="log-server-id"
          />
        </div>
        <div className="w-full sm:w-40">
          <label htmlFor="log-tool-name" className="mb-1 block text-xs text-slate-600">工具名</label>
          <Input
            id="log-tool-name"
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
            placeholder="如 echo"
            data-testid="log-tool-name"
          />
        </div>
        <div className="w-full sm:w-28">
          <label htmlFor="log-status" className="mb-1 block text-xs text-slate-600">状态</label>
          <NativeSelect id="log-status" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="log-status">
            <option value="">全部</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-28">
          <label htmlFor="log-user-id" className="mb-1 block text-xs text-slate-600">用户 ID</label>
          <Input
            id="log-user-id"
            type="number"
            min={1}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="如 830"
            data-testid="log-user-id"
          />
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={applyFilters} data-testid="log-apply">
            <Search className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 查询
          </Button>
          <Button size="sm" variant="outline" onClick={resetFilters} data-testid="log-reset">
            <FilterX className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 重置
          </Button>
        </div>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载调用日志…" />
      ) : isError ? (
        <ErrorState
          message={error instanceof Error ? error.message : "调用日志加载失败"}
          onRetry={() => refetch()}
        />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="暂无调用日志" hint="对工具发起测试调用后这里会出现记录" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[880px] text-sm" data-testid="call-log-table">
              <caption className="sr-only">MCP 工具调用日志列表（时间 / Server / 工具 / 状态 / 延迟 / 用户 / trace_id / 错误）</caption>
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
                  <th scope="col" className="px-3 py-2.5 font-medium">时间</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Server</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">工具</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">状态</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">延迟</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">用户</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">trace_id</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">错误</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data!.items.map((log: McpCallLogItem) => (
                  <tr key={log.id} className="hover:bg-slate-50/60" data-testid="call-log-row">
                    <td className="whitespace-nowrap px-3 py-2.5 text-[13px] text-slate-500">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[13px] text-slate-600">#{log.server_id}</td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-slate-800">{log.tool_name}</div>
                      <div className="font-mono text-[11px] text-slate-600">{log.call_id}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <CallStatusBadge status={log.status} />
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[13px] text-slate-600">{log.latency_ms}ms</td>
                    <td className="px-3 py-2.5 text-[13px] text-slate-600">#{log.user_id}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">{log.trace_id}</td>
                    <td className="max-w-[200px] px-3 py-2.5">
                      {log.error_message ? (
                        <span className="truncate text-[12px] text-rose-600" title={log.error_message}>
                          {log.error_message}
                        </span>
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

export function CallStatusBadge({ status }: { status: McpCallLogItem["status"] }) {
  const tone = {
    SUCCESS: "bg-emerald-100 text-emerald-700",
    ERROR: "bg-rose-100 text-rose-700",
    // HIGH-04：TIMEOUT 徽章 text-amber-700 on bg-amber-100 ≈4.43:1 < 4.5（临界）→ 加深为 amber-800
    TIMEOUT: "bg-amber-100 text-amber-800",
    SKIPPED: "bg-slate-100 text-slate-600",
  }[status] ?? "bg-slate-100 text-slate-600";

  return (
    <Badge variant="outline" className={cn("border-transparent", tone)}>
      {mcpCallStatusLabel(status)}
    </Badge>
  );
}
