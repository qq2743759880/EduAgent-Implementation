const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/admin-courses.html";
  const url = "file:///" + path.replace(/\\/g, "/");
  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });

  const shots = [
    { name: "ad-courses-success-1280", w: 1280, state: "success" },
    { name: "ad-courses-success-375", w: 375, state: "success" },
    { name: "ad-courses-loading-1280", w: 1280, state: "loading" },
    { name: "ad-courses-error-1280", w: 1280, state: "error" },
    { name: "ad-courses-empty-1280", w: 1280, state: "empty" },
  ];
  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.waitForTimeout(300);
    if (s.state === "success") {
      await page.evaluate(() => { const b = document.querySelector('[data-v="success"]'); b.click(); });
    } else {
      await page.evaluate((st) => { const b = document.querySelector('[data-v="' + st + '"]'); if (b) b.click(); }, s.state);
    }
    await page.waitForTimeout(200);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/${s.name}.png`, fullPage: true });
  }

  // 下拉菜单展开态（第 1 行「管理」）
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => { const b = document.querySelector('[data-v="success"]'); b.click(); });
  await page.waitForTimeout(200);
  await page.evaluate(() => { const btn = document.querySelector(".series-row .dd-btn"); btn && btn.click(); });
  await page.waitForTimeout(200);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/ad-courses-dropdown-1280.png`, fullPage: true });

  // probe
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForTimeout(250);
  const probe = await page.evaluate(() => ({
    bodyRows: document.querySelectorAll("#tbl-body tr.series-row").length,
    ddBtn: document.querySelectorAll(".dd-btn").length,
    badgeOn: !!document.querySelector(".badge-on"),
    badgeMut: !!document.querySelector(".badge-mut"),
    dmLive: !!document.querySelector(".b-live"),
    dmRec: !!document.querySelector(".b-rec"),
    dmOffline: !!document.querySelector(".b-offline"),
    stateCtrl: document.querySelectorAll("[data-v]").length,
  }));
  console.log("PROBE:", JSON.stringify(probe));
  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });