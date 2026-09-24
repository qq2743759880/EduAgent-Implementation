/**
 * blind_probe.mjs — TC2 盲测 B11(黄条) / B12(HITL 卡) CDP 探针（零侵入、只读观察）
 *
 * 用法：
 *   B11: EDU_TOKEN=<stu> node blind_probe.mjs --mode b11 --query "..." --out r.json --shot r.png
 *   B12: EDU_TOKEN=<adm> node blind_probe.mjs --mode b12 --action approve|reject --query "..." --out r.json --shot r.png
 *
 * 依赖：scripts/gates/_shared.mjs 的 createBrowser（仅 CDP 驱动，禁 Playwright）。
 * 不落盘 token（运行时注入 localStorage）；只读观察 DOM 与截图。
 */
import { createBrowser, sleep, DEFAULT_BASE } from "../../scripts/gates/_shared.mjs";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";

const args = process.argv.slice(2);
const getArg = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const mode = getArg("mode", "b11");
const page = getArg("page", "chat.html");
const role = getArg("role", "student");
const query = getArg("query", "");
const action = getArg("action", "none");
const out = getArg("out", null);
const shot = getArg("shot", null);
const base = getArg("base", DEFAULT_BASE);
const token = process.env.EDU_TOKEN || "";
if (!token) { console.error("EDU_TOKEN required"); process.exit(2); }

const url = page === "react" ? `${base}/chat` : `${base}/${page}`;
const browser = await createBrowser();
const diag = [];
browser.cdp.on("Runtime.exceptionThrown", (p) => diag.push("EXC:" + (p.exceptionDetails?.exception?.description || p.exceptionDetails?.text || "").slice(0, 300)));
browser.cdp.on("Log.entryAdded", (p) => { if (p.entry?.level === "error") diag.push("LOG:" + (p.entry.text || "").slice(0, 300)); });

const evalExpr = async (expr) => {
  const r = await browser.cdp.send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text || "Runtime.evaluate failed");
  return r.result?.value;
};

try {
  // 运行时注入 token（禁落盘）
  await browser.cdp.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try{localStorage.setItem("edu:auth:token", ${JSON.stringify(token)});localStorage.setItem("edu:auth:refresh","");}catch{}`,
  });
  await browser.setViewport(1440, 900);
  await browser.navigate(url, 2500);

  const st = await evalExpr(`JSON.stringify({href:location.href, token:!!localStorage.getItem("edu:auth:token"), hasInput:!!document.getElementById("composerInput"), hasSend:!!document.getElementById("sendBtn")})`);
  console.log("[probe] page state:", st);
  const state = JSON.parse(st);
  if (!state.token) { console.error("[probe] token NOT injected -> 登录态缺失"); }
  if (state.href.includes("login-register")) { console.error("[probe] redirected to login -> 身份未生效"); }

  // 输入 + 发送
  const setVal = `
  (() => {
    const ta = document.getElementById("composerInput") || document.querySelector("textarea") || document.querySelector('input[type="text"]');
    if (!ta) return "NO_INPUT";
    const proto = ta.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(ta, ${JSON.stringify(query)});
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    ta.dispatchEvent(new Event("change", { bubbles: true }));
    return "SET:" + ta.value.length;
  })()`;
  const setR = await evalExpr(setVal);
  console.log("[probe] setValue:", setR);
  await sleep(400);
  const click = `
  (() => {
    const b = document.getElementById("sendBtn") || [...document.querySelectorAll("button")].find(x => !x.disabled && x.getAttribute("aria-label") === "发送");
    if (!b) return "NO_SEND";
    if (b.disabled) return "SEND_DISABLED";
    b.click();
    return "CLICKED";
  })()`;
  const clickR = await evalExpr(click);
  console.log("[probe] drive:", clickR);
  const sendWall = Date.now();

  const result = { mode, page, role, query, clickR, sendWall: 0 };

  if (mode === "b11") {
    // 轮询 role=alert 黄底警示条（receipt-warn）
    let found = null;
    for (let i = 0; i < 90; i++) {
      await sleep(1000);
      const det = await evalExpr(`
        (() => {
          const el = document.querySelector('.receipt-warn[role="alert"]') || document.querySelector('[role="alert"]');
          if (!el) return null;
          const cs = getComputedStyle(el);
          const bg = cs.backgroundColor || cs.background || "";
          return JSON.stringify({ cls: el.className, text: (el.textContent||"").slice(0,200), bg, color: cs.color });
        })()`);
      if (det) { found = JSON.parse(det); found.atMs = Date.now() - sendWall; break; }
    }
    result.receipt = found;
    result.found = !!found;
  } else if (mode === "b12") {
    // 轮询 HITL 卡 #hitlCard
    let card = null;
    for (let i = 0; i < 120; i++) {
      await sleep(1000);
      const det = await evalExpr(`
        (() => {
          const el = document.getElementById("hitlCard");
          if (!el) return null;
          const tool = el.querySelector(".hitl-tool code")?.textContent || "";
          const risk = [...el.querySelectorAll(".hitl-risk")].map(x=>x.textContent).join("|");
          const args = el.querySelector(".hitl-args")?.textContent || "";
          const busy = el.classList.contains("hitl-busy");
          const confirm = !!el.querySelector(".hitl-confirm");
          const reject = !!el.querySelector(".hitl-reject");
          return JSON.stringify({ tool, risk, args: args.slice(0,300), busy, confirm, reject });
        })()`);
      if (det) { card = JSON.parse(det); card.atMs = Date.now() - sendWall; break; }
    }
    result.card = card;
    result.cardShown = !!card;
    if (card) {
      const sel = action === "reject" ? ".hitl-reject" : ".hitl-confirm";
      const clicked = await evalExpr(`
        (() => {
          const el = document.getElementById("hitlCard");
          const b = el && el.querySelector(${JSON.stringify(sel)});
          if (!b) return "NO_BTN";
          b.click();
          return "CLICKED_" + ${JSON.stringify(action)};
        })()`);
      result.actionClicked = clicked;
      console.log("[probe] hitl action:", clicked);
      // 等待结算（卡进入 busy / 被移除 / 出现后续回答）
      await sleep(20000);
      const after = await evalExpr(`
        (() => {
          const el = document.getElementById("hitlCard");
          let success = "";
          const msgs = [...document.querySelectorAll('.msg .bubb, .bubb')];
          for (const m of msgs) { const t = m.textContent||""; if (/已创建|创建成功|课程.*已|落库|成功/.test(t)) { success = t.slice(-160); break; } }
          return JSON.stringify({ cardPresent: !!el, busy: el?el.classList.contains("hitl-busy"):null, successHint: success });
        })()`);
      result.after = JSON.parse(after);
    }
  }

  // 截图证据
  if (shot) {
    const f = await browser.screenshot(shot, { quality: 70 });
    const buf = readFileSync(f);
    result.shotHash = createHash("sha256").update(buf).digest("hex");
    result.shotPath = f;
    console.log("[probe] shot:", f, result.shotHash.slice(0, 16));
  }
  result.diag = diag.slice(0, 10);
  console.log("\n=== RESULT ===");
  console.log(JSON.stringify(result, null, 2));
  if (out) { mkdirSync(path.dirname(out), { recursive: true }); writeFileSync(out, JSON.stringify(result, null, 1)); console.log("[probe] wrote", out); }
} finally {
  await browser.close();
}
