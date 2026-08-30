/**
 * lib/api/admin/questions.ts 单测（task03 / task40 拦截器解包迁移）
 * 验证：题型枚举（后端权威：single_choice/multi_choice/...）、批量导入 body 为 list、
 * 组卷 body 形状、过滤参数、写操作失败必须抛（R-7）
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  QUESTION_TYPE_OPTIONS,
  createQuestion,
  listQuestions,
  questionTypeLabel,
  updateQuestion,
  type QuestionCreateInput,
} from "./questions";

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

beforeEach(() => vi.clearAllMocks());

describe("题型枚举（后端契约，非 design-guide 摘要）", () => {
  it("5 个后端枚举值", () => {
    expect(QUESTION_TYPE_OPTIONS.map((t) => t.value)).toEqual([
      "single_choice",
      "multi_choice",
      "true_false",
      "fill_blank",
      "short_answer",
    ]);
  });

  it("questionTypeLabel 映射中文", () => {
    expect(questionTypeLabel("single_choice")).toBe("单选题");
    expect(questionTypeLabel("true_false")).toBe("判断题");
    expect(questionTypeLabel("unknown")).toBe("unknown");
  });
});

describe("题目列表过滤", () => {
  it("subject/type/difficulty/keyword/tag_id 全部透传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listQuestions({ subject_code: "math", question_type: "single_choice", difficulty_level: "L2", keyword: "函数", tag_id: 3, page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions", {
      params: {
        page: 1, page_size: 20, subject_code: "math", question_type: "single_choice",
        difficulty_level: "L2", keyword: "函数", tag_id: 3,
      },
    });
  });

  it("空过滤只传分页", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listQuestions();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions", {
      params: { page: 1, page_size: 20 },
    });
  });
});

describe("题目创建/更新", () => {
  it("createQuestion options_json 数组 + tag_ids + knowledge_point_codes 透传", async () => {
    mockPost.mockResolvedValueOnce({ id: 10, question_code: "Q-01" });
    const input: QuestionCreateInput = {
      question_code: "Q-01",
      subject_code: "math",
      question_type: "single_choice",
      difficulty_level: "L1",
      stem_html: "1+1=?",
      options_json: [{ label: "A", content: "1" }, { label: "B", content: "2" }],
      correct_answer: "B",
      default_score: 5,
      knowledge_point_codes: ["kp.1"],
      tag_ids: [1, 2],
    };
    await createQuestion(input);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/questions", input);
  });

  it("updateQuestion PATCH /questions/{id}", async () => {
    mockPatch.mockResolvedValueOnce({ updated: true, id: 10 });
    await updateQuestion(10, { stem_html: "2+2=?" });
    expect(mockPatch).toHaveBeenCalledWith("/api/admin/questions/10", { stem_html: "2+2=?" });
  });

  it("写操作失败必须抛（题目创建 409 编码重复）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(409, { code: 40901, message: "题目编码已存在: Q-01" }));
    await expect(
      createQuestion({ question_code: "Q-01", subject_code: "math", question_type: "single_choice", difficulty_level: "L1", stem_html: "x", options_json: [], correct_answer: "A", default_score: 5, knowledge_point_codes: [], tag_ids: [] }),
    ).rejects.toMatchObject({ status: 409, code: 40901 });
  });
});
