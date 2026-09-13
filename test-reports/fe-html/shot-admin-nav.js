const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;
const pages = ["admin-dashboard.html","admin-users.html","admin-question-detail.html","admin-rag-upload.html"];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const file of pages) {
    const base = file.replace(".html", "");
    // desktop success
    const d = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await d.goto(`file://${path.join(root, file).replace(/\\/g, "/")}`);
    await d.waitForTimeout(800);
    await d.screenshot({ path: path.join(root, `nav-${base}-success-1280.png`), fullPage: true });
    const itemCount = await d.evaluate(() => document.querySelectorAll(".gnav-list .gnav-item").length);
    const active = await d.evaluate(() => (document.querySelector(".gnav-item.active") || {}).textContent.trim());
    const hasAdmin = await d.evaluate(() => !!document.querySelector("header.gnav.gnav-admin"));
    const crumb = await d.evaluate(() => (document.querySelector(".crumb") ? document.querySelector(".crumb").textContent.replace(/\s+/g, " ").trim() : null));
    results.push({ file, nav1280: itemCount, active, gnavAdmin: hasAdmin, crumb });
    await d.close();
    // mobile
    const m = await browser.newPage({ viewport: { width: 375, height: 812 } });
    await m.goto(`file://${path.join(root, file).replace(/\\/g, "/")}`);
    await m.waitForTimeout(500);
    // open drawer to show nav on mobile
    const hasToggle = await m.evaluate(() => !!document.getElementById("gnavToggle"));
    if (hasToggle) { await m.click("#gnavToggle"); await m.waitForTimeout(400); }
    await m.screenshot({ path: path.join(root, `nav-${base}-mob-375.png`), fullPage: false });
    const overflowX = await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    results[results.length-1].mobOverflowX = overflowX;
    await m.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();