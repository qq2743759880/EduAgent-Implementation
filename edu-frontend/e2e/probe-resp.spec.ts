import { test, Page } from "@playwright/test";
import { ADMIN } from "./helpers";

test("探针：/admin/questions 响应状态与体", async ({ page }) => {
  test.setTimeout(90_000);
  const notes: string[] = [];
  page.on("response", async (res) => {
    const u = res.url();
    if (u.includes("/api/admin/questions") || u.includes("/api/progress/dashboard")) {
      let detail = `HTTP${res.status()}`;
      if (u.includes("/types") || u.includes("/questions/1") || u.includes("/dashboard")) {
        try {
          const j = await res.json();
          detail += ` code=${j?.code} dataType=${Array.isArray(j?.data) ? "array" : (j?.data ? typeof j?.data : "null")}`;
        } catch { detail += " [non-json]"; }
      }
      notes.push(`${res.request().method()} ${u.replace("http://127.0.0.1:8000", "")} -> ${detail}`);
    }
  });

  await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByPlaceholder(/账号|邮箱/).first().fill(ADMIN.account);
  await page.getByPlaceholder(/密码|6 位以上/).first().fill(ADMIN.password);
  await page.getByRole("button", { name: "登录" }).first().click();
  await page.waitForURL(/\/dashboard/, { timeout: 25_000 });

  await page.goto("/admin/questions/1", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(5000);

  console.log("\n### 响应记录 ===");
  notes.forEach((n) => console.log("  ", n));
  const txt = (await page.evaluate(() => document.body.innerText).catch(() => "")) || "";
  console.log("### 页面文本尾部 ===", txt.slice(-180));
});