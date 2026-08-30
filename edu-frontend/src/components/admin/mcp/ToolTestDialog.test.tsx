/**
 * ToolTestDialog 单测（task04 验收：工具测试展示 status/result/latency_ms）
 *  - 依据 input_schema 预填参数默认值（buildDefaultArgs）
 *  - 提交 POST /api/mcp/tools/test body {tool_id, args}
 *  - 结果区展示 status / latency / result JSON
 *  - 非法 JSON 不发起请求
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http } from "@/lib/api-client";
import { ToolTestDialog, buildDefaultArgs } from "./ToolTestDialog";
import type { McpServerItem } from "@/lib/api/admin/mcp";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockPost = vi.mocked(http.post);

const SERVER: McpServerItem = {
  id: 1,
  server_code: "stdio-echodemo",
  display_name: "Stdio 工具演示",
  description: "",
  provider: "self",
  transport: "stdio",
  enabled: 1,
  yn: 1,
  created_by: 1,
  created_at: "",
  updated_at: "",
  last_health_at: null,
  last_health_ok: 1,
  last_error: null,
  tool_count: 4,
};

const TOOL = {
  tool_name: "add",
  display_name: "整数加法",
  tool_id: 2,
  input_schema: {
    type: "object",
    properties: {
      a: { type: "integer" },
      b: { type: "integer" },
      flag: { type: "boolean" },
      text: { type: "string" },
    },
    required: ["a", "b"],
  },
};

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToolTestDialog server={SERVER} tool={TOOL} open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("buildDefaultArgs", () => {
  it("按 schema 类型生成默认值", () => {
    const args = buildDefaultArgs(TOOL.input_schema);
    expect(args).toEqual({ a: 0, b: 0, flag: false, text: "" });
  });

  it("无 properties 返回空对象", () => {
    expect(buildDefaultArgs({ type: "object" })).toEqual({});
  });
});

describe("ToolTestDialog", () => {
  it("预填参数 JSON 并展示 schema 参数名", () => {
    renderDialog();
    const args = screen.getByTestId("tool-args") as HTMLTextAreaElement;
    expect(JSON.parse(args.value)).toEqual({ a: 0, b: 0, flag: false, text: "" });
  }, 20_000);

  it("提交调用：POST /api/mcp/tools/test body {tool_id, args} → 展示 status/latency/result", async () => {
    mockPost.mockResolvedValueOnce({
      status: "SUCCESS",
      result: { sum: 3, was_negative: false },
      error_message: null,
      latency_ms: 94,
      call_id: "mcp-1",
      server_id: 1,
      tool_name: "add",
      content_text: '{"sum": 3, "was_negative": false}',
    });
    renderDialog();
    fireEvent.click(screen.getByTestId("tool-test-run"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/mcp/tools/test", {
        tool_id: 2,
        tool_name: "add",
        args: { a: 0, b: 0, flag: false, text: "" },
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("tool-test-status")).toHaveTextContent("成功");
      expect(screen.getByTestId("tool-test-latency")).toHaveTextContent("94ms");
      expect(screen.getByTestId("tool-test-result-json")).toHaveTextContent("was_negative");
    });
  });

  it("错误返回 ERROR 时展示 error_message", async () => {
    mockPost.mockResolvedValueOnce({
      status: "ERROR",
      result: null,
      error_message: "tools/call JSON-RPC err: boom",
      latency_ms: 120,
      call_id: "mcp-2",
      server_id: 1,
      tool_name: "add",
      content_text: null,
    });
    renderDialog();
    fireEvent.click(screen.getByTestId("tool-test-run"));
    await waitFor(() => {
      expect(screen.getByTestId("tool-test-status")).toHaveTextContent("失败");
      expect(screen.getByTestId("tool-test-error")).toHaveTextContent("boom");
    });
  });

  it("非法 JSON 不发起请求并提示解析错误", () => {
    renderDialog();
    const args = screen.getByTestId("tool-args");
    fireEvent.change(args, { target: { value: "{ not json" } });
    fireEvent.click(screen.getByTestId("tool-test-run"));
    expect(mockPost).not.toHaveBeenCalled();
  });
});
