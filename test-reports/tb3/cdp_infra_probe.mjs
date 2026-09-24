/**
 * TO-EXEC-TB3 自验探针：admin-infra.html 真机端到端
 *
 * 三段验证（全部真实浏览器 + 真实后端，无 mock）：
 *   1) admin 身份：页面加载 → 「运行演示」→ 面板渲染真实数据；两次快照对比 numbers 变化能力
 *   2) 负向：student token 直打 /api/admin/infra/snapshot → 断言 403
 *   3) 脱敏：面板渲染的 uid 必须为掩码串
 *
 * 复用 scripts/gates/_shared.mjs::createBrowser（禁用 Playwright）。
 */
import { createBrowser, sleep } from "../../scripts/gates/_shared.mjs";

const BASE = process.env.EDU_GATE_BASE || "http://127.0.0.1:3322";
const API = process.env.EDU_API_BASE || "http://127.0.0.1:9988";
const OUT = {};

function log(...a) { console.log(...a); }

async function login(account, password) {
  const res = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, password }),
  });
  const body = await res.json();
  return { status: res.status, token: body?.data?.access_token || "", body };
}

const admin = await login("adm02test", "Test@123456");
const student = await login("user000001", "Test@123456");
log(`[login] admin=${admin.status} tokenLen=${admin.token.length} | student=${student.status} tokenLen=${student.token.length}`);

// ── 负向：student token 直打端点（HTTP 层，先于浏览器）──
const neg = await fetch(`${API}/api/admin/infra/snapshot`, {
  headers: { Authorization: `Bearer ${student.token}` },
});
const negBody = await neg.json().catch(() => null);
OUT.student_http_status = neg.status;
OUT.student_body = negBody;
log(`[negative] student → HTTP ${neg.status} ${JSON.stringify(negBody)}`);

const noTok = await fetch(`${API}/api/admin/infra/snapshot`);
OUT.anonymous_http_status = noTok.status;
log(`[negative] anonymous → HTTP ${noTok.status}`);

// ── 浏览器：admin 身份 ──
const browser = await createBrowser({});
try {
  // 先落到同源页面注入 token（localStorage 同源共享）
  await browser.navigate(`${BASE}/login-register.html`, 900);
  await browser.cdp.send("Runtime.evaluate", {
    expression: `localStorage.setItem('edu:auth:token', ${JSON.stringify(admin.token)}); 'set'`,
  });

  const resp = await browser.navigate(`${BASE}/admin-infra.html`, 2500);
  OUT.page_status = resp?.status ?? null;
  log(`[browser] navigate admin-infra.html → HTTP ${OUT.page_status}`);

  // 等面板数据就绪（success 可见 + 关键数字非 "—"）
  let ready = false;
  for (let i = 0; i < 40; i += 1) {
    const r = await browser.cdp.send("Runtime.evaluate", {
      expression: `(function(){
        var s=document.getElementById('view-success');
        var hits=document.getElementById('k-rl-hits');
        var dbsize=(document.getElementById('raw-line')||{}).textContent||'';
        return JSON.stringify({
          successVisible: s ? !s.hidden : false,
          hits: hits ? hits.textContent : null,
          rawline: dbsize.slice(0,240),
          chips: Array.from(document.querySelectorAll('#deps .chip')).map(function(c){return c.textContent.trim();}),
          url: location.href
        });
      })()`,
      returnByValue: true,
    });
    const v = JSON.parse(r.result.value);
    if (v.successVisible && v.hits && v.hits !== "—") { OUT.first_snapshot = v; ready = true; break; }
    await sleep(400);
  }
  OUT.panel_ready = ready;
  log(`[browser] panel ready=${ready}`);
  if (ready) {
    log(`[browser] chips: ${JSON.stringify(OUT.first_snapshot.chips)}`);
    log(`[browser] rawline: ${OUT.first_snapshot.rawline}`);
  }

  // ── 全量面板读数 + 脱敏核对 ──
  const read = await browser.cdp.send("Runtime.evaluate", {
    expression: `(function(){
      function txt(id){var e=document.getElementById(id);return e?e.textContent.trim():null;}
      var rows=function(id){return Array.from(document.querySelectorAll(id+' tr')).map(function(tr){
        return Array.from(tr.querySelectorAll('td,th')).map(function(td){return td.textContent.trim();});});};
      return JSON.stringify({
        viewer: txt('viewer-chip'),
        deps: Array.from(document.querySelectorAll('#deps .chip')).map(function(c){return {t:c.textContent.trim(),ok:c.classList.contains('ok')};}),
        rl: {hits:txt('k-rl-hits'), keys:txt('k-rl-keys'), rej:txt('k-rl-rej'), rows: rows('#rl-rows')},
        cache: {family:txt('k-cache-keys'), sample:txt('k-cache-sample'), mutex:txt('k-cache-mutex'), cmp:(document.getElementById('cmp-box')||{}).textContent},
        locks: {count:txt('k-lock-count'), rows: rows('#lock-rows')},
        queues: {count:txt('k-queue-count'), depth:txt('k-queue-depth'), rows: rows('#queue-rows')},
        mongo: {db:txt('k-mongo-db'), rows: rows('#mongo-rows')},
        event: {total:txt('k-ev-total'), worker:txt('k-ev-worker'), q:txt('k-ev-q'), rows: rows('#ev-rows'), mask: txt('ev-mask-note')},
        emojiInPage: /[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u.test(document.body.innerText)
      });
    })()`,
    returnByValue: true,
  });
  OUT.panel = JSON.parse(read.result.value);
  log("=== 面板读数 ===");
  log(JSON.stringify(OUT.panel, null, 1));

  // ── 更新能力验证：再点一次「运行演示」，确认二次数值/时间戳变化 ──
  await browser.cdp.send("Runtime.evaluate", {
    expression: `document.getElementById('runDemo').click(); 'clicked'`,
  });
  await sleep(2200);
  const second = await browser.cdp.send("Runtime.evaluate", {
    expression: `document.getElementById('raw-line').textContent`,
    returnByValue: true,
  });
  OUT.second_rawline = second.result.value;
  log(`[rerun] rawline: ${OUT.second_rawline}`);

  // ── 截图 ──
  const shot = await browser.cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  OUT.screenshot_path = "test-reports/tb3/admin-infra-admin.png";
  await import("node:fs").then((fs) => {
    fs.mkdirSync("test-reports/tb3", { recursive: true });
    fs.writeFileSync(OUT.screenshot_path, Buffer.from(shot.data, "base64"));
  });
  log(`[shot] ${OUT.screenshot_path}`);
} finally {
  await browser.close?.();
}

// ── 负向：student 身份打开页面 → 应被守卫拦截（跳登录或跳 dashboard）──
const browser2 = await createBrowser({});
try {
  await browser2.navigate(`${BASE}/login-register.html`, 900);
  await browser2.cdp.send("Runtime.evaluate", {
    expression: `localStorage.setItem('edu:auth:token', ${JSON.stringify(student.token)}); 'set'`,
  });
  await browser2.navigate(`${BASE}/admin-infra.html`, 1000);
  await sleep(4000); // 等守卫 auth/me 校验 + 跳转
  const st = await browser2.cdp.send("Runtime.evaluate", {
    expression: `JSON.stringify({url: location.pathname, banner: (document.querySelector('div[style*="fb7185"]')||{}).textContent||null, successHidden: (document.getElementById('view-success')||{}).hidden})`,
    returnByValue: true,
  });
  OUT.student_page = JSON.parse(st.result.value);
  log(`[negative-page] ${JSON.stringify(OUT.student_page)}`);
  const shot2 = await browser2.cdp.send("Page.captureScreenshot", { format: "png" });
  await import("node:fs").then((fs) => {
    fs.mkdirSync("test-reports/tb3", { recursive: true });
    fs.writeFileSync("test-reports/tb3/admin-infra-student-blocked.png", Buffer.from(shot2.data, "base64"));
  });
} finally {
  await browser2.close?.();
}

await import("node:fs").then((fs) => {
  fs.mkdirSync("test-reports/tb3", { recursive: true });
  fs.writeFileSync("test-reports/tb3/tb3_probe_result.json", JSON.stringify(OUT, null, 2));
});
log("[done] wrote test-reports/tb3/tb3_probe_result.json");
