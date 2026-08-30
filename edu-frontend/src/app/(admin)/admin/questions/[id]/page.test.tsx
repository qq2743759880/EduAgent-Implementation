/** /admin/questions/[id] 编辑器交互测试（task59，契约④）
 *  GWT① 题型切换联动选项控件 + objective 徽章派生 + 已填数据不丢
 *  GWT② analysis_text 为空前端拦截（不调 PATCH）+ 保存 payload 持久化
 *  mock updateQuestion；真实 QueryClientProvider；mock next/navigation(useRouter)
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QuestionDetailEditor } from "@/components/admin/QuestionDetailEditor";
import { updateQuestion, type QuestionDetail, type QuestionTypeOption } from "@/lib/api/admin/question-bank";

vi.mock("@/lib/api/admin/question-bank", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/admin/question-bank")>();
  return { ...actual, updateQuestion: vi.fn() };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

const updateMock = vi.mocked(updateQuestion);

const TYPES: QuestionTypeOption[] = [
  { id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 },
  { id: 2, type_code: "multi_choice", type_name: "多选题", objective_flag: 1 },
  { id: 3, type_code: "true_false", type_name: "判断题", objective_flag: 1 },
  { id: 4, type_code: "fill_blank", type_name: "填空题", objective_flag: 0 },
  { id: 5, type_code: "short_answer", type_name: "简答题", objective_flag: 0 },
];

const DETAIL: QuestionDetail = {
  id: 9001,
  bank_id: 3,
  question_code: "Q1001",
  question_type_id: 1,
  stem: "下列 Python 代码的输出是？",
  options_json: [
    { key: "A", text: "Hello" },
    { key: "B", text: "World" },
  ],
  answer_text: "A",
  analysis_text: "print 输出",
  yn: 1,
};

function renderEditor(detail: QuestionDetail = DETAIL) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <QuestionDetailEditor questionId={detail.id} bankName="Python 题库" detail={detail} types={TYPES} />
    </QueryClientProvider>,
  );
}

const analysisInput = () => screen.getByPlaceholderText(/编写本题解析/);

beforeEach(() => updateMock.mockReset());

describe("task59 GWT① 题型联动 + 已填数据不丢", () => {
  it("单选默认 RadioGroup 选项 + 客观徽章", () => {
    renderEditor();
    expect(screen.getByText(/单选题选项（RadioGroup/)).toBeInTheDocument();
    expect(screen.getAllByRole("radio").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("Hello")).toBeInTheDocument();
    expect(screen.getAllByText(/客观 · 自动判题/).length).toBeGreaterThan(0);
  });

  it("切换判断 → 固定 对/错 按钮；切填空 → 无选项提示", async () => {
    const user = userEvent.setup();
    renderEditor();
    const sel = screen.getByRole("combobox");
    await user.selectOptions(sel, "true_false");
    expect(screen.getByRole("button", { name: /√/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /×/ })).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Hello")).toBeNull();

    await user.selectOptions(sel, "fill_blank");
    expect(screen.getByText(/该题型不提供选项编辑器/)).toBeInTheDocument();
    expect(screen.getAllByText(/主观 · 人工批改/).length).toBeGreaterThan(0);
  });

  it("题型切换已填数据不丢：单选填 A → 多选 → 切回单选仍保留", async () => {
    const user = userEvent.setup();
    renderEditor();
    const aInput = screen.getByPlaceholderText("选项 A 文本…");
    await user.clear(aInput);
    await user.type(aInput, "Hello!");
    const sel = screen.getByRole("combobox");

    await user.selectOptions(sel, "multi_choice");
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("Hello!")).toBeInTheDocument();

    await user.selectOptions(sel, "single_choice");
    expect(screen.getByDisplayValue("Hello!")).toBeInTheDocument();
  });
});

describe("task59 GWT② 解析必修 + 保存", () => {
  it("analysis_text 为空时保存被前端拦截（不调 PATCH），提示解析必填", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.clear(analysisInput());
    await user.click(screen.getByRole("button", { name: /^保存$/ }));
    expect(updateMock).not.toHaveBeenCalled();
    expect(screen.getByText(/解析（analysis_text）为必填/)).toBeInTheDocument();
  });

  it("保存调用 updateQuestion({id}, payload) 含 analysis_text + options_json，答案/题干持久化", async () => {
    const user = userEvent.setup();
    updateMock.mockResolvedValueOnce({ updated: true, id: 9001 });
    renderEditor();
    await user.click(screen.getByRole("button", { name: /^保存$/ }));
    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock).toHaveBeenCalledWith(
      9001,
      expect.objectContaining({
        question_type_id: 1,
        stem: "下列 Python 代码的输出是？",
        answer_text: "A",
        analysis_text: "print 输出",
        options_json: [
          { key: "A", text: "Hello" },
          { key: "B", text: "World" },
        ],
      }),
    );
  });
});