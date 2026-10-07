/**
 * /achievements 成就中心页测试（task53 candy-playful）：
 *  - 板块顺序：排行榜 → 积分 → 徽章墙（用户签收 achievements.html）
 *  - 各板块标题 + Hero 横幅
 * rend月份数据 mock 三个 gamification 接口，真实 QueryClientProvider。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AchievementsPageInner } from "./page";
import { getMyBadges, getMyPoints, getRankings } from "@/lib/api/community";

vi.mock("@/lib/api/community", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/community")>();
  return {
    ...actual,
    getMyBadges: vi.fn(),
    getMyPoints: vi.fn(),
    getRankings: vi.fn(),
  };
});

const badgesMock = vi.mocked(getMyBadges);
const pointsMock = vi.mocked(getMyPoints);
const rankingsMock = vi.mocked(getRankings);

function resolveAll() {
  badgesMock.mockResolvedValue({
    total: 2,
    unlocked_count: 1,
    next_milestone: "社区之星",
    items: [
      {
        badge_code: "FIRST_POST",
        badge_name: "初试锋芒",
        badge_desc: "发布第一帖",
        category: "SOCIAL",
        icon_emoji: "✍️",
        rarity: "COMMON",
        trigger_rule: "POST_CREATE",
        rule_value: 1,
        reward_points: 10,
        unlocked: true,
        unlocked_at: "2026-08-01T10:00:00",
        progress_current: 1,
        progress_required: 1,
        progress_pct: 100,
      },
    ],
  });
  pointsMock.mockResolvedValue({
    user_id: 1,
    total_points: 1280,
    level_no: 3,
    level_title: "学员",
    level_min: 2000,
    next_level_min: 5000,
    level_progress_pct: 42,
    logs_total: 1,
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
  rankingsMock.mockResolvedValue({
    scope: "DAILY",
    dimension: "POINTS",
    snapshot_date: "2026-08-12",
    top: [{ rank_no: 1, user_id: 2, user_name: "学霸A", metric_value: 1200, level_no: 5, is_myself: false, badge_count: 3 }],
    my_rank: null,
    source: "SNAPSHOT_OR_LIVE",
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AchievementsPageInner />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("/achievements 成就中心", () => {
  it("Hero 横幅 + 三大板块标题渲染", async () => {
    resolveAll();
    renderPage();
    expect(await screen.findByText("成就与成长")).toBeInTheDocument();
    expect(screen.getByText(/成就中心 · 让努力被看见/)).toBeInTheDocument();
    /* 板块标题（h2）精确匹配，「积分」维度 tab 文本不冲突 */
    expect(screen.getByRole("heading", { level: 2, name: "排行榜" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "积分" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "徽章" })).toBeInTheDocument();
  });

  it("板块顺序：排行榜 → 积分 → 徽章墙（用户签收顺序）", async () => {
    resolveAll();
    renderPage();
    await screen.findByText("排行榜");
    const main = screen.getByRole("main");
    const headings = within(main).getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["排行榜", "积分", "徽章"]);
  });

  it("真实 API 均被请求（无 MOCK 数据兜底）", async () => {
    resolveAll();
    renderPage();
    await screen.findByText("排行榜");
    expect(rankingsMock).toHaveBeenCalled();
    expect(pointsMock).toHaveBeenCalled();
    expect(badgesMock).toHaveBeenCalled();
  });
});