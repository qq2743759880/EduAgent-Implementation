/**
 * lib/api/admin/mcp.ts 单测（task04 / task40 拦截器解包迁移）
 * 验证：servers 列表、创建 Server body（stdio/sse 字段）、import-url、tools 列表、
 * 工具测试路径 POST /api/mcp/tools/test（body args dict）、call-log 过滤、健康灯辅助
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  createMcpServer,
  deleteMcpServer,
  importMcpServerByUrl,
  listMcpCallLog,
  listMcpServers,
  listMcpToolsOfServer,
  liveDiscoverMcpTools,
  mcpCallStatusLabel,
  mcpHealthTone,
  scanMcpServersHealth,
  testMcpTool,
} from "./mcp";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);
const mockDelete = vi.mocked(http.delete);

beforeEach(() => vi.clearAllMocks());

describe("Server 列表", () => {
  it("GET /api/mcp/servers 分页 + 健康字段透传", async () => {
    mockGet.mockResolvedValueOnce({
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          id: 1,
          server_code: "stdio-echodemo",
          display_name: "Stdio 工具演示",
          description: "",
          provider: "self",
          transport: "stdio",
          enabled: 1,
          yn: 1,
          created_by: 1,
          created_at: "2026-08-09T16:35:35",
          updated_at: "2026-08-09T16:36:34",
          last_health_at: "2026-08-09T16:36:34",
          last_health_ok: 1,
          last_error: null,
          tool_count: 4,
        },
      ],
    });
    const res = await listMcpServers({ page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/mcp/servers", {
      params: { page: 1, page_size: 20 },
    });
    expect(res.items[0].last_health_ok).toBe(1);
    expect(res.items[0].tool_count).toBe(4);
  });

  it("keyword/transport/enabled 过滤透传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listMcpServers({ transport: "sse", enabled: 0, keyword: "demo" });
    expect(mockGet).toHaveBeenCalledWith("/api/mcp/servers", {
      params: { page: 1, page_size: 20, transport: "sse", enabled: 0, keyword: "demo" },
    });
  });
});

describe("创建 Server", () => {
  it("stdio body：run_command + run_args", async () => {
    mockPost.mockResolvedValueOnce({ id: 9 });
    await createMcpServer({
      server_code: "my-tools",
      display_name: "我的工具",
      transport: "stdio",
      run_command: "python",
      run_args: ["-u", "demo.py"],
      enabled: 1,
    });
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/servers", {
      server_code: "my-tools",
      display_name: "我的工具",
      transport: "stdio",
      run_command: "python",
      run_args: ["-u", "demo.py"],
      enabled: 1,
    });
  });

  it("sse body：base_url", async () => {
    mockPost.mockResolvedValueOnce({ id: 10 });
    await createMcpServer({
      server_code: "sse-remote",
      display_name: "远程",
      transport: "sse",
      base_url: "https://host/mcp",
      enabled: 0,
    });
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/servers", {
      server_code: "sse-remote",
      display_name: "远程",
      transport: "sse",
      base_url: "https://host/mcp",
      enabled: 0,
    });
  });

  it("创建失败必须抛（写操作 R-7，如 409 重复编码）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(409, { code: 40900, message: "server_code 已存在" }));
    await expect(
      createMcpServer({ server_code: "dup", display_name: "d", transport: "stdio", run_command: "python" }),
    ).rejects.toMatchObject({ status: 409 });
  });
});

describe("import-url", () => {
  it("POST /servers/import-url body {url}", async () => {
    mockPost.mockResolvedValueOnce({
      imported: true, server_id: 5, server_code: "stdio-import-1", display_name: "Import", transport: "stdio", discovered_tool_count: 4, warning: null,
    });
    const res = await importMcpServerByUrl({ url: "data://test-stdio" });
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/servers/import-url", { url: "data://test-stdio" });
    expect(res.imported).toBe(true);
  });
});

describe("工具列表 / discover", () => {
  it("GET /servers/{id}/tools 分页", async () => {
    mockGet.mockResolvedValueOnce({
      total: 1, page: 1, page_size: 20, items: [{ id: 2, server_id: 1, tool_name: "add", display_name: "整数加法", description: "a+b", input_schema: { type: "object" }, category: "data", yn: 1, discovered_at: "" }],
    });
    const res = await listMcpToolsOfServer(1, { keyword: "add" });
    expect(mockGet).toHaveBeenCalledWith("/api/mcp/servers/1/tools", {
      params: { page: 1, page_size: 20, keyword: "add" },
    });
    expect(res.items[0].tool_name).toBe("add");
  });

  it("GET /servers/{id}/discover-live 直连实时快照", async () => {
    mockGet.mockResolvedValueOnce({
      server_id: 1, ok: true, tool_count: 4, tools: [{ tool_name: "ping", display_name: "ping", description: "pong", input_schema: {}, category: "" }], reason: null, latency_ms: 109,
    });
    const res = await liveDiscoverMcpTools(1);
    expect(mockGet).toHaveBeenCalledWith("/api/mcp/servers/1/discover-live", { params: undefined });
    expect(res.tools[0].tool_name).toBe("ping");
  });
});

describe("工具测试", () => {
  it("POST /api/mcp/tools/test body {tool_id, args}（args 是 dict 非字符串）", async () => {
    mockPost.mockResolvedValueOnce({
      status: "SUCCESS", result: { sum: 3, was_negative: false }, error_message: null, latency_ms: 94, call_id: "mcp-1", server_id: 1, tool_name: "add", content_text: '{"sum": 3}',
    });
    const res = await testMcpTool({ tool_id: 2, args: { a: 1, b: 2 } });
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/tools/test", {
      tool_id: 2,
      args: { a: 1, b: 2 },
    });
    expect(res.status).toBe("SUCCESS");
    expect(res.latency_ms).toBe(94);
  });

  it("无 tool_id 时按 server_id + tool_name 调用", async () => {
    mockPost.mockResolvedValueOnce({
      status: "SUCCESS", result: null, error_message: null, latency_ms: 10, call_id: "mcp-2", server_id: 1, tool_name: "ping", content_text: null,
    });
    await testMcpTool({ server_id: 1, tool_name: "ping", args: {} });
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/tools/test", {
      server_id: 1,
      tool_name: "ping",
      args: {},
    });
  });

  it("工具测试失败必须抛（写操作 R-7）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(500, { code: 50000, message: "INTERNAL" }));
    await expect(testMcpTool({ tool_id: 2, args: {} })).rejects.toMatchObject({ status: 500 });
  });
});

describe("调用日志", () => {
  it("server_id/tool_name/status/user_id 过滤 + 分页", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 10, items: [] });
    await listMcpCallLog({ page: 1, page_size: 10, server_id: 1, tool_name: "echo", status: "SUCCESS", user_id: 830 });
    expect(mockGet).toHaveBeenCalledWith("/api/mcp/call-log", {
      params: {
        page: 1,
        page_size: 10,
        server_id: 1,
        tool_name: "echo",
        status: "SUCCESS",
        user_id: 830,
      },
    });
  });
});

describe("健康扫描 / 注销", () => {
  it("POST /health-scan 返回扫描汇总", async () => {
    mockPost.mockResolvedValueOnce({
      scanned: 3, ok_count: 2, error_count: 1, items: [], elapsed_ms: 42,
    });
    const res = await scanMcpServersHealth();
    expect(mockPost).toHaveBeenCalledWith("/api/mcp/health-scan", undefined);
    expect(res.ok_count).toBe(2);
  });

  it("DELETE /servers/{id} 软删注销", async () => {
    mockDelete.mockResolvedValueOnce({ ok: true, server_id: 3, deleted: true });
    const res = await deleteMcpServer(3);
    expect(mockDelete).toHaveBeenCalledWith("/api/mcp/servers/3");
    expect(res.deleted).toBe(true);
  });
});

describe("显示辅助", () => {
  it("mcpHealthTone：1→ok / 0→error / null→unknown", () => {
    expect(mcpHealthTone(1)).toBe("ok");
    expect(mcpHealthTone(0)).toBe("error");
    expect(mcpHealthTone(null)).toBe("unknown");
    expect(mcpHealthTone(undefined)).toBe("unknown");
  });

  it("mcpCallStatusLabel 中文映射", () => {
    expect(mcpCallStatusLabel("SUCCESS")).toBe("成功");
    expect(mcpCallStatusLabel("ERROR")).toBe("失败");
    expect(mcpCallStatusLabel("TIMEOUT")).toBe("超时");
    expect(mcpCallStatusLabel("SKIPPED")).toBe("跳过");
  });
});
