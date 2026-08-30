/**
 * task04 浏览器 UI 验证（Playwright + page.route 注入 X-Force-Role: admin）
 * 覆盖验收：
 *  - RAG 控制台：集合列表（行数快照）、重建索引（202+job_id）、预设列表（默认唯一）、
 *    审计日志过滤分页、高级检索测试（docs + degraded）
 *  - MCP 控制台：Server 列表健康灯、discover-live 工具表格、工具测试（status/result/latency_ms）
 */
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://localhost:3000"; // L2：必须 localhost，127.0.0.1 会 403
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1500, height: 1000 } });

// 注入假 token 满足前端守卫（后端 DEBUG 下 X-Force-Role 优先级最高，token 会被忽略）
await pg.addInitScript(() => {
  localStorage.setItem("edu:auth:token", "debug-force-token");
  localStorage.setItem(
    "edu:auth:me",
    JSON.stringify({ id: 1, nickname: "调试管理员", email: "debug@edu.agent", roles: ["admin"] }),
  );
});

// 给所有后端请求：移除假 Authorization（否则走真实 JWT 校验 401）+ 注入 X-Force-Role（DEBUG 虚拟 admin）
// 用 route.fulfill 直接 Node fetch 转发，规避 Chromium 导航期 continue 竞态导致的 ERR_ABORTED
await pg.route("http://127.0.0.1:8000/**", async (route) => {
  const req = route.request();
  const headers = {};
  for (const [k, v] of Object.entries(req.headers())) {
    if (/^content-length$/i.test(k) || /^authorization$/i.test(k)) continue;
    headers[k] = String(v);
  }
  headers["X-Force-Role"] = "admin";
  headers["X-Force-User-Id"] = "1";
  const method = req.method();
  const body = req.postDataBuffer();
  try {
    const resp = await fetch(req.url(), { method, headers, body: body ?? undefined });
    const buf = Buffer.from(await resp.arrayBuffer());
    // Node fetch 已自动解压 gzip/br，删除编码头避免浏览器二次解压失败（ERR_ABORTED）
    const outHeaders = {};
    resp.headers.forEach((v, k) => {
      if (/^content-encoding$/i.test(k) || /^content-length$/i.test(k)) return;
      outHeaders[k] = v;
    });
    await route.fulfill({
      status: resp.status,
      headers: outHeaders,
      body: buf,
    });
  } catch (err) {
    console.error(`  [route.fetch] ${method} ${req.url().slice(20)} ERR:`, err instanceof Error ? err.message : String(err));
    await route.abort();
  }
});

pg.on("pageerror", (e) => console.error("  [pageerror]", e.message));
pg.on("console", (m) => {
  if (m.type() === "error") console.error("  [console.error]", m.text().slice(0, 200));
});
pg.on("requestfailed", (r) => console.error("  [reqfail]", r.url().slice(0, 140), r.failure()?.errorText));

const failedStatus = [];
pg.on("response", (r) => {
  const u = r.url();
  if (u.includes("/api/admin/rag") || u.includes("/api/mcp/")) {
    if (r.status() >= 400) failedStatus.push(`${u.split("/api/")[1]} -> ${r.status()}`);
  }
});

async function gotoAndWait(url, selector, timeout = 20000) {
  // headless 导航偶发 abort in-flight 请求（Chromium 导航竞态），最多重试 2 次
  for (let attempt = 1; attempt <= 3; attempt++) {
    await pg.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => undefined);
    try {
      await pg.waitForSelector(selector, { timeout });
      return true;
    } catch (err) {
      if (attempt === 3) throw err;
      console.log(`  [retry] ${url} 等待 ${selector} 失败，第 ${attempt + 1} 次尝试`);
      await pg.waitForTimeout(1500);
    }
  }
  return false;
}

try {
  /* ================= RAG 控制台 ================= */
  await gotoAndWait(`${BASE}/admin/rag`, '[data-testid="rag-collection-table"]');
  await pg.waitForTimeout(500);
  const rows = await pg.locator('[data-testid="rag-collection-row"]').count();
  check("RAG 集合列表渲染（含行数快照）", rows > 0, `${rows} 行`);
  const hasRowCount = await pg.locator("text=chunks").first().isVisible().catch(() => false);
  check("集合行数快照（chunks 单位）", hasRowCount, "");

  // 重建索引 → 202 + job_id
  const firstRebuildBtn = pg.locator('[data-testid^="rebuild-"]').first();
  await firstRebuildBtn.click();
  await pg.waitForSelector('[data-testid="rebuild-mode"]', { timeout: 10000 });
  await pg.click('[data-testid="rebuild-submit"]');
  await pg.waitForSelector('[data-testid="rebuild-job-id"]', { timeout: 15000 });
  const jobId = (await pg.textContent('[data-testid="rebuild-job-id"]'))?.trim() ?? "";
  check("重建索引返回 202 + job_id", /^r_[a-z0-9]+$/.test(jobId), jobId);
  await pg.click('[data-slot="dialog-content"] button:has-text("关闭")').catch(() => pg.keyboard.press("Escape"));

  // 预设列表（默认项）
  await pg.waitForSelector('[data-testid="preset-card"]', { timeout: 15000 });
  const presetCount = await pg.locator('[data-testid="preset-card"]').count();
  const defaultBadges = await pg.locator('[data-testid="preset-default-badge"]').count();
  check("预设列表渲染", presetCount > 0, `${presetCount} 个`);
  check("默认预设唯一（is_default 徽章 ≤1）", defaultBadges <= 1, `${defaultBadges} 个默认`);

  // 审计日志表格（分页 + 过滤控件）
  await pg.waitForSelector('[data-testid="audit-log-table"]', { timeout: 15000 });
  const logRows = await pg.locator('[data-testid="audit-log-row"]').count();
  check("审计日志表格渲染", logRows > 0, `${logRows} 行`);
  check("审计日志过滤控件（user_id/role/created_after）",
    (await pg.locator('[data-testid="audit-user-id"]').count()) > 0 &&
    (await pg.locator('[data-testid="audit-role"]').count()) > 0 &&
    (await pg.locator('[data-testid="audit-created-after"]').count()) > 0, "");

  // 高级检索测试 → docs
  await pg.fill('[data-testid="search-query"]', "勾股定理");
  await pg.click('[data-testid="search-run"]');
  await pg.waitForSelector('[data-testid="search-doc"]', { timeout: 20000 });
  const docCount = await pg.locator('[data-testid="search-doc"]').count();
  check("高级检索返回 docs 列表", docCount > 0, `${docCount} 条`);

  /* ================= MCP 控制台 ================= */
  await gotoAndWait(`${BASE}/admin/mcp`, '[data-testid="mcp-server-table"]');
  const srvRows = await pg.locator('[data-testid="mcp-server-row"]').count();
  check("MCP Server 列表渲染", srvRows > 0, `${srvRows} 行`);
  const dotTexts = await pg.locator('[data-testid="health-dot"]').allTextContents();
  check("Server 健康灯（OK/ERR/未知）", dotTexts.length > 0 && dotTexts.some((t) => /OK|ERR|未知/.test(t)), dotTexts.join(","));

  // 发现工具 → DB 工具列表
  await pg.click('[data-testid="tools-1"]');
  await pg.waitForSelector('[data-testid="tool-table"]', { timeout: 15000 });
  const toolRows = await pg.locator('[data-testid="tool-row"]').count();
  check("工具表格渲染（DB 列表）", toolRows > 0, `${toolRows} 个工具`);

  // discover-live
  await pg.click('[data-testid="tools-discover-live"]');
  await pg.waitForTimeout(1500);
  const liveCount = await pg.locator('[data-testid="tool-row"]').count().catch(() => 0);
  const sourceLabel = (await pg.textContent('[data-testid="tools-source"]'))?.trim() ?? "";
  check("discover-live 实时工具快照", liveCount > 0 && sourceLabel.includes("Live Discover"), `${liveCount} 个 · ${sourceLabel}`);

  // 工具测试 → status/result/latency_ms
  await pg.locator('[data-testid="tool-row"]').first().waitFor({ timeout: 10000 });
  // 选择 add 工具（有整数参数）→ 测试
  const addRow = pg.locator('[data-testid="tool-row"]', { hasText: "add" }).first();
  if ((await addRow.count()) > 0) {
    await addRow.locator('[data-testid^="test-"]').click();
    await pg.waitForSelector('[data-testid="tool-args"]', { timeout: 10000 });
    // add 需要 a/b 整数参数，填 1/2
    const argsText = await pg.inputValue('[data-testid="tool-args"]');
    const argsObj = JSON.parse(argsText || "{}");
    if ("a" in argsObj) {
      argsObj.a = 1;
      argsObj.b = 2;
      await pg.fill('[data-testid="tool-args"]', JSON.stringify(argsObj, null, 2));
    }
    await pg.click('[data-testid="tool-test-run"]');
    await pg.waitForSelector('[data-testid="tool-test-result"]', { timeout: 20000 });
    const status = (await pg.textContent('[data-testid="tool-test-status"]'))?.trim() ?? "";
    const latency = (await pg.textContent('[data-testid="tool-test-latency"]'))?.trim() ?? "";
    const hasResult = (await pg.locator('[data-testid="tool-test-result-json"]').count()) > 0;
    check("工具测试展示 status/result/latency_ms",
      /成功|失败|超时/.test(status) && /ms/.test(latency) && hasResult,
      `${status} · ${latency}`);
    await pg.click('[data-slot="dialog-content"] button:has-text("关闭")').catch(() => pg.keyboard.press("Escape"));
  } else {
    check("工具测试展示 status/result/latency_ms", false, "未找到 add 工具");
  }

  // 关闭工具弹窗 → 调用日志表格
  await pg.click('[data-slot="dialog-content"] button:has-text("关闭")').catch(() => pg.keyboard.press("Escape"));
  await pg.waitForSelector('[data-testid="call-log-table"]', { timeout: 15000 });
  const callRows = await pg.locator('[data-testid="call-log-row"]').count();
  check("调用日志表格渲染", callRows > 0, `${callRows} 行`);

  // 健康扫描
  await pg.click('[data-testid="health-scan"]');
  await pg.waitForSelector('[data-testid="scan-summary"]', { timeout: 30000 });
  const scanText = (await pg.textContent('[data-testid="scan-summary"]'))?.trim() ?? "";
  check("健康扫描汇总", /OK \d+ \/ ERR \d+/.test(scanText), scanText);

  // 页面无 4xx/5xx
  check("RAG+MCP 页面无 4xx/5xx 响应", failedStatus.length === 0, failedStatus.join(" | ") || "全部 2xx");
} catch (err) {
  console.error("脚本异常:", err.message);
  try {
    const dump = await pg.evaluate(() => ({
      url: location.href,
      bodyText: document.body.innerText.slice(0, 1500),
      toasts: [...document.querySelectorAll("[data-sonner-toast]")].map((t) => t.textContent.slice(0, 120)),
    }));
    fs.writeFileSync("C:/Users/Administrator/AppData/Local/Temp/opencode/task04-ui-fail.txt", JSON.stringify(dump, null, 2), "utf8");
    await pg.screenshot({ path: "C:/Users/Administrator/AppData/Local/Temp/opencode/task04-ui-fail.png" }).catch(() => undefined);
  } catch {
    /* ignore */
  }
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task04 UI 验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
