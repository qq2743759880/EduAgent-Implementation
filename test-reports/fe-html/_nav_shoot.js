const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;

const pages = [
  { file: "courses.html", alt: "empty", altSel: 'button[data-s="empty"]' },
  { file: "course-detail.html", alt: "error", altSel: '.toolbar button[data-s="error"]' },
  { file: "achievements.html", alt: "empty", altSel: 'button[data-st="empty"]' },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = [];
  for (const p of pages) {
    const name = p.file.replace(".html", "");
    // 1280 success
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`file://${path.join(root, p.file).replace(/\\/g, "/")}`);
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(root, `nav-${name}-success-1280.png`), fullPage: true });
    let metrics = await navMetrics(page);
    // alternate state (empty/error)
    try {
      await page.click(p.altSel);
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(root, `nav-${name}-${p.alt}-1280.png`), fullPage: true });
      const altGone = await page.evaluate(() =>
        document.body.innerText.includes("加载失败") || document.body.innerText.includes("暂无") || document.body.innerText.includes("没有符合") || document.body.innerText.includes("开小差")
      );
      metrics.altState = { state: p.alt, textSeen: altGone };
    } catch (e) { metrics.altState = { state: p.alt, error: e.message }; }
    await page.close();

    // mobile 375
    const mob = await browser.newPage({ viewport: { width: 375, height: 812 } });
    await mob.goto(`file://${path.join(root, p.file).replace(/\\/g, "/")}`);
    await mob.waitForTimeout(600);
    const hamburger = await mob.evaluate(() => {
      const t = document.getElementById("gnavToggle");
      if (!t) return { present: false };
      const cs = getComputedStyle(t);
      return { present: true, display: cs.display, opened: document.getElementById("gnav").classList.contains("open") };
    });
    // open drawer and screenshot
    if (hamburger.present) {
      await mob.click("#gnavToggle");
      await mob.waitForTimeout(400);
    }
    await mob.screenshot({ path: path.join(root, `nav-${name}-mob-375.png`), fullPage: true });
    hamburger.gnavOpenNow = await mob.evaluate(() => document.getElementById("gnav").classList.contains("open"));
    hamburger.overlayVisible = await mob.evaluate(() => {
      const o = document.getElementById("gnavOverlay");
      return o ? getComputedStyle(o).visibility === "visible" : false;
    });
    metrics.mobile = hamburger;
    // escape closes
    hamburger.escCloses = await mob.evaluate(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      return document.getElementById("gnav").classList.contains("open");
    });
    await mob.close();
    report.push({ name, metrics });
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 2));

  async function navMetrics(page) {
    return await page.evaluate(() => {
      const items = [...document.querySelectorAll(".gnav-list .gnav-item")];
      const active = items.filter(i => i.classList.contains("active") && i.getAttribute("aria-current") === "page");
      const overflowX = document.documentElement.scrollWidth > window.innerWidth;
      return {
        navItemCount: items.length,
        labels: items.map(i => i.textContent.trim()),
        hrefs: items.map(i => i.getAttribute("href")),
        activeCount: items.filter(i => i.classList.contains("active")).length,
        activeLabel: active.map(i => i.textContent.trim()),
        ariaCurrentCount: document.querySelectorAll('.gnav-item[aria-current="page"]').length,
        overflowX,
        topbarRight: (() => {
          const hasA = document.body.innerText.includes("问 AI") || document.body.innerText.includes("问AI");
          const av = document.querySelector("[data-user-menu],.user-menu,.avatar,.g-user");
          return { askAI: hasA, avatarPresent: !!av };
        })(),
      };
    });
  }
})();