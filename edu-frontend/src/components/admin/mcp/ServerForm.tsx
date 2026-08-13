/**
 * ServerForm — 新增 MCP Server 表单弹窗（task04）
 *  - 传输选择 stdio / sse：stdio 填 run_command + run_args；sse 填 base_url
 *  - server_code 唯一（后端重复 409）
 *  - import-url 输入框：data://test-stdio 或 https:// 快速导入
 *  - 写操作 useMutation（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldRow, NativeSelect } from "@/components/admin/controls";
import {
  MCP_TRANSPORT_OPTIONS,
  createMcpServer,
  importMcpServerByUrl,
  type McpServerInput,
  type McpTransportOption,
} from "@/lib/api/admin/mcp";

export interface ServerFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface ServerFormState {
  server_code: string;
  display_name: string;
  description: string;
  transport: McpTransportOption;
  run_command: string;
  run_args: string;
  base_url: string;
  enabled: boolean;
}

export function initialServerForm(): ServerFormState {
  return {
    server_code: "",
    display_name: "",
    description: "",
    transport: "stdio",
    run_command: "",
    run_args: "",
    base_url: "",
    enabled: true,
  };
}

export function ServerForm({ open, onOpenChange }: ServerFormProps) {
  return (
    <ServerFormBody key={open ? "open" : "closed"} open={open} onOpenChange={onOpenChange} />
  );
}

function ServerFormBody({ open, onOpenChange }: ServerFormProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ServerFormState>(initialServerForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [importUrl, setImportUrl] = useState("");

  const createMutation = useMutation({
    mutationFn: () => createMcpServer(buildServerPayload(form)),
    onSuccess: (res) => {
      toast.success(`Server 已注册（id=${res.id}）`);
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp", "servers"] });
      onOpenChange(false);
    },
    // 失败（含 409 重复编码）→ 全局 MutationCache onError → toast（R-7）
  });

  const importMutation = useMutation({
    mutationFn: () => importMcpServerByUrl({ url: importUrl }),
    onSuccess: (res) => {
      toast.success(
        `导入成功：${res.display_name}（${res.transport}${res.discovered_tool_count ? `，发现 ${res.discovered_tool_count} 个工具` : ""}）`,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp", "servers"] });
      onOpenChange(false);
    },
    // 失败 → 全局 toast（R-7）
  });

  function patch<K extends keyof ServerFormState>(key: K, value: ServerFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: "" }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = validateServerForm(form);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    createMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新增 MCP Server</DialogTitle>
        </DialogHeader>

        {/* import-url 快速导入 */}
        <div className="space-y-2 rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
          <label htmlFor="server-import-url" className="block text-[12px] font-medium text-indigo-700">一键导入（import-url）</label>
          <div className="flex gap-2">
            <Input
              id="server-import-url"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="data://test-stdio 或 https://host/mcp"
              className="h-8 flex-1"
              data-testid="import-url"
            />
            <Button
              size="sm"
              variant="outline"
              disabled={importMutation.isPending || !importUrl.trim()}
              onClick={() => importMutation.mutate()}
              data-testid="import-url-submit"
            >
              {importMutation.isPending ? "导入中…" : "导入"}
            </Button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <FieldRow label="传输类型" required>
            <NativeSelect
              id="transport-select"
              value={form.transport}
              onChange={(e) => patch("transport", e.target.value as McpTransportOption)}
              data-testid="transport-select"
            >
              {MCP_TRANSPORT_OPTIONS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </NativeSelect>
          </FieldRow>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FieldRow label="Server 编码" required error={errors.server_code}
              hint="英文 URL-safe，2-64 字符，唯一">
              <Input
                id="server-code"
                value={form.server_code}
                onChange={(e) => patch("server_code", e.target.value)}
                placeholder="如 my-local-tools"
                aria-invalid={Boolean(errors.server_code)}
                aria-describedby={errors.server_code ? "server-code-error-desc" : undefined}
                data-testid="server-code"
              />
              {errors.server_code && (
                <span id="server-code-error-desc" className="sr-only">{errors.server_code}</span>
              )}
            </FieldRow>
            <FieldRow label="显示名称" required error={errors.display_name}>
              <Input
                id="server-display-name"
                value={form.display_name}
                onChange={(e) => patch("display_name", e.target.value)}
                placeholder="如 本地工具演示"
                aria-invalid={Boolean(errors.display_name)}
                aria-describedby={errors.display_name ? "server-display-name-error-desc" : undefined}
              />
              {errors.display_name && (
                <span id="server-display-name-error-desc" className="sr-only">{errors.display_name}</span>
              )}
            </FieldRow>
          </div>

          {form.transport === "stdio" ? (
            <>
              <FieldRow label="启动命令 run_command" required error={errors.run_command}
                hint="如 python / npx">
                <Input
                  id="run-command"
                  value={form.run_command}
                  onChange={(e) => patch("run_command", e.target.value)}
                  placeholder="python"
                  aria-invalid={Boolean(errors.run_command)}
                  aria-describedby={errors.run_command ? "run-command-error-desc" : undefined}
                  data-testid="run-command"
                />
                {errors.run_command && (
                  <span id="run-command-error-desc" className="sr-only">{errors.run_command}</span>
                )}
              </FieldRow>
              <FieldRow label="参数 run_args" hint={'JSON 数组，如 ["-u","/path/demo.py"]'}>
                <Input
                  id="run-args"
                  value={form.run_args}
                  onChange={(e) => patch("run_args", e.target.value)}
                  placeholder='["-u","p8_stdio_demo_server.py"]'
                />
              </FieldRow>
            </>
          ) : (
            <FieldRow label="SSE URL" required error={errors.base_url}>
              <Input
                id="base-url"
                value={form.base_url}
                onChange={(e) => patch("base_url", e.target.value)}
                placeholder="https://host/mcp"
                aria-invalid={Boolean(errors.base_url)}
                aria-describedby={errors.base_url ? "base-url-error-desc" : undefined}
                data-testid="base-url"
              />
              {errors.base_url && (
                <span id="base-url-error-desc" className="sr-only">{errors.base_url}</span>
              )}
            </FieldRow>
          )}

          <FieldRow label="描述">
            <Textarea
              id="server-description"
              value={form.description}
              onChange={(e) => patch("description", e.target.value)}
              placeholder="Server 用途说明（选填）"
              rows={2}
            />
          </FieldRow>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={createMutation.isPending} data-testid="server-submit">
              {createMutation.isPending ? "注册中…" : "注册 Server"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 纯函数（可单测） ---------------- */

export function buildServerPayload(form: ServerFormState): McpServerInput {
  const base: McpServerInput = {
    server_code: form.server_code.trim(),
    display_name: form.display_name.trim(),
    description: form.description.trim() || undefined,
    transport: form.transport,
    enabled: form.enabled ? 1 : 0,
  };
  if (form.transport === "stdio") {
    base.run_command = form.run_command.trim();
    if (form.run_args.trim()) {
      try {
        const parsed = JSON.parse(form.run_args.trim());
        base.run_args = Array.isArray(parsed) ? parsed.map(String) : [form.run_args.trim()];
      } catch {
        base.run_args = form.run_args.trim().split(/\s+/);
      }
    }
  } else {
    base.base_url = form.base_url.trim();
  }
  return base;
}

export function validateServerForm(form: ServerFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  const code = form.server_code.trim();
  if (!code) errors.server_code = "请输入 Server 编码";
  else if (code.length < 2 || code.length > 64) errors.server_code = "编码 2-64 字符";
  else if (!/^[A-Za-z0-9_\-]+$/.test(code)) errors.server_code = "仅允许字母/数字/下划线/连字符";
  if (!form.display_name.trim()) errors.display_name = "请输入显示名称";
  if (form.transport === "stdio" && !form.run_command.trim()) errors.run_command = "stdio 必须提供启动命令";
  if (form.transport === "sse" && !form.base_url.trim()) errors.base_url = "SSE 必须提供 base_url";
  return errors;
}
