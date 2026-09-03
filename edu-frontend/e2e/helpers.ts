import { type Page } from "@playwright/test";

/** 测试账号（真实库中已存在，非 MOCK） */
export const STUDENT = Object.freeze({ account: "stu01test", password: "Test@123456" });
export const ADMIN = Object.freeze({ account: "adm02test", password: "Test@123456" });

/** 用户端侧边导航（对齐 navigation-baseline / (user)/layout.tsx，含 Season-2 订单/工单） */
export const USER_NAV = [
  ["/community", "社区"],
  ["/chat", "AI 学习问答"],
  ["/courses", "课程中心"],
  ["/orders", "我的订单"],
  ["/tickets", "我的工单"],
  ["/dashboard", "学习仪表盘"],
  ["/practice/wrong-book", "错题 / 单词本"],
  ["/my-courses", "我的班次"],
  ["/achievements", "成就中心"],
  ["/me", "个人中心"],
] as const;

interface LoginOptions {
  /** 重试次数（不含首次尝试），dev-server 慢编译时自愈 */
  retries?: number;
  /** 重试前的冷却间隔基准 ms（随次数线性放大） */
  waitMs?: number;
}

/** 通过登录页表单登录（含可选的 redirect 校验），等待跳转；对 dev-server 慢编译做有限重试自愈 */
export async function login(
  page: Page,
  account: string,
  password: string,
  expectRedirect: string | RegExp = "/dashboard",
  opts: LoginOptions = {},
): Promise<void> {
  /* 传入 RegExp（如 admin 的多路径 `/admin/dashboard|/dashboard`）时按正则匹配；
     string 按字面量安全转义——避免把 `|` 误转义导致 waitForURL 永远失配 */
  const target =
    expectRedirect instanceof RegExp ? expectRedirect : new RegExp(expectRedirect.replace(/[.+?^${}()|[\]\\]/g, "\\$&"));
  const attempts = (opts.retries ?? 1) + 1;
  for (let tryIdx = 0; tryIdx < attempts; tryIdx++) {
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 45_000 });
    await page.getByRole("button", { name: "登录" }).first().waitFor({ state: "visible", timeout: 30_000 });
    await page.getByPlaceholder(/账号|邮箱/).first().fill(account);
    await page.getByPlaceholder(/密码|6 位以上/).first().fill(password);
    await page.getByRole("button", { name: "登录" }).first().click();
    try {
      await page.waitForURL(target, { timeout: 25_000 });
      await page.waitForLoadState("domcontentloaded").catch(() => {});
      return;
    } catch {
      if (tryIdx === attempts - 1) {
        throw new Error(`登录后未能跳转到 ${expectRedirect}（当前地址：${page.url()}）`);
      }
      await page.waitForTimeout((opts.waitMs ?? 600) * (tryIdx + 1));
    }
  }
}

/** 断言用户端主导航项均在渲染中出现（桌面可见或移动端存在于 DOM） */
export async function expectUserNav(page: Page) {
  for (const [href, label] of USER_NAV) {
    const link = page.locator(`header nav a[href="${href}"], nav a[href="${href}"]`).first();
    const count = await link.count();
    if (count === 0) throw new Error(`缺导航项 ${label} (${href})`);
  }
}

/** 断言当前 URL 精确匹配路径（忽略 query/hash） */
export function expectPath(page: Page, path: string) {
  const u = new URL(page.url());
  if (u.pathname !== path) throw new Error(`期望路径 ${path}，实际 ${u.pathname}`);
}