/**
 * 积分板块单测（对抗 fe-task01 #4）：
 * Figure测试 PointOverview + PointLogList 两组件——后端错误时显示错误占位，绝不把积分渲染为 0。
 * PointOverview：等级/总积分/进度总览；PointLogList：流水分页列表。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { PointOverview } from "./PointOverview";
import { PointLogList } from "./PointLogList";
import { getMyPoints } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getMyPoints: vi.fn() };
});

const mockGetMyPoints = vi.mocked(getMyPoints);

function renderPoints() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PointOverview />
      <PointLogList />
    </QueryClientProvider>,
  );
}

function makePointsResponse() {
  return {
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
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("积分板块三态", () => {
  it("后端错误时不显示 0 积分/0 流水，PointOverview 显示错误态", async () => {
    mockGetMyPoints.mockRejectedValue(new Error("Network Error"));

    renderPoints();

    expect(await screen.findByText(/积分加载失败/)).toBeInTheDocument();
    expect(screen.queryByText("当前积分")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("PointOverview 显示积分与等级总览", async () => {
    mockGetMyPoints.mockResolvedValue(makePointsResponse());

    renderPoints();

    expect(await screen.findByText("1,280")).toBeInTheDocument();
    expect(screen.getByText(/Lv\.3 · 学员/)).toBeInTheDocument();
    /* <b> 内联拆分了「5000」，改用 textContent 聚合断言（可多匹配，忽略重叠节点） */
    expect(
      screen.getAllByText((_content, el) => el?.textContent?.includes("下一级 Lv.4（5000 分）") === true).length,
    ).toBeGreaterThan(0);
  });

  it("PointLogList 显示流水与余额", async () => {
    mockGetMyPoints.mockResolvedValue(makePointsResponse());

    renderPoints();

    expect(await screen.findByText("发布帖子")).toBeInTheDocument();
    expect(screen.getByText(/\+5/)).toBeInTheDocument();
    expect(screen.getByText(/余额 1,280/)).toBeInTheDocument();
  });

  it("PointOverview 满级判定：next_level_min<=level_min 显示「已达最高等级」+满进度", async () => {
    const resp = makePointsResponse();
    resp.level_no = 10;
    resp.level_title = "学神";
    resp.level_min = 50000;
    resp.next_level_min = 50000; // 最高级回退
    resp.level_progress_pct = 100;
    mockGetMyPoints.mockResolvedValue(resp);

    renderPoints();

    expect(await screen.findByText(/已达最高等级/)).toBeInTheDocument();
    expect(screen.getByText(/已达成全部等级/)).toBeInTheDocument();
  });
});