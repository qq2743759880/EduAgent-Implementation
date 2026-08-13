/**
 * lib/api/admin/courses.ts 单测（task03）
 * 验证：路径/参数/请求体契约 + 写操作失败必须抛（R-7）
 * 契约基准：app/admin/course_admin/router.py + schemas.py（L1）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api-client";
import {
  bindVideoToSession,
  createAdminCohort,
  createAdminModule,
  createAdminSeries,
  createAdminSession,
  finalizeVideoUpload,
  initVideoUpload,
  listAdminSeries,
  listAdminVideoAssets,
  updateAdminSeries,
  type SeriesCreateInput,
} from "./courses";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);

beforeEach(() => vi.clearAllMocks());

describe("系列 CRUD", () => {
  it("listAdminSeries 传递 subject/level/keyword 与分页参数", async () => {
    mockGet.mockResolvedValueOnce({ data: { total: 0, page: 1, page_size: 20, items: [] } });
    await listAdminSeries({ subject_code: "math", level_code: "L2", keyword: "雅思", page: 2, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/series", {
      params: {
        page: 2,
        page_size: 20,
        subject_code: "math",
        level_code: "L2",
        keyword: "雅思",
      },
    });
  });

  it("createAdminSeries 用 series_name（后端字段，非 series_title）", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 1, series_code: "S-01" } });
    const input: SeriesCreateInput = {
      series_code: "S-01",
      series_name: "雅思基础",
      subject_code: "english",
      level_code: "L1",
      level_name: "入门",
      target_hours: 20,
      sale_status: "on_sale",
    };
    await createAdminSeries(input);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/series", input);
  });

  it("updateAdminSeries PATCH /series/{id} 传补丁体", async () => {
    mockPatch.mockResolvedValueOnce({ data: { updated: true, id: 7 } });
    await updateAdminSeries(7, { series_name: "改名" });
    expect(mockPatch).toHaveBeenCalledWith("/api/admin/courses/series/7", { series_name: "改名" });
  });

  it("写操作失败必须抛 ApiError（R-7 不静默吞错）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(403, { code: 40300, message: "FORBIDDEN" }));
    await expect(createAdminSeries({ series_code: "x", series_name: "y", subject_code: "math", level_code: "L1", level_name: "入门" }))
      .rejects.toMatchObject({ status: 403, code: 40300 });
  });
});

describe("模块/课次/班次", () => {
  it("createAdminModule POST /modules 传 series_id", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 3, module_code: "M-01" } });
    await createAdminModule({ series_id: 1, module_code: "M-01", module_name: "词汇", stage_no: 1 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/modules", {
      series_id: 1, module_code: "M-01", module_name: "词汇", stage_no: 1,
    });
  });

  it("createAdminSession POST /sessions 传 module_id", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 5, session_title: "第 1 讲" } });
    await createAdminSession({ module_id: 3, session_no: 1, session_title: "第 1 讲", duration_minutes: 45 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/sessions", {
      module_id: 3, session_no: 1, session_title: "第 1 讲", duration_minutes: 45,
    });
  });

  it("createAdminCohort POST /cohorts 传 series_id", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 9, cohort_code: "C-01" } });
    await createAdminCohort({ series_id: 1, cohort_code: "C-01", cohort_name: "A 班" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/cohorts", {
      series_id: 1, cohort_code: "C-01", cohort_name: "A 班",
    });
  });
});

describe("视频三连（占位式上传）", () => {
  it("initVideoUpload 用 origin_file_name（后端字段）并携带 bind_session_id", async () => {
    mockPost.mockResolvedValueOnce({
      data: { asset_id: "V20260812-ABCD", upload_type: "direct_form_post", upload_url: "/_dev_direct_put", form_fields: {}, transcode_status_tip: "占位", expires_at: "2026-08-12T00:30:00", bind_session_id: 5 },
    });
    const resp = await initVideoUpload({ origin_file_name: "lesson1.mp4", file_size: 1024, bind_session_id: 5 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/upload/init", {
      origin_file_name: "lesson1.mp4",
      file_size: 1024,
      bind_session_id: 5,
    });
    expect(resp.asset_id).toBe("V20260812-ABCD");
  });

  it("finalizeVideoUpload POST /videos/upload/finalize 传 asset_id → ready + 播放地址", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        id: 1, asset_id: "V-X", session_id: null, asset_title: "t", origin_file_name: "a.mp4",
        file_size: 0, duration_seconds: 0, transcode_status: "ready", transcode_message: "占位转码完成",
        play_720_url: "https://cdn.placeholder.local/720/V-X.mp4",
        play_1080_url: "https://cdn.placeholder.local/1080/V-X.mp4",
        created_at: "", updated_at: "",
      },
    });
    const video = await finalizeVideoUpload({ asset_id: "V-X" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/upload/finalize", { asset_id: "V-X" });
    expect(video.transcode_status).toBe("ready");
    expect(video.play_720_url).toContain("720");
  });

  it("bindVideoToSession POST /videos/bind-session 传 {asset_id, session_id}", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 1, asset_id: "V-X", session_id: 5, asset_title: "", origin_file_name: "", file_size: 0, duration_seconds: 0, transcode_status: "ready", created_at: "", updated_at: "" } });
    await bindVideoToSession("V-X", 5);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/bind-session", { asset_id: "V-X", session_id: 5 });
  });

  it("listAdminVideoAssets 支持 session_id/status 过滤", async () => {
    mockGet.mockResolvedValueOnce({ data: { total: 0, page: 1, page_size: 20, items: [] } });
    await listAdminVideoAssets({ session_id: 5, status: "ready" });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/videos", {
      params: { page: 1, page_size: 20, session_id: 5, status: "ready" },
    });
  });

  it("视频写操作失败必须抛（Init 500）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(500, { code: 50000, message: "INTERNAL" }));
    await expect(initVideoUpload({ origin_file_name: "x.mp4" })).rejects.toMatchObject({ status: 500 });
  });
});
