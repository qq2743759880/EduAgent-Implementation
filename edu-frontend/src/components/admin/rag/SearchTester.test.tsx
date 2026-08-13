/**
 * SearchTester 单测（task04 验收：检索面板展示 docs + degraded）
 *  - 输入 query → 提交 POST /api/admin/rag/search
 *  - 结果渲染 docs（content/source_file/score）+ degraded_reason 提示
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { SearchTester } from "./SearchTester";
import type { RagPreset } from "@/lib/api/admin/rag";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockPost = vi.mocked(api.post);

const PRESETS: RagPreset[] = [
  { id: 1, preset_name: "平衡-default", is_default: true, top_k: 20, final_max_k: 6, cutoff_drop_ratio: 0.4, rrf_k: 60, use_hyde: true, enable_graph: true, llm_model_pref: "fast", created_at: "", updated_at: "" },
];

function renderTester() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SearchTester presets={PRESETS} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("SearchTester", () => {
  it("提交检索：POST /api/admin/rag/search body {query, top_k, final_max_k}", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        docs: [{ doc_id: "1", score: 0.36, content: "勾股定理推导", source_file: "题目资料.md", content_type: "question" }],
        graph_entities: [],
        retrieved_count: 1,
        final_count: 1,
        rewrite_query: null,
        degraded_reason: null,
        applied_preset_name: null,
      },
    });
    renderTester();
    const query = screen.getByTestId("search-query");
    fireEvent.change(query, { target: { value: "勾股定理" } });
    fireEvent.click(screen.getByTestId("search-run"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/search", {
        query: "勾股定理",
        preset_id: undefined,
        top_k: 20,
        final_max_k: 8,
      });
    });
    await waitFor(() => {
      expect(screen.getByText("勾股定理推导")).toBeInTheDocument();
      expect(screen.getByText("题目资料.md")).toBeInTheDocument();
    });
    // 召回/最终计数展示（文本被 <b> 分割，用正则）
    expect(screen.getByText(/召回/)).toBeInTheDocument();
  });

  it("degraded_reason 非空时渲染降级提示", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        docs: [],
        graph_entities: [],
        retrieved_count: 0,
        final_count: 0,
        rewrite_query: null,
        degraded_reason: "MILVUS_UNAVAILABLE",
        applied_preset_name: null,
      },
    });
    renderTester();
    fireEvent.change(screen.getByTestId("search-query"), { target: { value: "q" } });
    fireEvent.click(screen.getByTestId("search-run"));
    await waitFor(() => {
      expect(screen.getByTestId("search-degraded")).toHaveTextContent("MILVUS_UNAVAILABLE");
    });
  });

  it("query 为空时禁用提交按钮", () => {
    renderTester();
    expect(screen.getByTestId("search-run")).toBeDisabled();
  });
});
