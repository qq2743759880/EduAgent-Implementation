/**
 * CourseCard 单测（task44「学中玩」）：
 *  - 真实契约字段渲染：标题/编码/交付标签/分类徽章/价格「¥X 起」
 *  - 空字段显示「-」（description / min_price 空 → 无 fallback 假数据）
 *  - 整卡链接到详情页
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CourseCard } from "./CourseCard";
import type { SeriesListItem } from "@/lib/api/curriculum";

const sample: SeriesListItem = {
  id: 1001,
  institution_id: 1,
  delivery_mode: "online_live",
  series_code: "SC01001",
  series_name: "通用编程入门班",
  description: "通用编程入门（直播）真实示例",
  cover_url: null,
  target_learner_identity_codes: null,
  target_learning_goal_codes: null,
  target_grade_codes: null,
  sale_status: "on_sale",
  min_price: "2999.00",
  category_names: ["编程", "通用程序设计"],
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

describe("CourseCard · 真实数据渲染", () => {
  it("标题/编码/交付标签/分类徽章/价格「¥X 起」", () => {
    render(<CourseCard data={sample} />);
    // 标题出现两次（封面白字 + 卡片体）
    expect(screen.getAllByText("通用编程入门班").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("SC01001")).toBeInTheDocument();
    expect(screen.getByText("在线直播")).toBeInTheDocument();
    // 分类徽章：emoji + 二级方向
    expect(screen.getByText("💻 通用程序设计")).toBeInTheDocument();
    // 价格整数 + 起（C14 PriceText decimals=0）
    expect(screen.getByText("¥2,999")).toBeInTheDocument();
    expect(screen.getByText("起")).toBeInTheDocument();
    expect(screen.getByText("通用编程入门（直播）真实示例")).toBeInTheDocument();
  });

  it("整卡链接到详情页 /courses/{id}", () => {
    render(<CourseCard data={sample} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/courses/1001");
  });
});

describe("CourseCard · 空字段显示「-」（无 fallback 假数据）", () => {
  it("description 为空显示「-」", () => {
    render(<CourseCard data={{ ...sample, description: null }} />);
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("min_price 为空显示「-」且不渲染价格", () => {
    render(<CourseCard data={{ ...sample, min_price: null }} />);
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.queryByText(/¥/)).not.toBeInTheDocument();
    expect(screen.queryByText("起")).not.toBeInTheDocument();
  });
});
