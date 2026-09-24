// TA7 手册黄条站证据：chat.html 连续 3 次触发黄色警示条并截图。
// 复用既有 CDP 浏览器基建（scripts/gates/_shared.mjs::createBrowser，禁 Playwright）。
// 用法：node ta7_shots.mjs <studentToken> [outDir]
import { createBrowser, ensureDir } from "./scripts/gates/_shared.mjs";
import { writeFileSync } from "node:fs";

const token = process.argv[2];
const outDir = process.argv[3] || "test-reports/ta7/shots";
if (!token) { console.error("usage: node ta7_shots.mjs <studentToken> [outDir]"); process.exit(2); }
ensureDir(outDir);

// 清掉 gate 身份注入环境变量：本脚本自己写学生 token，避免被 gate 脚本的 admin 身份覆盖。
for (const k of Object.keys(process.env)) {
  if (k.startsWith("EDU_GATE_")) delete process.env[k];
}

const QUERY = "帮我把《Python 入门》这门课加入我的收藏，并说明你调用了哪个工具、结果如何。";
const results = [];

const browser = await createBrowser({ settleMs: 2500 });
try {
  // 注入登录态：导航到 chat 页 → 写 token → 重载
  await browser.navigate(`http://127.0.0.1:3322/chat.html?boot=1`, 2000);
  await browser.cdp.send("Runtime.evaluate", {
    expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); "ok"`,
    returnByValue: true,
  });

  for (let round = 1; round <= 3; round += 1) {
    await browser.navigate(`http://127.0.0.1:3322/chat.html?r=${round}&ts=${Date.now()}`, 3500);
    // 确认登录态（守卫生效 = 页面拿到 token）
    const hasTok = (await browser.cdp.send("Runtime.evaluate", {
      expression: `!!localStorage.getItem("edu:auth:token")`, returnByValue: true,
    }))?.result?.value;

    // 新建会话（避免历史消息干扰截图）
    await browser.cdp.send("Runtime.evaluate", {
      expression: `(typeof newSession === "function") && newSession(); "ok"`,
      returnByValue: true,
    }).catch(() => null);

    // 输入话术并发送
    await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => {
        const i = document.getElementById("composerInput");
        i.value = ${JSON.stringify(QUERY)};
        i.dispatchEvent(new Event("input", { bubbles: true }));
        document.getElementById("sendBtn").click();
        return i.value;
      })()`,
      returnByValue: true,
    });

    // 等黄条出现（最多 90s）：role="alert" 且文本含「未实际执行」
    let warned = false;
    let alertText = "";
    for (let i = 0; i < 90; i += 1) {
      const r = await browser.cdp.send("Runtime.evaluate", {
        expression: `(() => {
          const el = document.querySelector('[role="alert"]');
          if (!el) return "";
          const t = (el.innerText || "").trim();
          return t.includes("未实际执行") ? ("HIT:" + t) : "";
        })()`,
        returnByValue: true,
      }).catch(() => null);
      const v = r?.result?.value || "";
      if (v.startsWith("HIT:")) { warned = true; alertText = v.slice(4); break; }
      await new Promise((res) => setTimeout(res, 1000));
    }

    // 再等 1.5s 让打字机把答案收尾
    await new Promise((res) => setTimeout(res, 1500));
    const out = `${outDir}/b11-ta7-r${round}.png`;
    await browser.screenshot(out, { quality: 92 });
    results.push({ round, tokenPresent: !!hasTok, yellowBar: warned, alertText, shot: out });
    console.log(JSON.stringify({ round, yellowBar: warned, alertText: alertText.slice(0, 60), shot: out }));
  }
} finally {
  await browser.close?.();
}
writeFileSync(`${outDir}/b11-ta7-summary.json`, JSON.stringify({ query: QUERY, results }, null, 2));
const okCount = results.filter((r) => r.yellowBar).length;
console.log(JSON.stringify({ yellowBarTriggered: `${okCount}/3`, results }, null, 2));
process.exit(okCount === 3 ? 0 : 1);
