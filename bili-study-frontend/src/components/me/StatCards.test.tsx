/**
 * StatCards 单测（对抗 fe-task01 #4）：后端错误时不显示 0 兜底，显示错误态。
 * 学习时长(total_watched_seconds→小时) / 完成课次(active_cohorts_count) / 积分 / 等级。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { StatCards } from "./StatCards";
import { getLearningSummary } from "@/lib/api/me";
import { getMyPoints } from "@/lib/api/community";

vi.mock("@/lib/api/me", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/me")>("@/lib/api/me");
  return { ...actual, getLearningSummary: vi.fn() };
});
vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getMyPoints: vi.fn() };
});

const mockSummary = vi.mocked(getLearningSummary);
const mockPoints = vi.mocked(getMyPoints);

function renderCards() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StatCards />
    </QueryClientProvider>,
  );
}

function resolveAll() {
  mockSummary.mockResolvedValue({
    total_watched_seconds: 244_800, // 68h
    active_cohorts_count: 24,
    homework_submitted: 10,
    exam_submitted: 4,
    exam_avg_score: 89,
  });
  mockPoints.mockResolvedValue({
    user_id: 1,
    total_points: 1280,
    level_no: 3,
    level_title: "学员",
    level_min: 2000,
    next_level_min: 5000,
    level_progress_pct: 42,
    logs_total: 0,
    recent_logs: [],
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("StatCards", () => {
  it("渲染学习时长(小时)、完成课次、积分、等级", async () => {
    resolveAll();
    renderCards();
    expect(await screen.findByText("68")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("1,280")).toBeInTheDocument();
    expect(screen.getByText("Lv.3")).toBeInTheDocument();
    expect(screen.getAllByText("学员")).not.toHaveLength(0);
  });

  it("learning-summary 或 points 后端错误时不显示 0 积分/0 时长，显示错误态", async () => {
    mockSummary.mockRejectedValue(new Error("Network"));
    mockPoints.mockResolvedValue({
      user_id: 1,
      total_points: 0,
      level_no: 1,
      level_title: "学员",
      level_min: 0,
      next_level_min: 1000,
      level_progress_pct: 0,
      logs_total: 0,
      recent_logs: [],
    });
    renderCards();
    expect(await screen.findByText(/数据概览加载失败/)).toBeInTheDocument();
    expect(screen.queryByText("学习时长")).not.toBeInTheDocument();
  });
});