/**
 * 用户端仪表盘 API 聚合封装（G5 / fe-task06）
 *
 * 唯一数据访问入口：progress（统计看板 / 课程进度）+ users（学科偏好）+
 * gamification（徽章/积分/排行，直接复用 community.ts，不重复定义）。
 *
 * 契约口径（file:line 实证）：
 *   - GET /api/progress/dashboard?days=N        → DashboardOut（edu-agent/app/progress/schemas.py:86-94）
 *   - GET /api/progress/courses                 → ProgressCourseItem[]（schemas.py:119-126）
 *   - GET /api/users/me/profile                 → UserProfile.subject_preferences（users/schemas.py:59，default_factory=list 永不为 null）
 *   - GET /api/users/me                         → subjectPreferences: string[]（users/router.py:155-157，camelCase 降级源）
 *   - GET /api/gamification/me/badges|points|rankings → community.ts 已封装，直接 import 复用
 *
 * 错误处理（红线 4 / R-7）：读操作不 try/catch 兜底，错误向上抛 ApiError；
 * 不 catch 返回空数组/0 伪装成功。
 */
import { api } from "@/lib/api-client";
import { CHART_COLORS } from "@/lib/chart-palette";
import { type ProgressTrendPoint } from "@/components/dashboard/ProgressTrendChart";
import { type BadgeItem } from "@/components/dashboard/BadgeWallGrid";
import { type PointGainItem } from "@/components/dashboard/PointCard";
import { type RankEntry, type RankRange } from "@/components/dashboard/RankList";
import { type AbilityRadarSeries } from "@/components/dashboard/AbilityRadarChart";
import {
  type BadgeCategory,
  type BadgeListResponse,
  type PointsResponse,
  type RankingResponse,
  type RankingScope,
} from "./community";
import { SUBJECT_OPTIONS } from "@/lib/validators/profile-schemas";

/* =====================================================================
 * TYPES（对齐后端 schemas.py 实证形状）
 * ===================================================================*/

export interface DailyStatItem {
  stat_date: string; // YYYY-MM-DD（后端 date 序列化）
  study_seconds: number;
  video_ticks: number;
  homework_submitted: number;
  homework_correct_rate: number | null;
  exam_submitted: number;
  exam_avg_score: number | null;
  questions_attempted: number;
  questions_correct: number;
}

export interface DashboardOut {
  total_days: number;
  total_study_seconds: number;
  total_questions_attempted: number;
  total_questions_correct: number;
  overall_correct_rate: number | null; // 0-1 可 null
  latest_streak_days: number;
  recent_days: DailyStatItem[]; // 最新在前（service.py:422）
}

export interface ProgressCourseItem {
  series_id: number;
  series_title: string;
  overall_ratio: number; // 0-1
  total_sessions: number;
  completed_sessions: number;
}

export interface SubjectPreference {
  subject_code: string; // english/coding/math/chinese/physics
  preference_score: number; // 1-5
}

export interface DashboardKpis {
  minutesToday: number;
  exercisesToday: number;
  coursesInProgress: number;
  streakDays: number;
  accuracyPct: number | null; // null → 文案「暂无数据」
  yesterdayMinutes: number | null;
  last7ActiveDays: number;
}

export type DashboardTrendPoint = ProgressTrendPoint; // 复用组件类型（避免重复定义）

/** StreakBadge 单元格状态（组件内私有类型，此处为派生返回值定义，结构一致） */
export type DayStatus = "done" | "partial" | "rest" | "today";

/* =====================================================================
 * 数据获取（错误向上抛，不吞错）
 * ===================================================================*/

export async function getProgressDashboard(days = 14): Promise<DashboardOut> {
  const { data } = await api.get<DashboardOut>(`/api/progress/dashboard?days=${days}`);
  return data;
}

/** 严格封装：错误向上抛；不复用 learning.ts getMyCourses()（其 Array.isArray ? : [] 兜底吞错） */
export async function getProgressCourses(): Promise<ProgressCourseItem[]> {
  const { data } = await api.get<ProgressCourseItem[]>("/api/progress/courses");
  return data;
}

/**
 * 学科偏好（雷达派生输入）。snake/camel 双命名兜底：
 *   主源 = GET /api/users/me/profile 的 subject_preferences（结构化，永不为 null）；
 *   降级 = GET /api/users/me 的 subjectPreferences: string[]（code 数组）→ preference_score=5（对齐 PUT 语义）。
 * 主源字段存在（即使空数组）时不再发降级请求。
 */
export async function getMySubjectPreferences(): Promise<SubjectPreference[]> {
  const { data: profile } = await api.get<Record<string, unknown>>("/api/users/me/profile");
  const fromProfile = readSubjectPreferences(profile);
  if (fromProfile) return fromProfile;
  const { data: me } = await api.get<Record<string, unknown>>("/api/users/me");
  return readSubjectPreferences(me) ?? [];
}

function readSubjectPreferences(body: Record<string, unknown>): SubjectPreference[] | null {
  const raw = body.subject_preferences ?? body.subjectPreferences;
  if (Array.isArray(raw)) {
    if (raw.length === 0) return [];
    const first = raw[0] as unknown;
    if (first && typeof first === "object" && "subject_code" in (first as Record<string, unknown>)) {
      // 结构化 [{subject_code, preference_score}]
      const out: SubjectPreference[] = [];
      for (const item of raw) {
        const it = item as Record<string, unknown>;
        if (it && typeof it === "object" && typeof it.subject_code === "string") {
          out.push({
            subject_code: it.subject_code,
            preference_score: typeof it.preference_score === "number" ? it.preference_score : 5,
          });
        }
      }
      return out;
    }
    // string[]（subjectPreferences code 数组 / 兼容形态）→ preference_score=5
    return raw
      .filter((x): x is string => typeof x === "string")
      .map((code) => ({ subject_code: code, preference_score: 5 }));
  }
  // GET /api/users/me 的 profile.subject_preferences 兜一层
  const nested = body.profile;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const inner = readSubjectPreferences(nested as Record<string, unknown>);
    if (inner) return inner;
  }
  return null;
}

/* =====================================================================
 * 派生纯函数（可单测；调用处注释标注「派生自 …」）
 * ===================================================================*/

const clamp = (n: number, min: number, max: number): number => Math.min(Math.max(n, min), max);

/** "2026-08-13" → "08/13"；无法解析时原样返回 */
function formatDateLabel(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  return m ? `${m[2]}/${m[3]}` : isoDate;
}

/** ISO datetime → "HH:mm"（优先取字符串 T 段，避免时区偏移） */
function formatTimeHHMM(iso: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  if (m) return `${m[1]}:${m[2]}`;
  const d = new Date(iso);
  if (!Number.isNaN(d.getTime())) {
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  return "";
}

/** ISO datetime → "MM-DD"（徽章获得时间展示用） */
function formatDateShort(iso: string | null | undefined): string | undefined {
  if (!iso) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[2]}-${m[3]}` : iso.slice(0, 10);
}

/** 本地今日 "YYYY-MM-DD" */
function toLocalDateString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ── 趋势 ──
export function toProgressTrend(dash: DashboardOut): ProgressTrendPoint[] {
  // 派生自 GET /api/progress/dashboard（recent_days 最新在前，翻转成时间正序显示，末位 = 今天）
  return [...dash.recent_days].reverse().map((d) => ({
    dateLabel: formatDateLabel(String(d.stat_date)),
    minutes: Math.round(d.study_seconds / 60),
    // practiceMinutes 不设：后端 DailyStatItem 无练习分钟字段，不伪造 → hasPractice=false → 单线 + 无 legend
  }));
}

// ── KPI（4 卡，useMemo 派生）──
export function deriveDashboardKpis(dash: DashboardOut, courses: ProgressCourseItem[]): DashboardKpis {
  // 派生自 GET /api/progress/dashboard + GET /api/progress/courses
  const today = dash.recent_days[0]; // 最新在前，[0] = 今日（service.py:422）
  const yesterday = dash.recent_days[1];
  return {
    minutesToday: today ? Math.round(today.study_seconds / 60) : 0,
    exercisesToday: today ? today.questions_attempted : 0,
    coursesInProgress: courses.filter((c) => c.overall_ratio > 0 && c.overall_ratio < 1).length,
    streakDays: dash.latest_streak_days, // 权威字段
    accuracyPct:
      dash.total_questions_attempted > 0
        ? Math.round((dash.total_questions_correct / dash.total_questions_attempted) * 100)
        : null, // 除零保护：attempted=0 → null → 文案「暂无数据」
    yesterdayMinutes: yesterday ? Math.round(yesterday.study_seconds / 60) : null,
    last7ActiveDays: dash.recent_days.slice(0, 7).filter((d) => d.study_seconds > 0).length,
  };
}

// ── 打卡（StreakBadge 派生数据）──
export function deriveStreakLast7(dash: DashboardOut): { streakDays: number; last7Days: DayStatus[] } {
  // 派生自 GET /api/progress/dashboard；recent_days 最新在前 → slice(0,7).reverse() 得老→新，末位 = 今天。
  // 窗口不足 7 天时缺失的是「更早的日期」→ 前段补 rest（不占用末位今天），保证恒为 7 格且
  // 末位 = 今天语义正确（今天有学习 → done；今天无记录 → today 占位）。
  const reversed = dash.recent_days.slice(0, 7).reverse();
  const offset = 7 - reversed.length; // 前段缺失数量（更早日期）
  const last7Days: DayStatus[] = Array.from({ length: 7 }, (_, i) => {
    const d = reversed[i - offset];
    if (!d) return i === 6 ? "today" : "rest";
    if (d.study_seconds > 0) return "done";
    return i === 6 ? "today" : "rest";
  });
  return { streakDays: dash.latest_streak_days, last7Days };
}

// ── 徽章（BadgeWallGrid 映射）──
const BADGE_CATEGORY_MAP: Record<BadgeCategory, NonNullable<BadgeItem["category"]>> = {
  // 后端 3 值归并前端 2 类（contract §3；不臆造 subject/streak/explore）
  LEARNING: "social",
  ACHIEVEMENT: "achievement",
  SOCIAL: "social",
};

export function mapBadgesToWall(resp: BadgeListResponse): BadgeItem[] {
  // 派生自 GET /api/gamification/me/badges
  return resp.items.map((b) => ({
    key: b.badge_code,
    name: b.badge_name,
    description: b.badge_desc,
    unlockCondition: b.unlocked ? undefined : `${b.trigger_rule} ${b.rule_value}`,
    category: BADGE_CATEGORY_MAP[b.category] ?? "achievement",
    earned: b.unlocked,
    earnedAt: b.unlocked_at ? formatDateShort(b.unlocked_at) : undefined,
    // icon 不传（组件默认 Sparkle，避免引入多色）
  }));
}

// ── 积分（PointCard 映射 + kind 白名单）──
export function mapPointKind(pointType: string): PointGainItem["kind"] {
  // 白名单（contract §3，顺序匹配首命中）
  if (pointType.includes("BADGE")) return "badge";
  if (/(?:LIKE|COMMENT|SHARE)/.test(pointType)) return "share";
  if (pointType.includes("EXPLORE")) return "explore";
  return "study"; // 兜底
}

export function mapPointsToCard(resp: PointsResponse): {
  total: number;
  todayGain: number;
  recentGains: PointGainItem[];
} {
  // 派生自 GET /api/gamification/me/points
  const recentGains: PointGainItem[] = resp.recent_logs.map((log) => ({
    key: `log-${log.log_id}`,
    title: log.note || log.point_type, // note 优先，空则 point_type
    points: log.delta, // delta 可为负
    at: formatTimeHHMM(String(log.created_at)),
    kind: mapPointKind(log.point_type),
  }));
  const todayStr = toLocalDateString(new Date());
  // 派生：今日 logs delta 求和；当日无 log → 0（合法，gainTone=slate）
  const todayGain = resp.recent_logs
    .filter((log) => String(log.created_at).slice(0, 10) === todayStr)
    .reduce((sum, log) => sum + log.delta, 0);
  return { total: resp.total_points, todayGain, recentGains };
}

// ── 排行（RankList 映射 + range ↔ scope）──
export const RANGE_SCOPE: Record<RankRange, RankingScope> = {
  day: "DAILY",
  week: "WEEKLY",
  month: "MONTHLY",
};

export function buildRankSlice(
  resp: RankingResponse,
  range: RankRange,
): { list: RankEntry[]; myRank?: RankEntry & { totalPlayers?: number } } {
  // 派生自 GET /api/gamification/rankings；avatar/totalPlayers 后端无字段 → 不传
  // （RankList 已有首字母 fallback +「继续努力」文案）
  // 防御性一致性：请求周期与后端快照 scope 应一致（契约 RANGE_SCOPE），不一致仅提示不阻断
  const expectedScope = RANGE_SCOPE[range];
  if (expectedScope && resp.scope !== expectedScope) {
    console.warn(`[dashboard] rankings scope mismatch: requested=${expectedScope}, got=${resp.scope}`);
  }
  const list: RankEntry[] = resp.top.map((row) => ({
    rank: row.rank_no,
    userId: row.user_id,
    nickname: row.user_name || `学员${row.user_id}`,
    score: row.metric_value,
    mine: row.is_myself,
  }));
  const my = resp.my_rank;
  if (!my) return { list };
  return {
    list,
    myRank: {
      rank: my.rank_no,
      userId: my.user_id,
      nickname: my.user_name || "我",
      score: my.metric_value,
      mine: true,
    },
  };
}

// ── 雷达（派生数据：后端无分学科正确率接口）──
const RADAR_COLOR = CHART_COLORS.primary;

export function deriveAbilityRadar(overallRate: number | null, prefs: SubjectPreference[]): AbilityRadarSeries[] {
  // 派生自 GET /api/progress/dashboard.overall_correct_rate + GET /api/users/me/profile.subject_preferences
  if (overallRate == null) return []; // 无答题记录 → 空态（全 0 雷达禁止，会误读为能力为 0）
  const base = overallRate * 100; // 0-100 基础分
  if (prefs.length === 0) {
    // prefs 为空但 rate 非 null → 5 维均匀 = base（合法渲染，非空态）
    return [{ name: "我的能力", values: SUBJECT_OPTIONS.map(() => Math.round(base)), color: RADAR_COLOR, opacity: 0.24 }];
  }
  const scoreBySubject = new Map(prefs.map((p) => [p.subject_code, p.preference_score]));
  const values = SUBJECT_OPTIONS.map((code) => {
    const s = scoreBySubject.get(code);
    if (s == null) return clamp(Math.round(base), 0, 100); // 无偏好学科 → baseline（不偏移）
    return clamp(Math.round(base + (s - 3) * 5), 0, 100); // 偏好 1-5 → 偏移 (s-3)*5 ∈ ±10，clamp 0-100
  });
  // 仅「我的能力」1 组（后端无「全班平均」权威源，legend 自动隐藏）
  return [{ name: "我的能力", values, color: RADAR_COLOR, opacity: 0.24 }];
}
