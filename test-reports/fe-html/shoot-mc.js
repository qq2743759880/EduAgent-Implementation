const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/my-cohorts.html";
  const url = "file:///" + path.replace(/\\/g, "/");
  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });

  const shots = [];
  for (const w of [375, 768, 1024, 1280, 1440]) shots.push({ name: `success-${w}`, w, tab: null });
  shots.push({ name: "tab-completed-1280", w: 1280, tab: "completed" });
  shots.push({ name: "tab-refunded-1280", w: 1280, tab: "refunded" });
  shots.push({ name: "loading-1280", w: 1280, tab: "__loading" });
  shots.push({ name: "error-1280", w: 1280, tab: "__error" });
  shots.push({ name: "empty-1280", w: 1280, tab: "__empty" });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.waitForTimeout(350);
    if (s.tab) {
      if (s.tab === "__loading") { await page.evaluate(() => { const b=document.querySelector('.statebar [data-state="loading"]'); b.click(); }); }
      else if (s.tab === "__error") { await page.evaluate(() => { document.querySelector('.statebar [data-state="error"]').click(); }); }
      else if (s.tab === "__empty") { await page.evaluate(() => { document.querySelector('.statebar [data-state="empty"]').click(); }); }
      else { await page.evaluate((t) => { document.querySelector('.tab[data-tab="'+t+'"]').click(); }, s.tab); }
      await page.waitForTimeout(250);
    }
    await page.evaluate(() => window.scrollTo(0,0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/shot-mc-${s.name}.png`, fullPage: true });
  }

  // a11y + 交互 probe
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  const probe = await page.evaluate(() => ({
    tabs: document.querySelectorAll('.tab').length,
    tabControls: document.querySelectorAll('.tab[aria-controls]').length,
    tabIds: document.querySelectorAll('.tab[id]').length,
    panelLinked: document.querySelectorAll('.tab-panel[aria-labelledby]').length,
    initialFocused: document.activeElement && document.activeElement.id,
    activeVisible: document.getElementById('tab-active').classList.contains('active'),
    progressbars: document.querySelectorAll('[role=progressbar]').length,
    statusBarFocus: getComputedStyle(document.querySelector('.statebar button')).outlineStyle,
    inlineHotText: (document.querySelector('.prog-pct.hot') && document.querySelector('.prog-pct.hot').style.color) || "none",
  }));
  console.log("PROBE:", JSON.stringify(probe));

  // 方向键导航验证
  await page.evaluate(() => { document.querySelector('.tab').focus(); });
  await page.keyboard.press('ArrowRight');
  const arrowFocus = await page.evaluate(() => document.activeElement.id);
  const arrowSelected = await page.evaluate(() => document.activeElement.getAttribute('aria-selected'));
  console.log("TAB-NAV:", JSON.stringify({ arrowFocus, arrowSelected }));

  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });