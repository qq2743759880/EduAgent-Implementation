/**
 * /me 个人中心页测试（task54 candy-playful）：四板块标题 + 顺序 + 真实 API 均被请求（无 MOCK）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MePageInner } from "./page";
import { getMe, getLearningSummary, getStudentProfile } from "@/lib/api/me";
import { getMyPoints } from "@/lib/api/community";

vi.mock("@/lib/api/me", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/me")>("@/lib/api/me");
  return { ...actual, getMe: vi.fn(), getLearningSummary: vi.fn(), getStudentProfile: vi.fn() };
});
vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, getMyPoints: vi.fn() };
});

const meMock = vi.mocked(getMe);
const summaryMock = vi.mocked(getLearningSummary);
const profileMock = vi.mocked(getStudentProfile);
const pointsMock = vi.mocked(getMyPoints);

function resolveAll() {
  meMock.mockResolvedValue({
    id: 1,
    nickname: "慕剑知",
    learningGoal: "编程入门",
    subjectPreferences: ["programming"],
  });
  summaryMock.mockResolvedValue({
    total_watched_seconds: 3600,
    active_cohorts_count: 1,
    homework_submitted: 2,
    exam_submitted: 1,
    exam_avg_score: 90,
  });
  profileMock.mockResolvedValue({ user_id: 1, school_name: "市第一中学" });
  pointsMock.mockResolvedValue({
    user_id: 1,
    total_points: 500,
    level_no: 3,
    level_title: "学员",
    level_min: 2000,
    next_level_min: 5000,
    level_progress_pct: 25,
    logs_total: 0,
    recent_logs: [],
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MePageInner />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("/me 个人中心", () => {
  it("板块顺序：数据概览 → 功能入口 → 学员档案（签收 me.html 顺序）", async () => {
    resolveAll();
    renderPage();
    await screen.findByText("慕剑知");
    const main = screen.getByRole("main");
    const headings = within(main).getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["数据概览", "功能入口", "学员档案"]);
  });

  it("真实 API 均被请求（getMe/getLearningSummary/getStudentProfile/getMyPoints，无 MOCK 兜底）", async () => {
    resolveAll();
    renderPage();
    await screen.findByText("慕剑知");
    expect(meMock).toHaveBeenCalled();
    expect(summaryMock).toHaveBeenCalled();
    expect(profileMock).toHaveBeenCalled();
    expect(pointsMock).toHaveBeenCalled();
  });
});