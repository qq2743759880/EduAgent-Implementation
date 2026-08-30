/**
 * MeNavList 单测：J20 跳转表 7 入口全覆盖，href 与标题精确匹配。
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { MeNavList } from "./MeNavList";

describe("MeNavList（J20 跳转表）", () => {
  const expected: Array<[string, string]> = [
    ["/orders", "我的订单"],
    ["/coupons", "我的优惠券"],
    ["/favorites", "我的收藏"],
    ["/my-courses", "我的班次"],
    ["/refunds", "退款记录"],
    ["/tickets", "售后工单"],
    ["/practice/wrong-book", "错题本"],
  ];

  it("渲染 7 个入口，href 与标题一一对应（J20 表全覆盖）", () => {
    const { getAllByRole } = render(<MeNavList />);
    const links = getAllByRole("link");
    expect(links).toHaveLength(expected.length);
    const hrefs = links.map((l) => (l as HTMLAnchorElement).getAttribute("href"));
    const titles = links.map((l) => (l as HTMLAnchorElement).textContent);
    expected.forEach(([href, title], i) => {
      expect(hrefs[i]).toBe(href);
      expect(titles[i]).toContain(title);
    });
  });
});