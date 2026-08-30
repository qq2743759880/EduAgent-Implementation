import { test, expect } from "@playwright/test";
import { login, STUDENT } from "./helpers";

test("定位 /community 375 溢出元素", async ({ browser }) => {
  test.setTimeout(90_000);
  const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
  const page = await ctx.newPage();
  await login(page, STUDENT.account, STUDENT.password);
  await page.goto("/community", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(1500);

  const info = await page.evaluate(() => {
    const dw = document.documentElement.scrollWidth;
    const iw = window.innerWidth;
    const out: {
      doc: { scrollWidth: number; innerWidth: number; bodyScrollWidth: number; delta: number };
      culprits: { tag: string; cls: string; scrollW: number; clientW: number; delta: number; text: string }[];
    } = { doc: { scrollWidth: dw, innerWidth: iw, bodyScrollWidth: document.body.scrollWidth, delta: dw - iw }, culprits: [] };
    document.querySelectorAll("*").forEach((el) => {
      const sw = el.scrollWidth;
      const cw = el.clientWidth;
      if (sw > cw + 1 && sw > iw) {
        out.culprits.push({
          tag: el.tagName,
          cls: (el.getAttribute("class") || "").slice(0, 100),
          scrollW: sw,
          clientW: cw,
          delta: sw - cw,
          text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60),
        });
      }
    });
    out.culprits.sort((a, b) => b.delta - a.delta);
    return out;
  });
  console.log("DOC:", JSON.stringify(info.doc));
  console.log("TOP CULPRITS:", JSON.stringify(info.culprits.slice(0, 10), null, 2));
  await ctx.close();
  expect(true).toBeTruthy();
});