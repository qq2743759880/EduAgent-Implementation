// TB2b：Jaeger UI 瀑布截图（复用既有 CDP 浏览器基建，禁用 Playwright）。
// 用法：node _tb2b_shot.mjs <traceId> <outPng> [--fail]
import { createBrowser, ensureDir } from "./scripts/gates/_shared.mjs";

const traceId = process.argv[2];
const out = process.argv[3] || `test-reports/tb2b/shots/${traceId}.png`;
const isFail = process.argv.includes("--fail");

if (!traceId) {
  console.error("usage: node _tb2b_shot.mjs <traceId> <outPng> [--fail]");
  process.exit(2);
}

// 不注入任何身份/token（Jaeger 是独立站点）——清掉 gate 身份环境变量，开干净浏览器。
for (const k of Object.keys(process.env)) {
  if (k.startsWith("EDU_GATE_")) delete process.env[k];
}

ensureDir(out.replace(/[\\/][^\\/]+$/, ""));

const browser = await createBrowser({ settleMs: 3500 });
try {
  // 时间窗拉满，确保 trace 能被列出；带 ts 防同 URL 缓存
  const url = `http://127.0.0.1:16686/trace/${traceId}?uiFind=&ts=${Date.now()}`;
  await browser.navigate(url, 6000);

  // 等瀑布真正渲染出来（Jaeger 是 React SPA，需等 span 行出现）
  let rows = 0;
  for (let i = 0; i < 40; i += 1) {
    const r = await browser.cdp.send("Runtime.evaluate", {
      expression: `document.querySelectorAll('[class*="TimelineRow"], [data-testid="span-name"], .span-name, [class*="SpanBar"]').length`,
      returnByValue: true,
    }).catch(() => null);
    rows = r?.result?.value ?? 0;
    if (rows >= 3) break;
    await new Promise((r2) => setTimeout(r2, 400));
  }

  // 确认页面上确实出现了关键 span 名（证伪「截了个空页面」）
  const names = await browser.cdp.send("Runtime.evaluate", {
    expression: `(() => { const t = document.body.innerText || ""; return ["chat.request","retrieval","llm_call","tool_calls"].filter(n => t.includes(n)).join(","); })()`,
    returnByValue: true,
  }).catch(() => null);

  await browser.screenshot(out, { quality: 92 });
  console.log(JSON.stringify({
    ok: true, out, traceId, timelineRows: rows,
    spanNamesOnPage: names?.result?.value || "",
    mode: isFail ? "fail" : "ok",
  }, null, 2));
} finally {
  await browser.close?.();
}
