const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;

// Per page: array of {file, vw, h, stateSel, shotName, note}
const plan = [
  // community list
  { file: "community.html", vw: 1280, h: 800, stateSel: '.respbar [data-st="ok"]',      shot: "nav-community-success-1280.png" },
  { file: "community.html", vw: 1280, h: 800, stateSel: '.respbar [data-st="empty"]',     shot: "nav-community-empty-1280.png" },
  { file: "community.html", vw: 375,  h: 812, stateSel: null,                             shot: "nav-community-mob-375.png" },
  // community post
  { file: "community-post.html", vw: 1280, h: 800, stateSel: '.respbar [data-st="ok"]',   shot: "nav-community-post-success-1280.png" },
  { file: "community-post.html", vw: 1280, h: 800, stateSel: '.respbar [data-st="error"]',shot: "nav-community-post-error-1280.png" },
  { file: "community-post.html", vw: 375,  h: 812, stateSel: null,                        shot: "nav-community-post-mob-375.png" },
  // practice
  { file: "practice.html", vw: 1280, h: 800, stateSel: '.statebar button[data-state="success"]', shot: "nav-practice-success-1280.png" },
  { file: "practice.html", vw: 1280, h: 800, stateSel: '.statebar button[data-state="loading"]', shot: "nav-practice-loading-1280.png" },
  { file: "practice.html", vw: 375,  h: 812, stateSel: null,                               shot: "nav-practice-mob-375.png" },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const out = [];
  for (const p of plan) {
    const page = await browser.newPage({ viewport: { width: p.vw, height: p.h } });
    const url = `file://${path.join(root, p.file).replace(/\\/g, "/")}`;
    await page.goto(url);
    if (p.stateSel) { try { await page.click(p.stateSel); } catch (e) { out.push({ shot: p.shot, clickError: String(e).slice(0, 120) }); } }
    await page.waitForTimeout(200);
    await page.screenshot({ path: path.join(root, p.shot), fullPage: true });
    const m = await page.evaluate(() => {
      const list = Array.from(document.querySelectorAll(".gnav-list .gnav-item"));
      return {
        count: list.length,
        labels: list.map(a => a.textContent.trim()),
        activeText: (document.querySelector(".gnav-list .gnav-item.active") || {}).textContent || null,
        ariaCurrent: (document.querySelector(".gnav-list .gnav-item[aria-current='page']") || {}).textContent || null,
        hamburgerVisible: (() => { const t = document.getElementById("gnavToggle"); return !!(t && getComputedStyle(t).display !== "none"); })(),
        userGotAI: !!document.querySelector(".gnav-user .gnav-user-link"),
        overflowX: document.documentElement.scrollWidth > window.innerWidth,
      };
    });
    out.push({ shot: p.shot, vw: p.vw, ...m });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out, null, 2));
})();