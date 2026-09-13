const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");

const root = __dirname;
const pages = [
  "dashboard.html",
  "chat.html",
  "me.html",
  "admin-dashboard.html",
  "my-cohorts.html",
  "login-register.html",
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const file of pages) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`file://${path.join(root, file).replace(/\\/g, "/")}`);
    await page.screenshot({ path: path.join(root, `topnav-${file.replace(".html", "")}-1280.png`), fullPage: true });
    const metrics = await page.evaluate(() => {
      const nav = document.querySelector(".gnav")?.getBoundingClientRect();
      const pageEl = document.querySelector(".page")?.getBoundingClientRect();
      const chatStage = document.querySelector(".chat-stage")?.getBoundingClientRect();
      const chatSide = document.querySelector(".scrollside")?.getBoundingClientRect();
      const main = document.querySelector(".main")?.getBoundingClientRect();
      const body = document.body.getBoundingClientRect();
      return {
        navTop: nav ? Math.round(nav.top) : null,
        navBottom: nav ? Math.round(nav.bottom) : null,
        pageTop: pageEl ? Math.round(pageEl.top) : null,
        chatStageHeight: chatStage ? Math.round(chatStage.height) : null,
        chatSideIsRight: chatSide && main ? chatSide.left > main.left : null,
        overflowX: Math.ceil(body.width) > window.innerWidth,
      };
    });
    results.push({ file, ...metrics });
    await page.close();
  }
  const chat1024 = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  await chat1024.goto(`file://${path.join(root, "chat.html").replace(/\\/g, "/")}`);
  await chat1024.screenshot({ path: path.join(root, "topnav-chat-1024.png"), fullPage: true });
  results.push({
    file: "chat.html",
    viewport: 1024,
    ...(await chat1024.evaluate(() => {
      const main = document.querySelector(".main")?.getBoundingClientRect();
      const side = document.querySelector(".scrollside")?.getBoundingClientRect();
      const stage = document.querySelector(".chat-stage")?.getBoundingClientRect();
      const activeTitle = document.querySelector(".scrollside .sess.on .t")?.textContent?.trim() || "";
      const firstQuestion = document.querySelector(".chat-stage .msg.user .bubb")?.textContent?.trim() || "";
      const answerText = document.querySelector(".chat-stage .msg.ai .bubb")?.textContent?.trim() || "";
      return {
        mainRight: main ? Math.round(main.right) : null,
        sideRight: side ? Math.round(side.right) : null,
        sideIsRight: !!(main && side && side.left >= main.right),
        stageHeight: stage ? Math.round(stage.height) : null,
        overflowX: document.documentElement.scrollWidth > window.innerWidth,
        activeTitle,
        firstQuestion,
        activeMatchesQuestion: activeTitle.includes("脚本") && firstQuestion.includes("脚本与自动化"),
        answerComplete: answerText.includes("建议学习顺序"),
      };
    })),
  });
  await chat1024.close();

  const cohorts = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await cohorts.goto(`file://${path.join(root, "my-cohorts.html").replace(/\\/g, "/")}`);
  await cohorts.screenshot({ path: path.join(root, "topnav-my-cohorts-1280.png"), fullPage: true });
  results.push({
    file: "my-cohorts.html",
    viewport: 1280,
    ...(await cohorts.evaluate(() => {
      const pageEl = document.querySelector(".page")?.getBoundingClientRect();
      const toolbar = document.querySelector(".respbar,[role='toolbar']")?.getBoundingClientRect();
      return {
        pageBottom: pageEl ? Math.round(pageEl.bottom) : null,
        toolbarBottom: toolbar ? Math.round(toolbar.bottom) : null,
        lowerBoundFixed: !!(pageEl && pageEl.bottom >= window.innerHeight - 1),
      };
    })),
  });
  await cohorts.close();

  const login = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await login.goto(`file://${path.join(root, "login-register.html").replace(/\\/g, "/")}`);
  await login.screenshot({ path: path.join(root, "topnav-login-register-1280.png"), fullPage: true });
  results.push({
    file: "login-register.html",
    viewport: 1280,
    ...(await login.evaluate(() => {
      const pageEl = document.querySelector(".page")?.getBoundingClientRect();
      return {
        pageLeft: pageEl ? Math.round(pageEl.left) : null,
        pageRight: pageEl ? Math.round(pageEl.right) : null,
        fillsWidth: !!(pageEl && pageEl.left <= 0 && pageEl.right >= window.innerWidth),
        fillsHeight: !!(pageEl && pageEl.height >= window.innerHeight - 64),
      };
    })),
  });
  await login.close();
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();
