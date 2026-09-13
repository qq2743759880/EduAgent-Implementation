const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/practice.html";
const url = "file:///" + path.replace(/\\/g, "/");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push("PAGEERR: " + e.message));
  page.on("console", m => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });
  page.on("dialog", d => d.dismiss());

  await page.goto(url, { waitUntil: "load" });

  // ---- 1. Responsive overflow check ----
  const overflow = {};
  for (const w of [1280, 768, 375]) {
    await page.setViewportSize({ width: w, height: 950 });
    await page.waitForTimeout(200);
    const m = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
      bodySw: document.body.scrollWidth,
    }));
    overflow[w] = { ...m, overflowX: m.sw - m.cw };
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-success-${w}.png`, fullPage: true });
  }

  // also test overflow on blank/judge views at 375
  await page.setViewportSize({ width: 375, height: 950 });
  await page.evaluate(() => {
    setTimeout(() => {}, 0);
  });
  await page.waitForTimeout(100);
  const overflow375Type = {};
  for (const t of ["single","multi","blank","judge"]) {
    await page.evaluate((ty) => {
      document.querySelectorAll('.q-typebar button').forEach(x => { x.classList.remove('on'); x.setAttribute('aria-selected','false'); });
      const tb = document.querySelector(`.q-typebar button[data-type="${ty}"]`);
      if (tb) tb.classList.add('on');
      document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
      document.getElementById('qi-' + ty).classList.remove('hid');
    }, t);
    await page.waitForTimeout(120);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    overflow375Type[t] = m.sw - m.cw;
  }

  // ---- 2. Judge logic verification ----
  // Switch to judge, click "错误" (the genuinely correct choice for this false statement)
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.evaluate(() => {
    document.querySelectorAll('.q-typebar button').forEach(x => { x.classList.remove('on'); x.setAttribute('aria-selected','false'); });
    const tb = document.querySelector(`.q-typebar button[data-type="judge"]`);
    if (tb) tb.classList.add('on');
    document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
    document.getElementById('qi-judge').classList.remove('hid');
  });
  await page.evaluate(() => { document.getElementById('qi-judge-result').classList.add('hid'); });
  await page.click('.judge-opt[data-judge="wrong"]');
  await page.waitForTimeout(150);
  const judgeWrongResult = await page.evaluate(() => {
    const r = document.getElementById('qi-judge-result');
    return { shown: !r.classList.contains('hid'), text: r.querySelector('.t').textContent, cls: r.className };
  });
  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-judge-click-wrong-1280.png", fullPage: true });

  // also click "正确" on a fresh state
  await page.reload({ waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.evaluate(() => {
    document.querySelectorAll('.q-typebar button').forEach(x => { x.classList.remove('on'); x.setAttribute('aria-selected','false'); });
    const tb = document.querySelector(`.q-typebar button[data-type="judge"]`);
    if (tb) tb.classList.add('on');
    document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
    document.getElementById('qi-judge').classList.remove('hid');
  });
  await page.click('.judge-opt[data-judge="correct"]');
  await page.waitForTimeout(150);
  const judgeCorrectResult = await page.evaluate(() => {
    const r = document.getElementById('qi-judge-result');
    return { shown: !r.classList.contains('hid'), text: r.querySelector('.t').textContent, cls: r.className };
  });

  // ---- 3. Blank submit behavior ----
  await page.evaluate(() => {
    document.querySelectorAll('.q-typebar button').forEach(x => x.classList.remove('on'));
    const tb = document.querySelector(`.q-typebar button[data-type="blank"]`);
    if (tb) tb.classList.add('on');
    document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
    document.getElementById('qi-blank').classList.remove('hid');
  });
  await page.fill("#qi-blank-input", "404");
  await page.click("#qi-blank-submit");
  await page.waitForTimeout(150);
  const blank = await page.evaluate(() => {
    const input = document.getElementById('qi-blank-input');
    const btn = document.getElementById('qi-blank-submit');
    const res = document.getElementById('qi-blank-result');
    return {
      inputDisabled: input.disabled,
      submitHidden: btn.classList.contains('hid'),
      submitGray: btn.classList.contains('gray'),
      resultShown: !res.classList.contains('hid'),
      resultText: res.querySelector('.t').textContent,
      resultCls: res.className,
    };
  });
  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-blank-submit-wrong-1280.png", fullPage: true });

  // correct blank value
  await page.reload({ waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.evaluate(() => {
    document.querySelectorAll('.q-typebar button').forEach(x => x.classList.remove('on'));
    const tb = document.querySelector(`.q-typebar button[data-type="blank"]`);
    if (tb) tb.classList.add('on');
    document.querySelectorAll('.quiz-item').forEach(el => el.classList.add('hid'));
    document.getElementById('qi-blank').classList.remove('hid');
  });
  await page.fill("#qi-blank-input", "404");
  await page.click("#qi-blank-submit");
  await page.waitForTimeout(150);
  const blankOk = await page.evaluate(() => {
    const res = document.getElementById('qi-blank-result');
    return { resultText: res.querySelector('.t').textContent, resultCls: res.className };
  });

  // ---- 4. rank/heading/typebar a11y snapshot of success ----
  await page.reload({ waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.waitForTimeout(200);
  const a11y = await page.evaluate(() => {
    const headline = document.querySelector('h1') ? document.querySelector('h1').textContent : null;
    const hCount = document.querySelectorAll('h1,h2,h3').length;
    const secH = Array.from(document.querySelectorAll('h2.sec-h, h2')).map(h => h.textContent.trim());
    const progressbar = document.querySelector('[role="progressbar"]');
    const tabs = Array.from(document.querySelectorAll('[role="tab"]')).map(t => ({ sel: t.getAttribute('aria-selected'), ariaControls: t.getAttribute('aria-controls') }));
    const tabpanels = document.querySelectorAll('[role="tabpanel"]').length;
    const statusEls = Array.from(document.querySelectorAll('[role="status"],[role="alert"]')).map(e => e.className);
    return { headline, hCount, secH, progressbar: progressbar ? { val: progressbar.getAttribute('aria-valuenow'), text: progressbar.querySelector('#qBarFill') ? null : progressbar.getAttribute('aria-valuetext') } : null, tabs, tabpanels, statusEls };
  });

  console.log(JSON.stringify({ overflow, overflow375Type, judgeWrongResult, judgeCorrectResult, blank, blankOk, a11y, errors }, null, 2));

  await browser.close();
})();