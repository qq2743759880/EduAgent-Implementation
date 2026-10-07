/**
 * EmptyState(C7) / ErrorState(C8) / FilterBar(C9) 单测。
 *  a11y：EmptyState role=status、ErrorState role=alert（不吞错）、FilterBar role=group。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "../empty-state";
import { ErrorState } from "../error-state";
import { FilterBar } from "../filter-bar";
import { Button } from "../button";

describe("C7 EmptyState", () => {
  it("渲染 文案 + 可选 CTA，role=status", () => {
    render(
      <EmptyState
        title="暂无优惠券"
        description="去领取一张吧"
        action={<Button size="sm">去领券</Button>}
      />,
    );
    const el = screen.getByRole("status");
    expect(el).toHaveTextContent("暂无优惠券");
    expect(el).toHaveTextContent("去领取一张吧");
    expect(screen.getByRole("button", { name: "去领券" })).toBeInTheDocument();
  });
});

describe("C8 ErrorState · 不吞错", () => {
  it("展示原始 message + 重试按钮，role=alert", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<ErrorState message="GET /api/series 500: 后端处理超时" retry={retry} />);
    const el = screen.getByRole("alert");
    expect(el).toHaveTextContent("GET /api/series 500: 后端处理超时");
    const btn = screen.getByRole("button", { name: "重试" });
    await user.click(btn);
    expect(retry).toHaveBeenCalled();
  });

  it("未传 retry 时隐藏重试按钮（错误信息仍展示）", () => {
    render(<ErrorState message="网络异常" />);
    expect(screen.getByRole("alert")).toHaveTextContent("网络异常");
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  });
});

describe("C9 FilterBar", () => {
  it("容器 role=group + aria-label，透传 children", () => {
    render(
      <FilterBar>
        <input aria-label="搜索" placeholder="搜索" />
        <select aria-label="状态" />
      </FilterBar>,
    );
    const group = screen.getByRole("group", { name: "筛选条件" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "搜索" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "状态" })).toBeInTheDocument();
  });
});