/**
 * 管理端 · MCP 控制台（/admin/mcp，task04）
 *  - Server 列表（健康灯 last_health_ok/last_error）+ 新增 Server（stdio/sse）+ import-url
 *  - 工具列表（DB + live discover-live）+ 工具测试弹窗（status/result/latency_ms）
 *  - 调用日志表格（过滤 + 分页）
 *  - 全部数据来自真实 API；写操作 useMutation（L3），失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ServerTable } from "@/components/admin/mcp/ServerTable";
import { ServerForm } from "@/components/admin/mcp/ServerForm";
import { CallLogTable } from "@/components/admin/mcp/CallLogTable";
import { EmptyState, ErrorState, LoadingState } from "@/components/admin/controls";
import { listMcpServers, scanMcpServersHealth } from "@/lib/api/admin/mcp";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export default function AdminMcpPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [scanSummary, setScanSummary] = useState<string | null>(null);

  const serversQuery = useQuery({
    queryKey: ["admin", "mcp", "servers"] as const,
    queryFn: () => listMcpServers({ page_size: 100 }),
    staleTime: 15_000,
  });

  const scanMutation = useMutation({
    mutationFn: () => scanMcpServersHealth(),
    onSuccess: (res) => {
      setScanSummary(`OK ${res.ok_count} / ERR ${res.error_count}（共 ${res.scanned}，${res.elapsed_ms}ms）`);
      toast.success(`健康扫描完成：OK ${res.ok_count} / ERR ${res.error_count}`);
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp", "servers"] });
    },
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">MCP 控制台</h1>
          <p className="text-sm text-slate-500">
            Server 管理 / 工具发现与测试 / 调用审计（仅 admin）
          </p>
        </div>
        <div className="flex items-center gap-2">
          {scanSummary && (
            <span
              className="rounded-lg bg-slate-100 px-2.5 py-1 text-[12px] text-slate-600"
              data-testid="scan-summary"
              role="status"
              aria-live="polite"
            >
              {scanSummary}
            </span>
          )}
          <Button variant="outline" size="sm" disabled={scanMutation.isPending} onClick={() => scanMutation.mutate()} data-testid="health-scan">
            <Activity className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            {scanMutation.isPending ? "扫描中…" : "健康扫描"}
          </Button>
          <Button size="sm" onClick={() => setFormOpen(true)} data-testid="server-open">
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 新增 Server
          </Button>
        </div>
      </div>

      {/* Server 列表 */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">MCP Servers</h2>
          <Button variant="ghost" size="sm" onClick={() => serversQuery.refetch()} data-testid="servers-refresh">
            <RefreshCw className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 刷新
          </Button>
        </div>
        {serversQuery.isLoading && !serversQuery.data ? (
          <LoadingState label="加载 Server…" />
        ) : serversQuery.isError ? (
          <ErrorState
            message={serversQuery.error instanceof Error ? serversQuery.error.message : "Server 加载失败"}
            onRetry={() => serversQuery.refetch()}
          />
        ) : (serversQuery.data?.items?.length ?? 0) === 0 ? (
          <EmptyState message="暂无 MCP Server" hint="点击右上角「新增 Server」注册，或使用 import-url 快速导入" />
        ) : (
          <ServerTable servers={serversQuery.data!.items} />
        )}
      </section>

      {/* 调用日志 */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-700">工具调用日志</h2>
        <CallLogTable defaultServerId={serversQuery.data?.items?.[0]?.id} />
      </section>

      <ServerForm open={formOpen} onOpenChange={setFormOpen} />
    </div>
  );
}
