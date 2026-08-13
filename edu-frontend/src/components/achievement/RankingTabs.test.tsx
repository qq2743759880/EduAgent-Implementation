/**
 * RankingTabs 单测：默认日榜积分榜、Tab 切换触发对应 scope/dimension 请求、我的排名高亮。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RankingTabs } from "./RankingTabs";
import { getRankings, type RankingResponse } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getRankings: vi.fn() };
});

const mockGetRankings = vi.mocked(getRankings);

function makeRanking(scope: string, dimension: string): RankingResponse {
  return {
    scope: scope as RankingResponse["scope"],
    dimension: dimension as RankingResponse["dimension"],
    snapshot_date: "2026-08-12",
    top: [
      { rank_no: 1, user_id: 2, user_name: "学霸A", metric_value: 1200, level_no: 5, is_myself: false, badge_count: 3 },
      { rank_no: 2, user_id: 99, user_name: "我", metric_value: 800, level_no: 3, is_myself: true, badge_count: 2 },
    ],
    my_rank: { rank_no: 2, user_id: 99, user_name: "我", metric_value: 800, level_no: 3, is_myself: true, badge_count: 2 },
    source: "SNAPSHOT_OR_LIVE",
  };
}

function renderTabs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RankingTabs />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RankingTabs", () => {
  it("默认请求 DAILY + POINTS", async () => {
    mockGetRankings.mockResolvedValue(makeRanking("DAILY", "POINTS"));
    renderTabs();
    await waitFor(() => {
      expect(mockGetRankings).toHaveBeenCalledWith("DAILY", "POINTS", 20);
    });
    expect(await screen.findByText("学霸A")).toBeInTheDocument();
  });

  it("切换到周榜重新请求 WEEKLY", async () => {
    const user = userEvent.setup();
    mockGetRankings.mockResolvedValue(makeRanking("DAILY", "POINTS"));
    renderTabs();

    mockGetRankings.mockResolvedValue(makeRanking("WEEKLY", "POINTS"));
    await user.click(screen.getByRole("tab", { name: "周榜" }));

    await waitFor(() => {
      expect(mockGetRankings).toHaveBeenLastCalledWith("WEEKLY", "POINTS", 20);
    });
  });

  it("切换维度（学习时长）重新请求 STUDY_MIN", async () => {
    const user = userEvent.setup();
    mockGetRankings.mockResolvedValue(makeRanking("DAILY", "POINTS"));
    renderTabs();

    mockGetRankings.mockResolvedValue(makeRanking("DAILY", "STUDY_MIN"));
    await user.click(screen.getByRole("tab", { name: "学习时长" }));

    await waitFor(() => {
      expect(mockGetRankings).toHaveBeenLastCalledWith("DAILY", "STUDY_MIN", 20);
    });
  });

  it("is_myself 行显示「我」标记，底部展示我的排名", async () => {
    mockGetRankings.mockResolvedValue(makeRanking("DAILY", "POINTS"));
    renderTabs();
    /* 「我」标记与行用户名各出现一次（getByText 精确匹配唯一失败时用 findAllByText） */
    expect(await screen.findAllByText("我")).toHaveLength(2);
    expect(screen.getByText(/我的排名：/)).toBeInTheDocument();
    /* 「第 2 名」两处：第 2 名行的 sr-only 排名文本（a11y）+ 底部我的排名 */
    expect(screen.getAllByText("第 2 名")).toHaveLength(2);
  });
});
