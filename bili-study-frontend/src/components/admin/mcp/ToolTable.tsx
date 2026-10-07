/**
 * ToolTable — MCP 工具列表弹窗（task04）
 *  - DB 列表：GET /servers/{id}/tools（落库工具）
 *  - live discover：GET /servers/{id}/discover-live（直连 Server 实时快照，不落库）
 *  - 每行「测试」→ ToolTestDialog（参数 JSON 编辑 → status/result/latency_ms）
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Beaker, RefreshCw, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/admin/controls";
import { ToolTestDialog } from "@/components/admin/mcp/ToolTestDialog";
import {
  listMcpToolsOfServer,
  liveDiscoverMcpTools,
  type McpLiveTool,
  type McpServerItem,
  type McpToolItem,
} from "@/lib/api/admin/mcp";

export interface ToolTableProps {
  server: McpServerItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ToolRow = {
  tool_name: string;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  tool_id?: number;
};

export function ToolTable({ server, open, onOpenChange }: ToolTableProps) {
  return (
    <ToolTableBody
      key={open ? `tools-${server?.id ?? "none"}` : "closed"}
      server={server}
      open={open}
      onOpenChange={onOpenChange}
    />
  );
}

function ToolTableBody({ server, open, onOpenChange }: ToolTableProps) {
  const [testTool, setTestTool] = useState<ToolRow | null>(null);

  // DB 工具列表
  const dbTools = useQuery({
    queryKey: ["admin", "mcp", "tools", server?.id] as const,
    enabled: open && Boolean(server),
    queryFn: () => listMcpToolsOfServer(server!.id, { page_size: 100 }),
    staleTime: 15_000,
  });

  // live discover（手动触发）
  const [live, setLive] = useState<McpLiveTool[] | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  async function handleLiveDiscover() {
    if (!server) return;
    setLiveLoading(true);
    setLiveError(null);
    try {
      const res = await liveDiscoverMcpTools(server.id);
      if (!res.ok) {
        setLiveError(res.reason || "discover-live 返回异常");
        setLive(null);
        return;
      }
      setLive(res.tools);
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : "discover-live 失败");
      setLive(null);
    } finally {
      setLiveLoading(false);
    }
  }

  if (!server) return null;

  const dbRows: ToolRow[] = (dbTools.data?.items ?? []).map((t: McpToolItem) => ({
    tool_name: t.tool_name,
    display_name: t.display_name,
    description: t.description,
    input_schema: t.input_schema ?? {},
    tool_id: t.id,
  }));
  const liveRows: ToolRow[] = (live ?? []).map((t) => ({
    tool_name: t.tool_name,
    display_name: t.display_name || t.tool_name,
    description: t.description,
    input_schema: t.input_schema ?? {},
  }));

  const rows = live ? liveRows : dbRows;
  const sourceLabel = live ? "Live Discover（直连不落库）" : `DB 工具（${dbTools.data?.total ?? 0} 个）`;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              工具列表 · {server.display_name}{" "}
              <span className="ml-1 font-mono text-xs text-slate-600">#{server.server_code}</span>
            </DialogTitle>
          </DialogHeader>

          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => dbTools.refetch()} data-testid="tools-db-refresh">
              <RefreshCw className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 刷新 DB 列表
            </Button>
            <Button size="sm" onClick={handleLiveDiscover} disabled={liveLoading} data-testid="tools-discover-live">
              <Wrench className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              {liveLoading ? "Discover 中…" : "实时 Discover"}
            </Button>
            {live && (
              <Button size="sm" variant="ghost" onClick={() => setLive(null)} data-testid="tools-back-db">
                返回 DB 列表
              </Button>
            )}
            <span className="ml-auto text-[12px] text-slate-600" data-testid="tools-source">{sourceLabel}</span>
          </div>

          {liveError && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700" data-testid="tools-live-error">
              {liveError}
            </div>
          )}

          {liveLoading ? (
            <LoadingState label="正在直连 Server 获取 tools/list…" />
          ) : dbTools.isLoading && !live ? (
            <LoadingState label="加载工具…" />
          ) : dbTools.isError && !live ? (
            <ErrorState
              message={dbTools.error instanceof Error ? dbTools.error.message : "工具加载失败"}
              onRetry={() => dbTools.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              message={live ? "Server 返回空 tools/list" : "该 Server 暂无 DB 工具"}
              hint={live ? "请检查 Server 配置" : "点击「实时 Discover」直连获取，或先注册/发现工具"}
            />
          ) : (
            <div className="max-h-[360px] overflow-y-auto rounded-xl border border-slate-200">
              <table className="w-full text-sm" data-testid="tool-table">
                <caption className="sr-only">MCP 工具列表（工具名 / 描述参数 / 操作）</caption>
                <thead className="sticky top-0 z-10">
                  <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
                    <th scope="col" className="px-3 py-2.5 font-medium">工具名</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">描述 / 参数</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((t) => (
                    <tr key={`${sourceLabel}-${t.tool_name}`} className="hover:bg-slate-50/60" data-testid="tool-row">
                      <td className="whitespace-nowrap px-3 py-2.5">
                        <div className="font-medium text-slate-800">{t.tool_name}</div>
                        <div className="text-[11px] text-slate-600">{t.display_name}</div>
                      </td>
                      <td className="max-w-[360px] px-3 py-2.5">
                        <div className="truncate text-[13px] text-slate-600" title={t.description}>
                          {t.description || "—"}
                        </div>
                        <div className="font-mono text-[11px] text-slate-600">
                          {Object.keys(t.input_schema?.properties ?? {}).join(", ") || "无参数"}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex justify-end">
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid={`test-${t.tool_name}`}
                            onClick={() => setTestTool(t)}
                          >
                            <Beaker className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 测试
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ToolTestDialog
        server={server}
        tool={testTool}
        open={Boolean(testTool)}
        onOpenChange={(o) => !o && setTestTool(null)}
      />
    </>
  );
}
