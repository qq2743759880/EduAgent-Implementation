/**
 * StatusBadge 单测（task41 C3）：
 *  - 颜色+文字 双通道（无纯色块）：断言文本 + data-tone/语义色 class 同时存在
 *  - 11 组枚举映射表单源（lib/status）——statusText/statusTone/tone 断言
 *  a11y：role="status" + 文本承载语义
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../status-badge";
import { statusText, statusTone, TICKET_TYPE_TEXT, REFUND_TYPE_TEXT } from "@/lib/status";

describe("StatusBadge · 颜色+文字 双通道", () => {
  it("order_status=paid → 文字「已支付」+ success 语义色（非纯色块）", () => {
    const { container } = render(<StatusBadge map="order_status" status="paid" />);
    const badge = screen.getByRole("status");
    // 文字通道
    expect(badge).toHaveTextContent("已支付");
    // 颜色通道：语义色 class + data-tone 同时存在
    expect(badge).toHaveAttribute("data-tone", "success");
    expect(badge.className).toMatch(/text-success/);
    // 双通道：非空文本 + 有语义色类，缺一即失败
    expect(badge.textContent?.trim().length).toBeGreaterThan(0);
    expect(container.firstChild).not.toBeNull();
  });

  it("未知状态 → 原样回退展示 + neutral（不吞错，可见地暴露未映射值）", () => {
    render(<StatusBadge map="order_status" status="weird_status" />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("weird_status");
    expect(badge).toHaveAttribute("data-tone", "neutral");
  });

  it("手动传入 tone/label 覆盖映射", () => {
    render(<StatusBadge status="xx" tone="danger" label="仓库值" />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("仓库值");
    expect(badge).toHaveAttribute("data-tone", "danger");
    expect(badge.className).toMatch(/text-destructive/);
  });

  it("空状态 → 占位「-」", () => {
    render(<StatusBadge map="order_status" status={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("-");
  });
});

describe("layout 样式：不使用任意值色/固定字号（token 化）", () => {
  it("badge 基类不包含任意值色板或 text-[13px]", () => {
    const { container } = render(<StatusBadge map="delivery_mode" status="online_live" />);
    const html = container.innerHTML;
    // 命令书红线：color 一律走 shadcn 语义 class；不得引入任意值十六进制色 / 固定像素字号
    expect(html).not.toMatch(/bg-\[#/);
    expect(html).not.toMatch(/text-\[13px\]/);
    // primary 语义色走 token（bg-primary/bg-primary-soft 等，非 sky/violet/cyan/teal/fuchsia）
    expect(html).not.toMatch(/\b(sky|violet|cyan|teal|fuchsia)-\d/);
  });
});

describe("lib/status 枚举映射表（单源）", () => {
  it("order_status 全值映射 tone+文案", () => {
    expect(statusText("order_status", "pending")).toBe("待付款");
    expect(statusTone("order_status", "pending")).toBe("warning");
    expect(statusText("order_status", "refunded")).toBe("已退款");
    expect(statusTone("order_status", "refunded")).toBe("danger");
    expect(statusText("order_status", "completed")).toBe("已完成");
    expect(statusTone("order_status", "completed")).toBe("neutral");
  });

  it("payment/refund/receive/enroll/teaching/transcode/review/ticket 各权威值", () => {
    expect(statusText("payment_status", "failed")).toBe("失败");
    expect(statusTone("payment_status", "failed")).toBe("danger");
    expect(statusText("refund_status", "approved")).toBe("已通过");
    expect(statusTone("refund_status", "approved")).toBe("primary");
    expect(statusText("receive_status", "unused")).toBe("未使用");
    expect(statusTone("receive_status", "unused")).toBe("primary");
    expect(statusText("enroll_status", "active")).toBe("学习中");
    expect(statusTone("enroll_status", "active")).toBe("success");
    expect(statusText("teaching_status", "in_progress")).toBe("进行中");
    expect(statusTone("teaching_status", "in_progress")).toBe("primary");
    expect(statusText("transcode_status", "failed")).toBe("失败");
    expect(statusTone("transcode_status", "failed")).toBe("danger");
    expect(statusText("review_status", "rejected")).toBe("已驳回");
    expect(statusTone("review_status", "rejected")).toBe("danger");
    expect(statusText("ticket_status", "open")).toBe("待受理");
    expect(statusTone("ticket_status", "open")).toBe("warning");
    expect(statusText("ticket_status", "processing")).toBe("处理中");
    expect(statusTone("ticket_status", "processing")).toBe("primary");
    expect(statusText("ticket_status", "resolved")).toBe("已解决");
    expect(statusTone("ticket_status", "resolved")).toBe("success");
    expect(statusText("ticket_status", "closed")).toBe("已关闭");
    expect(statusTone("ticket_status", "closed")).toBe("neutral");
  });

  it("priority/series_sale/delivery_mode/order_item_status", () => {
    expect(statusText("priority_level", "urgent")).toBe("紧急");
    expect(statusTone("priority_level", "urgent")).toBe("danger");
    expect(statusText("priority_level", "medium")).toBe("中");
    expect(statusText("series_sale_status", "on_sale")).toBe("在售");
    expect(statusTone("series_sale_status", "on_sale")).toBe("success");
    expect(statusText("delivery_mode", "online_live")).toBe("在线直播");
    expect(statusTone("delivery_mode", "offline_face_to_face")).toBe("primary");
    expect(statusText("order_item_status", "paid")).toBe("已支付");
  });

  it("退费类型 / 工单类型纯文案枚举", () => {
    expect(REFUND_TYPE_TEXT.personal_reason).toBe("个人原因");
    expect(REFUND_TYPE_TEXT.duplicate_purchase).toBe("重复购买");
    expect(TICKET_TYPE_TEXT.after_sales).toBe("售后");
    expect(TICKET_TYPE_TEXT.appeal).toBe("人工申诉");
  });
});