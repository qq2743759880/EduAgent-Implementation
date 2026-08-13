/**
 * PointLogTable 单测（对抗 fe-task01 #4）：
 * 积分卡三态区分——后端错误时显示错误占位，绝不把积分渲染为 0。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { PointLogTable } from "./PointLogTable";
import { getMyPoints } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getMyPoints: vi.fn() };
});

const mockGetMyPoints = vi.mocked(getMyPoints);

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PointLogTable />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PointLogTable 三态", () => {
  it("后端错误时显示错误态，不显示 0 积分/0 流水", async () => {
    mockGetMyPoints.mockRejectedValue(new Error("Network Error"));

    renderTable();

    expect(await screen.findByText(/积分加载失败/)).toBeInTheDocument();
    expect(screen.queryByText("当前积分")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("加载成功显示积分与等级总览", async () => {
    mockGetMyPoints.mockResolvedValue({
      user_id: 1,
      total_points: 1280,
      level_no: 3,
      level_title: "学员",
      level_min: 2000,
      next_level_min: 5000,
      level_progress_pct: 42,
      logs_total: 6,
      recent_logs: [
        {
          log_id: 1,
          point_type: "POST_CREATE",
          delta: 5,
          balance_after: 1280,
          note: "发布帖子",
          created_at: "2026-08-12T10:00:00",
        },
      ],
    });

    renderTable();

    expect(await screen.findByText("1,280")).toBeInTheDocument();
    expect(screen.getByText(/Lv\.3 · 学员/)).toBeInTheDocument();
    expect(screen.getByText(/下一级 Lv\.4（5000 分）/)).toBeInTheDocument();
  });
});
