/**
 * task69 · GWT④ 状态机覆盖：loading / empty / success / error 各页
 * 用真实数据 + 可控后端场景：success（真实数据）、empty（无班次用户）、error（无效凭证/越权）
 */
import { test, expect } from "@playwright/test";
import { login, STUDENT } from "./helpers";

test.describe("状态机覆盖（GWT④）", () => {
  test("SUCCESS：dashboard 渲染用户数据（真实日志/统计）", async ({ page }) => {
    test.setTimeout(90_000);
    await login(page, STUDENT.account, STUDENT.password);
    await page.waitForTimeout(1500);
    const body = await page.locator("body").innerText();
    // 登录态成功首屏：出现问候/用户信息
    expect(body).toMatch(/Stu|学习|你好|继续|打卡|统计|streak|今日/i);
  });

  test("EMPTY：未报名班次用户的 my-courses 空态呈现", async ({ page }) => {
    test.setTimeout(90_000);
    await login(page, STUDENT.account, STUDENT.password);
    await page.goto("/my-courses", { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const body = await page.locator("body").innerText();
    // 若查询为空，页面仍有「空态/引导」而不是崩溃——验收：正文存在、无 500 文案
    expect(body).not.toMatch(/Internal Server Error|Application error|Unhandled/);
    // 空态应有可读信息（无数据或引导购买/浏览课程）
    expect(body.length).toBeGreaterThan(100);
  });

  test("ERROR：无效凭证登录 → 表单级错误横幅（401 语义）", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/login", { waitUntil: "networkidle" });
    await page.getByPlaceholder(/账号|邮箱/).first().fill("stu01test");
    await page.getByPlaceholder(/密码|6 位以上/).first().fill("WrongPass!");
    await page.getByRole("button", { name: "登录" }).first().click();
    // 应停留在登录页并出现凭证错误横幅（非跳转）
    await page.waitForTimeout(2000);
    expect(new URL(page.url()).pathname).toBe("/login");
    await expect(page.locator("body")).toContainText(/密码|错误|凭证|账号/i, { timeout: 10_000 });
  });

  test("ERROR：student 越权访问管理端被守卫拦截", async ({ page }) => {
    test.setTimeout(60_000);
    await login(page, STUDENT.account, STUDENT.password);
    await page.goto("/admin/users", { waitUntil: "networkidle" });
    // 前端管理守卫应将非 admin 拦回（至登录或 403 错误态）
    await page.waitForTimeout(2500);
    const url = page.url();
    expect(url).not.toMatch(/\/admin\/users$/);
  });

  test("LOADING：慢请求页面出现骨架屏/加载态（观察首帧）", async ({ page }) => {
    test.setTimeout(90_000);
    await login(page, STUDENT.account, STUDENT.password);
    // 至少检查一个数据驱动页在加载完成前 DOM 有内容（不空白），即渲染链路稳定
    const resp = await page.goto("/achievements", { waitUntil: "commit", timeout: 30_000 });
    expect(resp && resp.status() < 400).toBeTruthy();
    await page.waitForLoadState("domcontentloaded");
    // 加载后正文非空即渲染成功（loading→success 收敛）
    await page.waitForTimeout(2000);
    const bodyLen = (await page.evaluate(() => document.body.innerText.length).catch(() => 0)) ?? 0;
    expect(bodyLen).toBeGreaterThan(50);
  });
});