/**
 * fe-visual-auditor 诊断脚本（临时工具，非应用代码）
 * 目标：实机验证课程详情页「思维导图」Tab 渲染
 *  - canvas 是否渲染非空
 *  - 边颜色：PREREQUISITE 是否 amber（#f59e0b/#F6BD16）还是统一灰（#94a3b8）
 *  - tooltip 关系文本（先修/包含 vs 关联）
 *  - console 错误
 * 运行：cd edu-frontend && npx playwright test ../test-reports/diagnose-mindmap.spec.ts --reporter=list --timeout=150000
 */
import { test, expect } from "playwright/test";

const BASE = "http://127.0.0.1:3000";

test.describe.serial("mindmap diagnose", () => {
  test("登录 admin 并检查 /courses/1 思维导图 Tab", async ({ page }) => {
    test.setTimeout(180_000);

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
    });
    page.on("pageerror", (err) => pageErrors.push(String(err).slice(0, 300)));
    page.on("requestfailed", (req) => {
      consoleErrors.push(`requestfailed: ${req.url().slice(0, 180)} ${req.failure()?.errorText ?? ""}`);
    });

    // ---------- 1. 登录页 ----------
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    // 等待表单出现（若 dev server chunk 403 阻塞则表单不出现）
    let formOk = false;
    for (let i = 0; i < 10; i++) {
      const hasInput = await page
        .locator('input[placeholder="输入账号，或邮箱（含 @）"]')
        .count()
        .catch(() => 0);
      if (hasInput > 0) {
        formOk = true;
        break;
      }
      await page.waitForTimeout(2000);
    }
    console.log("== login form visible:", formOk);
    console.log("== login body:", (await page.evaluate(() => document.body?.innerText?.slice(0, 200))).trim());

    if (!formOk) {
      // 记录环境异常并输出证据
      console.log("== env-block: login form not rendered (chunk 403 suspected)");
      console.log("== body text:", await page.evaluate(() => document.body?.innerText?.slice(0, 400)));
      console.log("== console errors:", JSON.stringify(consoleErrors.slice(0, 10)));
      await page.screenshot({ path: "test-reports/screenshots/diagnose-mindmap-login-blocked.png", fullPage: true });
      return;
    }

    // ---------- 2. 登录 ----------
    await page.locator('input[placeholder="输入账号，或邮箱（含 @）"]').fill("admin");
    await page.locator('input[placeholder="6 位以上"]').fill("Admin@12345");
    await page.getByRole("button", { name: "登录" }).click();

    // 等跳转完成（login -> /dashboard 默认）
    await page.waitForURL(/(\/dashboard|\/courses)/, { timeout: 30_000 }).catch(() => {
      console.log("== warn: no redirect after login; url =", page.url());
    });
    await page.waitForTimeout(2500);
    console.log("== after login url:", page.url());

    // ---------- 3. 打开课程详情页 ----------
    await page.goto(`${BASE}/courses/1`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);
    console.log("== course page body head:", (await page.evaluate(() => document.body?.innerText?.slice(0, 400))).replace(/\n+/g, " | "));

    // ---------- 4. 切到「思维导图」Tab ----------
    const tab = page.getByRole("tab", { name: "思维导图" }).first();
    const tabCount = await tab.count().catch(() => 0);
    console.log("== mindmap tab count:", tabCount);
    if (tabCount > 0) {
      await tab.click();
      await page.waitForTimeout(5000); // ECharts 初始化 + force 布局
    } else {
      console.log("== warn: mindmap tab not found; try clicking text");
      await page.getByText("思维导图", { exact: true }).first().click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(5000);
    }

    // ---------- 5. canvas 检查 ----------
    const canvasInfo = await page.evaluate(() => {
      const canvases = Array.from(document.querySelectorAll("canvas"));
      return canvases.map((c) => ({
        w: c.width,
        h: c.height,
        cssW: c.getBoundingClientRect().width,
        cssH: c.getBoundingClientRect().height,
        parentClass: (c.parentElement?.className ?? "").slice(0, 60),
      }));
    });
    console.log("== canvases:", JSON.stringify(canvasInfo));

    let edgeColorStats = { amberCount: 0, grayCount: 0, blueCount: 0, opaque: 0, total: 0 };
    if (canvasInfo.length > 0) {
      // 取最大 canvas（ECharts 主画布）
      const target = canvasInfo.reduce((a, b) => (b.w * b.h > a.w * a.h ? b : a));
      edgeColorStats = await page.evaluate(({ w, h }) => {
        const cv = Array.from(document.querySelectorAll("canvas")).find((c) => c.width === w && c.height === h);
        if (!cv) return { amberCount: -1, grayCount: -1, blueCount: -1, opaque: -1, total: -1 };
        const ctx = cv.getContext("2d");
        const img = ctx.getImageData(0, 0, w, h).data;
        let amber = 0, gray = 0, blue = 0, opaque = 0;
        const n = w * h;
        for (let i = 0; i < n; i++) {
          const r = img[i * 4], g = img[i * 4 + 1], b = img[i * 4 + 2], a = img[i * 4 + 3];
          if (a < 40) continue;
          opaque++;
          // amber 系（前端 warning #f59e0b / 后端 #F6BD16）
          if (r > 190 && g > 110 && g < 215 && b < 100) amber++;
          // slate-400 灰 #94a3b8（r≈g≈b，130-200）
          else if (r > 120 && r < 205 && Math.abs(r - g) < 18 && Math.abs(g - b) < 24 && b > 120) gray++;
          // 蓝 #5B8FF9 系（b 高）
          else if (b > 200 && r < 170 && g < 190) blue++;
        }
        return { amberCount: amber, grayCount: gray, blueCount: blue, opaque, total: n };
      }, target);
      console.log("== edge color stats (amber/gray/blue):", JSON.stringify(edgeColorStats));
    }

    // ---------- 6. 悬停找 tooltip（关系文本） ----------
    let tooltipTexts: string[] = [];
    if (canvasInfo.length > 0) {
      const box = await page.evaluate(() => {
        const cv = Array.from(document.querySelectorAll("canvas")).sort((a, b) => b.width * b.height - a.width * a.height)[0];
        if (!cv) return null;
        const r = cv.getBoundingClientRect();
        return { x: r.x, y: r.y, w: r.width, h: r.height };
      });
      if (box && box.w > 0 && box.h > 0) {
        const step = 24;
        for (let gy = 0; gy < box.h && tooltipTexts.length < 8; gy += step) {
          for (let gx = 0; gx < box.w && tooltipTexts.length < 8; gx += step) {
            await page.mouse.move(box.x + gx + step / 2, box.y + gy + step / 2);
            const t = await page.evaluate(() => {
              const divs = Array.from(document.querySelectorAll("div"));
              const hit = divs
                .filter((d) => d.textContent && (d.textContent.includes("关系：") || d.textContent.includes("类型：")))
                .map((d) => d.textContent.trim());
              return hit.slice(0, 2);
            });
            if (t.length > 0) {
              for (const s of t) if (!tooltipTexts.includes(s)) tooltipTexts.push(s);
            }
          }
        }
      }
      console.log("== tooltip texts:", JSON.stringify(tooltipTexts.slice(0, 6)));
    }

    // ---------- 7. 最终截图 ----------
    await page.screenshot({ path: "test-reports/screenshots/diagnose-mindmap.png", fullPage: false });
    console.log("== screenshot saved: test-reports/screenshots/diagnose-mindmap.png");
    console.log("== console error count:", consoleErrors.length);
    console.log("== console errors:", JSON.stringify(consoleErrors.slice(0, 12)));
    console.log("== page errors:", JSON.stringify(pageErrors.slice(0, 5)));

    // ---------- 8. 汇总断言（信息性输出，不做硬失败） ----------
    const summary = {
      canvasRendered: canvasInfo.length > 0 && canvasInfo.some((c) => c.w > 100 && c.h > 100),
      amberEdgePixels: edgeColorStats.amberCount,
      grayEdgePixels: edgeColorStats.grayCount,
      blueEdgePixels: edgeColorStats.blueCount,
      tooltipTexts: tooltipTexts.slice(0, 6),
      consoleErrorCount: consoleErrors.length,
      loginFormVisible: formOk,
    };
    console.log("== SUMMARY:", JSON.stringify(summary, null, 2));

    expect(summary.canvasRendered).toBe(true);
  });
});
