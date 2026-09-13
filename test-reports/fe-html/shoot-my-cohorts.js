const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/my-cohorts.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });
  page.on("dialog", (d) => d.dismiss());

  // 矩阵：375/768/1024/1280/1440 × success(active) + completed/refunded/loading/error/empty
  const shots = [];
  for (const w of [375, 768, 1024, 1280, 1440]) shots.push({ name: `success-${w}`, w, state: "success" });
  shots.push({ name: "tab-completed-1280", w: 1280, state: "completed" });
  shots.push({ name: "tab-refunded-1280", w: 1280, state: "refunded" });
  shots.push({ name: "loading-1280", w: 1280, state: "loading" });
  shots.push({ name: "error-1280", w: 1280, state: "error" });
  shots.push({ name: "empty-1280", w: 1280, state: "empty" });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.waitForTimeout(400);
    if (s.state === "completed") {
      await page.evaluate(() => document.querySelector('.tab[data-tab="completed"]').click()); await page.waitForTimeout(300);
    } else if (s.state === "refunded") {
      await page.evaluate(() => document.querySelector('.tab[data-tab="refunded"]').click()); await page.waitForTimeout(300);
    } else if (s.state === "loading" || s.state === "error" || s.state === "empty") {
      await page.evaluate((st) => document.querySelector(`.statebar button[data-state="${st}"]`).click(), s.state); await page.waitForTimeout(300);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/shot-mc-${s.name}.png`, fullPage: true });
  }

  // 交互素质检测
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  const probe = await page.evaluate(() => ({
    tabs: document.querySelectorAll(".tab").length,
    activeCards: document.querySelectorAll("#tab-active .cohort-card").length,
    activeBadges: [...document.querySelectorAll("#tab-active .badge")].map((b) => b.textContent.trim()),
    progressbars: document.querySelectorAll('#tab-active [role="progressbar"]').length,
    nextLessons: document.querySelectorAll("#tab-active .next-lesson").length,
    actions: [...document.querySelectorAll("#tab-active .actions .btn")].map((b) => b.textContent.trim()),
    breadcrumb: document.querySelectorAll(".breadcrumb a").length,
  }));
  console.log("PROBE-ACTIVE:", JSON.stringify(probe));

  await page.evaluate(() => document.querySelector('.tab[data-tab="completed"]').click()); await page.waitForTimeout(200);
  const probeDone = await page.evaluate(() => ({
    doneCards: document.querySelectorAll("#tab-completed .cohort-card").length,
    doneActions: [...document.querySelectorAll("#tab-completed .done-actions .btn")].map((b) => b.textContent.trim()),
  }));
  console.log("PROBE-DONE:", JSON.stringify(probeDone));

  await page.evaluate(() => document.querySelector('.tab[data-tab="refunded"]').click()); await page.waitForTimeout(200);
  const probeRefunded = await page.evaluate(() => ({
    refundedCards: document.querySelectorAll("#tab-refunded .cohort-card").length,
    refundedGray: !!document.querySelector("#tab-refunded .cohort-card.refunded"),
    refundActions: [...document.querySelectorAll("#tab-refunded .actions .btn")].map((b) => b.textContent.trim()),
  }));
  console.log("PROBE-REFUNDED:", JSON.stringify(probeRefunded));

  await page.evaluate(() => document.querySelector('.statebar button[data-state="empty"]').click()); await page.waitForTimeout(200);
  const probeEmpty = await page.evaluate(() => ({
    emptyText: document.querySelector("#panel-empty .t")?.textContent.trim(),
    emptyCta: document.querySelector("#panel-empty .btn")?.textContent.trim(),
  }));
  console.log("PROBE-EMPTY:", JSON.stringify(probeEmpty));

  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
