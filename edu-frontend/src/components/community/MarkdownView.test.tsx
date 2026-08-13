/**
 * MarkdownView 单测（对抗 fe-task01 #1）：
 * 预览/正文渲染统一走 react-markdown 默认安全配置（skipHtml），
 * raw HTML（<img onerror=...>）不得产生 DOM 元素、不得执行脚本。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownView } from "./MarkdownView";

describe("MarkdownView（安全渲染）", () => {
  it("raw HTML <img onerror> 不渲染为 img 元素、不执行脚本（无 rehypeRaw）", () => {
    const { container } = render(
      <MarkdownView content={'<img src="x" onerror="window.__xss = 1">'} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect((window as { __xss?: number }).__xss).toBeUndefined();
  });

  it("raw HTML <script> 不被执行", () => {
    const { container } = render(
      <MarkdownView content={'<script>window.__scriptRan = true</script>'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect((window as { __scriptRan?: boolean }).__scriptRan).toBeUndefined();
  });

  it("markdown 语法仍正常渲染（标题/链接/行内代码）", () => {
    render(
      <MarkdownView content={"# 标题\n\n[链接](https://example.com)\n\n`code`"} />,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("标题");
    expect(screen.getByRole("link", { name: "链接" })).toHaveAttribute("href", "https://example.com");
  });

  it("markdown 图片语法仍渲染 img，但不带事件属性", () => {
    const { container } = render(
      <MarkdownView content={"![示意图](https://example.com/a.png)"} />,
    );
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.hasAttribute("onerror")).toBe(false);
  });
});
