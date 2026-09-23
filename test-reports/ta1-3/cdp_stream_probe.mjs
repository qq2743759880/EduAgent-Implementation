/**
 * TA1 定因 · CDP 前端探针 v2（零侵入）
 *
 * 修正 v1 的缺陷：v1 在 fetch 包装里调用 resp.body.getReader() 会锁住 ReadableStream，
 * 导致页面自身 getReader() 抛 "ReadableStream is locked"（探针自身制造了断点）。
 *
 * v2 方案：
 *  - 网络帧到达：用 CDP 域名事件 Network.dataReceived（不碰页面对象）
 *  - DOM 渲染：页面内 MutationObserver（只读 innerHTML/textContent 长度）
 *  - 时间基准：Node 侧 Date.now() 戳（同机时钟），click 时刻为 0
 *
 * 用法：
 *   EDU_GATE_TOKEN=<token> node test-reports/ta1-3/cdp_stream_probe.mjs --page chat.html --query "..." --out f.json
 */
import { createBrowser, sleep, DEFAULT_BASE } from "../../scripts/gates/_shared.mjs";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const getArg = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : dflt;
};
const page = getArg("page", "chat.html");
const query = getArg("query", "请用三句话介绍 Python 这门编程语言的特点");
const out = getArg("out", null);
const base = getArg("base", DEFAULT_BASE);
const maxMs = Number(getArg("maxms", 120000));
/* --replay <json>：LLM 配额耗尽时的确定性替代——
   用 CDP Fetch.fulfillRequest 重放该文件 raw.responseBody 里的**真实**后端 SSE 帧体。 */
const replay = getArg("replay", null);
const token = process.env.EDU_GATE_TOKEN || "";
if (!token) { console.error("EDU_GATE_TOKEN required"); process.exit(2); }
const url = page === "react" ? `${base}/chat` : `${base}/${page}`;

/* 只读 instrumentation：不拦截 fetch，不碰 body */
const INSTRUMENT = `
(() => {
  const T0 = Date.now();
  const S = { dom: [], t0: T0, errs: [] };
  window.__ta13 = S;
  window.addEventListener("error", (e) => S.errs.push("onerror:" + e.message));
  window.addEventListener("unhandledrejection", (e) => S.errs.push("rej:" + String(e.reason)));
  const pick = () => document.getElementById("aiResp") || document.querySelector("[data-chat-stage]")
                    || document.querySelector("main");
  let el = null;
  const attach = () => {
    const c = pick();
    if (!c || c === el) return !!el;
    el = c;
    S.observed = c.id || c.tagName;
    const mo = new MutationObserver(() => {
      const t = pick() || c;
      S.dom.push({ w: Date.now(), html: (t.innerHTML || "").length, txt: (t.textContent || "").length });
    });
    mo.observe(c, { childList: true, subtree: true, characterData: true });
    S.mo = mo;
    return true;
  };
  setInterval(attach, 25);
})();
`;

const browser = await createBrowser();
let result = null;
let clickWall = null;
const netChunks = [];
const netMeta = { reqId: null, url: null, responseWall: null, streamEndWall: null, status: null };
try {
  await browser.cdp.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); } catch {}`,
  });
  await browser.cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: INSTRUMENT });

  let replayBody = null;
  if (replay) {
    const src = JSON.parse(readFileSync(replay, "utf8"));
    replayBody = src.raw?.responseBody || "";
    if (!replayBody) { console.error("replay source has no raw.responseBody"); process.exit(2); }
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
            body: Buffer.from(replayBody, "utf-8").toString("base64"),
          });
        } else {
          await browser.cdp.send("Fetch.continueRequest", { requestId: p.requestId });
        }
      } catch (e) { /* ignore */ }
    });
    console.log(`[probe] REPLAY mode: ${replay} (${replayBody.length} bytes of real backend SSE frames)`);
  }

  browser.cdp.on("Network.requestWillBeSent", (p) => {
    // 只认 POST：同 URL 还有 CORS 预检 OPTIONS（会先/后各来一次），
    // 若把 reqId 指向 OPTIONS，loadingFinished 会在建连后 ~20ms 就误触发（v1 假"流已结束"根因）。
    if ((p.request?.url || "").includes("/api/chat/stream") && p.request?.method === "POST") {
      netMeta.reqId = p.requestId; netMeta.url = p.request.url;
      netMeta.requestWall = Date.now();
    }
  });
  browser.cdp.on("Network.responseReceived", (p) => {
    if (p.requestId === netMeta.reqId) {
      netMeta.responseWall = Date.now();
      netMeta.status = p.response?.status;
    }
  });
  browser.cdp.on("Network.dataReceived", (p) => {
    if (p.requestId === netMeta.reqId) {
      netChunks.push({ w: Date.now(), len: p.dataLength ?? 0, enc: p.encodedDataLength ?? 0 });
    }
  });
  browser.cdp.on("Network.loadingFinished", (p) => {
    if (p.requestId === netMeta.reqId) netMeta.streamEndWall = Date.now();
  });
  browser.cdp.on("Network.loadingFailed", (p) => {
    if (p.requestId === netMeta.reqId) { netMeta.streamEndWall = Date.now(); netMeta.failed = p.errorText; }
  });

  await browser.setViewport(1440, 900);
  await browser.navigate(url, 2500);

  const state = await browser.cdp.send("Runtime.evaluate", {
    expression: `JSON.stringify({ href: location.href, hasInput: !!document.getElementById("composerInput"),
      hasSend: !!document.getElementById("sendBtn"), ta13: !!window.__ta13,
      token: !!localStorage.getItem("edu:auth:token") })`,
    returnByValue: true,
  });
  console.log("[probe] page state:", state.result.value);

  clickWall = Date.now();
  /* React 受控输入：value 写入后必须等 React 重渲染（canSend 才为真、按钮才 enabled），
     故拆成两步 evaluate（中间 sleep），否则点击时 value 仍为空 → send() 早退、零请求。 */
  const setVal = `
(() => {
  const ta = document.getElementById("composerInput") || document.querySelector("textarea")
          || document.querySelector('input[type="text"]');
  if (!ta) return "NO_INPUT";
  const proto = ta.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(ta, ${JSON.stringify(query)});
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  ta.dispatchEvent(new Event("change", { bubbles: true }));
  return "SET";
})()`;
  const s1 = await browser.cdp.send("Runtime.evaluate", {
    expression: setVal, returnByValue: true,
  });
  console.log("[probe] setValue:", s1.result.value);
  await sleep(600);
  const click = `
(() => {
  /* 选择器优先级（踩坑）：React 页有 <form method="dialog" class="hidden"><button type="submit">
     的隐藏按钮，若把 button[type=submit] 排在前面会点到它 → 零请求假象。
     故：#sendBtn（chat.html）→ aria-label 精确等于 发送/发送消息（React 主 composer）→ 末位兜底 */
  const all = [...document.querySelectorAll("button")];
  const btn = document.getElementById("sendBtn")
           || all.find((b) => !b.disabled && b.getAttribute("aria-label") === "发送")
           || all.find((b) => !b.disabled && b.getAttribute("aria-label") === "发送消息")
           || all.find((b) => !b.disabled && /发送/.test(b.getAttribute("aria-label") || ""));
  if (!btn) return "NO_SEND";
  if (btn.disabled) return "SEND_DISABLED";
  btn.click();
  return "CLICKED";
})()`;
  const clicked = await browser.cdp.send("Runtime.evaluate", {
    expression: click, returnByValue: true,
  });
  console.log("[probe] drive:", clicked.result.value);

  const t0 = Date.now();
  let lastN = -1;
  while (Date.now() - t0 < maxMs) {
    await sleep(700);
    if (netMeta.streamEndWall) break;
    if (netChunks.length !== lastN) {
      lastN = netChunks.length;
      console.log(`[probe] +${Date.now() - clickWall}ms chunks=${netChunks.length}`);
    }
  }
  await sleep(1500);

  const dump = await browser.cdp.send("Runtime.evaluate", {
    expression: `JSON.stringify(window.__ta13)`, returnByValue: true,
  });
  result = JSON.parse(dump.result.value);
  const fin = await browser.cdp.send("Runtime.evaluate", {
    expression: `(() => { const e = document.getElementById("aiResp") || document.querySelector("main");
      return JSON.stringify({ text: e ? (e.textContent || "") : "",
                              htmlTail: e ? (e.innerHTML || "").slice(-400) : "" }); })()`,
    returnByValue: true,
  });
  result.finalDom = JSON.parse(fin.result.value);
  const bodyTxt = await browser.cdp
    .send("Network.getResponseBody", { requestId: netMeta.reqId })
    .catch((e) => ({ error: String(e) }));
  result.responseBody = (bodyTxt && bodyTxt.body) || ("<unavailable: " + (bodyTxt.error || "") + ">");
} finally {
  await browser.close();
}

const rel = (w) => (w == null ? null : w - clickWall);
const dom = (result.dom || []).map((d) => ({ t: rel(d.w), html: d.html, txt: d.txt }));
const chunks = netChunks.map((c) => ({ t: rel(c.w), len: c.len }));
const summary = {
  page: url, query, status: netMeta.status,
  clickAt: 0,
  requestAt: rel(netMeta.requestWall),
  responseAt: rel(netMeta.responseWall),
  streamEndAt: rel(netMeta.streamEndWall),
  failed: netMeta.failed || null,
  netChunks: chunks.length,
  netFirstT: chunks.length ? chunks[0].t : null,
  netLastT: chunks.length ? chunks[chunks.length - 1].t : null,
  netSpanMs: chunks.length ? chunks[chunks.length - 1].t - chunks[0].t : null,
  domMutations: dom.length,
  domAfterClick: dom.filter((d) => d.t >= 0).length,
  domFirstT: dom.length ? dom[0].t : null,
  domLastT: dom.length ? dom[dom.length - 1].t : null,
  finalTextLen: dom.length ? dom[dom.length - 1].txt : 0,
  distinctTextLens: [...new Set(dom.map((d) => d.txt))].length,
  errs: result.errs,
};
console.log("\n=== SUMMARY ===");
console.log(JSON.stringify(summary, null, 2));
const nc = chunks.filter((c) => c.len > 0);
console.log("\n=== NET dataReceived first 6 / last 6 (len>0) ===");
console.log(JSON.stringify(nc.slice(0, 6)));
console.log(JSON.stringify(nc.slice(-6)));
console.log("\n=== DOM first 10 / last 10 (t>=0) ===");
const d2 = dom.filter((d) => d.t >= 0);
console.log(JSON.stringify(d2.slice(0, 10)));
console.log(JSON.stringify(d2.slice(-10)));
console.log("\n=== FINAL DOM TEXT ===");
console.log((result.finalDom && result.finalDom.text || "").slice(0, 500));
console.log("--- html tail ---");
console.log((result.finalDom && result.finalDom.htmlTail || "").slice(-400));
console.log("\n=== SSE RAW BODY (first 900) ===");
console.log(String(result.responseBody || "").slice(0, 900));
if (out) {
  mkdirSync(path.dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify({ summary, net: chunks, dom, raw: result }, null, 1));
  console.log("[probe] wrote", out);
}
