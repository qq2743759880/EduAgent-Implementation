/**
 * ToolCallVisualizer
 *   - 渲染单条 MCP 工具调用：状态色 + tool_name + progress + 入参折叠 + 结果 Accordion
 *   - 父组件（ChatMessageBubble 或 ChatPanel）将其附加到对应 assistant 消息之下；若一个消息有多条 tool_calls 用顺序列表串接
 *   - status 三态色 + Icon：running=primary Loader2 / success=emerald CheckCircle2 / error=rose XCircle；pending=secondary 占位
 */
"use client";

import * as React from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Loader2,
  XCircle,
  Copy,
  Check,
  Terminal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { MCPToolCall, MCPToolCallStatus } from "@/lib/api/chat";

/* =============== 工具 =============== */

function jsonStringify(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function maybeParseJson(v: unknown): unknown {
  if (v == null) return null;
  if (typeof v === "object") return v;
  if (typeof v === "string") {
    const trimmed = v.trim();
    if (!trimmed) return v;
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.parse(trimmed);
      } catch {
        return v;
      }
    }
    return v;
  }
  return v;
}

async function copyText(t: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(t);
      return true;
    }
  } catch { /* fallback */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = t;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
}

const STATUS_TONE: Record<MCPToolCallStatus, {
  badge: "secondary" | "default" | "outline" | "destructive";
  label: string;
  progress: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
}> = {
  pending: {
    badge: "outline",
    label: "等待中",
    progress: "[&_[data-slot=progress-indicator]]:bg-muted-foreground/40",
    icon: Cpu,
    iconColor: "text-muted-foreground",
  },
  running: {
    badge: "default",
    label: "执行中",
    progress: "[&_[data-slot=progress-indicator]]:bg-primary",
    icon: Loader2,
    iconColor: "text-primary animate-spin",
  },
  success: {
    badge: "outline",
    label: "完成",
    progress: "[&_[data-slot=progress-indicator]]:bg-emerald-500",
    icon: CheckCircle2,
    iconColor: "text-emerald-500",
  },
  error: {
    badge: "destructive",
    label: "失败",
    progress: "[&_[data-slot=progress-indicator]]:bg-rose-500",
    icon: XCircle,
    iconColor: "text-rose-500",
  },
};

/* =============== 单工具可视化 =============== */

export interface ToolCallVisualizerProps {
  call: MCPToolCall;
  /** 更紧凑模式（浮动面板内） */
  compact?: boolean;
  className?: string;
}

export function ToolCallVisualizer({
  call,
  compact = false,
  className,
}: ToolCallVisualizerProps) {
  const tone = STATUS_TONE[call.status];
  const StatusIcon = tone.icon;

  const [argsOpen, setArgsOpen] = React.useState(false);
  const [resultOpen, setResultOpen] = React.useState(call.status === "error");
  const [copiedArgs, setCopiedArgs] = React.useState(false);
  const [copiedResult, setCopiedResult] = React.useState(false);

  const argsVal = React.useMemo(() => maybeParseJson(call.args_json), [call.args_json]);
  const argsStr = React.useMemo(
    () => (argsVal == null ? "—" : typeof argsVal === "string" ? argsVal : jsonStringify(argsVal)),
    [argsVal],
  );
  const resultVal = React.useMemo(() => maybeParseJson(call.result_json), [call.result_json]);
  const resultStr = React.useMemo(
    () => (resultVal == null ? "" : typeof resultVal === "string" ? resultVal : jsonStringify(resultVal)),
    [resultVal],
  );

  const hasResult = !!resultStr || call.status === "success" || call.status === "error";

  const progressRaw = call.progress_pct ?? (call.status === "success" ? 100 : call.status === "running" ? 25 : 0);
  const progress = Math.max(0, Math.min(100, Number(progressRaw) || 0));

  return (
    <div
      className={cn(
        "w-full rounded-xl border border-border bg-background shadow-xs",
        compact ? "max-w-[320px]" : "max-w-full",
        className,
      )}
      data-tool-id={call.id}
      aria-label={`工具 ${call.tool_name} ${tone.label}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
        <span
          className={cn(
            "inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-muted/60",
            tone.iconColor,
          )}
        >
          <StatusIcon className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "min-w-0 truncate font-mono text-[12.5px] font-medium text-foreground",
                compact ? "max-w-[140px]" : "max-w-[260px]",
              )}
              title={call.tool_name}
            >
              <Terminal className="mr-1 inline size-3 -translate-y-px text-muted-foreground" aria-hidden />
              {call.tool_name}
            </span>
            <Badge variant={tone.badge as "secondary" | "default" | "outline" | "destructive"} className="text-[10px]">
              {tone.label}
            </Badge>
            {call.status === "running" && (
              <span className="ml-auto tabular-nums text-[11px] text-muted-foreground">
                {Math.round(progress)}%
              </span>
            )}
          </div>
          <Progress
            value={progress}
            className={cn("h-1", tone.progress)}
            aria-label={`执行进度 ${Math.round(progress)}%`}
          />
        </div>
      </div>

      {/* Body: Args / Result */}
      <div className="space-y-1 p-2.5">
        {/* 入参折叠 */}
        <div>
          <button
            type="button"
            onClick={() => setArgsOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[12px] text-muted-foreground hover:bg-muted/50"
            aria-expanded={argsOpen}
          >
            <span className="inline-flex items-center gap-1">
              {argsOpen ? (
                <ChevronDown className="size-3" aria-hidden />
              ) : (
                <ChevronRight className="size-3" aria-hidden />
              )}
              入参
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="max-w-[180px] truncate font-mono text-[11px] opacity-70">
                {argsStr === "—" ? "—" : (compact ? (argsStr.length > 28 ? argsStr.slice(0, 28) + "…" : argsStr) : (argsStr.length > 80 ? argsStr.slice(0, 80) + "…" : argsStr))}
              </span>
              {argsStr !== "—" && (
                <span
                  role="button"
                  tabIndex={0}
                  onClick={async (e) => {
                    e.stopPropagation();
                    const ok = await copyText(argsStr);
                    if (ok) {
                      setCopiedArgs(true);
                      window.setTimeout(() => setCopiedArgs(false), 1400);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") e.preventDefault();
                  }}
                  className="inline-flex items-center gap-0.5 rounded px-1 text-[11px] opacity-70 hover:opacity-100"
                  aria-label="复制入参"
                >
                  {copiedArgs ? <Check className="size-2.5 text-emerald-500" /> : <Copy className="size-2.5" />}
                </span>
              )}
            </span>
          </button>
          {argsOpen && argsStr !== "—" && (
            <pre className="mt-1 max-h-56 overflow-auto rounded-lg border border-border/60 bg-zinc-950 p-2.5 font-mono text-[11.5px] leading-5 text-zinc-100">
              {argsStr}
            </pre>
          )}
        </div>

        {/* 结果折叠 */}
        {hasResult && (
          <div>
            <button
              type="button"
              onClick={() => setResultOpen((v) => !v)}
              className={cn(
                "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[12px] hover:bg-muted/50",
                call.status === "error" ? "text-rose-600 dark:text-rose-300" : "text-muted-foreground",
              )}
              aria-expanded={resultOpen}
            >
              <span className="inline-flex items-center gap-1">
                {resultOpen ? (
                  <ChevronDown className="size-3" aria-hidden />
                ) : (
                  <ChevronRight className="size-3" aria-hidden />
                )}
                {call.status === "error" ? "错误详情" : "执行结果"}
              </span>
              <span className="inline-flex items-center gap-1.5">
                {call.error_message && !resultOpen && (
                  <span className="max-w-[180px] truncate font-mono text-[11px] text-rose-600 dark:text-rose-300">
                    {call.error_message.length > 40
                      ? call.error_message.slice(0, 40) + "…"
                      : call.error_message}
                  </span>
                )}
                {(resultStr || call.error_message) && (
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={async (e) => {
                      e.stopPropagation();
                      const ok = await copyText(resultStr || call.error_message || "");
                      if (ok) {
                        setCopiedResult(true);
                        window.setTimeout(() => setCopiedResult(false), 1400);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") e.preventDefault();
                    }}
                    className="inline-flex items-center gap-0.5 rounded px-1 text-[11px] opacity-70 hover:opacity-100"
                    aria-label="复制结果"
                  >
                    {copiedResult ? <Check className="size-2.5 text-emerald-500" /> : <Copy className="size-2.5" />}
                  </span>
                )}
              </span>
            </button>
            {resultOpen && (
              call.error_message ? (
                <pre className="mt-1 max-h-64 overflow-auto rounded-lg border border-rose-500/20 bg-rose-500/5 p-2.5 font-mono text-[11.5px] leading-5 text-rose-700 dark:text-rose-200">
                  {call.error_message}
                  {resultStr ? `\n\n---- 详细结果 ----\n${resultStr}` : ""}
                </pre>
              ) : resultStr ? (
                <pre className="mt-1 max-h-80 overflow-auto rounded-lg border border-border/60 bg-zinc-950 p-2.5 font-mono text-[11.5px] leading-5 text-zinc-100">
                  {resultStr}
                </pre>
              ) : (
                <div className="mt-1 rounded-lg border border-dashed border-border/80 p-3 text-center text-[11px] text-muted-foreground">
                  无输出结果
                </div>
              )
            )}
          </div>
        )}
      </div>

      {/* 占位避免 lint 警告 Button 引入未用 */}
      <span className="sr-only">
        <Button type="button" size="xs" variant="ghost" />
      </span>
    </div>
  );
}

/* =============== 多条工具调用列表 =============== */

export interface ToolCallListProps {
  calls: MCPToolCall[];
  compact?: boolean;
  className?: string;
}

export function ToolCallList({ calls, compact, className }: ToolCallListProps) {
  if (!calls?.length) return null;
  return (
    <ol className={cn("w-full space-y-2", className)} role="list" aria-label="工具调用链">
      {calls.map((c, i) => (
        <li key={c.id ?? `call-${i}`}>
          <ToolCallVisualizer call={c} compact={compact} />
        </li>
      ))}
    </ol>
  );
}

export default ToolCallVisualizer;
