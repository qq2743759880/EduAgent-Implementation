/**
 * task46 课程详情页 Playwright 截图验证（fe-tester 验收）
 * 后端不可用 → 验证前端降级：error 态（ErrorState + 重试）与 invalid id 空态。
 */
import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const OUT_DIR = "e:/stu/project/stu/EduAgent实施手册/test-reports/screenshots";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const results = [];

// 1) 有效 seriesId，后端不可用 → 期望 error 态（ErrorState role=alert）
try {
  await page.goto(`${BASE}/courses/1001`, { waitUntil: "networkidle", timeout: 30000 });
  // 先截 loading 骨架（若仍在）
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT_DIR}/task46-loading.png` });
  // 等待 error 态出现（ErrorState role=alert + data-slot=error-state）
  await page.waitForSelector('[role="alert"][data-slot="error-state"]', { timeout: 20000 });
  const alertText = await page.locator('[role="alert"][data-slot="error-state"]').innerText();
  await page.screenshot({ path: `${OUT_DIR}/task46-error.png` });
  results.push({ case: "有效id/后端不可用 → error态", pass: /加载失败/.test(alertText), detail: alertText.replace(/\n/g, " | ") });
} catch (e) {
  results.push({ case: "有效id/后端不可用 → error态", pass: false, detail: e.message });
}

// 2) 无效 seriesId（非数字）→ 期望 empty 态（EmptyState role=status）
try {
  await page.goto(`${BASE}/courses/abc`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[role="status"][data-slot="empty-state"]', { timeout: 20000 });
  const statusText = await page.locator('[role="status"][data-slot="empty-state"]').innerText();
  await page.screenshot({ path: `${OUT_DIR}/task46-empty.png` });
  results.push({ case: "无效id → empty态", pass: /课程不存在/.test(statusText), detail: statusText.replace(/\n/g, " | ") });
} catch (e) {
  results.push({ case: "无效id → empty态", pass: false, detail: e.message });
}

await browser.close();

console.log(JSON.stringify(results, null, 2));
const allPass = results.every((r) => r.pass);
console.log(`\nPLAYWRIGHT_RESULT=${allPass ? "PASS" : "FAIL"}`);
process.exit(allPass ? 0 : 1);
