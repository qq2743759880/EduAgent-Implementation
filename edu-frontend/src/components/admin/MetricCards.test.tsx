/**
 * MetricCards 单测（task03 验收：dashboard 6 指标卡渲染）
 * 数据源 GET /api/admin/users/dashboard/metrics 真实 API（mock api 层，组件无 MOCK）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { MetricCards } from "./MetricCards";
import type { DashboardMetrics } from "@/lib/api/admin/users";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(api.get);

const METRICS: DashboardMetrics = {
  total_user_count: 128,
  active_user_count_7d: 45,
  role_breakdown: { admin: 1, manager: 2, teacher: 3, student: 122 },
  disabled_user_count: 6,
  new_register_count_7d: 13,
  avg_login_days_per_user_30d: 4.5,
};

function renderCards() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MetricCards />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("MetricCards", () => {
  it("加载成功渲染 6 项指标卡（总数/7d 活跃/角色分布/禁用/7d 新增/30d 均登录）", async () => {
    mockGet.mockResolvedValueOnce({ data: METRICS });
    renderCards();

    expect(await screen.findByTestId("metric-cards")).toBeInTheDocument();
    // 6 项指标卡
    expect(screen.getByText("用户总数")).toBeInTheDocument();
    expect(screen.getByTestId("metric-用户总数")).toHaveTextContent("128");
    expect(screen.getByTestId("metric-7d 活跃用户")).toHaveTextContent("45");
    expect(screen.getByTestId("metric-禁用账号")).toHaveTextContent("6");
    expect(screen.getByTestId("metric-7d 新增注册")).toHaveTextContent("13");
    expect(screen.getByTestId("metric-30d 人均登录（天）")).toHaveTextContent("4.50");
    // 角色分布 4 项
    expect(screen.getByTestId("metric-role-admin")).toHaveTextContent("1");
    expect(screen.getByTestId("metric-role-student")).toHaveTextContent("122");
  });

  it("请求路径为 /api/admin/users/dashboard/metrics", async () => {
    mockGet.mockResolvedValueOnce({ data: METRICS });
    renderCards();
    await screen.findByTestId("metric-cards");
    expect(mockGet).toHaveBeenCalledWith("/api/admin/users/dashboard/metrics", { params: undefined });
  });

  it("加载失败渲染错误态 + 可重试（不静默吞错）", async () => {
    mockGet.mockRejectedValueOnce(new Error("后端不可用"));
    renderCards();
    expect(await screen.findByText("加载失败")).toBeInTheDocument();
    expect(screen.getByText("后端不可用")).toBeInTheDocument();
  });
});
