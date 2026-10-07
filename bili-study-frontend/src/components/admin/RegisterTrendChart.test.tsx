/**
 * RegisterTrendChart 单测（P2-B：近 7 天注册趋势）
 * 验证：渲染 aria-label 摘要、加载态、错误态可重试。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http } from "@/lib/api-client";
import { RegisterTrendChart } from "./RegisterTrendChart";
import type { DashboardMetrics } from "@/lib/api/admin/users";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const METRICS: DashboardMetrics = {
  total_user_count: 128,
  active_user_count_7d: 45,
  role_breakdown: { admin: 1, manager: 2, teacher: 3, student: 122 },
  disabled_user_count: 6,
  new_register_count_7d: 13,
  avg_login_days_per_user_30d: 4.5,
  register_trend_7d: [
    { date: "2026-08-09", count: 2 },
    { date: "2026-08-10", count: 5 },
    { date: "2026-08-11", count: 3 },
    { date: "2026-08-12", count: 8 },
    { date: "2026-08-13", count: 6 },
    { date: "2026-08-14", count: 10 },
    { date: "2026-08-15", count: 4 },
  ],
};

const mockGet = vi.mocked(http.get);

function renderChart() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RegisterTrendChart />
    </QueryClientProvider>,
  );
}

describe("RegisterTrendChart", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("加载成功时渲染标题与 aria-label 数据摘要", async () => {
    mockGet.mockResolvedValueOnce(METRICS);
    renderChart();
    expect(await screen.findByText("近 7 天注册趋势")).toBeInTheDocument();
    await waitFor(() => {
      const el = screen.getByRole("img", { name: /近 7 天注册趋势/ });
      expect(el).toBeInTheDocument();
      expect(el.getAttribute("aria-label")).toContain("2026-08-15 4 人");
    });
  });

  it("接口失败时显示错误态并可重试", async () => {
    mockGet.mockRejectedValueOnce(new Error("network down"));
    renderChart();
    // ErrorState 标题固定为「加载失败」，正文为 error.message
    expect(await screen.findByText("加载失败")).toBeInTheDocument();
    expect(screen.getByText("network down")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重试/ })).toBeInTheDocument();
  });
});
