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
  applyTypeSwitch,
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

describe("applyTypeSwitch 题型切换边界（task69·task59 批判②：无旧选项/旧答案残留）", () => {
  const choiceForm = () => {
    const f = initialForm(null, "math");
    f.question_type = "single_choice";
    f.options = [
      { label: "A", content: "1 + 1" },
      { label: "B", content: "2" },
    ];
    f.correct_answer = "B";
    return f;
  };

  it("单选 → 填空：旧答案 label「B」被清空（不残余到填空答案）", () => {
    const next = applyTypeSwitch(choiceForm(), "fill_blank");
    expect(next.question_type).toBe("fill_blank");
    expect(next.correct_answer).toBe("");
  });

  it("单选 → 填空 → 切回单选：旧选项内容被重置为默认空选项（无残留选项）", () => {
    let f = choiceForm();
    f = applyTypeSwitch(f, "fill_blank");
    f.correct_answer = "transformation";
    f = applyTypeSwitch(f, "single_choice");
    expect(f.question_type).toBe("single_choice");
    expect(f.correct_answer).toBe("");
    expect(f.options.map((o) => o.label)).toEqual(["A", "B", "C", "D"]);
    expect(f.options.every((o) => o.content === "")).toBe(true);
  });

  it("单选 ↔ 多选互切保留已填选项，仅清空答案", () => {
    const f = choiceForm();
    const multi = applyTypeSwitch(f, "multi_choice");
    expect(multi.options.map((o) => o.content)).toEqual(["1 + 1", "2"]);
    expect(multi.correct_answer).toBe("");
    const back = applyTypeSwitch(multi, "single_choice");
    expect(back.options.map((o) => o.label)).toEqual(["A", "B"]);
    expect(back.options[0].content).toBe("1 + 1");
  });

  it("同一题型 / 空值切换 → 原样返回（不重置）", () => {
    const f = choiceForm();
    f.correct_answer = "B";
    expect(applyTypeSwitch(f, "single_choice")).toBe(f);
    expect(applyTypeSwitch(f, "")).toBe(f);
  });
});

describe("QuestionForm 题型分发", () => {
  it("标签接口返回空数组（后端已移除 tag 维度）", async () => {
    renderForm();
    await screen.findByTestId("question-form");
    expect(mockGet).not.toHaveBeenCalledWith("/api/admin/questions/tags", { params: {} });
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

  it("单选已标答案 B → 切填空：填空答案框为空（旧答案不残留）", async () => {
    mockGet.mockResolvedValue([]);
    renderForm();
    const typeSelect = await screen.findByTestId("question-type-select");
    fireEvent.change(typeSelect, { target: { value: "single_choice" } });
    fireEvent.click(screen.getByTestId("option-correct-B"));
    expect(screen.getByTestId("option-correct-B").getAttribute("aria-pressed")).toBe("true");
    fireEvent.change(typeSelect, { target: { value: "fill_blank" } });
    const fillInput = screen.getByPlaceholderText(/如：transformation/) as HTMLInputElement;
    expect(fillInput.value).toBe("");
  });
});
