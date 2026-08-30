/**
 * RankFallback 单测（task55：热门课程榜契约缺口占位卡）
 * 验证：展示契约缺口文案与状态徽标（禁 MOCK，非数据卡）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankFallback } from "./RankFallback";

describe("RankFallback", () => {
  it("渲染热门课程榜标题与契约缺口说明", () => {
    render(<RankFallback />);
    expect(screen.getByText("热门课程榜")).toBeInTheDocument();
    expect(screen.getByText(/无 admin 全局聚合端点/)).toBeInTheDocument();
    expect(screen.getByText(/待后端 task70~91/)).toBeInTheDocument();
  });

  it("不渲染任何伪造的榜单数据（无具体课程行）", () => {
    render(<RankFallback />);
    // 契约缺口占位不应臆造课程名/订单数
    expect(screen.queryByText(/第 1 名/)).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});