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
import type { SeriesCreateInput } from "@/lib/api/admin/courses";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

describe("SeriesForm 纯函数", () => {
  it("initialForm 创建模式置空、默认 draft", () => {
    const f = initialForm(null);
    expect(f.series_code).toBe("");
    expect(f.sale_status).toBe("draft");
    expect(f.delivery_mode).toBe("online_live");
    expect(f.institution_id).toBe(0);
  });

  it("initialForm 编辑模式回填系列字段", () => {
    const f = initialForm({
      id: 7,
      institution_id: 1,
      delivery_mode: "online_recorded",
      series_code: "S-01",
      series_name: "零基础 Python 入门营",
      description: "desc",
      cover_url: null,
      sale_status: "on_sale",
      created_by: 1,
      created_at: "",
      updated_at: "",
    });
    expect(f.series_code).toBe("S-01");
    expect(f.delivery_mode).toBe("online_recorded");
    expect(f.sale_status).toBe("on_sale");
  });

  it("validate 必填校验（编码/名称/机构ID/交付模式）", () => {
    const f = initialForm(null);
    // delivery_mode 有默认值 online_live，显式置空触发交付模式校验
    f.sale_status = "draft";
    (f as { delivery_mode?: string }).delivery_mode = "";
    const errs = validate(f as SeriesCreateInput);
    expect(errs.series_code).toBeTruthy();
    expect(errs.series_name).toBeTruthy();
    expect(errs.institution_id).toBeTruthy();
    expect(errs.delivery_mode).toBeTruthy();
  });

  it("validate 通过合法表单", () => {
    const f = initialForm(null);
    f.series_code = "PY-001";
    f.series_name = "入门营";
    f.institution_id = 1;
    f.delivery_mode = "online_live";
    expect(validate(f)).toEqual({});
  });

  it("buildEditPayload 只提交非空字段 + 排除不可改字段（series_code/institution_id）", () => {
    const f = initialForm(null);
    f.series_name = "改名";
    f.delivery_mode = "online_live";
    const patch = buildEditPayload(f);
    expect(patch.series_name).toBe("改名");
    expect(patch.delivery_mode).toBe("online_live");
    expect(patch.series_code).toBeUndefined(); // 编码不可改，不入补丁
    expect(patch.institution_id).toBeUndefined(); // 机构不可改，不入补丁
    expect(patch.description).toBeUndefined(); // 空串/空值不入补丁
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
    expect(screen.getByText("机构 ID")).toBeInTheDocument();
    expect(screen.getByText("交付模式")).toBeInTheDocument();
  }, 20_000);
});
