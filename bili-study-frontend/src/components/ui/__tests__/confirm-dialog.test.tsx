/**
 * ConfirmDialog(C10) 单测：
 *  - 确认按钮 destructive 语义色 + onConfirm
 *  - 取消按钮关闭（onOpenChange） / onCancel
 *  a11y：role=dialog + 标题关联 + 可聚焦确认
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "../confirm-dialog";

describe("C10 ConfirmDialog", () => {
  it("打开时渲染标题/描述 + 确认按钮（destructive）", () => {
    render(
      <ConfirmDialog
        open
        title="确认删除该班次？"
        description="删除后学习进度将被清空，不可恢复。"
        confirmText="删除"
        onConfirm={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("确认删除该班次？")).toBeInTheDocument();
    // 标题目于 dialog 内，aria 关联由 DialogTitle(aria-labelledby) 提供
    const confirmBtn = screen.getByRole("button", { name: "删除" });
    expect(confirmBtn).toHaveClass("text-destructive");
    expect(confirmBtn).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
  });

  it("点击确认 → onConfirm 触发", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="确认？" confirmText="确定" onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "确定" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("点击取消 → onCancel 触发", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<ConfirmDialog open title="确认？" onCancel={onCancel} onConfirm={() => {}} />);
    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("confirmVariant=primary 时确认按钮走主色（default variant）", () => {
    render(<ConfirmDialog open title="确认？" confirmText="提交" confirmVariant="primary" onConfirm={() => {}} />);
    const btn = screen.getByRole("button", { name: "提交" });
    expect(btn).toHaveClass("bg-primary");
  });

  it("loading 时确认按钮禁用", () => {
    render(<ConfirmDialog open title="确认？" confirmText="删除" loading onConfirm={() => {}} />);
    expect(screen.getByRole("button", { name: "删除" })).toBeDisabled();
  });
});