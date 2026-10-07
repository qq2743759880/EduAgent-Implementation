/**
 * ToolTestDialog — MCP 工具测试弹窗（task04）
 *  - 参数 JSON 编辑（预填 input_schema 默认值）→ POST /api/mcp/tools/test {tool_id?, args}
 *  - 结果展示：status（SUCCESS/ERROR/TIMEOUT/SKIPPED 徽章）+ result（JSON 树）+ latency_ms
 *  - 写操作 useMutation（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldRow } from "@/components/admin/controls";
import {
  mcpCallStatusLabel,
  testMcpTool,
  type McpServerItem,
  type McpToolTestResult,
} from "@/lib/api/admin/mcp";
import { cn } from "@/lib/utils";

export interface ToolTestDialogProps {
  server: McpServerItem | null;
  tool: {
    tool_name: string;
    display_name?: string;
    input_schema: Record<string, unknown>;
    tool_id?: number;
  } | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** 依据 JSON Schema 生成参数默认值（integer→0 / number→0.5 / boolean→false / 其余→""） */
export function buildDefaultArgs(schema: Record<string, unknown>): Record<string, unknown> {
  const props = (schema?.properties ?? {}) as Record<string, { type?: string }>;
  const defaults: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(props)) {
    if (!prop || typeof prop !== "object") continue;
    switch (prop.type) {
      case "integer":
      case "number":
        defaults[key] = 0;
        break;
      case "boolean":
        defaults[key] = false;
        break;
      default:
        defaults[key] = "";
    }
  }
  return defaults;
}

export function ToolTestDialog({ server, tool, open, onOpenChange }: ToolTestDialogProps) {
  return (
    <ToolTestBody
      key={open ? `test-${tool?.tool_name ?? "none"}` : "closed"}
      server={server}
      tool={tool}
      open={open}
      onOpenChange={onOpenChange}
    />
  );
}

function ToolTestBody({ server, tool, open, onOpenChange }: ToolTestDialogProps) {
  const queryClient = useQueryClient();
  const defaultArgs = useMemo(() => buildDefaultArgs(tool?.input_schema ?? {}), [tool?.input_schema]);
  const [argsText, setArgsText] = useState(() => JSON.stringify(defaultArgs, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [result, setResult] = useState<McpToolTestResult | null>(null);

  const testMutation = useMutation({
    mutationFn: () => {
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(argsText || "{}");
      } catch (err) {
        throw new Error(`参数 JSON 解析失败：${err instanceof Error ? err.message : String(err)}`);
      }
      return testMcpTool({
        tool_id: tool?.tool_id,
        server_id: tool?.tool_id ? undefined : server?.id,
        tool_name: tool?.tool_name,
        args,
      });
    },
    onSuccess: (res) => {
      setResult(res);
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp", "call-log"] });
    },
    onError: () => {
      // JSON 解析失败在 mutationFn 里 throw，走全局 toast；这里同时清结果
      setResult(null);
    },
    // 写操作失败：全局 MutationCache onError → toast（R-7）
  });

  if (!server || !tool) return null;

  function handleRun() {
    try {
      JSON.parse(argsText || "{}");
      setJsonError(null);
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : "JSON 解析失败");
      return;
    }
    setResult(null);
    testMutation.mutate();
  }

  const statusTone: Record<string, string> = {
    SUCCESS: "bg-emerald-100 text-emerald-700",
    ERROR: "bg-rose-100 text-rose-700",
    // HIGH-04：TIMEOUT 徽章 text-amber-700 on bg-amber-100 ≈4.43:1 < 4.5（临界）→ 加深为 amber-800
    TIMEOUT: "bg-amber-100 text-amber-800",
    SKIPPED: "bg-slate-100 text-slate-600",
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            测试工具 · {tool.tool_name}
            <span className="ml-2 font-mono text-xs text-slate-600">{server.server_code}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <FieldRow label="参数 args（JSON）" error={jsonError ?? undefined}
            hint={tool.tool_id ? `tool_id=${tool.tool_id} · POST /api/mcp/tools/test` : "live discover 工具按 server_id + tool_name 调用"}>
            <textarea
              id="tool-args"
              value={argsText}
              onChange={(e) => { setArgsText(e.target.value); setJsonError(null); }}
              rows={4}
              aria-invalid={Boolean(jsonError)}
              aria-describedby={jsonError ? "tool-args-error-desc" : undefined}
              className={cn(
                "w-full rounded-lg border border-input bg-transparent px-2.5 py-2 font-mono text-[12px]",
                "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 outline-none",
                jsonError ? "border-rose-400" : "",
              )}
              data-testid="tool-args"
            />
            {jsonError && (
              <span id="tool-args-error-desc" className="sr-only">{jsonError}</span>
            )}
          </FieldRow>

          {result && (
            <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/60 p-3" data-testid="tool-test-result" role="status" aria-live="polite">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn("border-transparent", statusTone[result.status] ?? "bg-slate-100 text-slate-600")}
                  data-testid="tool-test-status"
                >
                  {mcpCallStatusLabel(result.status)}
                </Badge>
                <span className="text-[13px] text-slate-600" data-testid="tool-test-latency">
                  延迟 <b className="font-mono">{result.latency_ms}ms</b>
                </span>
                <span className="font-mono text-[11px] text-slate-600">call_id={result.call_id}</span>
              </div>

              {result.error_message && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-700" data-testid="tool-test-error">
                  {result.error_message}
                </div>
              )}

              <div>
                <div className="mb-1 text-[12px] font-medium text-slate-500">result</div>
                <pre className="max-h-40 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[12px] leading-relaxed text-emerald-100" data-testid="tool-test-result-json">
                  {result.result === undefined || result.result === null
                    ? "(空)"
                    : typeof result.result === "string"
                      ? result.result
                      : JSON.stringify(result.result, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          <Button type="button" disabled={testMutation.isPending} onClick={handleRun} data-testid="tool-test-run">
            {testMutation.isPending ? "调用中…" : "▶ 调用工具"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
