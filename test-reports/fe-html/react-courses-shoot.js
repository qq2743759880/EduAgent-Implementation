// fe-tester 独立复核：/courses React 页面 error/loading 态截图 + console 检查
// 依赖：edu-frontend 的 playwright（dev server 需已运行于 localhost:3000）
const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

const BASE = "http://localhost:3000/courses";
const OUT = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/";
const API_PATTERN = "**/api/series*";

(async () => {
  const browser = await chromium.launch();
  const consoleErrors = [];
  const pageErrors = [];
  const keyWarnings = [];

  function attach(page, tag) {
    page.on("console", (m) => {
      const t = m.text();
      if (m.type() === "error") consoleErrors.push(`[${tag}] ${t}`);
      if (/unique "key" prop|Each child in a list|should have a unique key/i.test(t)) keyWarnings.push(`[${tag}] ${t}`);
    });
    page.on("pageerror", (e) => pageErrors.push(`[${tag}] ${String(e)}`));
  }

  // ---------- 1) error 态：后端不可达，请求自然失败 ----------
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  attach(page, "error");
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 60000 });
  // 等待 ErrorState（role=alert）
  await page.waitForSelector('[role="alert"]', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(600);
  const errProbe = await page.evaluate(() => ({
    alert: !!document.querySelector('[role="alert"]'),
    alertTitle: document.querySelector('[role="alert"] p')?.textContent ?? null,
    alertText: document.querySelector('[role="alert"]')?.innerText?.slice(0, 160) ?? null,
    retryBtn: !!document.querySelector('[role="alert"] button'),
    bodyHead: document.body.innerText.slice(0, 120),
  }));
  console.log("ERROR-PROBE:", JSON.stringify(errProbe));
  await page.screenshot({ path: OUT + "react-courses-error.png", fullPage: true });
  await page.close();

  // ---------- 2) loading 态：拦截 API 请求并延迟 8s ----------
  const page2 = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  attach(page2, "loading");
  await page2.route(API_PATTERN, async (route) => {
    await new Promise((r) => setTimeout(r, 8000));
    await route.continue().catch(() => {});
  });
  await page2.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page2.waitForTimeout(2000); // 骨架屏应已出现
  const loadProbe = await page2.evaluate(() => ({
    pulseCount: document.querySelectorAll(".animate-pulse").length,
    queryingText: /查询中…/.test(document.body.innerText),
    bodyHead: document.body.innerText.slice(0, 120),
  }));
  console.log("LOADING-PROBE:", JSON.stringify(loadProbe));
  await page2.screenshot({ path: OUT + "react-courses-loading.png", fullPage: true });
  await page2.unroute(API_PATTERN);
  await page2.close();

  console.log("CONSOLE-ERRORS:", JSON.stringify(consoleErrors, null, 2));
  console.log("PAGE-ERRORS:", JSON.stringify(pageErrors, null, 2));
  console.log("KEY-WARNINGS:", JSON.stringify(keyWarnings, null, 2));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
