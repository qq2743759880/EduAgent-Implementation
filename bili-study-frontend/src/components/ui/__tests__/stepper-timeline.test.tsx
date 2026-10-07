/**
 * Stepper(C4) / Timeline(C6) 单测。
 *  a11y：Stepper(ol + aria-current=step + sr-only 状态文案双通道)、Timeline(ol + 节点 aria-hidden + time)。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Stepper } from "../stepper";
import { Timeline } from "../timeline";

describe("C4 Stepper", () => {
  it("渲染状态步骤 + 当前项 aria-current=step", () => {
    render(
      <Stepper
        steps={[
          { title: "提交订单", status: "done" },
          { title: "支付", status: "current" },
          { title: "报名成功", status: "todo" },
        ]}
      />,
    );
    expect(screen.getByRole("list")).toHaveAttribute("aria-label", "步骤进度");
    const items = screen.getAllByRole("listitem");
    // 当前项（第二步骤「支付」）带 aria-current=step
    expect(items[1]).toHaveAttribute("aria-current", "step");
    // 已完成项（第一步骤）不携带 aria-current
    expect(items[0]).not.toHaveAttribute("aria-current");
    // 双通道：已完成项带 sr-only 文案（读屏），current 项 sr-only「当前」
    expect(screen.getByText("已完成：")).toBeInTheDocument();
    expect(screen.getAllByText("当前：").length).toBeGreaterThan(0);
    expect(screen.getByText("提交订单")).toBeInTheDocument();
  });
});

describe("C6 Timeline", () => {
  it("渲染标题/描述/时间，节点为装饰 aria-hidden", () => {
    const { container } = render(
      <Timeline
        items={[
          { title: "退款申请已提交", description: "等待审核", time: "2026-08-19 10:00", status: "warning" },
          { title: "退款已到账", time: "2026-08-19 18:30", status: "success" },
        ]}
      />,
    );
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("退款申请已提交")).toBeInTheDocument();
    expect(screen.getByText("2026-08-19 10:00")).toBeInTheDocument();
    expect(screen.getByText("退款已到账")).toBeInTheDocument();
    // 节点全部对读屏隐藏（装饰性）
    const nodes = container.querySelectorAll("[aria-hidden='true']");
    expect(nodes.length).toBeGreaterThanOrEqual(2);
  });
});