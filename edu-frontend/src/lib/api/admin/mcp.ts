/**
 * 管理端 MCP API（task04，G4 MCP 控制台）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.7 仅是摘要）：
 *  - app/mcp/router.py + schemas.py（P8 MCP 管理端）
 *
 * 与 design-guide 摘要的差异（后端代码实测，勿照抄摘要）：
 *  - 健康字段是 last_health_at + last_health_ok（0/1）+ last_error，不是摘要的 last_health_ts/status
 *  - 工具测试路径是 POST /api/mcp/tools/test（非 /tools/{tool_id}/test），body 用 {tool_id, args}，
 *    args 是 dict（非 args_json 字符串）
 *  - 新建 Server body 用 server_code/display_name/run_command/run_args/base_url（非 command/args/url）
 *  - 全部路由 require_role([ADMIN])（router 级 dependencies），student/manager 一律 403
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由 useMutation onError → toast。
 */
import { adminDelete, adminGet, adminPatch, adminPost } from "@/lib/api/admin";
import type { AdminPage } from "@/lib/admin-api-types";

/* ============================================================
 * 枚举
 * ============================================================ */
export type McpTransport = "stdio" | "sse" | "http";

export const MCP_TRANSPORT_OPTIONS = [
  { value: "stdio", label: "stdio · 本地子进程" },
  { value: "sse", label: "sse · HTTP Stream" },
] as const;
export type McpTransportOption = (typeof MCP_TRANSPORT_OPTIONS)[number]["value"];

/** 工具调用状态（ToolCallStatusEnum） */
export type McpCallStatus = "SUCCESS" | "ERROR" | "TIMEOUT" | "SKIPPED";

/* ============================================================
 * 类型（对齐后端 schemas）
 * ============================================================ */
/** MCPServerItem：Server 列表项（含健康检查结果） */
export interface McpServerItem {
  id: number;
  server_code: string;
  display_name: string;
  description: string;
  provider: string;
  transport: McpTransport | string;
  enabled: number;
  yn: number;
  created_by: number;
  created_at: string;
  updated_at: string;
  last_health_at?: string | null;
  last_health_ok?: number | null;
  last_error?: string | null;
  tool_count: number;
}

/** MCPServerCreate：注册 Server 请求体 */
export interface McpServerInput {
  server_code: string;
  display_name: string;
  description?: string;
  provider?: string;
  transport: McpTransport | string;
  run_command?: string;
  run_args?: string[];
  working_dir?: string;
  base_url?: string;
  http_headers?: Record<string, string>;
  env?: Record<string, string>;
  connect_timeout_ms?: number;
  call_timeout_ms?: number;
  enabled?: number;
}

/** MCPImportUrlReq：一键导入 */
export interface McpImportUrlInput {
  url: string;
  preset_name?: string;
  skip_health_check?: boolean;
}

/** MCPImportResp：导入结果 */
export interface McpImportResult {
  imported: boolean;
  server_id?: number | null;
  server_code: string;
  display_name: string;
  transport: string;
  discovered_tool_count: number;
  warning?: string | null;
}

/** MCPToolItem：工具列表项 */
export interface McpToolItem {
  id: number;
  server_id: number;
  server_code?: string | null;
  tool_name: string;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  category: string;
  yn: number;
  discovered_at: string;
}

/** MCPLiveToolItem：live discover 工具（不落库） */
export interface McpLiveTool {
  tool_name: string;
  display_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  category: string;
}

/** MCPLiveDiscoverResp */
export interface McpLiveDiscoverResult {
  server_id: number;
  ok: boolean;
  tool_count: number;
  tools: McpLiveTool[];
  reason?: string | null;
  latency_ms: number;
}

/** MCPToolTestReq → MCPToolTestResp */
export interface McpToolTestResult {
  status: McpCallStatus | string;
  result: unknown;
  error_message?: string | null;
  latency_ms: number;
  call_id: string;
  server_id: number;
  tool_name: string;
  content_text?: string | null;
}

/** MCPLogItem：调用日志项 */
export interface McpCallLogItem {
  id: number;
  call_id: string;
  server_id: number;
  tool_name: string;
  status: McpCallStatus | string;
  latency_ms: number;
  user_id: number;
  trace_id: string;
  error_message?: string | null;
  created_at: string;
}

/** MCPHealthScanItem */
export interface McpHealthScanItem {
  server_id: number;
  server_code: string;
  display_name: string;
  ok: boolean;
  latency_ms: number;
  reason?: string | null;
  last_health_at?: string | null;
}

/** MCPHealthScanResp */
export interface McpHealthScanResult {
  scanned: number;
  ok_count: number;
  error_count: number;
  items: McpHealthScanItem[];
  elapsed_ms: number;
}

/* ============================================================
 * 接口
 * ============================================================ */
/** Server 列表（分页 + transport/enabled/keyword 过滤） */
export async function listMcpServers(
  params: {
    page?: number;
    page_size?: number;
    transport?: string;
    enabled?: number;
    keyword?: string;
  } = {},
): Promise<AdminPage<McpServerItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.transport) query.transport = params.transport;
  if (typeof params.enabled === "number") query.enabled = params.enabled;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  return adminGet<AdminPage<McpServerItem>>("/api/mcp/servers", query);
}

/** 注册 MCP Server（stdio / sse / http） */
export async function createMcpServer(input: McpServerInput): Promise<{ id: number } & Partial<McpServerItem>> {
  return adminPost("/api/mcp/servers", input);
}

/** 更新 Server（局部修改） */
export async function updateMcpServer(
  serverId: number,
  input: Partial<McpServerInput>,
): Promise<McpServerItem> {
  return adminPatch<McpServerItem>(`/api/mcp/servers/${serverId}`, input);
}

/** 注销 Server（软删 yn=0） */
export async function deleteMcpServer(serverId: number): Promise<{ ok: boolean; server_id: number; deleted: boolean }> {
  return adminDelete(`/api/mcp/servers/${serverId}`);
}

/** 一键导入 URL（http(s):// 或 data://test-stdio） */
export async function importMcpServerByUrl(input: McpImportUrlInput): Promise<McpImportResult> {
  const body: Record<string, unknown> = { url: input.url };
  if (input.preset_name?.trim()) body.preset_name = input.preset_name.trim();
  if (typeof input.skip_health_check === "boolean") body.skip_health_check = input.skip_health_check;
  return adminPost<McpImportResult>("/api/mcp/servers/import-url", body);
}

/** 按 server 查工具列表（DB 落库工具，分页 + category/keyword 过滤） */
export async function listMcpToolsOfServer(
  serverId: number,
  params: { page?: number; page_size?: number; category?: string; keyword?: string } = {},
): Promise<AdminPage<McpToolItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.category) query.category = params.category;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  return adminGet<AdminPage<McpToolItem>>(`/api/mcp/servers/${serverId}/tools`, query);
}

/** live discover：直连 Server 取 tools/list 实时快照（不落库） */
export async function liveDiscoverMcpTools(serverId: number): Promise<McpLiveDiscoverResult> {
  return adminGet<McpLiveDiscoverResult>(`/api/mcp/servers/${serverId}/discover-live`);
}

/** 测试调用工具（tool_id 或 server_id + tool_name，body args 为 dict） */
export async function testMcpTool(
  input: { tool_id?: number; server_id?: number; tool_name?: string; args?: Record<string, unknown> },
): Promise<McpToolTestResult> {
  const body: Record<string, unknown> = {};
  if (typeof input.tool_id === "number") body.tool_id = input.tool_id;
  if (typeof input.server_id === "number") body.server_id = input.server_id;
  if (input.tool_name) body.tool_name = input.tool_name;
  body.args = input.args ?? {};
  return adminPost<McpToolTestResult>("/api/mcp/tools/test", body);
}

/** 调用日志（分页 + server_id/tool_name/status/user_id/时间过滤） */
export async function listMcpCallLog(
  params: {
    page?: number;
    page_size?: number;
    server_id?: number;
    tool_name?: string;
    status?: string;
    user_id?: number;
    created_from?: string;
    created_to?: string;
  } = {},
): Promise<AdminPage<McpCallLogItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (typeof params.server_id === "number") query.server_id = params.server_id;
  if (params.tool_name?.trim()) query.tool_name = params.tool_name.trim();
  if (params.status) query.status = params.status;
  if (typeof params.user_id === "number") query.user_id = params.user_id;
  if (params.created_from) query.created_from = params.created_from;
  if (params.created_to) query.created_to = params.created_to;
  return adminGet<AdminPage<McpCallLogItem>>("/api/mcp/call-log", query);
}

/** 批量健康扫描所有 yn=1 Server */
export async function scanMcpServersHealth(): Promise<McpHealthScanResult> {
  return adminPost<McpHealthScanResult>("/api/mcp/health-scan");
}

/* ============================================================
 * 显示辅助（纯函数）
 * ============================================================ */
export function mcpTransportLabel(t: string): string {
  return MCP_TRANSPORT_OPTIONS.find((o) => o.value === t)?.label ?? t;
}

export function mcpCallStatusLabel(s: string): string {
  switch (s) {
    case "SUCCESS": return "成功";
    case "ERROR": return "失败";
    case "TIMEOUT": return "超时";
    case "SKIPPED": return "跳过";
    default: return s;
  }
}

/** 健康灯语义：last_health_ok=1 → ok；0 → error；null → 未知 */
export function mcpHealthTone(
  lastHealthOk?: number | null,
): "ok" | "error" | "unknown" {
  if (lastHealthOk === 1) return "ok";
  if (lastHealthOk === 0) return "error";
  return "unknown";
}
