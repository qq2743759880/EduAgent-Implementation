/**
 * CohortCard 单测（task47）：
 *  - 三态渲染：active（进度+下次课+继续学习）/ completed（结课+查看证书）/ refunded（灰色+退款单+查看退款）
 *  - a11y：进度条 role="progressbar" + aria-valuenow；状态由文案承载
 *  - 跳转：继续学习 → /learning/{seriesId}/{sessionId}；已退款 → /refunds
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CohortCard } from "./cohort-card";
import type { EnrolledCohort } from "@/lib/api/enrollments";

const base: EnrolledCohort = {
  enrollment_id: 1,
  cohort_id: 11,
  series_id: 1001,
  series_name: "通用编程",
  cohort_name: "通用编程入门班 · 暑期一班",
  delivery_mode: "online_live",
  subject_code: "programming",
  level_code: "L1",
  enroll_status: "active",
  overall_ratio: 0.68,
  module_done: 4,
  module_total: 6,
  session_done: 16,
  session_total: 24,
  next_session: {
    session_id: 55,
    session_title: "变量与类型",
    module_title: "模块一",
    teaching_at: "2026-03-08 09:00",
  },
};

describe("CohortCard · active 学习中", () => {
  it("渲染班次/系列/状态徽章/进度/下次课", () => {
    render(<CohortCard data={base} />);
    expect(screen.getByText("通用编程入门班 · 暑期一班")).toBeInTheDocument();
    expect(screen.getByText(/通用编程 · 在线直播/)).toBeInTheDocument();
    expect(screen.getByText("学习中")).toBeInTheDocument();
    expect(screen.getByText("68%")).toBeInTheDocument();
    expect(screen.getByText("变量与类型")).toBeInTheDocument();
    expect(screen.getByText("03-08 09:00")).toBeInTheDocument();
    // 四级进度：模块/课次
    expect(screen.getByText("4/6")).toBeInTheDocument();
    expect(screen.getByText("16/24")).toBeInTheDocument();
  });

  it("进度条 a11y：role=progressbar + aria-valuenow", () => {
    render(<CohortCard data={base} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "68");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-label");
  });

  it("继续学习 → /learning/{seriesId}/{sessionId}", () => {
    render(<CohortCard data={base} />);
    const link = screen.getByRole("link", { name: /继续学习/ });
    expect(link).toHaveAttribute("href", "/learning/1001/55");
  });
});

describe("CohortCard · completed 已完成", () => {
  const done: EnrolledCohort = {
    ...base,
    enroll_status: "completed",
    overall_ratio: 1,
    module_done: 6,
    module_total: 6,
    session_done: 24,
    session_total: 24,
    finished_at: "2026-06-30",
    next_session: null,
  };
  it("渲染已完成徽章 + 100% + 结课 + 查看证书", () => {
    render(<CohortCard data={done} />);
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText(/2026-06-30/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看证书/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /写评价/ })).toBeInTheDocument();
  });
});

describe("CohortCard · refunded 已退款（灰色态）", () => {
  const refunded: EnrolledCohort = {
    ...base,
    enroll_status: "refunded",
    refund: { refund_no: "RF20260812001", refund_amount: "¥2,999", refunded_at: "2026-08-12" },
  };
  it("渲染已退款徽章 + 退款单 + 查看退款（不渲染进度条）", () => {
    render(<CohortCard data={refunded} />);
    expect(screen.getAllByText("已退款").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/RF20260812001/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看退款/ })).toHaveAttribute("href", "/refunds");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});