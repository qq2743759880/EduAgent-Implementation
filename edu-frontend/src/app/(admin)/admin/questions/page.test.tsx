/**
 * /admin/questions 页面测试（task58，contract④ 两级管理）
 *  - 两级 Tab：题库列表 → 选题库切「题目」Tab → 联动 GET /banks/{id}/questions
 *  - 「编辑/解析」跳 task59 详情路由 /admin/questions/{id}
 *  - 删除题库：Dropdown 菜单 → ConfirmDialog 二次确认 → deleteBank（软删）
 *  listBanks / listQuestionTypes / listBankQuestions / deleteBank 走 vi.mock（真实 QueryClientProvider）
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminQuestionsPage from "./page";
import type { AdminPage } from "@/lib/admin-api-types";
import {
  deleteBank,
  listBankQuestions,
  listBanks,
  listQuestionTypes,
  type QuestionBank,
  type QuestionListItem,
  type QuestionTypeOption,
} from "@/lib/api/admin/question-bank";

vi.mock("@/lib/api/admin/question-bank", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/admin/question-bank")>();
  return {
    ...actual,
    listBanks: vi.fn(),
    listQuestionTypes: vi.fn(),
    listBankQuestions: vi.fn(),
    deleteBank: vi.fn(),
  };
});

const listBanksMock = vi.mocked(listBanks);
const listTypesMock = vi.mocked(listQuestionTypes);
const listQsMock = vi.mocked(listBankQuestions);
const deleteBankMock = vi.mocked(deleteBank);

const TYPES: QuestionTypeOption[] = [
  { id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 },
  { id: 4, type_code: "fill_blank", type_name: "填空题", objective_flag: 0 },
];

const BANK: QuestionBank = {
  id: 3,
  institution_id: 1,
  category_id: 1,
  category_name: "编程",
  bank_code: "PY-001",
  bank_name: "Python 基础编程题库",
  description: null,
  question_count: 1752,
  yn: 1,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const QITEM: QuestionListItem = {
  id: 42,
  bank_id: 3,
  question_code: "Q-042",
  question_type_id: 4,
  question_type_code: "fill_blank",
  question_type_name: "填空题",
  stem: "Python 单行注释符号是 ____",
  objective_flag: 0,
  yn: 1,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

function banksPage(items: QuestionBank[] = [BANK]): AdminPage<QuestionBank> {
  return { total: items.length, page: 1, page_size: 10, items };
}
function qsPage(items: QuestionListItem[] = [QITEM]): AdminPage<QuestionListItem> {
  return { total: items.length, page: 1, page_size: 10, items };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AdminQuestionsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listBanksMock.mockReset();
  listTypesMock.mockReset();
  listQsMock.mockReset();
  deleteBankMock.mockReset();
  listBanksMock.mockResolvedValue(banksPage());
  listTypesMock.mockResolvedValue(TYPES);
  listQsMock.mockResolvedValue(qsPage());
  deleteBankMock.mockResolvedValue({ deleted: true, id: 3 });
});

describe("两级 Tab + 联动", () => {
  it("题库 Tab 展示题库列表；点击「查看题目」切到题目 Tab 并请求 /banks/{id}/questions", async () => {
    const user = userEvent.setup();
    renderPage();

    // 题库 Tab 显示题库
    await waitFor(() => expect(screen.getByTestId("bank-row")).toBeInTheDocument());
    expect(screen.getByText("Python 基础编程题库")).toBeInTheDocument();
    expect(screen.getByText(/1752/)).toBeInTheDocument();
    expect(listQsMock).not.toHaveBeenCalled();

    // 点击查看题目 → 切 Tab 并联动请求
    await user.click(screen.getByTestId("select-bank-3"));
    await waitFor(() =>
      expect(listQsMock).toHaveBeenCalledWith(3, expect.objectContaining({ page: 1, page_size: 10, yn: 1 })),
    );
    // 题目 Tab 内容出现
    expect(screen.getByText("Python 单行注释符号是 ____")).toBeInTheDocument();
  });

  it("「编辑/解析」按钮指向 task59 详情路由 /admin/questions/{id}", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByTestId("bank-row")).toBeInTheDocument());
    await user.click(screen.getByTestId("select-bank-3"));
    await waitFor(() => expect(screen.getByTestId("edit-42")).toBeInTheDocument());
    expect(screen.getByTestId("edit-42").getAttribute("href")).toBe("/admin/questions/42");
  });
});

describe("删除题库二次确认", () => {
  it("Dropdown → 删除题库 → ConfirmDialog 确认后调用 deleteBank", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByTestId("bank-row")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "题库 Python 基础编程题库 更多操作" }));
    await user.click(await screen.findByText("删除题库"));

    // ConfirmDialog 出现并展示题量警示
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/共有 1752 题/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(deleteBankMock).toHaveBeenCalledWith(3));
  });
});

describe("未选择题库时批量导入禁用", () => {
  it("初始「批量导入」按钮 disabled，选择题库后可导入", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByTestId("bank-row")).toBeInTheDocument());

    // 初始仅头部一个批量导入按钮（题目 Tab 未渲染），且 disabled
    const headerImport = screen.getByRole("button", { name: "批量导入" });
    expect(headerImport).toBeDisabled();

    await user.click(screen.getByTestId("select-bank-3"));
    await waitFor(() => expect(screen.getByTestId("edit-42")).toBeInTheDocument());
    // 选题库后出现可用的批量导入（题目 Tab 内）+ 头部按钮恢复可用
    const buttons = screen.getAllByRole("button", { name: "批量导入" });
    expect(buttons.length).toBeGreaterThan(1);
    expect(buttons.some((b) => (b as HTMLButtonElement).disabled === false)).toBe(true);
  });
});

describe("题目/题型过滤与空态", () => {
  it("切换题目 Tab（未选择时）显示空态引导", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByTestId("bank-row")).toBeInTheDocument());

    // 直接点「题目」Tab（Base UI Tab 用 onValueChange 同步 state）
    await user.click(screen.getByRole("tab", { name: /题目/ }));
    expect(screen.getByText("尚未选择题库")).toBeInTheDocument();
    expect(listQsMock).not.toHaveBeenCalled();
  });
});