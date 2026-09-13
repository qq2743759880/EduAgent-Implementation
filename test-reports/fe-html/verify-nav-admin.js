const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;

const pages = ["admin-courses.html", "admin-course-detail.html", "admin-questions.html"];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = {};

  for (const file of pages) {
    const tag = file.replace(".html", "");
    // 1280 success
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`file://${path.join(root, file).replace(/\\/g, "/")}`);
    // ensure success view (default)
    await page.waitForTimeout(200);
    await page.screenshot({ path: path.join(root, `nav-${tag}-success-1280.png`), fullPage: true });
    const nav = await page.evaluate(() => {
      const items = [...document.querySelectorAll(".gnav-list .gnav-item")].map(a => a.textContent.trim());
      const active = document.querySelector(".gnav-item.active");
      const hamb = window.innerWidth < 768 ? getComputedStyle(document.querySelector(".gnav-toggle")).display : "n/a(desktop)";
      return {
        itemCount: items.length,
        items,
        activeText: active ? active.textContent.trim() : null,
        hasAriaCurrent: active ? active.getAttribute("aria-current") : null,
        gnavAdmin: !!document.querySelector("header.gnav.gnav-admin"),
        hamburgerDisplay: hamb,
      };
    });
    const crumb = file.includes("course-detail") ? await page.evaluate(() => document.querySelector(".crumb")?.textContent.trim()) : null;
    results[file] = { nav, crumb };
    await page.close();

    // 375 mobile (hamburger visible)
    const mob = await browser.newPage({ viewport: { width: 375, height: 812 } });
    await mob.goto(`file://${path.join(root, file).replace(/\\/g, "/")}`);
    await mob.waitForTimeout(200);
    const mNav = await mob.evaluate(() => {
      const t = document.getElementById("gnavToggle");
      const disp = t ? getComputedStyle(t).display : "no-btn";
      return { hamburgerDisplay: disp, hambVisible: disp !== "none" };
    });
    await mob.screenshot({ path: path.join(root, `nav-${tag}-mob-375.png`), fullPage: true });
    results[file].mobile = mNav;
    await mob.close();
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();