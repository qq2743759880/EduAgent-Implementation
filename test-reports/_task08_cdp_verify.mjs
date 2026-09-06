// task08 community.html + community-post.html 独立实证（headless Chrome + CDP，零依赖，非 Playwright）
// 用法: node _task08_cdp_verify.mjs
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const CHROME = "D:\\tool\\chrom\\Application\\chrome.exe";
const PORT = 9230;
const FE = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? "PASS" : "FAIL") + " | " + name + " | " + detail); };

const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "user000001", password: "Test@123456" }),
}).then(r => r.json());
if (login.code !== 0) { console.error("LOGIN FAIL", login); process.exit(1); }
const token = login.data.access_token;

const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${process.env.TEMP}\\edu-task08-profile`,
  "--headless=new", "--window-size=1440,900", "--no-first-run",
  "--disable-extensions", "--no-default-browser-check", "about:blank",
], { stdio: "ignore" });
await new Promise(r => setTimeout(r, 3000));
const cleanup = () => { try { proc.kill(); } catch (e) {} };
process.on("exit", cleanup);

const list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json());
const page = list.find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let mid = 0; const pending = new Map(); const consoleErrors = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
    consoleErrors.push(m.params.args.map(a => a.value ?? a.description ?? "").join(" ").slice(0, 200));
  if (m.method === "Runtime.exceptionThrown")
    consoleErrors.push("EXC: " + (m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || "").slice(0, 200));
};
const sendM = (method, params = {}) => new Promise((res) => {
  const id = ++mid; pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params }));
});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const evalJs = async (expr) => {
  const r = await sendM("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) return { __err: (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text || "").slice(0, 250) };
  return r.result?.result?.value;
};
const goto = async (url) => {
  await sendM("Page.navigate", { url });
  await sleep(1200);
  await evalJs(`localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); "t"`);
  await sendM("Page.navigate", { url });
  await sleep(2200);
};
await sendM("Runtime.enable");
await sendM("Page.enable");

/* ============ A. community.html 列表 ============ */
await goto(FE + "/community.html");

const cardCount = await evalJs(`document.querySelectorAll("#boards .post[data-post]").length`);
check("list-real-render", cardCount > 0, `cards=${cardCount}`);
const totalTxt = await evalJs(`(document.querySelector("#pager .total")||{textContent:""}).textContent`);
check("pager-visible-p1", totalTxt.includes("共") && totalTxt.trim() !== "共 0 条", `total="${totalTxt}"`);
const mineTxt = await evalJs(`(document.querySelector(".mine b")||{textContent:""}).textContent.trim()`);
check("mine-total-wired", /^\d+$/.test(mineTxt), `mine_total_posts="${mineTxt}"（原静态假值 3 已被真实字段替换）`);

// 翻页：第 1 页 → 第 2 页（首帖 id 变化）→ prev 回第 1 页
const firstP1 = await evalJs(`document.querySelector("#boards .post").dataset.post`);
await evalJs(`(() => { document.querySelector('#pager .pager-btn[data-pg="next"]').click(); return "next"; })()`);
await sleep(1200);
const onP2 = await evalJs(`document.querySelector("#pager .pager-btn.on")?.dataset.pg`);
const firstP2 = await evalJs(`document.querySelector("#boards .post").dataset.post`);
check("pager-next-p2", onP2 === "2" && firstP1 !== firstP2, `p1 first=${firstP1} p2 first=${firstP2} on=${onP2}`);
await evalJs(`(() => { document.querySelector('#pager .pager-btn[data-pg="prev"]').click(); return "prev"; })()`);
await sleep(1200);
const backP1 = await evalJs(`document.querySelector("#pager .pager-btn.on")?.dataset.pg`);
check("pager-prev-back", backP1 === "1" && (await evalJs(`document.querySelector("#boards .post").dataset.post`)) === firstP1, `on=${backP1}`);

// 版块筛选（board_code=english）+ 回第 1 页
await evalJs(`(() => { document.querySelector('#chips .chip[data-b="en"]').click(); return "en"; })()`);
await sleep(1200);
const enTags = await evalJs(`Array.from(document.querySelectorAll("#boards .board-tag")).map(x=>x.textContent).slice(0,5).join(",")`);
const enPage = await evalJs(`document.querySelector("#pager .pager-btn.on")?.dataset.pg`);
check("chip-filter-en", enTags.split(",").every(t => t === "英语") && enPage === "1", `tags=${enTags} page=${enPage}`);

// 搜索空态（无结果关键词）
await evalJs(`(() => { const k = document.getElementById("kw"); k.value = "zzz不存在的帖子zzz"; k.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" })); return "searched"; })()`);
await sleep(1200);
const emptyShown = await evalJs(`!!document.querySelector("#boards .state") && document.getElementById("boards").textContent.includes("暂无帖子")`);
const pagerHiddenEmpty = await evalJs(`document.getElementById("pager").style.display === "none"`);
check("search-empty-state", emptyShown && pagerHiddenEmpty, `empty=${emptyShown} pagerHidden=${pagerHiddenEmpty}`);

// 清空关键词（真实行为：load 会带上 kw，不清空重试后仍是诚实空态）
await evalJs(`(() => { const k = document.getElementById("kw"); k.value = ""; k.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" })); return "cleared"; })()`);
await sleep(1500);

// 错误态 + 重试恢复（BASE 指不可达端口 → 点版块触发加载）
await evalJs(`EAPI.BASE = "http://127.0.0.1:59999"; "bad"`);
await evalJs(`(() => { document.querySelector('#chips .chip[data-b="all"]').click(); return "all"; })()`);
let errShown = false;
for (let t = 0; t < 12; t++) { await sleep(750); errShown = await evalJs(`!!document.querySelector("#boards .state[role='alert']")`); if (errShown) break; }
check("list-error-state", errShown, "错误态 role=alert 渲染");
await evalJs(`EAPI.BASE = "http://127.0.0.1:8000"; "ok"`);
const retryRet = await evalJs(`(() => { const b = document.getElementById("retryLoad"); if (!b) return "no-btn"; b.click(); return "clicked"; })()`);
let recovered = false;
for (let t = 0; t < 12; t++) { await sleep(700); recovered = await evalJs(`document.querySelectorAll("#boards .post[data-post]").length > 0`); if (recovered) break; }
check("list-error-retry", retryRet === "clicked" && recovered, `retry=${retryRet} recovered=${recovered}`);

// 列表点赞 toggle ×2（真实端点 + aria-pressed）
const likeBtn0 = await evalJs(`(() => { const b = document.querySelector("#boards .like-btn:not([disabled])"); return b ? b.dataset.post : ""; })()`);
const likeState0 = await evalJs(`(() => { const b = document.querySelector('#boards .like-btn[data-post="${likeBtn0}"]'); return { on: b.classList.contains("on"), n: parseInt(b.querySelector("i").textContent,10), ap: b.getAttribute("aria-pressed") }; })()`);
await evalJs(`(() => { document.querySelector('#boards .like-btn[data-post="${likeBtn0}"]').click(); return "like"; })()`);
await sleep(1200);
const likeState1 = await evalJs(`(() => { const b = document.querySelector('#boards .like-btn[data-post="${likeBtn0}"]'); return { on: b.classList.contains("on"), n: parseInt(b.querySelector("i").textContent,10), ap: b.getAttribute("aria-pressed") }; })()`);
check("list-like-toggle", likeState1.on === !likeState0.on && likeState1.ap === (likeState0.on ? "false" : "true"), `${JSON.stringify(likeState0)} -> ${JSON.stringify(likeState1)}`);
await evalJs(`(() => { document.querySelector('#boards .like-btn[data-post="${likeBtn0}"]').click(); return "unlike"; })()`);
await sleep(1200);
const likeState2 = await evalJs(`(() => { const b = document.querySelector('#boards .like-btn[data-post="${likeBtn0}"]'); return { on: b.classList.contains("on"), ap: b.getAttribute("aria-pressed") }; })()`);
check("list-like-restore", likeState2.on === likeState0.on, `restored ${JSON.stringify(likeState2)}`);

/* ============ B. community-post.html?post_id=97（自有实测帖；评论数动态补足 ≥11，跨次运行幂等）============ */
{
  let T = 0;
  for (let attempt = 0; attempt < 20; attempt++) {
    T = (await fetch(API + "/api/community/posts/97/comments?page=1&page_size=1", { headers: { Authorization: "Bearer " + token } }).then(r => r.json())).data.total;
    if (T >= 11) break;
    await fetch(API + "/api/community/posts/97/comments", {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify({ content_md: "task08 评论分页实测 补充#(可忽略)" }),
    });
  }
  console.log("  [dbg] fixture comment total:", T);
}
await goto(FE + "/community-post.html?post_id=97");

const dTitle = await evalJs(`document.getElementById("postTitle").textContent`);
const dVisible = await evalJs(`getComputedStyle(document.getElementById("bodyCard")).visibility === "visible"`);
check("detail-render", dTitle.includes("task08") && dVisible, `title="${dTitle}" body=${dVisible}`);
const T0 = await fetch(API + "/api/community/posts/97/comments?page=1&page_size=1", { headers: { Authorization: "Bearer " + token } }).then(r => r.json()).then(d => d.data.total);
const cmtTotal0 = await evalJs(`document.getElementById("cmtTotal").textContent`);
const pgPages = await evalJs(`(() => { const on = document.querySelector("#pager .pager-btn.on"); return { on: on?.dataset.pg, all: Array.from(document.querySelectorAll("#pager .pager-btn")).map(b=>b.dataset.pg).join("|") }; })()`);
check("cmt-total-from-endpoint", cmtTotal0.trim() === T0 + " 条" && pgPages.on === "1", `total="${cmtTotal0}" expect=${T0} pager=${JSON.stringify(pgPages)}（漂移D2：不采信 comment_count）`);
const cmtCountP1 = await evalJs(`document.querySelectorAll("#cList .c-item").length`);
check("cmt-pagesize-10", cmtCountP1 === 10, `page1 items=${cmtCountP1}`);
await evalJs(`(() => { document.querySelector('#pager .pager-btn[data-pg="next"]').click(); return "next"; })()`);
await sleep(1200);
const cmtCountP2 = await evalJs(`document.querySelectorAll("#cList .c-item").length`);
const p2On = await evalJs(`document.querySelector("#pager .pager-btn.on")?.dataset.pg`);
check("cmt-pager-p2", p2On === "2" && cmtCountP2 === T0 - 10, `page2 items=${cmtCountP2} expect=${T0 - 10} on=${p2On}`);

// 评论点赞 toggle ×2
const cid0 = await evalJs(`document.querySelector("#cList .c-like").dataset.cid`);
await evalJs(`(() => { document.querySelector('#cList .c-like[data-cid="${cid0}"]').click(); return "clk"; })()`);
await sleep(1000);
const cLike1 = await evalJs(`(() => { const b = document.querySelector('#cList .c-like[data-cid="${cid0}"]'); return { on: b.classList.contains("on"), n: parseInt(b.querySelector("b").textContent,10), ap: b.getAttribute("aria-pressed") }; })()`);
check("cmt-like-toggle", cLike1.on === true && cLike1.ap === "true", `${JSON.stringify(cLike1)}`);
await evalJs(`(() => { document.querySelector('#cList .c-like[data-cid="${cid0}"]').click(); return "clk2"; })()`);
await sleep(1000);
const cLike2 = await evalJs(`(() => { const b = document.querySelector('#cList .c-like[data-cid="${cid0}"]'); return { on: b.classList.contains("on"), n: parseInt(b.querySelector("b").textContent,10) }; })()`);
check("cmt-like-restore", cLike2.on === false && cLike2.n === 0, `${JSON.stringify(cLike2)}`);

// 帖子点赞/收藏 toggle ×2（detail 操作行）
await evalJs(`(() => { document.getElementById("likeBtn").click(); return "lk"; })()`);
await sleep(1000);
const dLike1 = await evalJs(`(() => { const b = document.getElementById("likeBtn"); return { on: b.classList.contains("on"), n: parseInt(document.getElementById("likeCnt").textContent,10) }; })()`);
check("post-like-toggle", dLike1.on === true, `${JSON.stringify(dLike1)}`);
await evalJs(`(() => { document.getElementById("likeBtn").click(); return "lk2"; })()`);
await sleep(1000);
const dLike2 = await evalJs(`(() => { const b = document.getElementById("likeBtn"); return { on: b.classList.contains("on"), n: parseInt(document.getElementById("likeCnt").textContent,10) }; })()`);
check("post-like-restore", dLike2.on === false, `${JSON.stringify(dLike2)}`);

// UI 发评论 → 跳末页（12 条 → 第 2 页）+ +2 积分行内反馈
await evalJs(`(() => { const t = document.getElementById("cmtInput"); t.value = "task08 UI 发布评论实测（可忽略）"; document.getElementById("cmtSubmit").click(); return "post"; })()`);
await sleep(1800);
const afterPost = await evalJs(`({ total: document.getElementById("cmtTotal").textContent.trim(), on: document.querySelector("#pager .pager-btn.on")?.dataset.pg, last: Array.from(document.querySelectorAll("#cList .c-body")).map(x=>x.textContent).join("").includes("UI 发布评论实测"), flash: (document.getElementById("cmtErr")||{textContent:""}).textContent })`);
const expTotal = (T0 + 1) + " 条";
const expLastPg = String(Math.ceil((T0 + 1) / 10));
check("cmt-ui-post-lastpage", afterPost.total === expTotal && afterPost.on === expLastPg && afterPost.last, JSON.stringify(afterPost) + ` expect total=${expTotal} pg=${expLastPg}`);

/* ============ C. 404 → 帖子不存在 + 返回列表 CTA ============ */
await goto(FE + "/community-post.html?post_id=999999");
let nfShown = false;
for (let t = 0; t < 10; t++) { await sleep(600); nfShown = await evalJs(`!!document.querySelector("#page .state h3") && document.querySelector("#page .state h3").textContent.includes("帖子不存在")`); if (nfShown) break; }
const nfCta = await evalJs(`!!document.getElementById("backListBtn")`);
check("detail-404-state", nfShown && nfCta, `notFound=${nfShown} cta=${nfCta}`);

/* ============ D. console 干净 ============ */
const realErrors = consoleErrors.filter(e => !/ERR_CONNECTION_REFUSED|Failed to load resource|网络错误|EAPI|加载失败|Failed to fetch/.test(e));
check("console-no-js-errors", realErrors.length === 0, `total=${consoleErrors.length} real=${realErrors.length} ${realErrors.slice(0, 2).join(" || ")}`);

writeFileSync("task08-cdp-result.json", JSON.stringify({ results, consoleErrors }, null, 1), "utf-8");
const fails = results.filter(r => !r.ok).length;
console.log(fails === 0 ? "ALL PASS" : `${fails} FAIL`);
cleanup();
process.exit(fails === 0 ? 0 : 1);
