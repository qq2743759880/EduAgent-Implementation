const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;
const byPath = p => `file://${path.join(root, p).replace(/\\/g, "/")}`;
(async () => {
  const b = await chromium.launch({ headless: true });
  const out = {};
  for (const file of ["community.html", "community-post.html", "practice.html"]) {
    const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
    await p.goto(byPath(file));
    const user = await p.evaluate(() => {
      const u = document.querySelector(".gnav-user");
      const foot = document.querySelector(".gnav-foot");
      const gnav = document.querySelector(".gnav");
      if (!u) return { exists: false };
      const cs = getComputedStyle(u);
      const r = u.getBoundingClientRect();
      return {
        exists: true, display: cs.display, inViewport: r.width > 0 && r.height > 0,
        rightSide: !!(gnav && foot && r.right >= foot.getBoundingClientRect().left - 5),
        hasAskAI: !!u.querySelector('.gnav-user-link[aria-label="问 AI"]'),
        hasAvatar: !!u.querySelector('.gnav-user-link.ava'),
      };
    });
    // mobile drawer + Escape
    await p.setViewportSize({ width: 375, height: 812 });
    await p.waitForTimeout(100);
    const mob = await p.evaluate(() => {
      const t = document.getElementById("gnavToggle");
      const n = document.getElementById("gnav");
      const hambVisible = t && getComputedStyle(t).display !== "none" && t.getBoundingClientRect().width > 0;
      return { hambVisible };
    });
    await p.click("#gnavToggle");
    await p.waitForTimeout(150);
    const opened = await p.evaluate(() => document.getElementById("gnav").classList.contains("open"));
    await p.keyboard.press("Escape");
    await p.waitForTimeout(150);
    const closedByEsc = await p.evaluate(() => !document.getElementById("gnav").classList.contains("open"));
    out[file] = { user, mob, opened, closedByEsc };
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(out, null, 2));
})();