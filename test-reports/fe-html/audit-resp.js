const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/community.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  const results = {};
  for (const vw of [1280, 520, 375]) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: vw, height: 1000 });
    await page.evaluate(() => { document.documentElement.style.width = ''; document.documentElement.style.margin = ''; });
    await page.waitForTimeout(250);
    const o = await page.evaluate(() => {
      const de = document.documentElement;
      const chips = document.querySelector('.chips');
      return {
        viewport: window.innerWidth,
        deClientWidth: de.clientWidth,
        deScrollWidth: de.scrollWidth,
        bodySW: document.body.scrollWidth,
        overflowXfail: de.scrollWidth > de.clientWidth,
        heroH1: getComputedStyle(document.querySelector('.hero h1')).fontSize,
        fab: getComputedStyle(document.getElementById('fab')).display,
        postNew: getComputedStyle(document.getElementById('postNewDesktop')).display,
        chips: { clientWidth: chips.clientWidth, scrollWidth: chips.scrollWidth, overflowX: getComputedStyle(chips).overflowX, canScroll: chips.scrollWidth > chips.clientWidth },
        filter: { display: getComputedStyle(document.querySelector('.filter')).display, direction: getComputedStyle(document.querySelector('.filter')).flexDirection },
      };
    });
    results[vw] = o;
    if (vw === 375) await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-c-ok-375.png", fullPage: true });
    if (vw === 520) await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-c-ok-520.png", fullPage: true });
  }
  console.log(JSON.stringify(results, null, 2));
  await browser.close();
})();