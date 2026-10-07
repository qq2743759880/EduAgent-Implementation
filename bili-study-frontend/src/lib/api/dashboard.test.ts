/**
 * dashboard.ts 聚合封装单测（fe-task06 / task40 拦截器解包迁移）
 * 覆盖：
 *   - 派生纯函数：KPI 计算（含除零保护）/ 雷达 clamp / 空态（overallRate null）/ 打卡顺序 / 趋势反转 / 映射白名单
 *   - 数据获取：query 拼装、getProgressCourses 严格抛错（不吞错）、getMySubjectPreferences 双命名兜底
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  RANGE_SCOPE,
  buildRankSlice,
  deriveAbilityRadar,
  deriveDashboardKpis,
  deriveStreakLast7,
  getMySubjectPreferences,
  getProgressCourses,
  getProgressDashboard,
  mapBadgesToWall,
  mapPointKind,
  mapPointsToCard,
  toProgressTrend,
  type DashboardOut,
  type ProgressCourseItem,
  type SubjectPreference,
} from "./dashboard";
import type { BadgeListResponse, PointsResponse, RankingResponse } from "./community";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);

beforeEach(() => {
  vi.clearAllMocks();
});

/* =====================================================================
 * fixtures
 * ===================================================================*/

function makeDashboard(overrides: Partial<DashboardOut> = {}): DashboardOut {
  return {
    total_days: 10,
    total_study_seconds: 36000,
    total_questions_attempted: 100,
    total_questions_correct: 82,
    overall_correct_rate: 0.82,
    latest_streak_days: 5,
    recent_days: [],
    ...overrides,
  };
}

function day(stat_date: string, study_seconds: number, questions_attempted = 0) {
  return {
    stat_date,
    study_seconds,
    video_ticks: 0,
    homework_submitted: 0,
    homework_correct_rate: null,
    exam_submitted: 0,
    exam_avg_score: null,
    questions_attempted,
    questions_correct: 0,
  };
}

/** 本地今日 YYYY-MM-DD（与实现 toLocalDateString 同口径） */
function localTodayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/* =====================================================================
 * toProgressTrend（趋势）
 * ===================================================================*/

describe("toProgressTrend", () => {
  it("recent_days 最新在前 → 翻转成时间正序（末位 = 今天）", () => {
    const dash = makeDashboard({
      recent_days: [day("2026-08-13", 3660), day("2026-08-12", 1800), day("2026-08-11", 0)],
    });
    const points = toProgressTrend(dash);
    expect(points.map((p) => p.dateLabel)).toEqual(["08/11", "08/12", "08/13"]);
    expect(points[0]?.minutes).toBe(0);
    expect(points[1]?.minutes).toBe(30);
    expect(points[2]?.minutes).toBe(61);
  });

  it("minutes = round(study_seconds / 60)，且不伪造 practiceMinutes（单线预期形态）", () => {
    const dash = makeDashboard({ recent_days: [day("2026-08-13", 3770)] }); // 62.8 分 → 63
    const points = toProgressTrend(dash);
    expect(points[0]?.minutes).toBe(63);
    expect("practiceMinutes" in (points[0] ?? {})).toBe(false);
  });

  it("recent_days 空数组 → 返回空数组（页面据此渲染覆盖层空态）", () => {
    expect(toProgressTrend(makeDashboard({ recent_days: [] }))).toEqual([]);
  });
});

/* =====================================================================
 * deriveDashboardKpis（KPI，含除零保护）
 * ===================================================================*/

describe("deriveDashboardKpis", () => {
  const dash = makeDashboard({
    latest_streak_days: 7,
    recent_days: [
      day("2026-08-13", 3660, 12), // 今日：61 分钟 / 12 道
      day("2026-08-12", 1800), // 昨日：30 分钟
      day("2026-08-11", 120),
      day("2026-08-10", 0),
      day("2026-08-09", 600),
      day("2026-08-08", 0),
      day("2026-08-07", 900),
      day("2026-08-06", 0),
    ],
  });

  it("今日/昨日分钟、今日练习题、streak 均从 recent_days[0]/[1] 与 latest_streak_days 派生", () => {
    const kpis = deriveDashboardKpis(dash, []);
    expect(kpis.minutesToday).toBe(61);
    expect(kpis.exercisesToday).toBe(12);
    expect(kpis.yesterdayMinutes).toBe(30);
    expect(kpis.streakDays).toBe(7);
  });

  it("coursesInProgress = overall_ratio∈(0,1) 的系列数（边界 0 / 1 不计）", () => {
    const courses: ProgressCourseItem[] = [
      { series_id: 1, series_title: "a", overall_ratio: 0.5, total_sessions: 4, completed_sessions: 2 },
      { series_id: 2, series_title: "b", overall_ratio: 1, total_sessions: 4, completed_sessions: 4 },
      { series_id: 3, series_title: "c", overall_ratio: 0, total_sessions: 4, completed_sessions: 0 },
      { series_id: 4, series_title: "d", overall_ratio: 0.99, total_sessions: 4, completed_sessions: 3 },
    ];
    expect(deriveDashboardKpis(dash, courses).coursesInProgress).toBe(2);
  });

  it("accuracyPct = correct / attempted × 100（round）", () => {
    const kpis = deriveDashboardKpis(
      makeDashboard({ total_questions_attempted: 100, total_questions_correct: 82 }),
      [],
    );
    expect(kpis.accuracyPct).toBe(82);
  });

  it("除零保护：attempted=0 → accuracyPct = null（文案「暂无数据」，非 0）", () => {
    const kpis = deriveDashboardKpis(
      makeDashboard({ total_questions_attempted: 0, total_questions_correct: 0 }),
      [],
    );
    expect(kpis.accuracyPct).toBeNull();
  });

  it("last7ActiveDays = 最近 7 天 study_seconds>0 的天数", () => {
    const kpis = deriveDashboardKpis(dash, []);
    // 最近 7 天（08-13 至 08-07）：3660/1800/120/0/600/0/900 → 5 天活跃
    expect(kpis.last7ActiveDays).toBe(5);
  });

  it("recent_days 空数组 → 今日 0 分钟合法（非空态），yesterday null", () => {
    const kpis = deriveDashboardKpis(makeDashboard({ recent_days: [] }), []);
    expect(kpis.minutesToday).toBe(0);
    expect(kpis.exercisesToday).toBe(0);
    expect(kpis.yesterdayMinutes).toBeNull();
  });
});

/* =====================================================================
 * deriveStreakLast7（打卡，顺序语义锁死）
 * ===================================================================*/

describe("deriveStreakLast7", () => {
  it("老→新顺序（末位 = 今天），学习日 done、今天无学习 today、更早无学习 rest", () => {
    const dash = makeDashboard({
      latest_streak_days: 3,
      recent_days: [
        day("2026-08-13", 0), // 今天无学习
        day("2026-08-12", 600), // 昨天
        day("2026-08-11", 0),
        day("2026-08-10", 900), // 4 天前有学习
        day("2026-08-09", 0),
        day("2026-08-08", 0),
        day("2026-08-07", 0),
      ],
    });
    const { streakDays, last7Days } = deriveStreakLast7(dash);
    expect(streakDays).toBe(3);
    expect(last7Days).toEqual(["rest", "rest", "rest", "done", "rest", "done", "today"]);
  });

  it("今天有学习 → 末位 done（有学习优先于 today 占位）", () => {
    const dash = makeDashboard({
      recent_days: [
        day("2026-08-13", 300), // 今天有学习
        day("2026-08-12", 0),
        day("2026-08-11", 0),
        day("2026-08-10", 0),
        day("2026-08-09", 0),
        day("2026-08-08", 0),
        day("2026-08-07", 0),
      ],
    });
    const { last7Days } = deriveStreakLast7(dash);
    expect(last7Days[6]).toBe("done");
    expect(last7Days[5]).toBe("rest");
  });

  it("recent_days 空 → 7 格全 rest + 末位 today（前段补位，末位今天语义正确）", () => {
    const { streakDays, last7Days } = deriveStreakLast7(makeDashboard({ recent_days: [] }));
    expect(streakDays).toBe(5);
    expect(last7Days).toHaveLength(7);
    expect(last7Days).toEqual(["rest", "rest", "rest", "rest", "rest", "rest", "today"]);
  });

  it("窗口不足 7 天 → 前段 rest 补位，末位仍为今天", () => {
    const dash = makeDashboard({
      recent_days: [day("2026-08-13", 300), day("2026-08-12", 0)], // 仅 2 天
    });
    const { last7Days } = deriveStreakLast7(dash);
    expect(last7Days).toHaveLength(7);
    expect(last7Days).toEqual(["rest", "rest", "rest", "rest", "rest", "rest", "done"]);
  });
});

/* =====================================================================
 * deriveAbilityRadar（雷达：clamp / 空态 / 单组）
 * ===================================================================*/

describe("deriveAbilityRadar", () => {
  it("overallRate null → []（空态；全 0 雷达禁止）", () => {
    expect(deriveAbilityRadar(null, [])).toEqual([]);
  });

  it("prefs 空但 rate 非 null → 5 维均匀 = base（合法渲染，非空态）", () => {
    const series = deriveAbilityRadar(0.82, []);
    expect(series).toHaveLength(1);
    expect(series[0]?.name).toBe("我的能力");
    expect(series[0]?.values).toEqual([82, 82, 82, 82, 82]);
  });

  it("偏好偏移：preference_score=5 → +10，=1 → -10；无偏好学科取 baseline 不偏移", () => {
    const prefs: SubjectPreference[] = [
      { subject_code: "english", preference_score: 5 },
      { subject_code: "math", preference_score: 1 },
    ];
    const series = deriveAbilityRadar(0.82, prefs);
    // SUBJECT_OPTIONS 顺序：english/coding/math/chinese/physics
    expect(series[0]?.values).toEqual([92, 82, 72, 82, 82]);
  });

  it("clamp：base + 偏移越界时限制在 0-100", () => {
    // base=100 + english(5-3)*5=10 → 110 → 100
    const high = deriveAbilityRadar(1, [{ subject_code: "english", preference_score: 5 }]);
    expect(high[0]?.values[0]).toBe(100);
    // base=1 + math(1-3)*5=-10 → -9 → 0
    const low = deriveAbilityRadar(0.01, [{ subject_code: "math", preference_score: 1 }]);
    expect(low[0]?.values[2]).toBe(0);
  });

  it("仅返回「我的能力」1 组（不渲染全班平均对比组）", () => {
    const series = deriveAbilityRadar(0.6, [{ subject_code: "chinese", preference_score: 4 }]);
    expect(series).toHaveLength(1);
    expect(series[0]?.values).toHaveLength(5);
  });
});

/* =====================================================================
 * mapBadgesToWall（徽章映射 + category 归并）
 * ===================================================================*/

describe("mapBadgesToWall", () => {
  const resp: BadgeListResponse = {
    total: 2,
    unlocked_count: 1,
    next_milestone: "",
    items: [
      {
        badge_code: "b-1",
        badge_name: "新手徽章",
        badge_desc: "完成第一节课",
        category: "ACHIEVEMENT",
        icon_emoji: null,
        rarity: "COMMON",
        trigger_rule: "FINISH_SESSION",
        rule_value: 1,
        reward_points: 10,
        unlocked: true,
        unlocked_at: "2026-08-12T10:00:00",
        progress_current: 1,
        progress_required: 1,
        progress_pct: 100,
      },
      {
        badge_code: "b-2",
        badge_name: "学习之星",
        badge_desc: "累计学习 10 天",
        category: "LEARNING",
        icon_emoji: null,
        rarity: "RARE",
        trigger_rule: "STUDY_DAYS",
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

  it("字段映射：badge_code→key / name / desc / unlocked→earned / unlocked_at→MM-DD", () => {
    const items = mapBadgesToWall(resp);
    expect(items[0]).toMatchObject({
      key: "b-1",
      name: "新手徽章",
      description: "完成第一节课",
      earned: true,
      earnedAt: "08-12",
      unlockCondition: undefined,
    });
  });

  it("未解锁徽章 unlockCondition = `${trigger_rule} ${rule_value}`", () => {
    const items = mapBadgesToWall(resp);
    expect(items[1]?.unlockCondition).toBe("STUDY_DAYS 10");
  });

  it("category 归并：ACHIEVEMENT→achievement、LEARNING→social、SOCIAL→social（不臆造 subject/streak/explore）", () => {
    const items = mapBadgesToWall(resp);
    expect(items[0]?.category).toBe("achievement");
    expect(items[1]?.category).toBe("social");
    const social = mapBadgesToWall({
      ...resp,
      items: [{ ...resp.items[0]!, category: "SOCIAL" as const }],
    });
    expect(social[0]?.category).toBe("social");
  });
});

/* =====================================================================
 * mapPointsToCard（积分映射 + kind 白名单 + 今日求和）
 * ===================================================================*/

describe("mapPointsToCard", () => {
  const todayStr = localTodayIso();
  const resp: PointsResponse = {
    user_id: 1,
    total_points: 1480,
    level_no: 3,
    level_title: "学员",
    level_min: 2000,
    next_level_min: 5000,
    level_progress_pct: 0,
    logs_total: 3,
    recent_logs: [
      { log_id: 1, point_type: "STUDY_CHAPTER", delta: 30, balance_after: 1480, note: "完成英语「时态 1」", created_at: `${todayStr}T09:10:00` },
      { log_id: 2, point_type: "BADGE_UNLOCK", delta: 50, balance_after: 1510, note: null, created_at: `${todayStr}T09:25:00` },
      { log_id: 3, point_type: "SHARE_NOTE", delta: -10, balance_after: 1500, note: null, created_at: "2026-07-01T12:40:00" },
    ],
  };

  it("total = total_points；title = note || point_type；at = HH:mm；points = delta（可为负）", () => {
    const card = mapPointsToCard(resp);
    expect(card.total).toBe(1480);
    expect(card.recentGains[0]).toMatchObject({ title: "完成英语「时态 1」", at: "09:10", points: 30 });
    expect(card.recentGains[1]?.title).toBe("BADGE_UNLOCK"); // note null → point_type
  });

  it("kind 白名单：BADGE→badge、SHARE→share、未知→study；今日 logs delta 求和", () => {
    const card = mapPointsToCard(resp);
    expect(card.recentGains[1]?.kind).toBe("badge");
    expect(card.recentGains[2]?.kind).toBe("share");
    // 今日两条（30 + 50）= 80；7 月的 SHARE_NOTE 不计入
    expect(card.todayGain).toBe(80);
  });

  it("当日无 log → todayGain = 0（合法，gainTone=slate）", () => {
    const card = mapPointsToCard({ ...resp, recent_logs: [] });
    expect(card.todayGain).toBe(0);
    expect(card.recentGains).toEqual([]);
  });

  it("mapPointKind 顺序匹配首命中（BADGE 优先于 EXPLORE/SHARE）", () => {
    expect(mapPointKind("BADGE_UNLOCK")).toBe("badge");
    expect(mapPointKind("SHARE_NOTE")).toBe("share");
    expect(mapPointKind("COMMENT_LIKE")).toBe("share");
    expect(mapPointKind("EXPLORE_MCP")).toBe("explore");
    expect(mapPointKind("RANDOM_UNKNOWN")).toBe("study");
    expect(mapPointKind("BADGE_AND_EXPLORE")).toBe("badge"); // 含 BADGE → 先命中 badge
  });
});

/* =====================================================================
 * buildRankSlice（排行映射 + range ↔ scope）
 * ===================================================================*/

describe("buildRankSlice", () => {
  it("RANGE_SCOPE：day/week/month → DAILY/WEEKLY/MONTHLY", () => {
    expect(RANGE_SCOPE).toEqual({ day: "DAILY", week: "WEEKLY", month: "MONTHLY" });
  });

  const resp: RankingResponse = {
    scope: "DAILY",
    dimension: "POINTS",
    snapshot_date: "2026-08-13",
    top: [
      { rank_no: 1, user_id: 10, user_name: "小明", metric_value: 3000, level_no: 5, is_myself: false, badge_count: 3 },
      { rank_no: 2, user_id: 20, user_name: null, metric_value: 2500, level_no: 4, is_myself: true, badge_count: 2 },
    ],
    my_rank: { rank_no: 2, user_id: 20, user_name: null, metric_value: 2500, level_no: 4, is_myself: true, badge_count: 2 },
    source: "SNAPSHOT_OR_LIVE",
  };

  it("top → list 映射：rank_no→rank、user_name 缺失 → 学员{user_id}、metric_value→score、is_myself→mine", () => {
    const slice = buildRankSlice(resp, "day");
    expect(slice.list).toEqual([
      { rank: 1, userId: 10, nickname: "小明", score: 3000, mine: false },
      { rank: 2, userId: 20, nickname: "学员20", score: 2500, mine: true },
    ]);
  });

  it("my_rank 存在 → myRank（mine=true，nickname 兜底「我」）；不传 avatar/totalPlayers", () => {
    const slice = buildRankSlice(resp, "day");
    expect(slice.myRank).toEqual({
      rank: 2,
      userId: 20,
      nickname: "我",
      score: 2500,
      mine: true,
    });
    expect("avatar" in slice.myRank!).toBe(false);
    expect("totalPlayers" in slice.myRank!).toBe(false);
  });

  it("my_rank null → 不设 myRank（RankList 仅渲染列表）", () => {
    const slice = buildRankSlice({ ...resp, my_rank: null }, "week");
    expect(slice.myRank).toBeUndefined();
    expect(slice.list).toHaveLength(2);
  });
});

/* =====================================================================
 * 数据获取封装（query 拼装 / 严格抛错 / 双命名兜底）
 * ===================================================================*/

describe("getProgressDashboard", () => {
  it("拼装 /api/progress/dashboard?days=14（默认）", async () => {
    mockGet.mockResolvedValueOnce(makeDashboard());
    await getProgressDashboard();
    expect(mockGet).toHaveBeenCalledWith("/api/progress/dashboard?days=14");
  });

  it("可传 days", async () => {
    mockGet.mockResolvedValueOnce(makeDashboard());
    await getProgressDashboard(7);
    expect(mockGet).toHaveBeenCalledWith("/api/progress/dashboard?days=7");
  });
});

describe("getProgressCourses（严格封装，不吞错）", () => {
  it("成功返回数组", async () => {
    mockGet.mockResolvedValueOnce([
      { series_id: 1, series_title: "a", overall_ratio: 0.5, total_sessions: 4, completed_sessions: 2 },
    ]);
    await expect(getProgressCourses()).resolves.toHaveLength(1);
    expect(mockGet).toHaveBeenCalledWith("/api/progress/courses");
  });

  it("失败向上抛（不复用 learning.ts 的 Array.isArray ? : [] 兜底）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(getProgressCourses()).rejects.toThrow("Network Error");
  });
});

describe("getMySubjectPreferences（snake/camel 双命名兜底）", () => {
  it("主源：/me/profile 结构化 subject_preferences 直接返回，不再请求 /me", async () => {
    mockGet.mockResolvedValueOnce({
      subject_preferences: [{ subject_code: "english", preference_score: 5 }],
    });
    const prefs = await getMySubjectPreferences();
    expect(prefs).toEqual([{ subject_code: "english", preference_score: 5 }]);
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it("主源 subject_preferences 空数组 → 返回 []（合法空偏好，不发降级请求）", async () => {
    mockGet.mockResolvedValueOnce({ subject_preferences: [] });
    const prefs = await getMySubjectPreferences();
    expect(prefs).toEqual([]);
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it("降级：主源无字段 → /me 的 subjectPreferences: string[] → preference_score=5", async () => {
    mockGet
      .mockResolvedValueOnce({ nickname: "x" }) // /me/profile 无 subject_preferences
      .mockResolvedValueOnce({ subjectPreferences: ["english", "math"] }); // /me
    const prefs = await getMySubjectPreferences();
    expect(prefs).toEqual([
      { subject_code: "english", preference_score: 5 },
      { subject_code: "math", preference_score: 5 },
    ]);
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it("降级：/me 的 profile.subject_preferences 结构化也兜底", async () => {
    mockGet
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({
        profile: { subject_preferences: [{ subject_code: "physics", preference_score: 4 }] },
      });
    const prefs = await getMySubjectPreferences();
    expect(prefs).toEqual([{ subject_code: "physics", preference_score: 4 }]);
  });

  it("C-A 对齐：主源无字段 → /me 顶层 subject_preferences（snake_case code 数组）优先", async () => {
    mockGet
      .mockResolvedValueOnce({ nickname: "x" }) // /me/profile 无 subject_preferences
      .mockResolvedValueOnce({ subject_preferences: ["english", "math"] }); // /me C-A snake_case
    const prefs = await getMySubjectPreferences();
    expect(prefs).toEqual([
      { subject_code: "english", preference_score: 5 },
      { subject_code: "math", preference_score: 5 },
    ]);
    expect(mockGet).toHaveBeenCalledTimes(2);
  });
});
