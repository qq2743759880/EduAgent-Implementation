/**
 * lib/api/admin/courses.ts 单测（task03 / task40 拦截器解包迁移）
 * 验证：路径/参数/请求体契约 + 写操作失败必须抛（R-7）
 * 契约基准：app/admin/course_admin/router.py + schemas.py（L1）
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  bindSessionVideo,
  createAdminCohort,
  createAdminModule,
  createAdminSeries,
  createAdminSession,
  deleteAdminSeries,
  deliveryModeLabel,
  finalizeChunkedUpload,
  getTranscodeStatus,
  initChunkedUpload,
  listAdminSeries,
  transcodeBadgeTone,
  updateAdminSeries,
  type SeriesCreateInput,
} from "./courses";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);
const mockPatch = vi.mocked(http.patch);
const mockDelete = vi.mocked(http.delete);

beforeEach(() => vi.clearAllMocks());

describe("系列 CRUD", () => {
  it("listAdminSeries 传递 delivery_mode/sale_status/sort/institution_id/keyword 与分页参数", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 2, page_size: 20, items: [] });
    await listAdminSeries({
      delivery_mode: "online_live",
      sale_status: "on_sale",
      sort: "newest",
      institution_id: 3,
      keyword: "Python",
      page: 2,
      page_size: 20,
    });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/series", {
      params: {
        page: 2,
        page_size: 20,
        delivery_mode: "online_live",
        sale_status: "on_sale",
        sort: "newest",
        institution_id: 3,
        keyword: "Python",
      },
    });
  });

  it("listAdminSeries 关键字前后空格会被 trim，空筛选不传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listAdminSeries({ keyword: "  ", delivery_mode: undefined });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/series", {
      params: { page: 1, page_size: 20 },
    });
  });

  it("listAdminSeries include_deleted=true 触发 -> 传 ?include_deleted（C-C 回收站视图）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listAdminSeries({ include_deleted: true, page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/series", {
      params: { page: 1, page_size: 20, include_deleted: true },
    });
  });

  it("listAdminSeries 缺省 include_deleted 不传（默认过滤已下架）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listAdminSeries({ page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/series", {
      params: { page: 1, page_size: 20 },
    });
  });

  it("createAdminSeries 用 series_name + delivery_mode + institution_id（domains 契约）", async () => {
    mockPost.mockResolvedValueOnce({ id: 1 });
    const input: SeriesCreateInput = {
      institution_id: 1,
      delivery_mode: "online_recorded",
      series_code: "PY-001",
      series_name: "零基础 Python 入门营",
      sale_status: "draft",
    };
    await createAdminSeries(input);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/series", input);
  });

  it("updateAdminSeries PATCH /series/{id} 传补丁体", async () => {
    mockPatch.mockResolvedValueOnce({ updated: true, id: 7 });
    await updateAdminSeries(7, { series_name: "改名", sale_status: "off_sale" });
    expect(mockPatch).toHaveBeenCalledWith("/api/admin/courses/series/7", { series_name: "改名", sale_status: "off_sale" });
  });

  it("deleteAdminSeries DELETE /series/{id}（软删）", async () => {
    mockDelete.mockResolvedValueOnce({ deleted: true, id: 9 });
    await deleteAdminSeries(9);
    expect(mockDelete).toHaveBeenCalledWith("/api/admin/courses/series/9");
  });

  it("deleteAdminSeries hard=true -> DELETE /series/{id}?hard=true（C-C 硬删）", async () => {
    mockDelete.mockResolvedValueOnce({ deleted: true, id: 9 });
    await deleteAdminSeries(9, true);
    expect(mockDelete).toHaveBeenCalledWith("/api/admin/courses/series/9?hard=true");
  });

  it("deliveryModeLabel 枚举标签映射", () => {
    expect(deliveryModeLabel("online_live")).toBe("直播");
    expect(deliveryModeLabel("online_recorded")).toBe("录播");
    expect(deliveryModeLabel("offline_face_to_face")).toBe("面授");
    expect(deliveryModeLabel("unknown")).toBe("unknown");
  });

  it("写操作失败必须抛 ApiError（R-7 不静默吞错）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(403, { code: 40300, message: "FORBIDDEN" }));
    await expect(createAdminSeries({ institution_id: 1, delivery_mode: "online_live", series_code: "x", series_name: "y" }))
      .rejects.toMatchObject({ status: 403, code: 40300 });
  });
});

describe("模块/课次/班次", () => {
  it("createAdminModule POST /modules 传 cohort_id（归属班次，非 series_id）", async () => {
    mockPost.mockResolvedValueOnce({ id: 3, module_code: "M-01" });
    await createAdminModule({ cohort_id: 1, module_code: "M-01", module_name: "词汇", stage_no: 1, lesson_count: 1, total_hours: 0 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/modules", {
      cohort_id: 1, module_code: "M-01", module_name: "词汇", stage_no: 1, lesson_count: 1, total_hours: 0,
    });
  });

  it("createAdminSession POST /sessions 传 series_cohort_course_id（模块物理 ID）", async () => {
    mockPost.mockResolvedValueOnce({ id: 5, session_title: "第 1 讲" });
    await createAdminSession({ series_cohort_course_id: 3, session_no: 1, session_title: "第 1 讲" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/sessions", {
      series_cohort_course_id: 3, session_no: 1, session_title: "第 1 讲",
    });
  });

  it("createAdminCohort POST /cohorts 传 institution_id + series_id + head_teacher_id", async () => {
    mockPost.mockResolvedValueOnce({ id: 9, cohort_code: "C-01" });
    await createAdminCohort({ institution_id: 1, series_id: 1, head_teacher_id: 2, cohort_code: "C-01", cohort_name: "A 班", sale_price: 0, max_student_count: 1 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/cohorts", {
      institution_id: 1, series_id: 1, head_teacher_id: 2, cohort_code: "C-01", cohort_name: "A 班", sale_price: 0, max_student_count: 1,
    });
  });
});

describe("视频分片上传四段 + 转码徽章（task57 契约）", () => {
  it("initChunkedUpload POST /videos/init-chunked 参数走 query（session_id/file_name/file_size/chunk_count）", async () => {
    mockPost.mockResolvedValueOnce({ upload_id: "UP-1", chunk_size: 5 * 1024 * 1024, upload_urls: ["u0", "u1"], strategy: "chunked" });
    const resp = await initChunkedUpload(5, { file_name: "lesson1.mp4", file_size: 10 * 1024 * 1024, chunk_count: 2 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/init-chunked", undefined, {
      params: { session_id: 5, file_name: "lesson1.mp4", file_size: 10 * 1024 * 1024, chunk_count: 2 },
    });
    expect(resp.strategy).toBe("chunked");
  });

  it("finalizeChunkedUpload POST /videos/finalize-chunked 传 upload_id → asset_id/video_id/transcode_status", async () => {
    mockPost.mockResolvedValueOnce({ upload_id: "UP-1", asset_id: 1, video_id: 2, transcode_status: "pending" });
    const resp = await finalizeChunkedUpload("UP-1");
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/finalize-chunked", undefined, {
      params: { upload_id: "UP-1" },
    });
    expect(resp.asset_id).toBe(1);
    expect(resp.transcode_status).toBe("pending");
  });

  it("bindSessionVideo POST /videos/bind-session 传 {session_id, video_id, sort_no}", async () => {
    mockPost.mockResolvedValueOnce({ bound: true, video_id: 2, session_id: 5 });
    await bindSessionVideo(5, 2, 0);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/videos/bind-session", undefined, {
      params: { session_id: 5, video_id: 2, sort_no: 0 },
    });
  });

  it("getTranscodeStatus GET /videos/{video_id}/transcode-status", async () => {
    mockGet.mockResolvedValueOnce({ video_id: 2, transcode_status: "completed", review_status: "approved" });
    const s = await getTranscodeStatus(2);
    expect(mockGet).toHaveBeenCalledWith("/api/admin/courses/videos/2/transcode-status");
    expect(s.transcode_status).toBe("completed");
  });

  it("分片上传写操作失败必须抛（Init 500）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(500, { code: 50000, message: "INTERNAL" }));
    await expect(initChunkedUpload(5, { file_name: "x.mp4", file_size: 1, chunk_count: 1 }))
      .rejects.toMatchObject({ status: 500 });
  });

  it("transcodeBadgeTone 徽章映射：pending→warning / in_progress→primary / completed→green / failed→destructive", () => {
    expect(transcodeBadgeTone("pending")).toContain("warning");
    expect(transcodeBadgeTone("in_progress")).toContain("primary");
    expect(transcodeBadgeTone("completed")).toContain("candy-green");
    expect(transcodeBadgeTone("failed")).toContain("destructive");
  });
});
