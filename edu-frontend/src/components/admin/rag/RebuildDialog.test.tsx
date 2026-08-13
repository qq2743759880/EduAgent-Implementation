/**
 * RebuildDialog 单测（task04 验收：重建返回 202 + job_id）
 *  - 打开弹窗展示分区信息
 *  - 提交 POST /collections/rebuild → 展示 job_id
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { RebuildDialog } from "./RebuildDialog";
import type { RagCollection } from "@/lib/api/admin/rag";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockPost = vi.mocked(api.post);

const COLLECTION: RagCollection = {
  id: 1,
  collection_name: "knowledge_chunk_v1",
  partition_name: "_default",
  tenant_id: null,
  display_name: "公共知识库（_default）",
  row_count: 4969,
  source_count: 0,
  last_rebuild_at: null,
  last_snapshot_at: "2026-08-12T21:16:55",
  status: "ready",
  status_message: null,
  visibility: "public",
  created_at: "2026-08-09T09:17:02",
  updated_at: "2026-08-12T21:16:55",
};

function renderDialog(open = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <RebuildDialog collection={COLLECTION} open={open} onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

beforeEach(() => vi.clearAllMocks());

describe("RebuildDialog", () => {
  it("打开后展示分区信息", () => {
    renderDialog();
    expect(screen.getByText(/重建索引/)).toBeInTheDocument();
    expect(screen.getByText(/knowledge_chunk_v1/)).toBeInTheDocument();
    expect(screen.getByText(/4,969/)).toBeInTheDocument();
  });

  it("提交重建：POST /collections/rebuild body {collection_name, partition_name, mode} → 展示 job_id", async () => {
    mockPost.mockResolvedValueOnce({
      data: { job_id: "r_abc123def456", accepted: true, message: "已接受重建", estimated_rows: 4969 },
    });
    renderDialog();
    fireEvent.click(screen.getByTestId("rebuild-submit"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/collections/rebuild", {
        collection_name: "knowledge_chunk_v1",
        partition_name: "_default",
        mode: "incremental",
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("rebuild-job-id")).toHaveTextContent("r_abc123def456");
    });
  });

  it("切换全量模式后提交 mode=full", async () => {
    mockPost.mockResolvedValueOnce({
      data: { job_id: "r_x", accepted: true, message: "ok", estimated_rows: 0 },
    });
    renderDialog();
    const select = screen.getByTestId("rebuild-mode") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "full" } });
    fireEvent.click(screen.getByTestId("rebuild-submit"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/collections/rebuild", {
        collection_name: "knowledge_chunk_v1",
        partition_name: "_default",
        mode: "full",
      });
    });
  });
});
