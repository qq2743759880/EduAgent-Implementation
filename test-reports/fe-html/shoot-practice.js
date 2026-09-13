const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/practice.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  const errors = [];
  page.on("pageerror", (e) => { errors.push("PAGEERR: " + e.message); });
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });
  page.on("dialog", (d) => d.dismiss());

  // 矩阵：375/768/1024/1280/1440 × success；另补 loading/error/empty 态 + 四题型
  const shots = [];
  for (const w of [375, 768, 1024, 1280, 1440]) shots.push({ name: `shot-p-success-${w}`, w, state: "success" });
  shots.push({ name: "shot-p-loading-1280", w: 1280, state: "loading" });
  shots.push({ name: "shot-p-error-1280", w: 1280, state: "error" });
  shots.push({ name: "shot-p-empty-1280", w: 1280, state: "empty" });
  shots.push({ name: "shot-p-typesingle-1280", w: 1280, state: "single" });
  shots.push({ name: "shot-p-typemulti-1280", w: 1280, state: "multi" });
  shots.push({ name: "shot-p-typeblank-1280", w: 1280, state: "blank" });
  shots.push({ name: "shot-p-typejudge-1280", w: 1280, state: "judge" });

  const setState = (s) => page.evaluate((st) => {
    document.querySelectorAll('.statebar button').forEach(b => b.classList.remove('on'));
    ['panel-success','panel-loading','panel-error','panel-empty'].forEach(id => {
      document.getElementById(id).style.display = id === 'panel-' + st ? '' : 'none';
    });
    const btn = document.querySelector(`.statebar button[data-state="${st}"]`);
    if (btn) btn.classList.add('on');
  }, s);

  const setType = (t) => page.evaluate((ty) => {
    document.querySelectorAll('.q-typebar button').forEach(b => { b.classList.remove('on'); b.setAttribute('aria-selected','false'); });
    const tb = document.querySelector(`.q-typebar button[data-type="${ty}"]`);
    if (tb) { tb.classList.add('on'); tb.setAttribute('aria-selected','true'); }
    document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
    document.getElementById('qi-' + ty).classList.remove('hid');
  }, t);

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 950 });
    await page.waitForTimeout(300);
    if (s.state !== "success") { setState(s.state); await page.waitForTimeout(250); }
    if (["single","multi","blank","judge"].includes(s.state)) {
      setState("success"); setType(s.state); await page.waitForTimeout(250);
    }
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/${s.name}.png`, fullPage: true });
    console.log("shot:", s.name, "ok");
  }

  // 交互素质 probe：四题型各点一次判分，确认结果区非空
  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.waitForTimeout(300);
  // 填空判分
  setType("blank");
  await page.fill("#qi-blank-input", "404");
  await page.click("#qi-blank-submit");
  const blankResShown = await page.isVisible("#qi-blank-result");
  const blankAnaShown = await page.isVisible("#qi-blank-analysis");
  // 判断判分
  setType("judge");
  await page.click('.judge-opt[data-judge="wrong"]');
  const judgeResShown = await page.isVisible("#qi-judge-result");
  const judgeAnaShown = await page.isVisible("#qi-judge-analysis");
  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/shot-p-probe-judge-1280.png", fullPage: true });

  console.log(JSON.stringify({ blankResult: blankResShown, blankAnalysis: blankAnaShown, judgeResult: judgeResShown, judgeAnalysis: judgeAnaShown }, null, 2));
  console.log("errors:", errors.length ? errors : "none");

  await browser.close();
})();