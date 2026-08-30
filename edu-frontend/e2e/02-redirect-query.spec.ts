/**
 * task69 · task42 批判② —— redirect 含 query 深层路由回跳
 * 验收：/login?redirect=/admin/users?page=2 → 登录成功回跳 URL 完整含 query；用例 PASS
 */
import { test, expect } from "@playwright/test";
import { STUDENT } from "./helpers";

test.describe("redirect 深层路由含 query 回跳（task42 批判②）", () => {
  test("登录前携带 redirect query，登录后完整回跳（含 page=2）", async ({ page }) => {
    // 访问一个带 redirect 的登录页（深层路由 + query）
    await page.goto("/login?redirect=%2Fadmin%2Fusers%3Fpage%3D2", {
      waitUntil: "networkidle",
      timeout: 45_000,
    });
    const redirectInput = page.getByPlaceholder(/账号|邮箱/).first();
    await redirectInput.fill(STUDENT.account);
    await page.getByPlaceholder(/密码|6 位以上/).first().fill(STUDENT.password);
    await page.getByRole("button", { name: "登录" }).first().click();

    // 回跳应含完整路径与 query（相对安全 redirect，不会误入外部）
    await page.waitForURL(/\/admin\/users/, { timeout: 20_000 }).catch(() => {});
    const u = new URL(page.url());
    // 断言路径与 query 均被保留（redirect 解码后 /admin/users?page=2）
    expect(decodeURIComponent(u.pathname + u.search)).toBe("/admin/users?page=2");
  });

  test("不带 redirect 默认回跳 /dashboard", async ({ page }) => {
    await page.goto("/login", { waitUntil: "networkidle", timeout: 45_000 });
    await page.getByPlaceholder(/账号|邮箱/).first().fill(STUDENT.account);
    await page.getByPlaceholder(/密码|6 位以上/).first().fill(STUDENT.password);
    await page.getByRole("button", { name: "登录" }).first().click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  });
});