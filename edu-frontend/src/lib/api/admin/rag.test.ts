/**
 * lib/api/admin/rag.ts 单测（task04 / task40 拦截器解包迁移）
 * 验证：collections 数组、rebuild body（collection_name/partition_name/mode）→ 202 job_id、
 * presets 创建（is_default 透传）、audit-log 过滤参数、search body、写操作失败必须抛（R-7）
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  createRagPreset,
  listRagAuditLog,
  listRagCollections,
  listRagPresets,
  ragAdminSearch,
  ragCollectionStatusLabel,
  rebuildRagCollection,
} from "./rag";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

beforeEach(() => vi.clearAllMocks());

describe("集合列表", () => {
  it("GET /api/admin/rag/collections 返回数组（含行数快照）", async () => {
    mockGet.mockResolvedValueOnce([
      {
        id: 1,
        collection_name: "knowledge_chunk_v1",
        partition_name: "_default",
        tenant_id: null,
        display_name: "公共知识库（_default）",
        row_count: 4969,
        source_count: 0,
        last_rebuild_at: null,
        last_snapshot_at: "2026-08-12T21:16:55.455000",
        status: "ready",
        status_message: null,
        visibility: "public",
        created_at: "2026-08-09T09:17:02.884000",
        updated_at: "2026-08-12T21:16:55.459000",
      },
    ]);
    const items = await listRagCollections();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/rag/collections", { params: undefined });
    expect(items).toHaveLength(1);
    expect(items[0].row_count).toBe(4969);
  });

  it("collections 失败必须抛（不静默返回空态）", async () => {
    mockGet.mockRejectedValueOnce(new ApiError(403, { code: 40300, message: "角色无权限" }));
    await expect(listRagCollections()).rejects.toMatchObject({ status: 403, code: 40300 });
  });
});

describe("重建索引", () => {
  it("POST /collections/rebuild body {collection_name, partition_name, mode} → 202 job_id", async () => {
    mockPost.mockResolvedValueOnce({
      job_id: "r_abc123", accepted: true, message: "已接受重建", estimated_rows: 4969,
    });
    const res = await rebuildRagCollection({
      collection_name: "knowledge_chunk_v1",
      partition_name: "_default",
      mode: "full",
    });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/collections/rebuild", {
      collection_name: "knowledge_chunk_v1",
      partition_name: "_default",
      mode: "full",
    });
    expect(res.job_id).toBe("r_abc123");
  });

  it("缺省参数时用后端默认（knowledge_chunk_v1/_default/incremental）", async () => {
    mockPost.mockResolvedValueOnce({
      job_id: "r_x", accepted: true, message: "ok", estimated_rows: 0,
    });
    await rebuildRagCollection({});
    expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/collections/rebuild", {
      collection_name: "knowledge_chunk_v1",
      partition_name: "_default",
      mode: "incremental",
    });
  });

  it("重建失败必须抛（写操作 R-7）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(500, { code: 50000, message: "INTERNAL" }));
    await expect(rebuildRagCollection({ partition_name: "_default" })).rejects.toMatchObject({ status: 500 });
  });
});

describe("参数预设", () => {
  it("GET /presets 返回列表", async () => {
    mockGet.mockResolvedValueOnce([{ id: 1, preset_name: "平衡-default", is_default: true, top_k: 20, final_max_k: 6, cutoff_drop_ratio: 0.4, rrf_k: 60, use_hyde: true, enable_graph: true, llm_model_pref: "fast", created_at: "", updated_at: "" }]);
    const items = await listRagPresets();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/rag/presets", { params: undefined });
    expect(items[0].is_default).toBe(true);
  });

  it("POST /presets is_default=true 透传（后端事务置 0 旧默认）", async () => {
    mockPost.mockResolvedValueOnce({
      id: 3, preset_name: "新默认", is_default: true, top_k: 20, final_max_k: 6, cutoff_drop_ratio: 0.4, rrf_k: 60, use_hyde: true, enable_graph: true, llm_model_pref: "quality", created_at: "", updated_at: "",
    });
    const res = await createRagPreset({ preset_name: "新默认", is_default: true, llm_model_pref: "quality" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/presets", {
      preset_name: "新默认",
      is_default: true,
      llm_model_pref: "quality",
    });
    expect(res.is_default).toBe(true);
  });

  it("presets 创建失败必须抛（写操作 R-7）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(400, { code: 40000, message: "RAG_PRESET_INVALID" }));
    await expect(createRagPreset({ preset_name: "x" })).rejects.toMatchObject({ status: 400 });
  });
});

describe("审计日志", () => {
  it("user_id/role/created_after 过滤 + 分页透传", async () => {
    mockGet.mockResolvedValueOnce({
      page: 1, page_size: 10, total: 1, items: [],
    });
    await listRagAuditLog({
      page: 1,
      page_size: 10,
      user_id: 841,
      role: "student",
      created_after: "2026-08-01T00:00:00",
    });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/rag/audit-log", {
      params: {
        page: 1,
        page_size: 10,
        user_id: 841,
        role: "student",
        created_after: "2026-08-01T00:00:00",
      },
    });
  });

  it("空过滤只传 page/page_size", async () => {
    mockGet.mockResolvedValueOnce({ page: 1, page_size: 20, total: 0, items: [] });
    await listRagAuditLog({});
    expect(mockGet).toHaveBeenCalledWith("/api/admin/rag/audit-log", {
      params: { page: 1, page_size: 20 },
    });
  });
});

describe("高级检索", () => {
  it("POST /search body {query, preset_id, top_k, final_max_k}", async () => {
    mockPost.mockResolvedValueOnce({
      docs: [{ doc_id: "1", score: 0.36, content: "勾股定理", source_file: "题目资料.md", content_type: "question" }],
      graph_entities: [],
      retrieved_count: 1,
      final_count: 1,
      rewrite_query: null,
      degraded_reason: null,
      applied_preset_name: null,
    });
    const res = await ragAdminSearch({ query: "勾股定理", preset_id: 2, top_k: 40, final_max_k: 10 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/search", {
      query: "勾股定理",
      preset_id: 2,
      top_k: 40,
      final_max_k: 10,
    });
    expect(res.docs[0].score).toBeCloseTo(0.36);
  });

  it("tenant_ids/content_types 数组透传", async () => {
    mockPost.mockResolvedValueOnce({
      docs: [], graph_entities: [], retrieved_count: 0, final_count: 0, degraded_reason: "MILVUS_UNAVAILABLE",
    });
    const res = await ragAdminSearch({
      query: "q",
      tenant_ids: ["_default", "user_802"],
      content_types: ["document", "question"],
    });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/rag/search", {
      query: "q",
      tenant_ids: ["_default", "user_802"],
      content_types: ["document", "question"],
    });
    expect(res.degraded_reason).toBe("MILVUS_UNAVAILABLE");
  });

  it("search 失败必须抛（写操作 R-7）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(403, { code: 40300, message: "角色无权限" }));
    await expect(ragAdminSearch({ query: "q" })).rejects.toMatchObject({ status: 403 });
  });
});

describe("显示辅助", () => {
  it("ragCollectionStatusLabel 中文映射", () => {
    expect(ragCollectionStatusLabel("ready")).toBe("就绪");
    expect(ragCollectionStatusLabel("rebuilding")).toBe("重建中");
    expect(ragCollectionStatusLabel("error")).toBe("异常");
    expect(ragCollectionStatusLabel("x" as never)).toBe("x");
  });
});
