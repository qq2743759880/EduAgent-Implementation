/**
 * curriculum-catalog 单测（task44）：
 *  - 两级导航目录：9 大类 + 二级方向
 *  - emoji / 封面渐变 / 分类徽章派生（真实 category_names → 视觉）
 *  - parsePriceRange 价格区间解析
 */
import { describe, expect, it } from "vitest";
import {
  COURSE_CATALOG,
  categoryEmoji,
  categoryLabel,
  coverEmoji,
  coverGradient,
  directionEmoji,
  parsePriceRange,
} from "./curriculum-catalog";

describe("COURSE_CATALOG · 两级导航", () => {
  it("一级学科大类 9 类（含用户方案全部大类）", () => {
    const names = COURSE_CATALOG.map((c) => c.name);
    expect(names).toEqual([
      "编程",
      "计算机系统",
      "数据与AI",
      "图形与游戏",
      "数学",
      "考研/考证/公考",
      "管理与职场",
      "企业培训",
      "校园成长",
    ]);
  });

  it("每个大类含非空二级方向", () => {
    for (const c of COURSE_CATALOG) {
      expect(c.directions.length).toBeGreaterThan(0);
    }
    // 抽查：编程 → 通用程序设计/系统级编程/脚本与自动化编程
    const prog = COURSE_CATALOG.find((c) => c.name === "编程")!;
    expect(prog.directions).toContain("通用程序设计");
    expect(prog.directions).toContain("系统级编程");
    expect(prog.directions).toContain("脚本与自动化编程");
  });
});

describe("emoji / 封面 / 徽章派生", () => {
  it("categoryEmoji 已知返回对应 emoji，未知回退 📚", () => {
    expect(categoryEmoji("编程")).toBe("💻");
    expect(categoryEmoji("数学")).toBe("📐");
    expect(categoryEmoji("未知学科")).toBe("📚");
  });

  it("directionEmoji 已知返回对应 emoji，未知回退 📚", () => {
    expect(directionEmoji("通用程序设计")).toBe("💻");
    expect(directionEmoji("脚本与自动化编程")).toBe("🤖");
    expect(directionEmoji("未知方向")).toBe("📚");
  });

  it("coverGradient 按一级学科返回糖果渐变类，未知回退糖果绿", () => {
    expect(coverGradient({ category_names: ["编程"] })).toContain("from-candy-orange");
    expect(coverGradient({ category_names: ["数学"] })).toContain("from-candy-green");
    expect(coverGradient({ category_names: ["未知"] })).toContain("from-candy-green");
    expect(coverGradient({ category_names: [] })).toContain("from-candy-green");
  });

  it("coverEmoji 优先二级方向 emoji，回退一级，再回退 📚", () => {
    expect(coverEmoji({ category_names: ["编程", "脚本与自动化编程"] })).toBe("🤖");
    expect(coverEmoji({ category_names: ["编程"] })).toBe("💻");
    expect(coverEmoji({ category_names: [] })).toBe("📚");
  });

  it("categoryLabel 优先二级方向，回退一级，再回退「课程」", () => {
    expect(categoryLabel({ category_names: ["编程", "通用程序设计"] })).toBe("通用程序设计");
    expect(categoryLabel({ category_names: ["编程"] })).toBe("编程");
    expect(categoryLabel({ category_names: [] })).toBe("课程");
  });
});

describe("parsePriceRange", () => {
  it("any / 空 → 无价格过滤", () => {
    expect(parsePriceRange("any")).toEqual({});
    expect(parsePriceRange("")).toEqual({});
  });

  it("0-2000 → min=0 max=2000", () => {
    expect(parsePriceRange("0-2000")).toEqual({ min: 0, max: 2000 });
  });

  it("3000- → 仅 min=3000", () => {
    expect(parsePriceRange("3000-")).toEqual({ min: 3000 });
  });
});
