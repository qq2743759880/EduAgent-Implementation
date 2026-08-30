import { test, Page } from "@playwright/test";
import { ADMIN } from "./helpers";

test("探针：失败原因与CORS", async ({ page }) => {
  test.setTimeout(90_000);
  const failed: string[] = [];
  const done: string[] = [];
  page.on("requestfailed", (req) => {
    failed.push(`${req.method()} ${req.url().replace("http://127.0.0.1:8000", "")} :: ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    if (res.url().includes("127.0.0.1:8000")) done.push(`${res.request().method()} ${res.url().replace("http://127.0.0.1:8000", "")} -> ${res.status()}`);
  });
  page.on("console", (m) => { if (m.type() === "error") console.log("[console.error]", m.text().slice(0, 160)); });

  await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByPlaceholder(/账号|邮箱/).first().fill(ADMIN.account);
  await page.getByPlaceholder(/密码|6 位以上/).first().fill(ADMIN.password);
  await page.getByRole("button", { name: "登录" }).first().click();
  await page.waitForURL(/\/dashboard/, { timeout: 25_000 }).catch(() => console.log("[wait dash 超时]"));
  await page.waitForTimeout(3000);

  await page.goto("/admin/questions/1", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(5000);

  console.log("\n### 已完成请求 ===");
  done.forEach((d) => console.log("  ", d));
  console.log("\n### 失败请求 ===");
  failed.forEach((f) => console.log("  ", f));
  if (!done.length && !failed.length) console.log("  (两者皆空 = 请求发出但无响应事件)");
});