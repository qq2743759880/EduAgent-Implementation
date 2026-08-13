/**
 * redirect.ts 单测：open redirect 防护（对抗 #4）
 *
 * 覆盖挑战报告要求的四例：//evil.com、/\evil.com（拒绝）；
 * /admin/dashboard、/login（放行）；另补外域 URL / 伪协议 / 空值边界。
 */
import { describe, expect, it } from "vitest";
import { isSafeRedirect } from "./redirect";

describe("isSafeRedirect（open redirect 防护）", () => {
  it("拒绝协议相对路径：//evil.com（旧正则漏洞实锤）", () => {
    expect(isSafeRedirect("//evil.com")).toBe(false);
  });

  it("拒绝反斜杠协议相对路径：/\\evil.com", () => {
    expect(isSafeRedirect("/\\evil.com")).toBe(false);
  });

  it("放行站内绝对路径：/admin/dashboard", () => {
    expect(isSafeRedirect("/admin/dashboard")).toBe(true);
  });

  it("放行站内绝对路径：/login", () => {
    expect(isSafeRedirect("/login")).toBe(true);
  });

  it("放行带查询串 / hash 的站内路径", () => {
    expect(isSafeRedirect("/dashboard?tab=progress#section")).toBe(true);
  });

  it("拒绝外域完整 URL：http/https/协议相对 + 路径", () => {
    expect(isSafeRedirect("http://evil.com")).toBe(false);
    expect(isSafeRedirect("https://evil.com")).toBe(false);
    expect(isSafeRedirect("//evil.com/path")).toBe(false);
  });

  it("拒绝 javascript: 伪协议", () => {
    expect(isSafeRedirect("javascript:alert(1)")).toBe(false);
  });

  it("拒绝空值 / 纯空白 / null / undefined", () => {
    expect(isSafeRedirect("")).toBe(false);
    expect(isSafeRedirect("   ")).toBe(false);
    expect(isSafeRedirect(null)).toBe(false);
    expect(isSafeRedirect(undefined)).toBe(false);
  });
});
