/**
 * task69 · task59 批判① —— 管理端 QuestionDetailEditor「预览」Tab 与用户端 QuizPanel
 * 对同一题渲染内容一致性单测（Playwright 已被项目禁用，以渲染级数据奇偶替代截图 diff）：
 *  - 同一语义题干 + 选项（key→text），两处渲染均含题干与全部选项文本（真实数据源，非硬编码）
 *  - 客观选项 key 字母（A/B）在两处均渲染
 * 说明：Markdown 题干两者都经 MarkdownView 渲染；选项文本两处同为 options[{key,text}] 来源。
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* ---- mocks：禁用真实网络 ---- */
vi.mock("@/lib/api/learning", () => ({
  getNextQuestion: vi.fn(),
  submitAnswer: vi.fn(),
  getVocabDaily: vi.fn(),
}));
vi.mock("@/lib/api/admin/question-bank", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/admin/question-bank")>();
  return { ...actual, updateQuestion: vi.fn() };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { getNextQuestion } from "@/lib/api/learning";
import { QuizPanel } from "./QuizPanel";
import { QuestionDetailEditor } from "@/components/admin/QuestionDetailEditor";
import type { QuestionTypeOption } from "@/lib/api/admin/question-bank";

const nextMock = vi.mocked(getNextQuestion);

/* ---- 同一道选择题的两种数据形状：后端题库 QuestionDetail（bank） vs P5 QuestionOut（mode） ---- */
const STEM = "下列 Python 代码的输出是？";
const OPT_A = "Hello";
const OPT_B = "World";

const TYPES: QuestionTypeOption[] = [
  { id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 },
  { id: 2, type_code: "multi_choice", type_name: "多选题", objective_flag: 1 },
  { id: 3, type_code: "true_false", type_name: "判断题", objective_flag: 1 },
  { id: 4, type_code: "fill_blank", type_name: "填空题", objective_flag: 0 },
  { id: 5, type_code: "short_answer", type_name: "简答题", objective_flag: 0 },
];

const BANK_DETAIL = {
  id: 9001,
  bank_id: 3,
  question_code: "Q1001",
  question_type_id: 1,
  stem: STEM,
  options_json: [
    { key: "A", text: OPT_A },
    { key: "B", text: OPT_B },
  ],
  answer_text: "A",
  analysis_text: "print 输出",
  yn: 1,
};

const P5_QUESTION = {
  question_id: 101,
  subject_code: "math",
  mode: "SINGLE",
  stem: STEM,
  options: [
    { key: "A", text: OPT_A },
    { key: "B", text: OPT_B },
  ],
};

function renderQuizPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <QuizPanel subject_code="math" from_wrong_book={false} />
    </QueryClientProvider>,
  );
}

function renderAdminPreview() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <QuestionDetailEditor questionId={9001} bankName="Python 题库" detail={BANK_DETAIL} types={TYPES} />
    </QueryClientProvider>,
  );
}

beforeEach(() => nextMock.mockReset());

describe("task59 批判①：管理端预览 vs 用户端 QuizPanel 渲染一致性（数据奇偶）", () => {
  it("同题干 + 同选项文本在两处均渲染（真实数据源，非硬编码）", async () => {
    nextMock.mockResolvedValue(P5_QUESTION as never);

    // 用户端 QuizPanel：题干 + 选项 A/B
    renderQuizPanel();
    await screen.findByText(STEM);
    expect(screen.getByText(OPT_A)).toBeInTheDocument();
    expect(screen.getByText(OPT_B)).toBeInTheDocument();

    // 管理端预览：题干 + 选项 A/B
    cleanup();
    renderAdminPreview();
    await userEvent.click(screen.getByRole("tab", { name: /预览/ }));
    expect(screen.getByText(STEM)).toBeInTheDocument();
    expect(screen.getByText(OPT_A)).toBeInTheDocument();
    expect(screen.getByText(OPT_B)).toBeInTheDocument();
  });

  it("客观选项 key 字母（A/B）在两处渲染一致", async () => {
    nextMock.mockResolvedValue(P5_QUESTION as never);

    renderQuizPanel();
    await screen.findByText(STEM);
    // QuizPanel 单选以字母徽章渲染选项 key
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("B").length).toBeGreaterThan(0);

    cleanup();
    renderAdminPreview();
    await userEvent.click(screen.getByRole("tab", { name: /预览/ }));
    // 预览选项行首渲染 key 字母
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("B").length).toBeGreaterThan(0);
  });
});