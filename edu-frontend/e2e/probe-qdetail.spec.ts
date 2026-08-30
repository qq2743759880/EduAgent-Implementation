import { test, expect, Page } from "@playwright/test";
import { login, ADMIN } from "./helpers";

async function dump(page: Page, tag: string): Promise<void> {
  const body = await page.locator("body").innerText().catch(() => "(error)");
  console.log(`\n### [${tag}] url=${page.url()}`);
  console.log("BODY_TEXT>>", body.replace(/\n+/g, " | ").slice(0, 600));
  const hasType = await page.getByLabel("题型").count();
  console.log("题型控件 count:", hasType);
  const tabs = await page.getByRole("tab").allInnerTexts().catch(() => []);
  console.log("TABS:", JSON.stringify(tabs));
}

test("探针：/admin/questions/1 渲染与请求全览", async ({ page }) => {
  test.setTimeout(120_000);
  const net: string[] = [];
  page.on("request", (r) => {
    if (/8000/.test(r.url())) net.push(`REQ ${r.method()} ${r.url()}`);
  });
  page.on("response", (r) => {
    if (/8000/.test(r.url())) net.push(`RES ${r.status()} ${r.url()}`);
  });
  page.on("console", (m) => { if (m.type() === "error") console.log("[console.error]", m.text().slice(0, 200)); });

  await login(page, ADMIN.account, ADMIN.password, "/dashboard");
  await page.goto("/admin/questions/1", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(15000);
  await dump(page, "after-goto-15s");

  // 若出现错误态/重试按钮，点击重试并再等
  const retry = page.getByRole("button", { name: "重试" });
  if (await retry.count()) {
    await retry.first().click();
    await page.waitForTimeout(4000);
    await dump(page, "after-retry");
  }
  if (await page.getByRole("button", { name: /预览/ }).count()) {
    await page.getByRole("tab", { name: /预览/ }).first().click();
    await page.waitForTimeout(2000);
    await dump(page, "after-preview-tab");
  }

  console.log("\n### NET ===");
  net.forEach((n) => console.log("  ", n));
  expect(true).toBeTruthy();
});