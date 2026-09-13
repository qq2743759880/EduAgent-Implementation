const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // v4：糖果色封面——拦截 SVG 按课程 id 分配渐变族（与 courses.html v4 一致）
  const TONES = [["#FF4D00","#FFB199"],["#58CC02","#A5F36A"],["#7C3AED","#C4B5FD"],["#1CB0F6","#A5E8FF"],["#FFC800","#FFE58A"]];
  await page.route("**/cdn.example.com/**", (r) => {
    const m = r.request().url().match(/course-(\d+)\.jpg/);
    const id = m ? parseInt(m[1]) : 1001;
    const [c1, c2] = TONES[(id - 1001) % 5];
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="338"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs><rect width="600" height="338" fill="url(#g)"/></svg>`;
    r.fulfill({ status: 200, contentType: "image/svg+xml", body: svg });
  });
  const url = "file:///" + "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/courses.html".replace(/\\/g, "/");

  const results = [];
  const check = (name, pass, detail) => results.push({ name, pass, detail });

  // --- 折叠断点：375 折叠 / 768+ 完整 ---
  for (const w of [375, 768, 1024, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto(url, { waitUntil: "load" });
    await page.waitForTimeout(400);
    const r = await page.evaluate(() => {
      const rows = document.getElementById("fbRows");
      const tog = document.getElementById("fbToggle");
      return { rowsDisplay: getComputedStyle(rows).display, togDisplay: getComputedStyle(tog).display };
    });
    const collapsedAtMobile = w < 768 ? (r.rowsDisplay === "none" && r.togDisplay !== "none") : (r.rowsDisplay !== "none");
    check(`375折叠/768+完整 @${w}`, collapsedAtMobile, `fbRows display=${r.rowsDisplay}, fbToggle display=${r.togDisplay}`);
  }

  // --- 两级导航：一级学科大类 9 类 + 二级方向动态 ---
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(600);
  const nav = await page.evaluate(() => {
    const cats = [...document.querySelectorAll("#categoryRow .chip")].map((c) => c.dataset.v);
    // 点击「编程」触发二级方向
    const prog = [...document.querySelectorAll("#categoryRow .chip")].find((c) => c.dataset.v === "编程");
    prog.click();
    const subs = [...document.querySelectorAll("#subRow .chip")].map((c) => c.dataset.v);
    const subGroupVisible = document.getElementById("subGroup").style.display !== "none";
    return { cats, subs, subGroupVisible };
  });
  check("一级学科大类 9 类", nav.cats.length === 10 && nav.cats.includes("全部") && nav.cats.includes("编程") && nav.cats.includes("数学") && nav.cats.includes("考研/考证/公考") && nav.cats.includes("校园成长"), JSON.stringify(nav.cats));
  check("二级方向随一级联动(编程→8 方向)", nav.subGroupVisible && nav.subs.length === 9 && nav.subs.includes("通用程序设计") && nav.subs.includes("脚本与自动化编程"), JSON.stringify(nav.subs));

  // --- 成功态：15 门真实课程 + 价格 + 分页 + 交付 + 糖果封面 + 学中玩元素 ---
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(600);
  const dom = await page.evaluate(() => {
    const cards = [...document.querySelectorAll("#contentArea .card:not(.skeleton)")];
    const titles = cards.map((c) => c.querySelector(".card-title")?.textContent);
    const prices = cards.map((c) => c.querySelector(".price")?.textContent?.trim());
    const cats = cards.map((c) => c.querySelector(".cat")?.textContent);
    const deliveries = cards.map((c) => c.querySelector(".delivery")?.textContent);
    const covers = cards.map((c) => c.querySelector(".cov")?.getAttribute("src"));
    const coverCombos = cards.map((c) => {
      const cls = [...c.querySelector(".cover").classList];
      const t = cls.find((x) => x.startsWith("cover--t"));
      const p = cls.find((x) => x.startsWith("cover--p"));
      return `${t} ${p}`;
    });
    const tones = [...new Set(coverCombos.map((x) => x.split(" ")[0]))];
    const emojis = cards.map((c) => c.querySelector(".subject-emoji")?.textContent);
    const xpBadges = cards.map((c) => c.querySelector(".xp-badge")?.textContent);
    const coverTitles = cards.map((c) => c.querySelector(".cover-title")?.textContent);
    const coverTitleStyle = cards[0] ? (() => {
      const el = c => c.querySelector(".cover-title");
      const s = getComputedStyle(el(cards[0]));
      return { fontFamily: s.fontFamily, color: s.color, fontWeight: s.fontWeight, textAlign: s.textAlign };
    })() : null;
    const rings = cards.filter((c) => c.querySelector(".ring")).length;
    const pag = document.getElementById("pagination");
    const pagStyle = getComputedStyle(pag);
    const pagBtns = [...document.querySelectorAll("#pgPages .pg-btn")].map((b) => {
      const r = b.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y) };
    });
    return {
      count: cards.length,
      titles, prices, cats, deliveries,
      coverCombos, tones, emojis, xpBadges, coverTitles, coverTitleStyle, rings,
      pagFlexDirection: pagStyle.flexDirection, pagFlexWrap: pagStyle.flexWrap, pagBtns,
      pgInfo: document.getElementById("pgInfo")?.textContent,
      resText: document.getElementById("resText")?.textContent,
      hasCoverUrl: covers.every((s) => s && s.includes("cdn.example.com")),
      heroMascot: !!document.querySelector(".hero-mascot"),
      heroSlogan: document.querySelector(".hero-slogan")?.textContent || "",
      xpFill: !!document.getElementById("xpFill"),
    };
  });
  check("成功态 15 门课程", dom.count === 15, `实际 ${dom.count}`);
  check("标题含 15 门真实课程名", dom.titles.length === 15 && dom.titles[0] === "通用编程入门班·直播" && dom.titles[14] === "办公与运维自动化班·直播", JSON.stringify(dom.titles));
  check("价格「¥X 起」格式(千分位)", dom.prices.length === 15 && dom.prices.every((p) => /¥[\d,]+\s*起/.test(p || "")), JSON.stringify(dom.prices));
  check("交付模式标签（在线直播/在线录播）", dom.deliveries.length === 15 && ["在线直播", "在线录播"].every((x) => dom.deliveries.includes(x)), JSON.stringify(dom.deliveries));
  check("封面=cdn.example.com 占位", dom.hasCoverUrl, "");
  check("封面差异化 15/15 组合唯一", dom.coverCombos.length === 15 && new Set(dom.coverCombos).size === 15, JSON.stringify(dom.coverCombos));
  check("相邻卡片渐变必不同", dom.coverCombos.every((c, i) => i === 0 || c.split(" ")[0] !== dom.coverCombos[i - 1].split(" ")[0]), "");
  check("糖果色封面 5 色全出现", dom.tones.length === 5 && ["cover--t1","cover--t2","cover--t3","cover--t4","cover--t5"].every((t) => dom.tones.includes(t)), JSON.stringify(dom.tones));
  check("学科 emoji 图标在封面", dom.emojis.length === 15 && dom.emojis.every((e) => e && e.trim().length > 0), JSON.stringify(dom.emojis));
  check("XP 徽章在封面", dom.xpBadges.length === 15 && dom.xpBadges.every((x) => /\+?\d+\s*XP/.test(x || "")), JSON.stringify(dom.xpBadges));
  check("封面标题 15/15 注入课程名", dom.coverTitles.length === 15 && dom.coverTitles.every((t) => t && t.trim().length > 0), JSON.stringify(dom.coverTitles));
  check("封面标题去掉交付后缀(·直播/·录播)", dom.coverTitles.every((t) => !/·(直播|录播)$/.test(t || "")), JSON.stringify(dom.coverTitles));
  check("封面标题对应课程名(首/尾)", dom.coverTitles[0] === "通用编程入门班" && dom.coverTitles[14] === "办公与运维自动化班", JSON.stringify(dom.coverTitles));
  check("封面标题字体=Baloo 2 圆润粗体", /Baloo 2/.test(dom.coverTitleStyle?.fontFamily || ""), dom.coverTitleStyle?.fontFamily);
  check("封面标题白字+粗体+居中", dom.coverTitleStyle?.color === "rgb(255, 255, 255)" && dom.coverTitleStyle?.fontWeight === "800" && dom.coverTitleStyle?.textAlign === "center", JSON.stringify(dom.coverTitleStyle));
  check("学习进度环 ≥10 张卡", dom.rings >= 10, `rings=${dom.rings}`);
  check("分页水平排列(从左到右)", dom.pagFlexDirection === "row" && dom.pagFlexWrap === "nowrap", `flex-direction=${dom.pagFlexDirection}, flex-wrap=${dom.pagFlexWrap}`);
  check("页码按钮同一行(同y)且x递增", dom.pagBtns.length >= 4 && dom.pagBtns.every((b, i) => i === 0 || (b.y === dom.pagBtns[0].y && b.x > dom.pagBtns[i - 1].x)), JSON.stringify(dom.pagBtns));
  check("分页文案真实数据量(共2628门·第1/176页)", /共 2628 门 · 第 1\/176 页/.test(dom.pgInfo || ""), dom.pgInfo);
  check("结果条总文案=共2628门", /共\s*<b>2628<\/b>|共\s*2628/.test(dom.resText || ""), dom.resText);
  check("Hero 吉祥物存在", dom.heroMascot, "");
  check("Hero 口号含「学中玩」", /学中玩/.test(dom.heroSlogan), dom.heroSlogan);
  check("XP 等级进度条存在", dom.xpFill, "");

  // --- 空态/错误态 DOM 断言 ---
  for (const st of ["empty", "error"]) {
    await page.evaluate((s) => applyState(s), st);
    await page.waitForTimeout(400);
    const r = await page.evaluate((s) => ({
      empty: !!document.querySelector(".empty"),
      error: !!document.querySelector(".error"),
    }), st);
    check(`状态 ${st} 渲染`, st === "empty" ? r.empty && !r.error : r.error && !r.empty, JSON.stringify(r));
  }

  let all = true;
  for (const r of results) { console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.detail ? " -> " + r.detail : ""}`); if (!r.pass) all = false; }
  console.log(all ? "VERIFY: ALL PASS" : "VERIFY: FAIL");
  await browser.close();
  process.exit(all ? 0 : 1);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
