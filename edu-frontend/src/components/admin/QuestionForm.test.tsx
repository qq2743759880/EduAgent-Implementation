/**
 * QuestionForm 单测（task03 验收：题库创建题目→tag_ids→过滤命中）
 *  - 纯函数：initialForm / buildQuestionPayload / validateForm
 *  - 题型分发：切到 true_false 出现对/错按钮；单选出现选项编辑器
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http } from "@/lib/api-client";
import {
  QuestionForm,
  buildQuestionPayload,
  initialForm,
  validateForm,
} from "./QuestionForm";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);

function renderForm(extra?: { defaultSubject?: string; question?: never }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <QuestionForm open onOpenChange={() => undefined} defaultSubject={extra?.defaultSubject} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("QuestionForm 纯函数", () => {
  it("initialForm 默认 4 个选项 A/B/C/D、难度 L2、分值 5", () => {
    const f = initialForm(null, "math");
    expect(f.subject_code).toBe("math");
    expect(f.difficulty_level).toBe("L2");
    expect(f.default_score).toBe(5);
    expect(f.options.map((o) => o.label)).toEqual(["A", "B", "C", "D"]);
  });

  it("initialForm 编辑模式回填 options_json/tags/knowledge_points", () => {
    const f = initialForm({
      id: 9,
      question_code: "Q-09",
      subject_code: "english",
      question_type: "multi_choice",
      difficulty_level: "L3",
      stem_html: "Which are fruits?",
      options_json: [{ label: "A", content: "apple" }, { label: "B", content: "car" }],
      correct_answer: "A",
      default_score: 5,
      knowledge_point_codes: ["kp.a", "kp.b"],
      yn: 1,
      created_at: "",
      updated_at: "",
      tags: [{ id: 3, tag_type: "t", tag_code: "T3", tag_name: "水果", sort_no: 0, yn: 1, created_at: "", updated_at: "" }],
    });
    expect(f.question_code).toBe("Q-09");
    expect(f.options).toHaveLength(2);
    expect(f.knowledge_points).toBe("kp.a, kp.b");
    expect(f.tag_ids).toEqual([3]);
  });

  it("buildQuestionPayload knowledge_point_codes 逗号拆分、tag_ids 去重、空选项过滤", () => {
    const f = initialForm(null, "math");
    f.question_code = "Q-01";
    f.question_type = "single_choice";
    f.stem_html = "1+1=?";
    f.options = [
      { label: "A", content: "1" },
      { label: "B", content: "2" },
      { label: "C", content: "" },
    ];
    f.correct_answer = "B";
    f.knowledge_points = "kp.1, kp.1, kp.2";
    f.tag_ids = [1, 2, 1];
    const p = buildQuestionPayload(f);
    expect(p.options_json).toEqual([{ label: "A", content: "1" }, { label: "B", content: "2" }]);
    expect(p.knowledge_point_codes).toEqual(["kp.1", "kp.2"]);
    expect(p.tag_ids).toEqual([1, 2]);
    expect(p.question_type).toBe("single_choice");
  });

  it("validateForm：选择题无有效选项/未标答案 → 报错", () => {
    const f = initialForm(null, "math");
    f.question_code = "Q-01";
    f.question_type = "single_choice";
    f.stem_html = "x";
    f.options = [{ label: "A", content: "1" }];
    const errs = validateForm(f);
    expect(errs.correct_answer).toBeTruthy();
  });

  it("validateForm：判断题必须选对/错", () => {
    const f = initialForm(null, "math");
    f.question_code = "Q-01";
    f.question_type = "true_false";
    f.stem_html = "地球是圆的";
    const errs = validateForm(f);
    expect(errs.correct_answer).toBeTruthy();
    f.correct_answer = "对";
    expect(validateForm(f).correct_answer).toBeUndefined();
  });
});

describe("QuestionForm 题型分发", () => {
  it("标签接口 GET /api/admin/questions/tags 被调用", async () => {
    mockGet.mockResolvedValue([]);
    renderForm();
    await screen.findByTestId("question-form");
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/tags", { params: {} });
  }, 20_000);

  it("切换题型为判断题出现「正确/错误」按钮", async () => {
    mockGet.mockResolvedValue([]);
    renderForm();
    const typeSelect = await screen.findByTestId("question-type-select");
    fireEvent.change(typeSelect, { target: { value: "true_false" } });
    expect(screen.getByTestId("tf-对")).toBeInTheDocument();
    expect(screen.getByTestId("tf-错")).toBeInTheDocument();
  });

  it("切换题型为单选题出现选项正确标记按钮", async () => {
    mockGet.mockResolvedValue([]);
    renderForm();
    const typeSelect = await screen.findByTestId("question-type-select");
    fireEvent.change(typeSelect, { target: { value: "single_choice" } });
    expect(screen.getByTestId("option-correct-A")).toBeInTheDocument();
    expect(screen.getByTestId("option-correct-D")).toBeInTheDocument();
  });
});
