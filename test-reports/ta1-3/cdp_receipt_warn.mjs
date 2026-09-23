/**
 * TA3 黄条视觉实证（CDP，禁 Playwright）
 *
 * 流程（每个 run 独立页面加载）：
 *   1) 打开 http://127.0.0.1:3322/chat.html（student token 注入 localStorage）
 *   2) 输入稳定触发话术并点发送
 *   3) 轮询 .receipt-warn 出现（最多 75s），取「出现时刻 / 计算样式 / 尺寸 / 文本」
 *   4) 截图落 test-reports/ta1-3/shots/
 *
 * 用法：EDU_GATE_TOKEN=<token> node test-reports/ta1-3/cdp_receipt_warn.mjs --runs 3
 */
import { createBrowser, sleep, DEFAULT_BASE } from "../../scripts/gates/_shared.mjs";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const getArg = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const runs = Number(getArg("runs", 3));
const query = getArg("query", "请严格按格式回复：第一行只写「已收藏」，第二行起用两句话介绍《Python 入门》适合谁学。");
const base = getArg("base", DEFAULT_BASE);
const outDir = getArg("outdir", "test-reports/ta1-3/shots");
const token = process.env.EDU_GATE_TOKEN || "";
if (!token) { console.error("EDU_GATE_TOKEN required"); process.exit(2); }
mkdirSync(outDir, { recursive: true });

const results = [];
const browser = await createBrowser();
try {
  await browser.cdp.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); } catch {}`,
  });
  await browser.setViewport(1440, 900);

  for (let n = 1; n <= runs; n += 1) {
    await browser.navigate(`${base}/chat.html`, 2500);
    const t0 = Date.now();
    await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => { const ta = document.getElementById("composerInput");
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(ta, ${JSON.stringify(query)});
        ta.dispatchEvent(new Event("input", { bubbles: true })); return "SET"; })()`,
      returnByValue: true,
    });
    await sleep(400);
    const cl = await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => { const b = document.getElementById("sendBtn"); if (!b) return "NO_SEND";
        b.click(); return "CLICKED"; })()`, returnByValue: true });
    console.log(`[run${n}] ${cl.result.value}`);

    let hit = null;
    for (let i = 0; i < 150; i += 1) {
      await sleep(500);
      const r = await browser.cdp.send("Runtime.evaluate", {
        expression: `(() => {
          const w = document.querySelector("#aiResp .receipt-warn, .bubb .receipt-warn, .receipt-warn");
          if (!w) return null;
          const cs = getComputedStyle(w); const rect = w.getBoundingClientRect();
          const ans = document.getElementById("aiResp");
          return JSON.stringify({
            cls: w.className, role: w.getAttribute("role"),
            text: (w.textContent || "").trim(),
            display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
            bg: cs.backgroundColor, border: cs.borderStyle + " " + cs.borderColor,
            fontWeight: cs.fontWeight, color: cs.color,
            w: Math.round(rect.width), h: Math.round(rect.height), top: Math.round(rect.top),
            hasIcon: !!w.querySelector(".receipt-ic"), hasTx: !!w.querySelector(".receipt-tx"),
            answerChars: ans ? (ans.textContent || "").length : -1,
            inAiResp: ans ? ans.contains(w) : false,
          });
        })()`, returnByValue: true });
      if (r.result.value) { hit = { t: Date.now() - t0, ...JSON.parse(r.result.value) }; break; }
    }

    const shot = path.join(outDir, `ta3_receipt_warn_run${n}.png`);
    await browser.screenshot(shot, { quality: 70 });
    results.push({ run: n, hit, shot });
    console.log(`[run${n}] ${hit ? "FOUND @+" + hit.t + "ms :: " + JSON.stringify(hit) : "NOT FOUND"}`);
    await sleep(6000);   /* 拉开间距：上游 LLM 偶发 llm_failed，密集请求会放大失败率 */
  }
} finally {
  await browser.close();
}

console.log("\n=== TA3 SUMMARY ===");
for (const r of results) {
  console.log(JSON.stringify({ run: r.run, found: !!r.hit, t: r.hit?.t ?? null,
    visible: r.hit ? (r.hit.display !== "none" && r.hit.visibility !== "hidden" && Number(r.hit.opacity) > 0 && r.hit.w > 0 && r.hit.h > 0) : false,
    text: r.hit?.text ?? null, bg: r.hit?.bg ?? null, shot: r.shot }));
}
const ok = results.filter((r) => r.hit).length;
console.log(`触发成功 ${ok}/${results.length}`);
writeFileSync(path.join(outDir, "ta3_result.json"), JSON.stringify(results, null, 1));
