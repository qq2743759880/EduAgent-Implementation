/**
 * AppShell 组件测试（fe-task00 验收①首个组件测试）。
 *
 * 覆盖：渲染（品牌/菜单 label）、激活态（matchPrefix 语义）、移动菜单交互（<768 打开 /
 * Escape 关闭 / ≥768 顶部导航可用）、a11y（关闭态 inert）。
 *
 * 注：next/link 已由 src/test/setup.ts mock 为普通 <a>；matchMedia 按用例覆写
 * （setup 默认 matches:false）。测试不依赖 next/link 运行时上下文。
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppShell, { type AppShellNavItem } from "@/components/layout/AppShell";
import { BookOpen, LayoutDashboard, Sparkles } from "lucide-react";

/** 复用 usePathname mock：默认 /courses/123（验证 matchPrefix 激活语义） */
const { pathnameMock } = vi.hoisted(() => ({
  pathnameMock: { value: "/courses/123", set: (v: string) => (pathnameMock.value = v) },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock.value,
}));

const NAV_ITEMS: AppShellNavItem[] = [
  { href: "/courses", label: "课程中心", Icon: BookOpen, matchPrefix: "/courses" },
  { href: "/dashboard", label: "学习仪表盘", Icon: LayoutDashboard },
];

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
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

function renderShell() {
  return render(
    <AppShell
      brand={{ href: "/", label: "EduAgent", Icon: Sparkles }}
      navItems={NAV_ITEMS}
      navAriaLabel="主导航"
    >
      <div>shell-children</div>
    </AppShell>,
  );
}

function getSidebar() {
  return screen.getByRole("complementary", { name: "主导航" });
}

function getDesktopNav() {
  return screen.getByRole("navigation", { name: "主导航" });
}

beforeEach(() => {
  vi.clearAllMocks();
  pathnameMock.value = "/courses/123";
});

describe("AppShell 渲染", () => {
  it("渲染品牌 label 与全部菜单 label", () => {
    renderShell();

    expect(screen.getAllByText("EduAgent").length).toBeGreaterThan(0);
    expect(within(getDesktopNav()).getByText("课程中心")).toBeInTheDocument();
    expect(within(getDesktopNav()).getByText("学习仪表盘")).toBeInTheDocument();
    expect(screen.getByText("shell-children")).toBeInTheDocument();
  });

  it("footer 缺省渲染 © EduAgent 版权行", () => {
    renderShell();
    expect(screen.getByText("© EduAgent")).toBeInTheDocument();
  });
});

describe("AppShell 激活态（matchPrefix 语义）", () => {
  it("pathname /courses/123 → 课程中心（matchPrefix=/courses）aria-current=page，其他项无", () => {
    renderShell();

    const nav = getDesktopNav();
    const courses = within(nav).getByRole("link", { name: "课程中心" });
    const dashboard = within(nav).getByRole("link", { name: "学习仪表盘" });
    expect(courses).toHaveAttribute("aria-current", "page");
    expect(dashboard).not.toHaveAttribute("aria-current");
    // 品牌链接不参与激活
    const brand = screen.getAllByRole("link", { name: /EduAgent/ })[0];
    expect(brand).not.toHaveAttribute("aria-current");
  });

  it("pathname 精确命中（/dashboard）→ 无 matchPrefix 项按 === 激活", () => {
    pathnameMock.value = "/dashboard";
    renderShell();

    const nav = getDesktopNav();
    expect(within(nav).getByRole("link", { name: "学习仪表盘" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "课程中心" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});

describe("AppShell 移动抽屉（<768px）", () => {
  it("点击打开按钮 → 移动菜单 translate-x-0 + aria-expanded=true + 聚焦首菜单项", () => {
    mockMatchMedia(false);
    renderShell();

    const openBtn = screen.getByRole("button", { name: "打开导航" });
    const sidebar = getSidebar();
    expect(sidebar).toHaveClass("-translate-x-full");
    expect(openBtn).toHaveAttribute("aria-expanded", "false");
    expect(openBtn).toHaveAttribute("aria-controls", "app-mobile-nav");

    fireEvent.click(openBtn);

    expect(sidebar).toHaveClass("translate-x-0");
    expect(openBtn).toHaveAttribute("aria-expanded", "true");
    expect(within(sidebar).getByRole("link", { name: "课程中心" })).toHaveFocus();
  });

  it("Escape 关闭抽屉 → -translate-x-full + aria-expanded=false + 焦点归还打开按钮", () => {
    mockMatchMedia(false);
    const { container } = renderShell();

    fireEvent.click(screen.getByRole("button", { name: "打开导航" }));
    const openBtn = screen.getByRole("button", { name: "打开导航" });
    const sidebar = getSidebar();
    expect(sidebar).toHaveClass("translate-x-0");

    // 根容器 keydown Escape
    fireEvent.keyDown(container.firstElementChild as Element, { key: "Escape" });

    expect(sidebar).toHaveClass("-translate-x-full");
    expect(openBtn).toHaveAttribute("aria-expanded", "false");
    expect(openBtn).toHaveFocus();
  });

  it("关闭态侧边栏 inert（移出 Tab 序与无障碍树），打开后移除", () => {
    mockMatchMedia(false);
    renderShell();

    const sidebar = getSidebar();
    expect(sidebar).toHaveAttribute("inert");

    fireEvent.click(screen.getByRole("button", { name: "打开导航" }));
    expect(sidebar).not.toHaveAttribute("inert");
  });
});

describe("AppShell 桌面（≥768px）", () => {
  it("移动打开按钮以 md:hidden 隐藏（SSR/hydration 安全保留在 DOM）；桌面顶部导航可用", () => {
    mockMatchMedia(true);
    renderShell();

    // 渲染契约（component-contracts §1.3）：汉堡按钮 md:hidden（CSS 隐藏，桌面不可交互）
    const openBtn = screen.getByRole("button", { name: "打开导航" });
    expect(openBtn).toHaveClass("md:hidden");
    expect(openBtn).toHaveAttribute("aria-expanded", "false");

    // 桌面端移动菜单不 inert，顶部导航可用
    expect(getSidebar()).not.toHaveAttribute("inert");
    expect(within(getDesktopNav()).getByRole("link", { name: "课程中心" })).toBeInTheDocument();
  });
});
