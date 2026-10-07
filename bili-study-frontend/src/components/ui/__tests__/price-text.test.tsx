/**
 * PriceText(C14) 单测：
 *  - formatAmount 千分位 + 空值「-」
 *  - original 划线原价 + highlight 促销高亮；tabular-nums 对齐
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PriceText, formatAmount } from "../price-text";

describe("formatAmount", () => {
  it("千分位 + 两位小数", () => {
    expect(formatAmount(12345.6)).toBe("¥12,345.60");
    expect(formatAmount("299")).toBe("¥299.00");
    expect(formatAmount(0)).toBe("¥0.00");
  });

  it("空/非法值回退「-」", () => {
    expect(formatAmount(null)).toBe("-");
    expect(formatAmount(undefined)).toBe("-");
    expect(formatAmount("")).toBe("-");
  });
});

describe("PriceText", () => {
  it("渲染金额 + tabular-nums 对齐", () => {
    const { container } = render(<PriceText amount={299} />);
    expect(screen.getByText("¥299.00")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("tabular-nums");
  });

  it("original 划线原价", () => {
    render(<PriceText amount={199} original={399} />);
    const original = screen.getByText("¥399.00");
    expect(original).toHaveClass("line-through");
    expect(original).toHaveClass("text-muted-foreground");
    expect(screen.getByText("¥199.00")).toBeInTheDocument();
  });

  it("highlight 促销强调（primary 语义色，非硬编码色）", () => {
    const { container } = render(<PriceText amount={129} highlight />);
    const price = container.querySelector(".font-semibold");
    expect(price).toHaveClass("text-primary");
    // 红线：不得用任意值十六进制色
    expect(container.innerHTML).not.toMatch(/text-\[#/);
  });
});