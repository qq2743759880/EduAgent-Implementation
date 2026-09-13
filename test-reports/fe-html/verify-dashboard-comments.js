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
  await page.goto(`file://${path.join(root, "dashboard.html").replace(/\\/g, "/")}`);
  await page.screenshot({ path: path.join(root, "dashboard-comments-fixed-1433.png"), fullPage: true });
  const result = await page.evaluate(() => {
    const demoNote = document.querySelector(".demo-note");
    const cta = document.querySelector('[data-sec="cta"]');
    const badgePanel = document.querySelector(".badge-row-panel");
    const badgeGrid = document.querySelector(".badges-strip");
    const section = document.querySelector('[data-sec="structure-badge-rank"]');
    const panels = Array.from(section?.querySelectorAll(":scope > .panel") || []);
    const badgeRect = badgePanel?.getBoundingClientRect();
    const rankRect = panels[1]?.getBoundingClientRect();
    const masteryValues = Array.from(document.querySelectorAll("#mastery .mval")).map((el) => el.textContent.trim());
    const yAxisLabel = Array.from(document.querySelectorAll(".trend-svg text")).map((el) => el.textContent.trim());
    const badgeColumns = badgeGrid ? getComputedStyle(badgeGrid).gridTemplateColumns.split(" ").filter(Boolean).length : 0;
    return {
      demoRemoved: !demoNote,
      quickEntryRemoved: !cta,
      badgeMovedBelow: !!(badgeRect && rankRect && badgeRect.top > rankRect.top),
      badgeHorizontal: badgeColumns >= 6,
      donutText: document.querySelector("#donut .center")?.textContent.trim() || "",
      masteryValues,
      allMasteryPercent: masteryValues.length === 9 && masteryValues.every((v) => v.endsWith("%")),
      yAxisHasUnit: yAxisLabel.includes("时间/min"),
      yTickCount: document.querySelectorAll("#trend-y-axis text").length,
      overflowX: document.documentElement.scrollWidth > window.innerWidth,
    };
  });
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
  const pass = result.demoRemoved
    && result.quickEntryRemoved
    && result.badgeMovedBelow
    && result.badgeHorizontal
    && result.donutText.includes("投入时间")
    && result.allMasteryPercent
    && result.yAxisHasUnit
    && result.yTickCount > 0
    && !result.overflowX;
  if (!pass) process.exit(1);
})();
