import { test } from "@playwright/test";
import { STUDENT, ADMIN } from "./helpers";

test("probe /login behavior fresh context", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.waitForTimeout(3000);
  const a = await page.evaluate(() => ({
    url: location.href,
    token: !!localStorage.getItem("edu:auth:token"),
    hasLoginBtn: Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.includes("登录")),
    bodyHead: (document.body.innerText || "").replace(/\n+/g, " | ").slice(0, 150),
  }));
  console.log("PROBE_STUDENT_CTX:", JSON.stringify(a));
  await ctx.close();
});