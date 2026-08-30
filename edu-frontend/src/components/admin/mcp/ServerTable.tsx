/**
 * ServerTable — MCP Server 列表表格（task04）
 *  - 健康灯：last_health_ok=1 → 绿点 OK；0 → 红点 ERR（含 last_error 提示）；null → 灰点未知
 *  - 每行：「发现工具」→ ToolTable（listMcpToolsOfServer + live discover-live）
 *  - 注销：软删 yn=0（DELETE /servers/{id}）
 *  - 写操作 useMutation（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Cable, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ToolTable } from "@/components/admin/mcp/ToolTable";
import {
  deleteMcpServer,
  mcpHealthTone,
  mcpTransportLabel,
  type McpServerItem,
} from "@/lib/api/admin/mcp";
import { cn } from "@/lib/utils";

export function ServerTable({ servers }: { servers: McpServerItem[] }) {
  const queryClient = useQueryClient();
  const [toolServer, setToolServer] = useState<McpServerItem | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (serverId: number) => deleteMcpServer(serverId),
    onSuccess: (_res, serverId) => {
      toast.success(`Server #${serverId} 已注销`);
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp", "servers"] });
    },
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[840px] text-sm" data-testid="mcp-server-table">
          <caption className="sr-only">MCP Server 列表（健康 / 传输 / 状态 / 工具数 / 最近健康检查 / 操作）</caption>
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
              <th scope="col" className="px-3 py-2.5 font-medium">健康</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Server</th>
              <th scope="col" className="px-3 py-2.5 font-medium">传输</th>
              <th scope="col" className="px-3 py-2.5 font-medium">状态</th>
              <th scope="col" className="px-3 py-2.5 font-medium">工具数</th>
              <th scope="col" className="px-3 py-2.5 font-medium">最近健康检查</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {servers.map((s) => {
              const tone = mcpHealthTone(s.last_health_ok);
              const busy = deleteMutation.isPending && deleteMutation.variables === s.id;
              return (
                <tr key={s.id} className="hover:bg-slate-50/60" data-testid="mcp-server-row">
                  <td className="px-3 py-2.5">
                    <HealthDot tone={tone} />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <Cable className="h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true" />
                      <div>
                        <div className="font-medium text-slate-800">{s.display_name}</div>
                        <div className="font-mono text-[11px] text-slate-600">{s.server_code}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge variant="outline" className="border-slate-200 text-slate-600">
                      {mcpTransportLabel(s.transport)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge
                      variant="outline"
                      className={cn(
                        s.enabled === 1
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-slate-200 bg-slate-50 text-slate-500",
                      )}
                      data-testid={`server-enabled-${s.id}`}
                    >
                      {s.enabled === 1 ? "已启用" : "已停用"}
                    </Badge>
                    {s.last_error && (
                      <div className="mt-0.5 max-w-[180px] truncate text-[11px] text-rose-600" title={s.last_error}>
                        {s.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[13px] text-slate-600">{s.tool_count}</td>
                  <td className="px-3 py-2.5 text-[13px] text-slate-500">
                    {s.last_health_at ? new Date(s.last_health_at).toLocaleString() : "从未检查"}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        data-testid={`tools-${s.id}`}
                        onClick={() => setToolServer(s)}
                      >
                        <Search className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 发现工具
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        data-testid={`delete-server-${s.id}`}
                        onClick={() => deleteMutation.mutate(s.id)}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5 text-rose-600" aria-hidden="true" /> 注销
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ToolTable
        server={toolServer}
        open={Boolean(toolServer)}
        onOpenChange={(o) => !o && setToolServer(null)}
      />
    </>
  );
}

export function HealthDot({ tone }: { tone: "ok" | "error" | "unknown" }) {
  // HIGH-03 对比度修复：点与文本全部加深到 ≥3:1（非文本）/ ≥4.5:1（文本）
  //   ok      文本 emerald-600(3.76:1) → emerald-700(≈5.2:1)；点 emerald-500(2.51:1) → emerald-600(≈3.6:1)
  //   error   文本 rose-600(≈4.8:1) 达标保留；点 rose-500(≈3.2:1) 达标保留
  //   unknown 文本 slate-400(2.6:1) → slate-600(≈7.7:1)；点 slate-300(1.47:1) → slate-500(≈4.8:1)
  const dot = {
    ok: "bg-emerald-600",
    error: "bg-rose-500",
    unknown: "bg-slate-500",
  }[tone];
  const label = {
    ok: "OK",
    error: "ERR",
    unknown: "未知",
  }[tone];
  return (
    <span className="inline-flex items-center gap-1.5" data-testid="health-dot">
      <span className={cn("inline-block h-2.5 w-2.5 rounded-full", dot)} aria-hidden="true" />
      <span className={cn("text-[12px] font-medium", tone === "error" ? "text-rose-600" : tone === "ok" ? "text-emerald-700" : "text-slate-600")}>
        {label}
      </span>
    </span>
  );
}
