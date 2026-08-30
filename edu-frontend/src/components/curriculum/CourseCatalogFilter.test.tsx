/**
 * CourseCatalogFilter 单测（task44「两级导航」）：
 *  - 一级学科大类 chips（9 类 + 全部）
 *  - 选中一级后出现二级方向 chips；切换一级重置方向
 *  - 交付 / 排序 chips 与价格 Select 变更
 *  - 重置按钮恢复 DEFAULT_FILTER
 *  - 折叠摘要（summary）随条件变化
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  CourseCatalogFilter,
  DEFAULT_FILTER,
  type CourseFilterValue,
} from "./CourseCatalogFilter";

function setup(initial: CourseFilterValue = DEFAULT_FILTER) {
  const onChange = vi.fn();
  render(<CourseCatalogFilter value={initial} onChange={onChange} />);
  return { onChange };
}

describe("CourseCatalogFilter · 两级导航", () => {
  it("渲染一级学科大类（全部 + 9 类）", () => {
    setup();
    // 「全部」出现两次：学科全部 + 交付全部
    expect(screen.getAllByRole("button", { name: "全部" }).length).toBeGreaterThanOrEqual(2);
    for (const name of ["编程", "数学", "数据与AI", "校园成长"]) {
      expect(screen.getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
    }
    // 未选中一级时不显示二级方向组
    expect(screen.queryByText("方向")).not.toBeInTheDocument();
  });

  it("选中一级学科后出现二级方向 chips，切换一级重置方向", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole("button", { name: /编程/ }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTER, category: "编程", direction: "" });

    // 重新渲染为选中「编程」后，二级方向出现
    const { onChange: onChange2 } = setup({ ...DEFAULT_FILTER, category: "编程" });
    expect(screen.getByText("方向")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /通用程序设计/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /系统级编程/ })).toBeInTheDocument();

    // 点击二级方向
    await user.click(screen.getByRole("button", { name: /通用程序设计/ }));
    expect(onChange2).toHaveBeenCalledWith({
      ...DEFAULT_FILTER,
      category: "编程",
      direction: "通用程序设计",
    });
  });

  it("交付 chips 变更 delivery", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole("button", { name: "在线直播" }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTER, delivery: "online_live" });
  });

  it("排序 chips 变更 sort", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole("button", { name: "价格↑" }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTER, sort: "price_asc" });
  });

  it("重置按钮恢复 DEFAULT_FILTER", async () => {
    const user = userEvent.setup();
    const { onChange } = setup({
      category: "编程",
      direction: "通用程序设计",
      delivery: "online_live",
      price: "0-2000",
      sort: "price_asc",
    });
    await user.click(screen.getByRole("button", { name: /重置/ }));
    expect(onChange).toHaveBeenCalledWith(DEFAULT_FILTER);
  });

  it("折叠摘要随条件变化（全部课程 → 条件串联）", () => {
    setup({ ...DEFAULT_FILTER, category: "编程", delivery: "online_live" });
    expect(screen.getByText(/编程 · 在线直播/)).toBeInTheDocument();
  });
});
