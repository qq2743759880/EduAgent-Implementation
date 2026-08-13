/**
 * SeriesForm 单测（task03 验收：课程创建系列链路）
 *  - 纯函数：initialForm / validate / buildEditPayload
 *  - 渲染冒烟：创建模式弹窗关键字段存在
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  SeriesForm,
  buildEditPayload,
  initialForm,
  validate,
} from "./SeriesForm";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

describe("SeriesForm 纯函数", () => {
  it("initialForm 创建模式置空、默认 on_sale", () => {
    const f = initialForm(null);
    expect(f.series_code).toBe("");
    expect(f.sale_status).toBe("on_sale");
    expect(f.sort_no).toBe(0);
  });

  it("initialForm 编辑模式回填系列字段", () => {
    const f = initialForm({
      id: 7,
      series_code: "S-01",
      series_name: "雅思基础",
      subject_code: "english",
      level_code: "L1",
      level_name: "入门",
      description: "desc",
      cover_url: null,
      target_hours: 20,
      sale_status: "on_sale",
      sort_no: 2,
      created_at: "",
      updated_at: "",
      cohort_count: 0,
      total_session_count: 0,
    });
    expect(f.series_code).toBe("S-01");
    expect(f.subject_code).toBe("english");
    expect(f.target_hours).toBe(20);
  });

  it("validate 必填校验（编码/名称/学科/分级/分级名）", () => {
    const errs = validate(initialForm(null));
    expect(errs.series_code).toBeTruthy();
    expect(errs.series_name).toBeTruthy();
    expect(errs.subject_code).toBeTruthy();
    expect(errs.level_code).toBeTruthy();
    expect(errs.level_name).toBeTruthy();
  });

  it("validate 通过合法表单", () => {
    const f = initialForm(null);
    f.series_code = "S-01";
    f.series_name = "系列";
    f.subject_code = "math";
    f.level_code = "L2";
    f.level_name = "基础";
    expect(validate(f)).toEqual({});
  });

  it("buildEditPayload 只提交非空字段（对齐后端全 Optional PATCH）", () => {
    const f = initialForm(null);
    f.series_name = "改名";
    f.subject_code = "math";
    const patch = buildEditPayload(f);
    expect(patch.series_name).toBe("改名");
    expect(patch.series_code).toBeUndefined(); // 空编码不入补丁
    expect(patch.description).toBeUndefined(); // 空串不入补丁
  });
});

describe("SeriesForm 渲染冒烟", () => {
  it("创建模式展示核心字段", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SeriesForm open onOpenChange={() => undefined} />
      </QueryClientProvider>,
    );
    // 标题与提交按钮都可能含「创建系列」，用 getAllByText 断言存在
    expect(screen.getAllByText("创建系列").length).toBeGreaterThan(0);
    expect(screen.getByText("系列编码")).toBeInTheDocument();
    expect(screen.getByText("系列名称")).toBeInTheDocument();
    expect(screen.getByText("学科")).toBeInTheDocument();
    expect(screen.getByText("难度分级")).toBeInTheDocument();
  });
});
