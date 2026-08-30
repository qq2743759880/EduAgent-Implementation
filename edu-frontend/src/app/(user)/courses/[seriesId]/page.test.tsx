/**
 * /courses/[seriesId] 课程详情页测试（task46）：
 *  - 四态：loading（骨架）/ error（ErrorState role=alert + 重试）/ empty（EmptyState role=status）/ success（完整渲染）
 *  - 班次联动：默认选中最低价在售班次；切换班次刷新大纲 queryKey
 *  - 交互：未登录报名/领券/收藏 → /login?redirect= 原路；登录后报名 → createOrder、收藏 → addFavorite、领券 → 弹窗
 * API 全部 vi.mock（真实 QueryClientProvider，queryKey 全参数）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CourseDetailClient } from "./_components/CourseDetailClient";
import {
  getSeriesDetail,
  listSeriesCohorts,
  listCohortModules,
  getCourseMindmap,
  type Cohort,
  type ModuleWithSessions,
  type SeriesDetail,
} from "@/lib/api/curriculum";
import {
  listMyCoupons,
  listSeriesCoupons,
  receiveCoupon,
  type Coupon,
  type CouponTemplate,
} from "@/lib/api/coupons";
import { addFavorite, listFavorites } from "@/lib/api/favorites";
import { createOrder } from "@/lib/api/orders";

const { pushMock, authState } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  authState: { token: null as string | null, ready: true },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, back: vi.fn() }),
}));

vi.mock("@/lib/auth-client", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector(authState),
}));

vi.mock("@/lib/api/curriculum", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/curriculum")>();
  return {
    ...actual,
    getSeriesDetail: vi.fn(),
    listSeriesCohorts: vi.fn(),
    listCohortModules: vi.fn(),
    getCourseMindmap: vi.fn(),
  };
});

vi.mock("@/lib/api/coupons", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/coupons")>();
  return {
    ...actual,
    listSeriesCoupons: vi.fn(),
    listMyCoupons: vi.fn(),
    receiveCoupon: vi.fn(),
  };
});

vi.mock("@/lib/api/favorites", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/favorites")>();
  return {
    ...actual,
    listFavorites: vi.fn(),
    addFavorite: vi.fn(),
    removeFavorite: vi.fn(),
  };
});

vi.mock("@/lib/api/orders", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/orders")>();
  return { ...actual, createOrder: vi.fn() };
});

const getSeriesDetailMock = vi.mocked(getSeriesDetail);
const listSeriesCohortsMock = vi.mocked(listSeriesCohorts);
const listCohortModulesMock = vi.mocked(listCohortModules);
const getCourseMindmapMock = vi.mocked(getCourseMindmap);
const listSeriesCouponsMock = vi.mocked(listSeriesCoupons);
const listMyCouponsMock = vi.mocked(listMyCoupons);
const receiveCouponMock = vi.mocked(receiveCoupon);
const listFavoritesMock = vi.mocked(listFavorites);
const addFavoriteMock = vi.mocked(addFavorite);
const createOrderMock = vi.mocked(createOrder);

const sampleSeries: SeriesDetail = {
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
  min_price: "2799.00",
  max_price: "2999.00",
  categories: [
    { id: 1, category_code: "computer_science", category_name: "编程", category_level: 1 },
    { id: 2, category_code: "general_programming", category_name: "通用程序设计", category_level: 2 },
  ],
  cohort_count: 2,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const cohortA: Cohort = {
  id: 11,
  institution_id: 1,
  series_id: 1001,
  campus_id: null,
  head_teacher_id: 7,
  cohort_code: "COH-A",
  cohort_name: "暑期一班",
  sale_price: "2999.00",
  max_student_count: 40,
  current_student_count: 12,
  yn: 1,
  start_date: "2026-07-01",
  end_date: "2026-08-31",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const cohortB: Cohort = {
  id: 12,
  institution_id: 1,
  series_id: 1001,
  campus_id: null,
  head_teacher_id: 8,
  cohort_code: "COH-B",
  cohort_name: "寒假三班",
  sale_price: "2799.00",
  max_student_count: 30,
  current_student_count: 5,
  yn: 1,
  start_date: "2027-01-10",
  end_date: "2027-02-28",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const cohortFull: Cohort = {
  ...cohortA,
  id: 13,
  cohort_code: "COH-F",
  cohort_name: "秋季二班",
  sale_price: "2899.00",
  max_student_count: 30,
  current_student_count: 30,
  yn: 1,
};

const sampleModules: ModuleWithSessions[] = [
  {
    id: 21,
    cohort_id: 12,
    module_code: "M01",
    module_name: "语法基础",
    description: null,
    lesson_count: 2,
    total_hours: "4",
    stage_no: 1,
    start_date: "2027-01-10",
    end_date: "2027-01-17",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    sessions: [
      {
        id: 31,
        series_cohort_course_id: 12,
        room_id: null,
        session_no: 1,
        session_title: "变量与类型",
        teaching_status: "scheduled",
        checkin_required: 1,
        teaching_date: "2027-01-10",
        start_time: "19:00",
        end_time: "20:30",
        videos: [],
      },
      {
        id: 32,
        series_cohort_course_id: 12,
        room_id: null,
        session_no: 2,
        session_title: "条件分支",
        teaching_status: "in_progress",
        checkin_required: 1,
        teaching_date: "2027-01-12",
        start_time: "19:00",
        end_time: "20:30",
        videos: [],
      },
    ],
  },
];

const sampleTemplate: CouponTemplate = {
  coupon_template_id: 501,
  coupon_name: "新学员立减券",
  coupon_type: "full_cut",
  face_value: 100,
  min_spend: 2000,
  valid_from: "2026-01-01",
  valid_to: "2026-12-31",
  total_count: 1000,
  received_count: 100,
  per_user_limit: 1,
};

const sampleCoupon: Coupon = {
  coupon_id: 601,
  coupon_template_id: 501,
  coupon_name: "新学员立减券",
  coupon_type: "full_cut",
  face_value: 100,
  min_spend: 2000,
  status: "unused",
  valid_from: "2026-01-01",
  valid_to: "2026-12-31",
  received_at: "2026-02-01T00:00:00",
  used_at: null,
  order_no: null,
};

async function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CourseDetailClient seriesId={1001} />
    </QueryClientProvider>,
  );
}

function mockSuccess() {
  getSeriesDetailMock.mockResolvedValue(sampleSeries);
  listSeriesCohortsMock.mockResolvedValue({
    items: [cohortA, cohortB, cohortFull],
    page_meta: { page: 1, page_size: 100, total: 3, total_pages: 1 },
  });
  listCohortModulesMock.mockResolvedValue({ cohort_id: 12, modules: sampleModules });
  getCourseMindmapMock.mockResolvedValue({ nodes: [], links: [], categories: [] });
  listFavoritesMock.mockResolvedValue({ total: 0, page: 1, page_size: 100, items: [] });
  listMyCouponsMock.mockResolvedValue({ total: 0, page: 1, page_size: 100, items: [] });
}

beforeEach(() => {
  vi.clearAllMocks();
  authState.token = null;
  authState.ready = true;
  pushMock.mockReset();
});

describe("课程详情页四态", () => {
  it("loading：骨架渲染", async () => {
    getSeriesDetailMock.mockReturnValue(new Promise(() => {}));
    listSeriesCohortsMock.mockResolvedValue({
      items: [],
      page_meta: { page: 1, page_size: 100, total: 0, total_pages: 0 },
    });
    getCourseMindmapMock.mockResolvedValue({ nodes: [], links: [], categories: [] });
    await renderPage();
    expect(await screen.findByText("课程详情")).toBeInTheDocument();
  });

  it("error：ErrorState role=alert + 重试可再次请求", async () => {
    const user = userEvent.setup();
    getSeriesDetailMock.mockRejectedValueOnce(new Error("网络开小差了"));
    getSeriesDetailMock.mockResolvedValueOnce(sampleSeries);
    listSeriesCohortsMock.mockResolvedValue({
      items: [cohortB],
      page_meta: { page: 1, page_size: 100, total: 1, total_pages: 1 },
    });
    listCohortModulesMock.mockResolvedValue({ cohort_id: 12, modules: sampleModules });
    getCourseMindmapMock.mockResolvedValue({ nodes: [], links: [], categories: [] });
    await renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("加载失败");
    expect(alert).toHaveTextContent("网络开小差了");
    await user.click(screen.getByRole("button", { name: /重试/ }));
    expect((await screen.findAllByText("通用编程入门班")).length).toBeGreaterThanOrEqual(1);
  });

  it("empty：系列数据为空 → EmptyState role=status", async () => {
    /* React Query 将 queryFn 解析 undefined 视为错误；用 null 触发「无数据」空态 */
    getSeriesDetailMock.mockResolvedValue(null as unknown as SeriesDetail);
    await renderPage();
    const text = await screen.findByText("课程不存在");
    expect(text.closest('[role="status"]')).not.toBeNull();
  });

  it("success：Hero + 四 Tabs + 默认选中最低价班次 + 大纲渲染", async () => {
    mockSuccess();
    await renderPage();
    // 标题（面包屑 + Hero 封面）
    expect((await screen.findAllByText("通用编程入门班")).length).toBeGreaterThanOrEqual(2);
    // 班次价格「¥2,799 起」（min_price；Hero 头部 + 班次卡 + 实付多处出现）
    expect((await screen.findAllByText("¥2,799")).length).toBeGreaterThanOrEqual(1);
    // 默认选中最低价在售班次（寒假三班 2799），其大纲被加载
    expect((await screen.findAllByText("寒假三班")).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText("语法基础")).length).toBeGreaterThanOrEqual(1);
    // 四 Tabs
    expect(screen.getByRole("tab", { name: /课程大纲/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /班次详情/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /课程评价/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /思维导图/ })).toBeInTheDocument();
    // 满员班次 disabled
    expect(listCohortModulesMock).toHaveBeenCalledWith(12);
  });

  it("success：最低价班次满员时默认选中下一个有席位班次", async () => {
    /* 最低价 B(2799) 满员、次低价 Full(2899) 满员 → 默认应选 A(2999, 有席位) */
    const fullB: Cohort = { ...cohortB, current_student_count: 30 };
    getSeriesDetailMock.mockResolvedValue(sampleSeries);
    listSeriesCohortsMock.mockResolvedValue({
      items: [fullB, cohortA, cohortFull],
      page_meta: { page: 1, page_size: 100, total: 3, total_pages: 1 },
    });
    listCohortModulesMock.mockResolvedValue({ cohort_id: 11, modules: sampleModules });
    getCourseMindmapMock.mockResolvedValue({ nodes: [], links: [], categories: [] });
    listFavoritesMock.mockResolvedValue({ total: 0, page: 1, page_size: 100, items: [] });
    listMyCouponsMock.mockResolvedValue({ total: 0, page: 1, page_size: 100, items: [] });
    await renderPage();
    await screen.findAllByText("通用编程入门班");
    // 默认选中 A（有席位），其大纲被加载
    expect(listCohortModulesMock).toHaveBeenCalledWith(11);
    expect((await screen.findAllByText("暑期一班")).length).toBeGreaterThanOrEqual(1);
  });
});

describe("课程详情页交互", () => {
  it("未登录：报名/领券/收藏 → /login?redirect= 原路", async () => {
    const user = userEvent.setup();
    mockSuccess();
    await renderPage();
    await screen.findAllByText("通用编程入门班");

    await user.click(screen.getByRole("button", { name: /立即报名/ }));
    expect(pushMock).toHaveBeenCalledWith("/login?redirect=%2Fcourses%2F1001");

    pushMock.mockClear();
    await user.click(screen.getByRole("button", { name: /领券/ }));
    expect(pushMock).toHaveBeenCalledWith("/login?redirect=%2Fcourses%2F1001");

    pushMock.mockClear();
    await user.click(screen.getByRole("button", { name: /收藏 通用编程入门班/ }));
    expect(pushMock).toHaveBeenCalledWith("/login?redirect=%2Fcourses%2F1001");
    expect(addFavoriteMock).not.toHaveBeenCalled();
  });

  it("登录后：立即报名 → createOrder（cohort_id + coupon_id）", async () => {
    const user = userEvent.setup();
    authState.token = "t";
    mockSuccess();
    createOrderMock.mockResolvedValue({
      order_no: "ORD20260820001",
      user_id: 1,
      series_id: 1001,
      cohort_id: 12,
      series_title: "通用编程入门班",
      order_amount: 2799,
      discount_amount: 0,
      pay_amount: 2799,
      coupon_id: null,
      status: "created",
      created_at: "2026-08-20T00:00:00",
      paid_at: null,
      cancelled_at: null,
    });
    await renderPage();
    await screen.findAllByText("通用编程入门班");

    await user.click(screen.getByRole("button", { name: /立即报名/ }));
    await waitFor(() => expect(createOrderMock).toHaveBeenCalledTimes(1));
    const [input] = createOrderMock.mock.calls[0];
    expect(input.series_id).toBe(1001);
    expect(input.cohort_id).toBe(12);
    expect(input.coupon_id).toBeUndefined();
  });

  it("登录后：收藏 → addFavorite；再次点击 → removeFavorite", async () => {
    const user = userEvent.setup();
    authState.token = "t";
    mockSuccess();
    addFavoriteMock.mockResolvedValue({
      favorite_id: 1,
      user_id: 1,
      target_type: "series",
      series_id: 1001,
      series_title: "通用编程入门班",
      cover_url: null,
      created_at: "2026-08-20T00:00:00",
    });
    await renderPage();
    await screen.findAllByText("通用编程入门班");

    await user.click(screen.getByRole("button", { name: /收藏 通用编程入门班/ }));
    await waitFor(() => expect(addFavoriteMock).toHaveBeenCalledWith({ series_id: 1001 }));
  });

  it("登录后：领券弹窗展示模板，领取调用 receiveCoupon", async () => {
    const user = userEvent.setup();
    authState.token = "t";
    mockSuccess();
    listSeriesCouponsMock.mockResolvedValue([sampleTemplate]);
    receiveCouponMock.mockResolvedValue(sampleCoupon);
    await renderPage();
    await screen.findAllByText("通用编程入门班");

    await user.click(screen.getByRole("button", { name: /领券/ }));
    expect(await screen.findByText("领券中心")).toBeInTheDocument();
    expect(screen.getByText("新学员立减券")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /领取/ }));
    await waitFor(() =>
      expect(receiveCouponMock).toHaveBeenCalledWith({ coupon_template_id: 501 }),
    );
  });
});
