/**
 * QuizSession 单测（task49 核心）— 覆盖 GWT①②③
 *   facts参数构建 / 题干选项渲染 / 作答→判分→explain_content(Markdown) 展示 /
 *   空态(无题) / 错误态(拉题失败→重试)。learning 契约⑤ 采用 mock，验证禁用假数据。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/learning", () => ({
  getNextQuestion: vi.fn(),
  submitAnswer: vi.fn(),
}));

import { getNextQuestion, submitAnswer } from "@/lib/api/learning";
import { QuizSession, buildParams, modeLabel, answerToString } from "./QuizSession";

const nextMock = vi.mocked(getNextQuestion);
const submitMock = vi.mocked(submitAnswer);

const singleQuestion = {
  question_id: 11,
  mode: "SINGLE",
  stem: "2 + 2 = ？",
  options: [
    { key: "A", text: "3" },
    { key: "B", text: "4" },
  ],
};
const judgeNoOptions = {
  question_id: 12,
  mode: "JUDGE",
  stem: "Python 的 list 可修改。",
  options: null,
};

describe("QuizSession · 出题参数构建（GWT② 数据来源 question 表）", () => {
  it("wrong-book → from_wrong_book + only_not_mastered", () => {
    expect(buildParams({ source: "wrong-book" })).toEqual({
      from_wrong_book: true,
      prefer_wrong_book_ratio: 1,
      only_not_mastered: true,
    });
  });
  it("topic → 按题型 mode 过滤，且不从错题优先", () => {
    expect(buildParams({ source: "topic", qmode: "SINGLE" })).toEqual({
      mode: "SINGLE",
      from_wrong_book: false,
    });
  });
});

describe("QuizSession · GWT① 判分即时展示 + explain_content(analysis_text) 解析渲染", () => {
  beforeEach(() => {
    nextMock.mockReset();
    submitMock.mockReset();
  });

  it("渲染题干与选项，答对后展示判分横幅与 Markdown 解析", async () => {
    nextMock.mockResolvedValue(singleQuestion as never);
    submitMock.mockResolvedValue({
      is_correct: true,
      score: 5,
      explain_content: "# 解析\n一眼看出 4",
    } as never);

    render(<QuizSession session={{ source: "wrong-book" }} onBack={() => undefined} />);

    await screen.findByText("2 + 2 = ？");
    expect(screen.getAllByRole("radio")).toHaveLength(2);

    await userEvent.click(screen.getByText("4"));
    await userEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText(/回答正确/)).toBeInTheDocument();
    /* explain_content → MarkdownView 渲染（h1「解析」+ 文本） */
    expect(screen.getByText("解析")).toBeInTheDocument();
    expect(screen.getByText(/一眼看出 4/)).toBeInTheDocument();

    /* 真实计时（非假值）：time_spent_seconds 应为非负秒数 */
    const arg = submitMock.mock.calls[0][0] as { time_spent_seconds: number };
    expect(arg.time_spent_seconds).toBeTypeOf("number");
    expect(arg.time_spent_seconds).toBeGreaterThanOrEqual(0);
  });

  it("答错时展示错误横幅与正确答案提示", async () => {
    nextMock.mockResolvedValue(singleQuestion as never);
    submitMock.mockResolvedValue({
      is_correct: false,
      correct_answer: "B",
      explain_content: "见上",
    } as never);

    render(<QuizSession session={{ source: "topic", qmode: "SINGLE" }} onBack={() => undefined} />);
    await screen.findByText("2 + 2 = ？");

    await userEvent.click(screen.getByText("3"));
    await userEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText(/回答错误/)).toBeInTheDocument();
    expect(screen.getByText("正确答案：B")).toBeInTheDocument();
  });
});

describe("QuizSession · JUDGE 无 options 回退为「对/错」", () => {
  it("提供标准判断题选项（非假数据）", async () => {
    nextMock.mockResolvedValue(judgeNoOptions as never);
    render(<QuizSession session={{ source: "wrong-book" }} onBack={() => undefined} />);
    await screen.findByText("Python 的 list 可修改。");
    expect(screen.getByText("正确")).toBeInTheDocument();
    expect(screen.getByText("错误")).toBeInTheDocument();
  });
});

describe("QuizSession · 空态与错误态兜底（禁 MOCK）", () => {
  it("无题出空态", async () => {
    nextMock.mockResolvedValue(null as never);
    render(<QuizSession session={{ source: "wrong-book" }} onBack={() => undefined} />);
    expect(await screen.findByText("错题已全部复盘完成")).toBeInTheDocument();
  });

  it("拉题失败出错误态，重试可恢复", async () => {
    nextMock.mockRejectedValueOnce(new Error("contract 未就绪"));
    nextMock.mockResolvedValueOnce(singleQuestion as never);
    render(<QuizSession session={{ source: "topic", qmode: "JUDGE" }} onBack={() => undefined} />);
    expect(await screen.findByText("出题失败")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByText("2 + 2 = ？")).toBeInTheDocument());
  });
});

describe("QuizSession · 显示辅助函数", () => {
  it("modeLabel 中英映射", () => {
    expect(modeLabel("SINGLE")).toBe("单选");
    expect(modeLabel("JUDGE")).toBe("判断");
    expect(modeLabel("DRAG")).toBe("拖拽");
  });
  it("answerToString 归一化答案", () => {
    expect(answerToString(["A", "B"])).toBe("A、B");
    expect(answerToString(true)).toBe("对");
    expect(answerToString(false)).toBe("错");
    expect(answerToString(null)).toBe("—");
    expect(answerToString("B")).toBe("B");
  });
});