import { test, Page } from "@playwright/test";
import { ADMIN } from "./helpers";

async function traceApis(page: Page, label: string) {
  const hits: string[] = [];
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("127.0.0.1:8000") || u.includes("/api/")) {
      hits.push(`${req.method()} ${u.replace("http://", "")}`);
    }
  });
  return {
    hits,
    flush: () => page.waitForTimeout(1500),
    report: () => {
      console.log(`\n### ${label} — ${hits.length} 个 /api 请求`);
      hits.forEach((h) => console.log("   ", h));
    },
  };
}

test("探针：登录+题型 请求路径", async ({ page }) => {
  test.setTimeout(90_000);
  const t = await traceApis(page, "登录");
  await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByPlaceholder(/账号|邮箱/).first().fill(ADMIN.account);
  await page.getByPlaceholder(/密码|6 位以上/).first().fill(ADMIN.password);
  await page.getByRole("button", { name: "登录" }).first().click();
  await page.waitForURL(/\/dashboard/, { timeout: 25_000 });
  await t.flush();
  t.report();

  const t2 = await traceApis(page, "题型枚举(页面导航后)");
  await page.goto("/admin/questions/1", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(4000);
  t2.report();

  console.log("\n=== 页面当前文本 ===");
  const txt = (await page.evaluate(() => document.body.innerText).catch(() => "")) || "";
  console.log(txt.slice(0, 400));
});