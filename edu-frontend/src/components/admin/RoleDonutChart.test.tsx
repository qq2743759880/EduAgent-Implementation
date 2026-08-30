/**
 * RoleDonutChart 单测（task55：角色分布环形饼图）
 * 验证：渲染 aria-label 摘要、加载态、错误态可重试。
 * 数据源 GET /api/admin/users/dashboard/metrics 真实 API（mock http 层，组件无 MOCK）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http } from "@/lib/api-client";
import { RoleDonutChart } from "./RoleDonutChart";
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
  register_trend_7d: [],
};

const mockGet = vi.mocked(http.get);

function renderChart() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoleDonutChart />
    </QueryClientProvider>,
  );
}

describe("RoleDonutChart", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("加载成功时渲染标题与角色分布 aria-label 摘要", async () => {
    mockGet.mockResolvedValueOnce(METRICS);
    renderChart();
    expect(await screen.findByText("角色分布")).toBeInTheDocument();
    await waitFor(() => {
      const el = screen.getByRole("img", { name: /角色分布/ });
      expect(el).toBeInTheDocument();
      expect(el.getAttribute("aria-label")).toContain("学员 122");
    expect(el.getAttribute("aria-label")).toContain("管理员 1");
    // 图例应展示每个角色的具体人数 + 占比
    const legend = screen.getByTestId("role-dist-legend");
    const items = Array.from(legend.querySelectorAll("li"));
    expect(items).toHaveLength(4);
    expect(items[0].textContent).toContain("管理员");
    expect(items[0].textContent).toContain("1");
    expect(items[3].textContent).toContain("学员");
    expect(items[3].textContent).toContain("122");
    expect(items[3].textContent).toContain("%");
    });
  });

  it("接口失败时显示错误态并可重试", async () => {
    mockGet.mockRejectedValueOnce(new Error("network down"));
    renderChart();
    expect(await screen.findByText("加载失败")).toBeInTheDocument();
    expect(screen.getByText("network down")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重试/ })).toBeInTheDocument();
  });
});