/**
 * Pagination 单测（task41 C2）：
 *  - 页码区间 + 总数文案 + 上/下页边界 disabled
 *  - 交互：onPageChange 回传正确页码
 *  a11y：nav[aria-label=分页导航] + 上/下页按钮 aria-label + aria-live 区间
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pagination } from "../pagination";

describe("Pagination · 区间与边界", () => {
  it("page=1/total=45/pageSize=20 显示首区间 + 上一页禁用", () => {
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={() => {}} />);
    expect(screen.getByText("第 1-20 条 / 共 45 条")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();
  });

  it("末页下一页禁用", () => {
    render(<Pagination page={3} pageSize={20} total={45} onPageChange={() => {}} />);
    expect(screen.getByText("第 41-45 条 / 共 45 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });

  it("total=0 显示共 0 条且上下页均禁用", () => {
    render(<Pagination page={1} total={0} onPageChange={() => {}} />);
    expect(screen.getByText("共 0 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });
});

describe("Pagination · 交互与 a11y", () => {
  it("点击下一页回调 onPageChange(2)", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(<Pagination page={1} pageSize={20} total={60} onPageChange={onPageChange} />);
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("page 越界时钳制到合法范围（page>totalPages）", () => {
    render(<Pagination page={99} pageSize={20} total={10} onPageChange={() => {}} />);
    // totalPages=1，页码显示钳制为 1/1
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("a11y：导航 role 与按钮 aria-label", () => {
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={() => {}} />);
    const nav = screen.getByRole("navigation", { name: "分页导航" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toHaveAccessibleName("上一页");
    expect(screen.getByRole("button", { name: "下一页" })).toHaveAccessibleName("下一页");
  });

  it("disabled 时交互全部禁用", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={onPageChange} disabled />);
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(onPageChange).not.toHaveBeenCalled();
  });
});