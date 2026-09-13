const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/community.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });
  page.on("dialog", (d) => d.dismiss());

  const setVw = (vw) => page.evaluate((w) => {
    document.querySelectorAll('[data-vw]').forEach(x => x.classList.remove('on'));
    const b = document.querySelector(`[data-vw="${w}"]`); if (b) b.classList.add('on');
    document.documentElement.style.width = w + 'px';
    document.documentElement.style.margin = '0 auto';
  }, vw);

  const setSt = (st) => page.evaluate((s) => {
    document.querySelectorAll('[data-st]').forEach(x => x.classList.remove('on'));
    const b = document.querySelector(`[data-st="${s}"]`); if (b) b.classList.add('on');
    var views = {ok: buildOk, loading: buildLoading, empty: buildEmpty, error: buildError};
    // 直接调用页内演示函数
    window.__community = window.__community || {};
    document.getElementById('boards').setAttribute('data-state', s);
    var ev = new CustomEvent('_demo', { detail: s });
    document.dispatchEvent(ev);
  }, st);

  const shots = [];
  for (const w of [1440, 1280, 1024, 768, 520, 375]) shots.push({ name: `shot-c-ok-${w}`, w, st: "ok" });
  shots.push({ name: "shot-c-loading-1280", w: 1280, st: "loading" });
  shots.push({ name: "shot-c-empty-1280", w: 1280, st: "empty" });
  shots.push({ name: "shot-c-error-1280", w: 1280, st: "error" });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 950 });
    await page.evaluate(() => { document.documentElement.style.width = ''; });
    await page.waitForTimeout(350);
    await setVw(s.w);
    await page.waitForTimeout(150);
    // 通过点击 respbar 的 状态按钮 驱动演示
    if (s.st !== "ok") {
      await page.click(`.respbar [data-st="${s.st}"]`);
      await page.waitForTimeout(250);
    }
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/${s.name}.png`, fullPage: true });
    console.log("shot:", s.name, "ok");
  }

  // 交互 probe：四态切换 + 版块筛选可点 + 无横向溢出
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 375, height: 950 });
  await page.evaluate(() => { document.documentElement.style.width = '375px'; });
  await page.waitForTimeout(300);
  const ov375 = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  await page.click('.respbar [data-st="empty"]'); await page.waitForTimeout(150);
  const emptyShown = await page.isVisible('#boards .state');
  await page.click('.respbar [data-st="error"]'); await page.waitForTimeout(150);
  const errShown = await page.isVisible('#boards .state');
  await page.click('.respbar [data-st="ok"]'); await page.waitForTimeout(150);
  // 版块筛选点击
  await page.click('.chip[data-b="en"]');
  const chipOn = await page.evaluate(() => document.querySelector('.chip.on') && document.querySelector('.chip.on').dataset.b);
  // 净文本检查：无 undefined、无污染内联 transform
  await page.evaluate(() => { document.documentElement.style.width = '375px'; });
  const bodyText = await page.evaluate(() => document.body.innerText);
  const hasUndefined = bodyText.includes('undefined');

  console.log(JSON.stringify({
    overflow375: ov375.sw + '>' + ov375.cw + ' => ' + (ov375.sw > ov375.cw ? 'FAIL' : 'OK'),
    emptyShown, errShown, chipOn, hasUndefined
  }, null, 2));
  console.log("errors:", errors.length ? errors : "none");
  await browser.close();
})();