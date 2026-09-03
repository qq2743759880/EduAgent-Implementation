/**
 * courses 页面四态测试（task44）：
 *  - loading：骨架 + 「查询中…」
 *  - error：ErrorState role=alert + 重试
 *  - empty：EmptyState role=status + 空态文案
 *  - success：真实卡片 + 总数 + Pagination
 * listSeries 走 vi.mock（真实 QueryClientProvider，queryKey 全参数）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CoursesHomePage from "./page";
import { listSeries, type SeriesListData, type SeriesListItem } from "@/lib/api/curriculum";

vi.mock("@/lib/api/curriculum", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/curriculum")>();
  return { ...actual, listSeries: vi.fn() };
});

const listSeriesMock = vi.mocked(listSeries);

const sampleItem: SeriesListItem = {
  id: 1001,
  institution_id: 1,
  delivery_mode: "online_live",
  series_code: "SC01001",
  series_name: "通用编程入门班",
  description: "通用编程入门（直播）真实示例",
  cover_url: null,
  target_learner_identity_codes: null,
  target_learning_goal_codes: null,
  target_grade_codes: null,
  sale_status: "on_sale",
  min_price: "2999.00",
  category_names: ["编程", "通用程序设计"],
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

/**
 * makeData — C-B（task115）后 SeriesListData 权威结构：外层 {total,page,page_size,items}。
 * page_meta 为过渡期兼容字段，页面不再消费；分页断言一律走外层 triple。
 */
function makeData(
  items: SeriesListData["items"] = [sampleItem],
  overrides: Partial<Pick<SeriesListData, "total" | "page" | "page_size">> = {},
): SeriesListData {
  return {
    total: overrides.total ?? items.length,
    page: overrides.page ?? 1,
    page_size: overrides.page_size ?? 15,
    items,
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CoursesHomePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listSeriesMock.mockReset();
});

describe("courses 页面四态", () => {
  it("loading：骨架 + 查询中…", () => {
    listSeriesMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("查询中…")).toBeInTheDocument();
    expect(screen.getByText("课程中心")).toBeInTheDocument();
  });

  it("error：ErrorState role=alert + 重试可再次请求", async () => {
    const user = userEvent.setup();
    listSeriesMock.mockRejectedValueOnce(new Error("网络开小差了"));
    listSeriesMock.mockResolvedValueOnce(makeData());
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("加载失败");
    expect(alert).toHaveTextContent("网络开小差了");
    await user.click(screen.getByRole("button", { name: /重试|重新加载/ }));
    // 标题渲染两次（封面白字 + 卡片体）
    expect((await screen.findAllByText("通用编程入门班")).length).toBeGreaterThanOrEqual(2);
  });

  it("empty：EmptyState role=status + 空态文案", async () => {
    listSeriesMock.mockResolvedValue(makeData([]));
    renderPage();
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("没有符合条件的课程");
    // 总数被 <b> 拆分，用 textContent 断言
    expect(
      screen.getByText((_, el) => el?.textContent === "共 0 门课程"),
    ).toBeInTheDocument();
  });

  it("success：真实卡片 + 总数 + Pagination", async () => {
    listSeriesMock.mockResolvedValue(makeData());
    renderPage();
    expect((await screen.findAllByText("通用编程入门班")).length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText((_, el) => el?.textContent === "共 1 门课程"),
    ).toBeInTheDocument();
    expect(screen.getByText("¥2,999")).toBeInTheDocument();
    // Pagination 渲染（C2）
    expect(screen.getByRole("navigation")).toBeInTheDocument();
  });

  it("分页权威字段：总数/页码/分页尺寸从外层 triple 读取（page_meta 兼容字段不再消费）", async () => {
    // 只返回外层 {total,page,page_size,items}，天然不含 page_meta ——
    // 若页面仍读 page_meta.total 会得到 0，断言 45 可证明读的是外层 total。
    listSeriesMock.mockResolvedValue(
      makeData([sampleItem], { total: 45, page: 3, page_size: 15 }),
    );
    renderPage();
    // 异步等待 query 解析后，总数从外层 total 渲染
    expect(
      await screen.findByText((_, el) => el?.textContent === "共 45 门课程"),
    ).toBeInTheDocument();
    // 页码也来自外层 page=3：Pagination 渲染范围为「第 31-45 条 / 共 45 条」
    // （start=(page-1)*page_size+1=31），读不到外层 page 会落到 fallback=1 → 第 1-15 条。
    expect(
      await screen.findByText("第 31-45 条 / 共 45 条"),
    ).toBeInTheDocument();
  });
});
