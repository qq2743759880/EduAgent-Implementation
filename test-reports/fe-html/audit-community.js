const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/community.html";
  const url = "file:///" + path.replace(/\\/g, "/");
  const errors = [];
  page.on("pageerror", (e) => errors.push("PAGEERR: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text()); });

  const setVw = (w) => page.evaluate((v) => {
    document.querySelectorAll('[data-vw]').forEach(x => x.classList.remove('on'));
    const b = document.querySelector(`[data-vw="${v}"]`); if (b) b.classList.add('on');
    document.documentElement.style.width = v + 'px';
    document.documentElement.style.margin = '0 auto';
  }, w);

  await page.goto(url, { waitUntil: "load" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.evaluate(() => { document.documentElement.style.width = ''; });
  await page.waitForTimeout(200);
  await setVw(1280);
  await page.waitForTimeout(200);

  // ===== 1. 对齐/留白：测量各块 y 间距 @1280 =====
  const gaps = await page.evaluate(() => {
    const sel = ['.hero', '.filter', '.toolbar', '.boards', '.pager', 'footer.demo-note'];
    const r = {};
    let prev = null, prevName = null;
    sel.forEach(s => {
      const el = document.querySelector(s); if (!el) return;
      const b = el.getBoundingClientRect();
      r[s + '.top'] = Math.round(b.top);
      r[s + '.h'] = Math.round(b.height);
      if (prev !== null) r[prevName + '->' + s + '.gapBefore'] = Math.round(b.top - prev);
      prev = b.top + b.height; prevName = s;
    });
    // 卡片间距
    const cards = [...document.querySelectorAll('.post')].map(c => Math.round(c.getBoundingClientRect().height));
    const cardCaps = [...document.querySelectorAll('.post')].slice(0,2).map((c,i,arr)=>{
      if (i === arr.length-1) return 0;
      return Math.round(arr[i+1].getBoundingClientRect().top - c.getBoundingClientRect().height - c.getBoundingClientRect().top);
    });
    return { r, cards, cardCaps };
  });

  // ===== 2. 字段映射验证：置顶帖 💬/+1 =====
  const pinned = await page.evaluate(() => {
    const first = document.querySelector('.post'); // default 置顶
    const txt = first.innerText;
    const cmt = first.querySelector('.cmt i').textContent;
    // 找 👍 数字
    const m = txt.match(/👍\s*([\d,]+)/);
    const c = txt.match(/💬\s*([\d,]+)/);
    const v = txt.match(/👁\s*([\d,]+)/);
    return { cmt, like: m && m[1], comment: c && c[1], view: v && v[1] };
  });

  // ===== 3. a11y 检查 =====
  const a11y = await page.evaluate(() => {
    const chips = document.querySelector('.chips');
    const chipRole = chips && chips.getAttribute('role');
    const tabRole = [...document.querySelectorAll('.chip')].map(c=>c.getAttribute('role')).join(',');
    const hasTabpanel = !!document.querySelector('[role=tabpanel]');
    const kw = document.getElementById('kw');
    const kwLabel = document.getElementById('kw-label');
    const kwAria = kw && kw.getAttribute('aria-label');
    const sortAria = document.getElementById('sort') && document.getElementById('sort').getAttribute('aria-label');
    const focus = document.querySelector('*:focus-visible');
    const focusCSS = { outline: focus ? getComputedStyle(focus).outline : '' };
    const fabAria = document.getElementById('fab').getAttribute('aria-label');
    const postNewLabel = document.getElementById('postNewDesktop');
    const pinnedCard = document.querySelector('.post'); // 置顶
    const pinnedARIA = pinnedCard && pinnedCard.getAttribute('aria-label');
    const boardsLive = document.getElementById('boards').getAttribute('aria-live');
    return { chipRole, tabRole, hasTabpanel, kwLabelNeedle: document.querySelectorAll('label[for=kw]').length, kwAria, sortAria, fabAria, boardsLive, pinnedARIA };
  });

  // tabindex 可达性 + tab 顺序
  const tab = await page.evaluate(() => {
    const posts = [...document.querySelectorAll('.post')];
    return { postTabindex: posts.map(p=>p.getAttribute('tabindex')), postFocusable: posts.every(p=>p.tabIndex>=0) };
  });

  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-c-ok-1280.png", fullPage: true });

  // 模拟键盘 focus 到第一张卡，验证焦点环
  await page.evaluate(() => document.querySelector('.post').focus());
  const focusRing = await page.evaluate(() => {
    const el = document.querySelector('.post:focus');
    const cs = el ? getComputedStyle(el) : null;
    return cs ? { outline: cs.outline, outlineOffset: cs.outlineOffset } : null;
  });

  // ===== 4. 响应式 @520、@375 =====
  await setVw(520); await page.waitForTimeout(150);
  const at520 = await page.evaluate(() => {
    const postNew = getComputedStyle(document.getElementById('postNewDesktop')).display;
    const fab = getComputedStyle(document.getElementById('fab')).display;
    const chips = document.querySelector('.chips');
    const chipCS = getComputedStyle(chips);
    const chipsScroll = { overflowX: chipCS.overflowX, clientWidth: chips.clientWidth, scrollWidth: chips.scrollWidth };
    return { postNew, fab, chipsScroll, canScroll: chips.scrollWidth > chips.clientWidth };
  });
  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-c-ok-520.png", fullPage: true });

  await setVw(375); await page.waitForTimeout(150);
  const ov = await page.evaluate(() => ({
    docSW: document.documentElement.scrollWidth,
    docCW: document.documentElement.clientWidth,
    bodySW: document.body.scrollWidth,
    fabDisplay: getComputedStyle(document.getElementById('fab')).display,
    postNewDisplay: getComputedStyle(document.getElementById('postNewDesktop')).display,
  }));
  await page.screenshot({ path: "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/audit-c-ok-375.png", fullPage: true });

  // @container 是否随 html 宽度真实响应：对比 hero h1 font-size in 1280 vs 375
  const h1 = await page.evaluate(() => getComputedStyle(document.querySelector('.hero h1')).fontSize);

  // chips 横向滚动验证：375 检查 scrollWidth vs clientWidth
  const chip375 = await page.evaluate(() => {
    const c = document.querySelector('.chips');
    return { cw: c.clientWidth, sw: c.scrollWidth, overflowX: getComputedStyle(c).overflowX };
  });

  // ===== 5. 微观交互 UX：帖子卡是否有点击 handler（误导性）=====
  const postUX = await page.evaluate(() => {
    const p = document.querySelector('.post');
    const cls = p.className;
    const cursor = getComputedStyle(p).cursor;
    const el = p; // 事件冒泡检测
    return { className: cls, cursor };
  });

  // 四态文案
  const states = {};
  for (const s of ['loading','empty','error']) {
    await page.evaluate((s)=>document.querySelector(`.respbar [data-st="${s}"]`).click(), s);
    await page.waitForTimeout(120);
    states[s] = await page.evaluate(() => document.getElementById('boards').innerText.slice(0,120));
  }
  await page.evaluate(()=>document.querySelector('.respbar [data-st="ok"]').click());

  console.log("=== GAPS @1280 ===", JSON.stringify(gaps, null, 1));
  console.log("=== PINNED FIELD MAPPING ===", JSON.stringify(pinned));
  console.log("=== A11Y ===", JSON.stringify(a11y));
  console.log("=== TAB ===", JSON.stringify(tab));
  console.log("=== FOCUS RING (after focus) ===", JSON.stringify(focusRing));
  console.log("=== @520 ===", JSON.stringify(at520));
  console.log("=== @375 ===", JSON.stringify(ov), "chip375:", JSON.stringify(chip375), "heroH1@375:", h1);
  console.log("=== POST UX ===", JSON.stringify(postUX));
  console.log("=== STATES TEXT ===", JSON.stringify(states, null, 1));
  console.log("=== errors ===", errors.length ? errors : "none");
  await browser.close();
})();