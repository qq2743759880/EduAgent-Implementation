/**
 * ServerTable 单测（task04 验收：Server 列表健康灯）
 *  - 渲染健康灯（last_health_ok=1 → OK；0 → ERR；null → 未知）
 *  - 「发现工具」打开 ToolTable 弹窗
 *  - 注销 DELETE /servers/{id}
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { ServerTable } from "./ServerTable";
import type { McpServerItem } from "@/lib/api/admin/mcp";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockDelete = vi.mocked(api.delete);
const mockGet = vi.mocked(api.get);

const SERVERS: McpServerItem[] = [
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
  {
    id: 2,
    server_code: "sse-demo",
    display_name: "SSE 演示",
    description: "",
    provider: "self",
    transport: "sse",
    enabled: 0,
    yn: 1,
    created_by: 1,
    created_at: "2026-08-09T16:35:35",
    updated_at: "2026-08-09T16:36:36",
    last_health_at: "2026-08-09T16:36:36",
    last_health_ok: 0,
    last_error: "httpx fail: All connection attempts failed",
    tool_count: 0,
  },
];

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ServerTable servers={SERVERS} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("ServerTable", () => {
  it("渲染 Server 行 + 健康灯（OK 绿 / ERR 红）", () => {
    renderTable();
    expect(screen.getByTestId("mcp-server-table")).toBeInTheDocument();
    expect(screen.getAllByTestId("mcp-server-row")).toHaveLength(2);
    const dots = screen.getAllByTestId("health-dot");
    expect(dots[0]).toHaveTextContent("OK");
    expect(dots[1]).toHaveTextContent("ERR");
    expect(screen.getByText("Stdio 工具演示")).toBeInTheDocument();
  });

  it("已停用 Server 显示停用徽章 + 错误信息", () => {
    renderTable();
    expect(screen.getByTestId("server-enabled-2")).toHaveTextContent("已停用");
    expect(screen.getByText("httpx fail: All connection attempts failed")).toBeInTheDocument();
  });

  it("点击「发现工具」→ 拉取 DB 工具列表并打开弹窗", async () => {
    mockGet.mockResolvedValueOnce({
      data: { total: 1, page: 1, page_size: 20, items: [{ id: 2, server_id: 1, tool_name: "add", display_name: "整数加法", description: "a+b", input_schema: { type: "object", properties: {} }, category: "data", yn: 1, discovered_at: "" }] },
    });
    renderTable();
    fireEvent.click(screen.getByTestId("tools-1"));
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/api/mcp/servers/1/tools", {
        params: { page: 1, page_size: 100 },
      });
    });
    await waitFor(() => {
      expect(screen.getByText("add")).toBeInTheDocument();
    });
  });

  it("注销 Server：DELETE /servers/{id}", async () => {
    mockDelete.mockResolvedValueOnce({ data: { ok: true, server_id: 2, deleted: true } });
    renderTable();
    fireEvent.click(screen.getByTestId("delete-server-2"));
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/mcp/servers/2");
    });
  });
});
