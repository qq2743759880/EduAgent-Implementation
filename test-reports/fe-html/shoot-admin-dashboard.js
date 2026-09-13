const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/admin-dashboard.html";
  const url = "file:///" + path.replace(/\\/g, "/");
  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });

  const shots = [];
  for (const w of [375, 520, 768, 1280, 1440]) shots.push({ name: `ad-success-${w}`, w, state: "success" });
  shots.push({ name: "ad-loading-1280", w: 1280, state: "loading" });
  shots.push({ name: "ad-error-1280", w: 1280, state: "error" });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.waitForTimeout(350);
    await page.evaluate((st) => { const b = document.querySelector('.respbar [data-state="' + st + '"]'); b.click(); }, s.state);
    await page.waitForTimeout(250);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/${s.name}.png`, fullPage: true });
  }

  // a11y / probe
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  const probe = await page.evaluate(() => ({
    successVisible: !document.getElementById('view-success').hidden,
    barsRole: !!document.querySelector('.bars[role="img"][aria-label]'),
    donutRole: !!document.querySelector('.donut[role="img"][aria-label]'),
    legendCount: document.querySelectorAll('.legend .lg').length,
    retryBtn: !!document.querySelector('.retry'),
  }));
  console.log("PROBE:", JSON.stringify(probe));
  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });