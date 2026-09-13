const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/course-detail.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });
  page.on("dialog", (d) => d.dismiss()); // 吞掉 alert，避免阻塞截图

  // 矩阵：375/768/1024/1280/1440 × 成功；另补 弹窗/错误/加载 态截图
  const shots = [];
  for (const w of [375, 768, 1024, 1280, 1440]) shots.push({ name: `success-${w}`, w, state: "success" });
  shots.push({ name: "loading-1280", w: 1280, state: "loading" });
  shots.push({ name: "error-1280", w: 1280, state: "error" });
  shots.push({ name: "coupon-open-1280", w: 1280, state: "coupon" });
  shots.push({ name: "cohort-selected-1280", w: 1280, state: "cohort3" });
  shots.push({ name: "tabs-mind-1280", w: 1280, state: "mind" });
  shots.push({ name: "notauth-375", w: 375, state: "success" });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.waitForTimeout(400);
    if (s.state === "loading") {
      await page.evaluate(() => applyState("loading")); await page.waitForTimeout(300);
    } else if (s.state === "error") {
      await page.evaluate(() => applyState("error")); await page.waitForTimeout(300);
    } else if (s.state === "coupon") {
      await page.evaluate(() => { renderCoupons(); openCoupon(true); }); await page.waitForTimeout(300);
    } else if (s.state === "cohort3") {
      await page.evaluate(() => { selected = 503; renderBody(); }); await page.waitForTimeout(300);
    } else if (s.state === "mind") {
      await page.evaluate(() => { document.querySelector('.tab[data-tab="mind"]').click(); }); await page.waitForTimeout(300);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/shot-cd-${s.name}.png`, fullPage: true });
  }

  // 交互素质检测：首屏按钮/徽章/班次/四级/分页
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 900 });
  const probe = await page.evaluate(() => ({
    hero: !!document.querySelector(".hero"),
    cover: !!document.querySelector(".cover .title"),
    cohorts: document.querySelectorAll(".cohort").length,
    disabled: document.querySelectorAll(".cohort.disabled").length,
    favPressed: document.querySelector("#favBtn").getAttribute("aria-pressed"),
    tabs: document.querySelectorAll("#tablist .tab").length,
    modules: document.querySelectorAll("[data-panel=outline] .lvl[data-lvl=module]").length,
    sessions: document.querySelectorAll("[data-panel=outline] .session").length,
    tabReviewCount: /课程评价 \((\d+)\)/.exec(document.querySelector('#tablist .tab[data-tab=review]').textContent)[1],
    breadcrumb: document.querySelectorAll(".breadcrumb a").length,
  }));
  console.log("PROBE:", JSON.stringify(probe));

  // 收藏/报名 未登录提示校验（authed=false 默认）
  const authProbe = await page.evaluate(() => ({ authed, favBtn: !!document.getElementById("favBtn") }));
  console.log("AUTH-PROBE:", JSON.stringify(authProbe));

  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });