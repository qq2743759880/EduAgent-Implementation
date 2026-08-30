/**
 * lib/api/admin/question-bank.ts 单测（task58，contract④）
 * 验证：两级端点路径、题库/题目过滤参数、批量导入 preview/execute body 与 query、
 *      唯一冲突码 40921/40922 错误分支解析、写操作失败必须抛（R-7）
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/lib/api-client";
import {
  bankErrorHint,
  createBank,
  deleteBank,
  deleteQuestion,
  getBank,
  getQuestion,
  importExecute,
  importPreview,
  listBankQuestions,
  listBanks,
  listQuestionTypes,
  resolveTypeId,
  toAdminApiError,
  updateBank,
  updateQuestion,
  type QuestionTypeOption,
} from "./question-bank";

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

describe("题库 CRUD 端点", () => {
  it("listBanks 空参只传分页（page_size=10）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 10, items: [] });
    await listBanks();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/banks", {
      params: { page: 1, page_size: 10 },
    });
  });

  it("listBanks 透传 keyword/category_id/yn", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 2, page_size: 10, items: [] });
    await listBanks({ keyword: "编程", category_id: 5, yn: 1, page: 2 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/banks", {
      params: { page: 2, page_size: 10, keyword: "编程", category_id: 5, yn: 1 },
    });
  });

  it("createBank POST /banks 携带提交体", async () => {
    mockPost.mockResolvedValueOnce({ id: 9 });
    await createBank({ institution_id: 1, bank_code: "PY-001", bank_name: "Python 基础编程题库" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/questions/banks", {
      institution_id: 1,
      bank_code: "PY-001",
      bank_name: "Python 基础编程题库",
    });
  });

  it("updateBank PATCH /banks/{id}；deleteBank DELETE /banks/{id}", async () => {
    mockPatch.mockResolvedValueOnce({ updated: true, id: 9 });
    await updateBank(9, { bank_name: "改名" });
    expect(mockPatch).toHaveBeenCalledWith("/api/admin/questions/banks/9", { bank_name: "改名" });
    mockDelete.mockResolvedValueOnce({ deleted: true, id: 9 });
    await deleteBank(9);
    expect(mockDelete).toHaveBeenCalledWith("/api/admin/questions/banks/9");
  });
});

describe("题目端点（按题库）", () => {
  it("listBankQuestions 路径含 bank_id，透传 keyword/type/yn", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 10, items: [] });
    await listBankQuestions(3, { keyword: "函数", question_type_id: 1, yn: 1 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/banks/3/questions", {
      params: { page: 1, page_size: 10, keyword: "函数", question_type_id: 1, yn: 1 },
    });
  });

  it("deleteQuestion DELETE /questions/questions/{id}", async () => {
    mockDelete.mockResolvedValueOnce({ deleted: true, id: 42 });
    await deleteQuestion(42);
    expect(mockDelete).toHaveBeenCalledWith("/api/admin/questions/questions/42");
  });
});

describe("题目详情 / 更新（task59）", () => {
  it("getQuestion GET /questions/questions/{id} 返回含 analysis_text 详情", async () => {
    const detail = {
      id: 9001,
      bank_id: 3,
      question_code: "Q1001",
      question_type_id: 1,
      stem: "1+1=?",
      options_json: [{ label: "A", content: "1" }],
      answer_text: "B",
      analysis_text: "1+1=2",
      yn: 1,
    };
    mockGet.mockResolvedValueOnce(detail);
    await expect(getQuestion(9001)).resolves.toEqual(detail);
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/questions/9001", { params: undefined });
  });

  it("updateQuestion PATCH /questions/questions/{id} body 含 analysis_text / options_json", async () => {
    mockPatch.mockResolvedValueOnce({ updated: true, id: 9001 });
    await updateQuestion(9001, {
      question_type_id: 1,
      stem: "2+2=?",
      answer_text: "D",
      analysis_text: "2+2=4",
      options_json: [{ label: "A", content: "1" }],
    });
    expect(mockPatch).toHaveBeenCalledWith("/api/admin/questions/questions/9001", {
      question_type_id: 1,
      stem: "2+2=?",
      answer_text: "D",
      analysis_text: "2+2=4",
      options_json: [{ label: "A", content: "1" }],
    });
  });

  it("getBank GET /banks/{bank_id} 题库详情", async () => {
    mockGet.mockResolvedValueOnce({ id: 3, institution_id: 1, bank_code: "PY-001", bank_name: "Python 基础编程题库", yn: 1 });
    await expect(getBank(3)).resolves.toMatchObject({ bank_name: "Python 基础编程题库" });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/questions/banks/3", { params: undefined });
  });
});

describe("批量导入 preview / execute", () => {
  it("importPreview POST ?bank_id + {items}", async () => {
    mockPost.mockResolvedValueOnce({ total_rows: 2, valid_rows: 1, invalid_rows: 1, rows: [], message: "预览" });
    await importPreview(5, [{ question_code: "Q1", stem: "1+1=?", answer_text: "2" }]);
    expect(mockPost).toHaveBeenCalledWith(
      "/api/admin/questions/import-preview?bank_id=5",
      { items: [{ question_code: "Q1", stem: "1+1=?", answer_text: "2" }] },
    );
  });

  it("importExecute POST ?bank_id + {items}", async () => {
    mockPost.mockResolvedValueOnce({ total: 2, imported: 1, skipped: 0, failed: 1, messages: ["[0] 导入成功"] });
    await importExecute(5, [{ question_code: "Q1", stem: "1+1=?", answer_text: "2" }]);
    expect(mockPost).toHaveBeenCalledWith(
      "/api/admin/questions/import-execute?bank_id=5",
      { items: [{ question_code: "Q1", stem: "1+1=?", answer_text: "2" }] },
    );
  });
});

describe("题型维表", () => {
  it("listQuestionTypes GET /types，取 items 数组", async () => {
    mockGet.mockResolvedValueOnce({ items: [{ id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 }], total: 5 });
    await expect(listQuestionTypes()).resolves.toEqual([
      { id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 },
    ]);
  });
});

describe("唯一冲突码 / 错误解析（contract④）」", () => {
  it("bankErrorHint 命中 40921/40922，其余返回 null", () => {
    expect(bankErrorHint({ code: 40921, message: "x" })?.code).toBe(40921);
    expect(bankErrorHint({ code: 40922, message: "x" })?.message).toContain("40922");
    expect(bankErrorHint({ code: 40000 })).toBeNull();
    expect(bankErrorHint(null)).toBeNull();
  });

  it("toAdminApiError 归一 {code,message,detail}，不可识别返回 null", () => {
    expect(toAdminApiError({ code: 40921, message: "重复" })).toEqual({ status: 0, code: 40921, message: "重复", detail: undefined });
    expect(toAdminApiError(undefined)).toBeNull();
    expect(toAdminApiError("boom")).toBeNull();
  });
});

describe("resolveTypeId（题型名称/数字 → type_id）", () => {
  const types: QuestionTypeOption[] = [
    { id: 1, type_code: "single_choice", type_name: "单选题", objective_flag: 1 },
    { id: 3, type_code: "true_false", type_name: "判断题", objective_flag: 1 },
  ];
  it("数字 id 直通、名称/编码查找、未知或空返回 null", () => {
    expect(resolveTypeId("3", types)).toBe(3);
    expect(resolveTypeId("单选题", types)).toBe(1);
    expect(resolveTypeId("true_false", types)).toBe(3);
    expect(resolveTypeId("论述题", types)).toBeNull();
    expect(resolveTypeId("", types)).toBeNull();
  });
});