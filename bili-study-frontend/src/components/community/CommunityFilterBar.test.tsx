/**
 * CommunityFilterBar（task51 糖果筛选行）单测：
 * - 版块 chips：role=group + 单选 aria-pressed，点击回传 onBoardChange
 * - 排序 select：变更回传 onSortChange
 * - 搜索：输入防抖 300ms 回传 onSearch；点搜索按钮立即回传
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommunityFilterBar } from "./CommunityFilterBar";

function setup() {
  const onBoardChange = vi.fn();
  const onSortChange = vi.fn();
  const onSearch = vi.fn();
  const utils = render(
    <CommunityFilterBar
      board=""
      onBoardChange={onBoardChange}
      sort="HOT"
      onSortChange={onSortChange}
      onSearch={onSearch}
    />,
  );
  return { onBoardChange, onSortChange, onSearch, rerender: utils.rerender };
}

describe("CommunityFilterBar", () => {
  it("渲染全部 + 4 版块 chips，选中态 aria-pressed", () => {
    setup();
    const group = screen.getByRole("group", { name: "按版块筛选" });
    expect(group).toBeInTheDocument();
    expect(screen.getByText("全部")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("数学")).toHaveAttribute("aria-pressed", "false");
  });

  it("点击版块 chip 回传 onBoardChange 并切换 aria-pressed", async () => {
    const { onBoardChange, onSearch, rerender } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByText("数学"));
    expect(onBoardChange).toHaveBeenCalledWith("math");
    expect(onSearch).not.toHaveBeenCalled();
    // 受控组件：父级更新 board 后翻转 aria-pressed
    rerender(
      <CommunityFilterBar
        board="math"
        onBoardChange={onBoardChange}
        sort="HOT"
        onSortChange={() => {}}
        onSearch={onSearch}
      />,
    );
    expect(screen.getByText("数学")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("全部")).toHaveAttribute("aria-pressed", "false");
  });

  it("排序 select 变更回传 onSortChange", async () => {
    const { onSortChange } = setup();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("排序方式"), "NEW");
    expect(onSortChange).toHaveBeenCalledWith("NEW");
  });

  it("搜索输入经防抖后回传 onSearch", async () => {
    const { onSearch } = setup();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("搜索帖子关键词"), "积分");
    await waitFor(() => expect(onSearch).toHaveBeenCalledWith("积分"));
  });

  it("点搜索按钮立即回传 onSearch（trim）", async () => {
    const { onSearch } = setup();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("搜索帖子关键词"), "崩溃 ");
    await user.click(screen.getByRole("button", { name: "搜索" }));
    expect(onSearch).toHaveBeenLastCalledWith("崩溃");
  });
});