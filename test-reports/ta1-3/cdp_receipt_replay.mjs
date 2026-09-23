/**
 * TA3 黄条渲染路径实证（帧重放 · LLM 配额耗尽时的确定性替代）
 *
 * 背景：2026-09-24 01:43 起本机两个 LLM 均不可用（deepseek 余额 -0.01 / ark 订阅失效），
 *       端到端真实生成无法再复现。端到端证据已在此之前取得（见 REPORT-TA1-3「黄条」节）。
 *
 * 本脚本证明的是 **前端渲染路径**：用 CDP Fetch.fulfillRequest 重放一份
 * **真实后端 SSE 帧体**（取自 test-reports/ta1-3/after1_chat_html.json 的 responseBody，
 * 逐字节保留 start/retrieval/token/done），**仅**把 done 帧里的
 * `tool_receipt_unverified` 由 false 改成 true（该字段的真实取值已由后端 curl 3/3 断言）。
 * → 若前端仍能渲染出可见黄条，说明 chat.html 的黄条渲染路径本身是通的。
 *
 * 用法：EDU_GATE_TOKEN=<token> node test-reports/ta1-3/cdp_receipt_replay.mjs --runs 3
 */
import { createBrowser, sleep, DEFAULT_BASE } from "../../scripts/gates/_shared.mjs";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const getArg = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const runs = Number(getArg("runs", 3));
const base = getArg("base", DEFAULT_BASE);
const src = getArg("src", "test-reports/ta1-3/after1_chat_html.json");
const outDir = getArg("outdir", "test-reports/ta1-3/shots");
const token = process.env.EDU_GATE_TOKEN || "";
if (!token) { console.error("EDU_GATE_TOKEN required"); process.exit(2); }
mkdirSync(outDir, { recursive: true });

const captured = JSON.parse(readFileSync(src, "utf8"));
let body = captured.raw?.responseBody || "";
if (!body.includes('"tool_receipt_unverified": false')) {
  console.error("source body missing expected flag field"); process.exit(2);
}
body = body.replace('"tool_receipt_unverified": false', '"tool_receipt_unverified": true');
console.log(`[replay] 源帧体 ${body.length} 字节（${src}），仅改 done 帧 tool_receipt_unverified → true`);

const results = [];
const browser = await createBrowser();
try {
  await browser.cdp.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); } catch {}`,
  });
  await browser.cdp.send("Fetch.enable", {
    patterns: [{ urlPattern: "*api/chat/stream*", requestStage: "Request" }],
  });
  browser.cdp.on("Fetch.requestPaused", async (p) => {
    try {
      if (p.request.method === "POST" && (p.request.url || "").includes("/api/chat/stream")) {
        await browser.cdp.send("Fetch.fulfillRequest", {
          requestId: p.requestId,
          responseCode: 200,
          responseHeaders: [
            { name: "Content-Type", value: "text/event-stream; charset=utf-8" },
            { name: "Cache-Control", value: "no-cache" },
            { name: "Access-Control-Allow-Origin", value: "http://127.0.0.1:3322" },
            { name: "Access-Control-Allow-Credentials", value: "true" },
          ],
          body: Buffer.from(body, "utf-8").toString("base64"),
        });
      } else {
        await browser.cdp.send("Fetch.continueRequest", { requestId: p.requestId });
      }
    } catch (e) { /* ignore */ }
  });
  await browser.setViewport(1440, 900);

  for (let n = 1; n <= runs; n += 1) {
    await browser.navigate(`${base}/chat.html`, 2500);
    // 新建会话，避免复用历史会话（历史里已有上一次的正文提示，会干扰判定）
    await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => { const b = document.getElementById("newSession"); if (b) b.click(); return "new"; })()`,
      returnByValue: true,
    }).catch(() => {});
    await sleep(1200);
    const t0 = Date.now();
    await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => { const ta = document.getElementById("composerInput");
        if (!ta) return "NO_INPUT";
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(ta, "请把《Python 入门》收藏一下");
        ta.dispatchEvent(new Event("input", { bubbles: true })); return "SET"; })()`,
      returnByValue: true,
    });
    await sleep(400);
    const cl = await browser.cdp.send("Runtime.evaluate", {
      expression: `(() => { const b = document.getElementById("sendBtn"); if (!b) return "NO_SEND"; b.click(); return "CLICKED"; })()`,
      returnByValue: true });
    console.log(`[run${n}] ${cl.result.value}`);

    let hit = null;
    for (let i = 0; i < 120; i += 1) {
      await sleep(250);
      const r = await browser.cdp.send("Runtime.evaluate", {
        expression: `(() => {
          const w = document.querySelector("#aiResp .receipt-warn");
          if (!w) return null;
          const cs = getComputedStyle(w); const rect = w.getBoundingClientRect();
          return JSON.stringify({
            cls: w.className, role: w.getAttribute("role"), text: (w.textContent||"").trim(),
            display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
            bg: cs.backgroundColor, border: cs.borderStyle + " " + cs.borderColor,
            w: Math.round(rect.width), h: Math.round(rect.height),
            hasIcon: !!w.querySelector(".receipt-ic"), hasTx: !!w.querySelector(".receipt-tx"),
            answerChars: (document.getElementById("aiResp")||{textContent:""}).textContent.length,
          });
        })()`, returnByValue: true });
      if (r.result.value) { hit = { t: Date.now() - t0, ...JSON.parse(r.result.value) }; break; }
    }
    // 记录本次渲染的逐帧 DOM 增量（打字机证据）
    const shot = path.join(outDir, `ta3_replay_run${n}.png`);
    await browser.screenshot(shot, { quality: 70 });
    results.push({ run: n, hit, shot });
    console.log(`[run${n}] ${hit ? "FOUND @+" + hit.t + "ms " + JSON.stringify(hit) : "NOT FOUND"}`);
  }
} finally {
  await browser.close();
}

const ok = results.filter((r) => r.hit).length;
console.log("\n=== REPLAY SUMMARY ===");
for (const r of results) {
  const vis = r.hit ? (r.hit.display !== "none" && r.hit.visibility !== "hidden" && Number(r.hit.opacity) > 0 && r.hit.w > 0 && r.hit.h > 0) : false;
  console.log(JSON.stringify({ run: r.run, found: !!r.hit, visible: vis, t: r.hit?.t ?? null, text: r.hit?.text ?? null, bg: r.hit?.bg ?? null, shot: r.shot }));
}
console.log(`渲染路径实证 黄条可见 ${ok}/${results.length}`);
writeFileSync(path.join(outDir, "ta3_replay_result.json"), JSON.stringify(results, null, 1));
