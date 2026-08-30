/**
 * task46 课程详情组件测试：
 *  - CohortList：班次卡渲染 / 满员 disabled / 选择回调
 *  - FavoriteButton：aria-pressed 双通道 + aria-label 切换
 *  - CourseDetailHero：价格联动（选中班次 + 券后实付）+ 满员锁定
 *  - CourseDetailSyllabus：模块 stage_no 升序 → 课次 session_no 升序 + teaching_status 徽章
 *  - CouponPicker：模板渲染 / 已领取禁用领取 / 领取回调
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CohortList } from "./CohortList";
import { FavoriteButton } from "./FavoriteButton";
import { CourseDetailHero } from "./CourseDetailHero";
import { CourseDetailSyllabus } from "./CourseDetailSyllabus";
import { CouponPicker } from "./CouponPicker";
import type { Cohort, ModuleWithSessions, SeriesDetail } from "@/lib/api/curriculum";
import type { Coupon, CouponTemplate } from "@/lib/api/coupons";

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

const series: SeriesDetail = {
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

const modules: ModuleWithSessions[] = [
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
        session_no: 2,
        session_title: "条件分支",
        teaching_status: "in_progress",
        checkin_required: 1,
        teaching_date: "2027-01-12",
        start_time: "19:00",
        end_time: "20:30",
        videos: [],
      },
      {
        id: 32,
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
    ],
  },
];

const template: CouponTemplate = {
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

const coupon: Coupon = {
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

describe("CohortList", () => {
  it("渲染班次名/价格/余席；满员班次 disabled", () => {
    const onSelect = vi.fn();
    render(<CohortList cohorts={[cohortA, cohortFull]} selectedId={11} onSelect={onSelect} />);
    expect(screen.getByText("暑期一班")).toBeInTheDocument();
    expect(screen.getByText("秋季二班")).toBeInTheDocument();
    expect(screen.getByText("已满员")).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios[0]).not.toBeDisabled();
    expect(radios[1]).toBeDisabled();
  });

  it("选择班次触发 onSelect(id)", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<CohortList cohorts={[cohortA]} selectedId={null} onSelect={onSelect} />);
    await user.click(screen.getByRole("radio"));
    expect(onSelect).toHaveBeenCalledWith(11);
  });
});

describe("FavoriteButton", () => {
  it("aria-pressed 双通道 + aria-label 随状态切换", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const { rerender } = render(
      <FavoriteButton favorited={false} onToggle={onToggle} seriesName="通用编程入门班" />,
    );
    const btn = screen.getByRole("button", { name: "收藏 通用编程入门班" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await user.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(<FavoriteButton favorited={true} onToggle={onToggle} seriesName="通用编程入门班" />);
    expect(screen.getByRole("button", { name: "取消收藏 通用编程入门班" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("CourseDetailHero", () => {
  it("价格联动：选中班次价 + 券后实付", async () => {
    render(
      <CourseDetailHero
        series={series}
        cohorts={[cohortA]}
        selectedCohortId={11}
        onSelectCohort={vi.fn()}
        coupon={coupon}
        onOpenCoupon={vi.fn()}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onEnroll={vi.fn()}
        enrolling={false}
        authed
      />,
    );
    // 券后实付 2999 - 100 = 2899（报名按钮 + 实付行多处出现）
    expect((await screen.findAllByText("¥2,899")).length).toBeGreaterThanOrEqual(1);
    // 已选券按钮文案
    expect(screen.getByRole("button", { name: /已选券 -¥100/ })).toBeInTheDocument();
  });

  it("满员班次：报名按钮 disabled 且文案「该班次已满员」", () => {
    render(
      <CourseDetailHero
        series={series}
        cohorts={[cohortFull]}
        selectedCohortId={13}
        onSelectCohort={vi.fn()}
        coupon={null}
        onOpenCoupon={vi.fn()}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onEnroll={vi.fn()}
        enrolling={false}
        authed
      />,
    );
    const enroll = screen.getByRole("button", { name: /该班次已满员/ });
    expect(enroll).toBeDisabled();
  });
});

describe("CourseDetailSyllabus", () => {
  it("模块 stage_no 升序 → 课次 session_no 升序 + teaching_status 徽章", () => {
    render(<CourseDetailSyllabus cohortName="寒假三班" modules={modules} />);
    // 课次按 session_no 升序：变量与类型(1) 在 条件分支(2) 前
    const titles = screen.getAllByText(/变量与类型|条件分支/).map((el) => el.textContent);
    expect(titles.indexOf("变量与类型")).toBeLessThan(titles.indexOf("条件分支"));
    // teaching_status 双通道徽章（文字）
    expect(screen.getByText("未开始")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
  });
});

describe("CouponPicker", () => {
  it("模板渲染 + 领取回调；已领取禁用领取", async () => {
    const user = userEvent.setup();
    const onReceive = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <CouponPicker
        open
        onOpenChange={vi.fn()}
        templates={[template]}
        templatesLoading={false}
        receivedCoupons={[]}
        onReceive={onReceive}
        selectedCouponId={null}
        onSelectCoupon={vi.fn()}
      />,
    );
    expect(screen.getByText("领券中心")).toBeInTheDocument();
    expect(screen.getByText("新学员立减券")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /领取/ }));
    expect(onReceive).toHaveBeenCalledWith(501);

    // 已领取：领取按钮消失 → 显示「已领取」+ 抵扣 radio
    rerender(
      <CouponPicker
        open
        onOpenChange={vi.fn()}
        templates={[template]}
        templatesLoading={false}
        receivedCoupons={[coupon]}
        onReceive={onReceive}
        selectedCouponId={null}
        onSelectCoupon={vi.fn()}
      />,
    );
    expect(screen.getByText("已领取")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /领取/ })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /抵扣/ })).toBeInTheDocument();
  });
});
