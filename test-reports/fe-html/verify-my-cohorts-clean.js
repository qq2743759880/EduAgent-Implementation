const path = require("path");
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = require(path.join(__dirname, "..", "..", "edu-frontend", "node_modules", "playwright")));
}

const root = __dirname;

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1433, height: 838 } });
  await page.goto(`file://${path.join(root, "my-cohorts.html").replace(/\\/g, "/")}`);
  await page.screenshot({ path: path.join(root, "my-cohorts-clean-1433.png"), fullPage: true });
  const result = await page.evaluate(() => {
    const pageEl = document.querySelector(".page")?.getBoundingClientRect();
    return {
      statebarRemoved: !document.querySelector(".statebar"),
      demoNoteRemoved: !document.querySelector(".demo-note"),
      successVisible: getComputedStyle(document.getElementById("panel-success")).display !== "none",
      lowerBoundFixed: !!(pageEl && pageEl.bottom >= window.innerHeight - 1),
      overflowX: document.documentElement.scrollWidth > window.innerWidth,
    };
  });
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
  if (!result.statebarRemoved || !result.demoNoteRemoved || !result.successVisible || !result.lowerBoundFixed || result.overflowX) {
    process.exit(1);
  }
})();
