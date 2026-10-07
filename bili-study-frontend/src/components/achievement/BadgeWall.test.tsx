/**
 * BadgeWall 单测：已解锁高亮显示、未解锁置灰 + 解锁进度、统计头。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { BadgeWall } from "./BadgeWall";
import { getMyBadges, type BadgeListResponse } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getMyBadges: vi.fn() };
});

const mockGetMyBadges = vi.mocked(getMyBadges);

function makeBadges(): BadgeListResponse {
  return {
    total: 8,
    unlocked_count: 2,
    next_milestone: "社区之星（再发 3 帖）",
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
      {
        badge_code: "POST_10",
        badge_name: "社区之星",
        badge_desc: "累计发帖 10 篇",
        category: "SOCIAL",
        icon_emoji: "🌟",
        rarity: "RARE",
        trigger_rule: "POST_CREATE",
        rule_value: 10,
        reward_points: 50,
        unlocked: false,
        unlocked_at: null,
        progress_current: 3,
        progress_required: 10,
        progress_pct: 30,
      },
    ],
  };
}

function renderWall() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BadgeWall />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BadgeWall", () => {
  it("展示已解锁统计与下一枚提示", async () => {
    mockGetMyBadges.mockResolvedValue(makeBadges());
    renderWall();
    expect(await screen.findByText(/已解锁 2 \/ 8 枚/)).toBeInTheDocument();
    expect(screen.getByText(/下一枚：社区之星/)).toBeInTheDocument();
  });

  it("已解锁徽章显示解锁态（+积分）", async () => {
    mockGetMyBadges.mockResolvedValue(makeBadges());
    renderWall();
    expect(await screen.findByText("初试锋芒")).toBeInTheDocument();
    expect(screen.getByText(/\+10 积分 · 已解锁/)).toBeInTheDocument();
    /* 卡片不携带冗余 aria-label（内部文本即完整信息，避免读屏器重复朗读） */
    expect(screen.queryByLabelText("徽章 初试锋芒（已解锁）")).not.toBeInTheDocument();
  });

  it("未解锁徽章显示进度数字（progress_current/required）", async () => {
    mockGetMyBadges.mockResolvedValue(makeBadges());
    renderWall();
    expect(await screen.findByText("社区之星")).toBeInTheDocument();
    expect(screen.getByText("3/10")).toBeInTheDocument();
    /* 进度条带 progressbar 语义（aria-valuenow 与文本一致） */
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
    expect(screen.queryByLabelText("徽章 社区之星（未解锁）")).not.toBeInTheDocument();
  });

  it("接口失败显示错误态而非空态", async () => {
    mockGetMyBadges.mockRejectedValue(new Error("500"));
    renderWall();
    expect(await screen.findByText(/徽章加载失败/)).toBeInTheDocument();
  });

  it("全部解锁（unlocked_count=total）显示「已满级」，不再展示下一枚占位文案（对抗 fe-task01 #5）", async () => {
    const badges = makeBadges();
    badges.total = 8;
    badges.unlocked_count = 8;
    badges.next_milestone = "已解锁全部徽章，继续积累学习时长吧"; // 后端满级时的兜底占位
    mockGetMyBadges.mockResolvedValue(badges);
    renderWall();
    expect(await screen.findByText(/已满级：8 枚徽章全部解锁/)).toBeInTheDocument();
    expect(screen.queryByText(/下一枚：/)).not.toBeInTheDocument();
  });
});
