const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.route("**/cdn.example.com/**", (r) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="338"><rect width="600" height="338" fill="#ccc"/></svg>`;
    r.fulfill({ status: 200, contentType: "image/svg+xml", body: svg });
  });
  const url = "file:///" + "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/courses.html".replace(/\\/g, "/");
  for (const w of [1280, 1024, 768, 375]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto(url, { waitUntil: "load" });
    await page.waitForTimeout(500);
    const info = await page.evaluate(() => {
      const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
      };
      const sortChips = [...document.querySelectorAll("#sortRow .chip")].map(box);
      const pagBtns = [...document.querySelectorAll("#pgPages .pg-btn")].map(box);
      const fbRows = box(document.getElementById("fbRows"));
      const fGroups = [...document.querySelectorAll(".fb-rows .f-group")].map(box);
      return { sortChips, pagBtns, fbRows, fGroups };
    });
    console.log(`WIDTH ${w}:`);
    console.log("  sortChips:", JSON.stringify(info.sortChips));
    console.log("  pagBtns:", JSON.stringify(info.pagBtns));
    console.log("  fbRows:", JSON.stringify(info.fbRows));
    console.log("  fGroups:", JSON.stringify(info.fGroups));
  }
  await browser.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
