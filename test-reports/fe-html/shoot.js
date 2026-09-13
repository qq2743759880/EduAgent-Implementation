const { chromium } = require("E:/stu/project/stu/EduAgent实施手册/edu-frontend/node_modules/playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // 封面 cover_url 占位域名 cdn.example.com：路由拦截，按课程 id 返回对应糖果渐变族 SVG（与 courses.html v4
  // 封面差异化一致：t1~t5 糖果渐变按 (id-1001)%5 分配），字段保持契约 cover_url，避免无效域名报错污染矩阵
  const TONES = [["#FF4D00","#FFB199"],["#58CC02","#A5F36A"],["#7C3AED","#C4B5FD"],["#1CB0F6","#A5E8FF"],["#FFC800","#FFE58A"]];
  await page.route("**/cdn.example.com/**", (r) => {
    const m = r.request().url().match(/course-(\d+)\.jpg/);
    const id = m ? parseInt(m[1]) : 1001;
    const [c1, c2] = TONES[(id - 1001) % 5];
    const coverSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="338"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs><rect width="600" height="338" fill="url(#g)"/><circle cx="130" cy="120" r="80" fill="#fff" opacity=".14"/><circle cx="470" cy="250" r="110" fill="#fff" opacity=".10"/></svg>`;
    r.fulfill({ status: 200, contentType: "image/svg+xml", body: coverSvg });
  });
  const path = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/courses.html";
  const url = "file:///" + path.replace(/\\/g, "/");

  // 完整矩阵：375/768/1024/1280 × 四态
  const shots = [];
  const STATES = [
    { key: "success", fn: null },
    { key: "empty", fn: "empty" },
    { key: "loading", fn: "loading" },
    { key: "error", fn: "error" },
  ];
  const WIDTHS = [375, 768, 1024, 1280];
  for (const w of WIDTHS) {
    for (const s of STATES) {
      shots.push({ name: `${s.key}-${w}`, w, setState: s.fn });
    }
  }

  const errors = [];
  page.on("pageerror", (e) => { errors.push(String(e)); console.log("PAGERR-STACK:", e.stack); });
  page.on("console", (m) => {
    // 封面 cover_url 占位域名 cdn.example.com 无效——命中 onerror 回退渐变，属预期，不视为响应残缺
    if (m.type() === "error" && /ERR_CONNECTION_CLOSED/.test(m.text()) && /cdn\.example\.com/.test(m.text())) return;
    errors.push(m.text()); console.log("CONSOLE-ERR:", m.text());
  });

  for (const s of shots) {
    await page.goto(url, { waitUntil: "load" });
    await page.setViewportSize({ width: s.w, height: 900 });
    await page.evaluate(() => {
      window.__errors = [];
      window.onerror = (msg) => window.__errors.push(String(msg));
    });
    await page.waitForTimeout(600);
    const probe = await page.evaluate(() => ({
      resText: !!document.getElementById("resText"),
      contentArea: !!document.getElementById("contentArea"),
      fbToggle: !!document.getElementById("fbToggle"),
      cards: document.querySelectorAll(".card:not(.skeleton)").length,
      state: typeof window.state !== "undefined" ? window.state : "n/a",
    }));
    console.log(`PROBE[${s.name}]:`, JSON.stringify(probe));
    const pageErrs = await page.evaluate(() => window.__errors || []);
    if (pageErrs.length) console.log(`PAGE-ERRORS[${s.name}]:`, JSON.stringify(pageErrs));
    if (s.setState) {
      await page.evaluate((st) => { applyState(st); }, s.setState);
      await page.waitForTimeout(400);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html/shot-${s.name}.png`, fullPage: true });
  }
  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
  console.log(process.exitCode);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });