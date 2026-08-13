/**
 * lib/api/admin/questions.ts 单测（task03）
 * 验证：题型枚举（后端权威：single_choice/multi_choice/...）、批量导入 body 为 list、
 * 组卷 body 形状、过滤参数、写操作失败必须抛（R-7）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api-client";
import {
  QUESTION_TYPE_OPTIONS,
  batchImportQuestions,
  composePaper,
  createQuestion,
  createQuestionTag,
  listQuestions,
  listQuestionTags,
  questionTypeLabel,
  updateQuestion,
  type QuestionCreateInput,
} from "./questions";

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
    mockGet.mockResolvedValueOnce({ data: { total: 0, page: 1, page_size: 20, items: [] } });
    await listQuestions({ subject_code: "math", question_type: "single_choice", difficulty_level: "L2", keyword: "函数", tag_id: 3, page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions", {
      params: {
        page: 1, page_size: 20, subject_code: "math", question_type: "single_choice",
        difficulty_level: "L2", keyword: "函数", tag_id: 3,
      },
    });
  });

  it("空过滤只传分页", async () => {
    mockGet.mockResolvedValueOnce({ data: { total: 0, page: 1, page_size: 20, items: [] } });
    await listQuestions();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions", {
      params: { page: 1, page_size: 20 },
    });
  });
});

describe("题目创建/更新", () => {
  it("createQuestion options_json 数组 + tag_ids + knowledge_point_codes 透传", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 10, question_code: "Q-01" } });
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
    mockPatch.mockResolvedValueOnce({ data: { updated: true, id: 10 } });
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

describe("批量导入 / 组卷", () => {
  it("batchImportQuestions body 为 list[dict]（非包裹对象）", async () => {
    mockPost.mockResolvedValueOnce({
      data: { total: 3, imported: 1, skipped: 1, failed: 1, messages: ["[1] skip 编码重复", "[2] schema invalid"] },
    });
    const items = [{ question_code: "Q-1" }, { question_code: "Q-1" }, { bad: true }];
    const resp = await batchImportQuestions(items as QuestionCreateInput[]);
    expect(mockPost).toHaveBeenCalledWith("/api/admin/questions/batch-import", items);
    expect(resp).toMatchObject({ imported: 1, skipped: 1, failed: 1 });
    expect(resp.messages.length).toBeGreaterThan(0);
  });

  it("composePaper body 为 {spec:{...}, paper_code, paper_title, expected_question_count}", async () => {
    mockPost.mockResolvedValueOnce({
      data: { draft_paper_id: 99, paper_code: "P-01-AB12", paper_title: "数学卷", selected_count: 20, total_score: 100, message: "ok", items: [] },
    });
    await composePaper({
      spec: { subject_code: "math", difficulty_level: "L2", tag_ids: [1], per_question_score: 5, total_score: 100, duration_minutes: 120, pass_score: 60 },
      paper_code: "P-01",
      paper_title: "数学卷",
      expected_question_count: 20,
    });
    const body = mockPost.mock.calls[0][1];
    expect(mockPost.mock.calls[0][0]).toBe("/api/admin/questions/papers/compose");
    expect(body).toMatchObject({
      spec: { subject_code: "math", tag_ids: [1], per_question_score: 5 },
      paper_code: "P-01",
      expected_question_count: 20,
    });
  });
});

describe("标签", () => {
  it("listQuestionTags GET /tags", async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await listQuestionTags({ subject_code: "math" });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/tags", {
      params: { subject_code: "math" },
    });
  });

  it("createQuestionTag POST /tags", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 1, tag_code: "T-01" } });
    await createQuestionTag({ tag_type: "knowledge_point", tag_code: "T-01", tag_name: "定语从句" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/questions/tags", {
      tag_type: "knowledge_point", tag_code: "T-01", tag_name: "定语从句",
    });
  });
});
