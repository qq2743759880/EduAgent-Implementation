/**
 * Vitest 全局 setup：
 *  - 注册 jest-dom matchers
 *  - mock next/link（渲染为普通 <a>），避免依赖 App Router 上下文
 *  - jsdom 缺失的浏览器 API 补齐（matchMedia / ResizeObserver / scrollTo）
 */
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

/* ---------------- next/link → <a> ---------------- */

vi.mock("next/link", async () => {
  const React = await import("react");
  return {
    default: React.forwardRef(function NextLinkMock(
      props: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
        href: string | object;
        children?: React.ReactNode;
      },
      ref: React.Ref<HTMLAnchorElement>,
    ) {
      const href = typeof props.href === "string" ? props.href : "/";
      return React.createElement("a", { ...props, href, ref }, props.children);
    }),
  };
});

/* ---------------- jsdom 缺失 API 补齐 ---------------- */

if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  }
  if (!window.ResizeObserver) {
    /* Base UI TabsList 等组件用 `new ResizeObserver(...)`，mock 必须是构造函数 */
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.defineProperty(window, "ResizeObserver", {
      writable: true,
      value: ResizeObserverMock,
    });
  }
}
