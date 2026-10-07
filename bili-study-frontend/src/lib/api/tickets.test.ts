/**
 * tickets.ts API 封装单测（task100 Season-2：我的工单契约）
 * 覆盖：我的工单列表（status/ticket_type 过滤）、工单详情、新建工单、
 * 满意度评价（score/comment）。mock http.* 直接返回业务体（拦截器已解包）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  createTicket,
  getTicket,
  listMyTickets,
  submitTicketSatisfaction,
  type Ticket,
} from "./tickets";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

function makeTicket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    ticket_id: 101,
    ticket_no: "TK2026081300001",
    user_id: 1,
    order_no: "E20260813000001",
    ticket_type: "consult",
    title: "课程咨询",
    content: "想了解班次安排",
    status: "open",
    reply: null,
    satisfaction_score: null,
    satisfaction_comment: null,
    created_at: "2026-08-13T09:12:00",
    updated_at: "2026-08-13T09:12:00",
    closed_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listMyTickets", () => {
  it("默认分页参数透传（page/page_size 到后端分页壳）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 100, items: [] });
    await listMyTickets({ page: 1, page_size: 100 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/after_sales/tickets", {
      params: { page: 1, page_size: 100 },
    });
  });

  it("status + ticket_type 过滤传后端权威枚举值", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listMyTickets({ status: "processing", ticket_type: "appeal", page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/after_sales/tickets", {
      params: { status: "processing", ticket_type: "appeal", page: 1, page_size: 20 },
    });
  });

  it("空列表正常返回空 items（不抛错）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    const resp = await listMyTickets();
    expect(resp.items).toEqual([]);
  });

  it("失败向上抛（页面负责错误态，不静默返回空）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(listMyTickets()).rejects.toThrow("Network Error");
  });
});

describe("getTicket（工单详情）", () => {
  it("按 id 取详情，含 reply + satisfaction 字段", async () => {
    const detail = makeTicket({
      status: "resolved",
      reply: "已由教务老师答复",
      satisfaction_score: null,
    });
    mockGet.mockResolvedValueOnce(detail);
    const resp = await getTicket(101);
    expect(mockGet).toHaveBeenCalledWith("/api/trade/after_sales/ticket/101");
    expect(resp.ticket_id).toBe(101);
    expect(resp.reply).toBe("已由教务老师答复");
    expect(resp.satisfaction_score).toBeNull();
  });
});

describe("createTicket（新建工单）", () => {
  it("body 字段完整透传（order_no 可选）", async () => {
    mockPost.mockResolvedValueOnce(makeTicket({ status: "open" }));
    await createTicket({
      order_no: "E20260813000001",
      ticket_type: "refund",
      title: "申请退款跟进",
      content: "订单已超过可走流程时间",
    });
    expect(mockPost).toHaveBeenCalledWith("/api/trade/after_sales/ticket", {
      order_no: "E20260813000001",
      ticket_type: "refund",
      title: "申请退款跟进",
      content: "订单已超过可走流程时间",
    });
  });

  it("无 order_no 时省略该字段（非订单类咨询工单）", async () => {
    mockPost.mockResolvedValueOnce(makeTicket());
    await createTicket({ ticket_type: "consult", title: "咨询", content: "开班时间?" });
    expect(mockPost).toHaveBeenCalledWith("/api/trade/after_sales/ticket", {
      ticket_type: "consult",
      title: "咨询",
      content: "开班时间?",
    });
  });

  it("创建失败向上抛（不吞错）", async () => {
    mockPost.mockRejectedValueOnce(new Error("工单已存在"));
    await expect(
      createTicket({ ticket_type: "other", title: "x", content: "y" }),
    ).rejects.toThrow("工单已存在");
  });
});

describe("submitTicketSatisfaction（满意度评价）", () => {
  it("默认只传 score/comment 两个字段", async () => {
    mockPost.mockResolvedValueOnce({ ticket_id: 101, satisfaction_score: 5, submitted: true });
    const resp = await submitTicketSatisfaction(101, {
      satisfaction_score: 5,
      satisfaction_comment: "处理及时，很满意",
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/trade/after_sales/ticket/101/satisfaction",
      { satisfaction_score: 5, satisfaction_comment: "处理及时，很满意" },
    );
    expect(resp.submitted).toBe(true);
  });

  it("评分下界/上界透传（1~5）不做前端二次限制", async () => {
    mockPost.mockResolvedValueOnce({ ticket_id: 101, satisfaction_score: 1, submitted: true });
    await submitTicketSatisfaction(101, { satisfaction_score: 1 });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/trade/after_sales/ticket/101/satisfaction",
      { satisfaction_score: 1 },
    );
  });
});