const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const url = "file:///E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/practice.html";
  const result = [];
  const run = async (sel, label) => {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: 1280, height: 950 });
    await page.click(sel);
    result.push({ case: label, t: (await page.textContent("#qi-judge-result .t")).trim() });
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-judge-${label}.png` });
  };
  await run('.judge-opt[data-judge="wrong"]', "erda"); // 点「错误」→ 应为回答正确
  await run('.judge-opt[data-judge="correct"]', "zhengque"); // 点「正确」→ 应为回答错误
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();