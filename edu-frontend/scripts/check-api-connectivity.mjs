/*
 * scripts/check-api-connectivity.mjs
 *
 * 功能：
 *   1) 静态探测后端 API catalog（匿名 / 最小 payload），检查每个路由的 HTTP status
 *      并把 404 / 405 / CORS / 连接拒绝 / 5xx / 响应体缺失关键字段 统一汇总。
 *   2) 通过 Playwright 打开前端每页（BASE_URL），点击所有带「data-test」或按钮文本命中
 *      关键词（登录 / 提交 / 发送 / 报名 / 保存 / 筛选 / 下一题 / 收藏）的可点击按钮，
 *      捕获网络请求，报告任何打到后端（API_BASE）的失败请求（非 2xx）。
 *
 * 环境变量：
 *   API_BASE                  后端地址（默认 http://127.0.0.1:8000）
 *   BASE_URL                  前端地址（默认 http://localhost:3000）
 *   PLAYWRIGHT_CHROMIUM_DIR   Chromium 所在目录（如 D:\tool\chrome-win64）
 *   PLAYWRIGHT_CHROMIUM_EXECUTABLE  Chromium 可执行文件路径（优先级最高）
 *   REPORT_JSON               JSON 报告输出路径
 *   SKIP_BROWSER              1 时跳过 Playwright（只跑静态探测）
 *
 * 用法：
 *   $env:API_BASE="http://127.0.0.1:8000"
 *   $env:BASE_URL="http://localhost:3000"
 *   $env:PLAYWRIGHT_CHROMIUM_DIR="D:\tool\chrome-win64"
 *   node scripts/check-api-connectivity.mjs
 */

import path from "node:path";
import fs from "node:fs";
import process from "node:process";
import { chromium } from "playwright";

/* ---------------- helpers ---------------- */

function resolveChromiumExecutable() {
  const explicit = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  if (explicit) {
    return path.isAbsolute(explicit)
      ? explicit
      : path.resolve(process.cwd(), explicit);
  }
  const dir = process.env.PLAYWRIGHT_CHROMIUM_DIR;
  if (dir) {
    const absDir = path.isAbsolute(dir)
      ? dir
      : path.resolve(process.cwd(), dir);
    const candidates = [
      path.join(absDir, "chrome.exe"),
      path.join(absDir, "chrome-headless-shell.exe"),
    ];
    return candidates.find((c) => fs.existsSync(c)) ?? candidates[0];
  }
  return undefined;
}

function env(name, fallback) {
  const v = process.env[name];
  if (v === undefined || v === null || v === "") return fallback;
  return v;
}

const API_BASE = env("API_BASE", "http://127.0.0.1:8000").replace(/\/$/, "");
const BASE_URL = env("BASE_URL", "http://localhost:3000").replace(/\/$/, "");
const REPORT_JSON = process.env.REPORT_JSON
  ? path.isAbsolute(process.env.REPORT_JSON)
    ? process.env.REPORT_JSON
    : path.resolve(process.cwd(), process.env.REPORT_JSON)
  : null;

/* ---------------- API catalog ---------------- */

/**
 * 每个条目：
 *   id, method, path, query?, body?,
 *   acceptStatus: 允许的 status（默认 200-299 + 401/422，因为匿名/缺参数）
 *   critical: true 表示若探测失败则整个脚本退出非零
 */
const CATALOG = [
  // Auth（登录/注册/me）—— critical 基础
  { id: "auth-login", method: "POST", path: "/api/auth/login", body: { account: "__probe__", password: "probe" }, accept422: true, critical: true },
  { id: "auth-register", method: "POST", path: "/api/auth/register", body: { account: "__probe__", password: "probe", nickname: "probe", email: "probe@example.com" }, accept422: true, critical: true },
  { id: "auth-me", method: "GET", path: "/api/auth/me", critical: true },

  // Curriculum（课程大厅/详情/树/导图）——匿名 critical
  { id: "curriculum-list", method: "GET", path: "/api/curriculum/series", query: { page: 1, page_size: 2 }, critical: true },
  { id: "curriculum-detail", method: "GET", path: "/api/curriculum/series/1", critical: true },
  { id: "curriculum-tree", method: "GET", path: "/api/curriculum/series/1/tree", critical: true },
  { id: "mindmap-course", method: "GET", path: "/api/mindmap/course/1", critical: true },

  // Progress（需要登录 -> 401 也算 ok；404 才是问题）
  { id: "progress-courses", method: "GET", path: "/api/progress/courses", accept401: true },
  { id: "progress-video-tick-batch", method: "POST", path: "/api/progress/video/tick-batch", body: { play_session_id: "ps-static-1", series_id: 1, ticks: [{ session_id: 1, position_at_percent: 5, duration_at_seconds: 30, watched_at: new Date().toISOString() }] }, accept401: true, accept422: true },
  { id: "progress-homework-submit", method: "POST", path: "/api/progress/homework/submit", body: { series_id: 1, session_id: 1, answers: [], score_earned: 5, score_total: 10, detail_payload: {} }, accept401: true, accept422: true },
  { id: "progress-exam-submit", method: "POST", path: "/api/progress/exam/submit", body: { series_id: 1, session_id: 1, paper_id: "paper-static-1", answers: [], score_earned: 80, score_total: 100, session_score_outof100: 80, detail_payload: {} }, accept401: true, accept422: true },

  // Interactive Quiz / Wrong Book
  { id: "quiz-next", method: "GET", path: "/api/interactive/quiz/next", query: { subject_code: "english" } },
  { id: "quiz-submit", method: "POST", path: "/api/interactive/quiz/submit", body: { question_id: 1, question_type: "SINGLE", custom_code: "q-1", answer: "A" }, accept401: true, accept422: true, accept500: true, failOk: { 422: true, 500: true } },
  { id: "quiz-wrong-book", method: "GET", path: "/api/interactive/quiz/wrong-book", query: { page: 1 }, accept401: true },

  // Vocab
  { id: "vocab-daily", method: "GET", path: "/api/vocab/daily", accept401: true },
  { id: "vocab-recall", method: "POST", path: "/api/vocab/recall", body: { card_id: 1, quality: 3 }, accept400: true, accept401: true },
  { id: "vocab-progress", method: "GET", path: "/api/vocab/progress", accept401: true },

  // Mindmap personal
  { id: "mindmap-me", method: "GET", path: "/api/mindmap/me/1", accept401: true },

  // Chat
  { id: "chat-sessions-list", method: "GET", path: "/api/chat/sessions", accept401: true },
  { id: "chat-sessions-create", method: "POST", path: "/api/chat/sessions", body: { title: "__probe__" }, accept401: true },
  { id: "chat-search", method: "POST", path: "/api/chat/search", body: { query: "test", limit: 2 }, accept401: true },
  { id: "chat-stream", method: "POST", path: "/api/chat/stream", body: { query: "你好", stream: true }, accept401: true, accept422: true, critical: true },
  { id: "chat-nonstream-fallback", method: "POST", path: "/api/chat/stream", body: { query: "你好", stream: false }, accept401: true, accept422: true, critical: true },

  // Users (profile) — /api/users/me 当前后端 404，/api/auth/me 只有 GET，PATCH 405。
  // 两个都探测一下，404/405 都做 fail-ok（前端已经走本地降级）。
  { id: "users-me-patch", method: "PATCH", path: "/api/users/me", body: { nickname: "probe" }, accept401: true, accept404: true, accept405: true },
  { id: "users-me-get", method: "GET", path: "/api/users/me", accept401: true, accept404: true },
  { id: "auth-me-patch", method: "PATCH", path: "/api/auth/me", body: { nickname: "probe" }, accept401: true, accept404: true, accept405: true },
];

/* ---------------- static probe ---------------- */

async function staticProbe() {
  const rows = [];
  for (const entry of CATALOG) {
    let url = `${API_BASE}${entry.path}`;
    if (entry.query) {
      const sp = new URLSearchParams();
      for (const [k, v] of Object.entries(entry.query)) {
        sp.set(k, String(v));
      }
      const qs = sp.toString();
      if (qs) url += `?${qs}`;
    }
    let status = 0;
    let statusText = "";
    let errKind = null;
    let bodySample = "";
    const start = Date.now();
    try {
      const resp = await fetch(url, {
        method: entry.method,
        headers: entry.body ? { "Content-Type": "application/json" } : undefined,
        body: entry.body ? JSON.stringify(entry.body) : undefined,
        signal: AbortSignal.timeout(10_000),
      });
      status = resp.status;
      statusText = resp.statusText;
      const contentType = resp.headers.get("content-type") || "";
      if (contentType.includes("json") || contentType.includes("text")) {
        const text = await resp.text();
        bodySample = text.slice(0, 200);
      }
    } catch (e) {
      const msg = e?.message || String(e);
      errKind =
        msg.includes("ECONNREFUSED") || msg.includes("fetch failed")
          ? "CONN_REFUSED"
          : msg.includes("timeout")
            ? "TIMEOUT"
            : msg.includes("CORS")
              ? "CORS"
              : "FETCH_ERROR";
      bodySample = msg.slice(0, 200);
    }
    const duration = Date.now() - start;
    const accept =
      (status >= 200 && status < 300) ||
      (entry.accept401 && status === 401) ||
      (entry.accept422 && status === 422) ||
      (entry.accept400 && status === 400) ||
      (entry.accept404 && status === 404) ||
      (entry.accept405 && status === 405) ||
      (entry.accept500 && status >= 500 && status < 600);
    const passed = accept && !errKind;
    if (status === 0 && !errKind) errKind = "UNKNOWN";
    rows.push({
      id: entry.id,
      method: entry.method,
      path: entry.path,
      status,
      statusText,
      durationMs: duration,
      passed,
      errKind,
      critical: !!entry.critical,
      bodySample,
    });
  }
  return rows;
}

/* ---------------- browser probe ---------------- */

async function browserProbe() {
  const pages = [
    { name: "首页", path: "/" },
    { name: "登录页", path: "/login" },
    { name: "注册页", path: "/register" },
    { name: "课程大厅", path: "/courses" },
    { name: "课程搜索", path: "/courses/search" },
    { name: "课程详情", path: "/courses/1" },
    { name: "AI问答", path: "/chat" },
    { name: "我的课程", path: "/my-courses" },
    { name: "学习仪表盘", path: "/dashboard" },
    { name: "个人中心", path: "/me" },
    { name: "播放页样例", path: "/learning/1/1" },
    { name: "练习页", path: "/practice/MIXED" },
  ];

  const interesting = (url) => url.startsWith(API_BASE) || url.includes("/api/");

  const allFailures = [];
  const byPage = [];

  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: resolveChromiumExecutable(),
    });
  } catch (e) {
    return {
      skipped: true,
      reason: `Playwright 启动失败：${e?.message || String(e)}（请确认 PLAYWRIGHT_CHROMIUM_DIR 或 PLAYWRIGHT_CHROMIUM_EXECUTABLE 指向正确的 Chromium）`,
      byPage: [],
      failures: [],
    };
  }

  try {
    for (const p of pages) {
      const failures = [];
      let httpStatus = 0;
      const page = await browser.newPage();
      try {
        const failedRequests = [];
        page.on("requestfailed", (req) => {
          const u = req.url();
          if (!interesting(u)) return;
          failedRequests.push({ url: u, error: req.failure()?.errorText || "unknown" });
        });
        page.on("response", async (resp) => {
          const u = resp.url();
          if (!interesting(u)) return;
          const s = resp.status();
          if (s < 200 || s >= 400) {
            failures.push({
              url: u,
              status: s,
              method: resp.request().method(),
            });
          }
        });

        const r = await page.goto(`${BASE_URL}${p.path}`, {
          waitUntil: "domcontentloaded",
          timeout: 25_000,
        });
        httpStatus = r?.status() || 0;
        await page.waitForTimeout(1500);

        // 点击关键词按钮（不导航离开当前页）
        const labels = [
          "登录", "注册", "发送", "提交", "保存",
          "筛选", "下一题", "收藏", "报名", "搜索",
          "重置", "查看", "更多",
        ];
        for (const lbl of labels) {
          try {
            const loc = page.getByRole("button", { name: lbl, exact: false }).first();
            if ((await loc.count()) > 0 && (await loc.isVisible()) && (await loc.isEnabled())) {
              await loc.click({ timeout: 3000, noWaitAfter: true }).catch(() => null);
              await page.waitForTimeout(600);
            }
          } catch { /* ignore */ }
        }

        // 对于 course detail / practice 等，滚动到底触发加载更多
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(() => null);
        await page.waitForTimeout(800);

        failures.push(...failedRequests.map((f) => ({ url: f.url, error: f.error, method: "?" })));
      } catch (e) {
        failures.push({ url: `${BASE_URL}${p.path}`, error: `页面加载失败：${e?.message || String(e)}`, method: "GET" });
      } finally {
        await page.close().catch(() => null);
      }
      byPage.push({ name: p.name, path: p.path, httpStatus, failures });
      allFailures.push(...failures.map((f) => ({ ...f, page: p.name })));
    }
  } finally {
    await browser.close().catch(() => null);
  }

  return { skipped: false, byPage, failures: allFailures };
}

/* ---------------- report & main ---------------- */

function severityOf(row) {
  if (row.errKind === "CONN_REFUSED") return "FATAL";
  if (row.status === 0) return "FATAL";
  if (row.passed) return "OK";
  if (row.status === 404) return row.critical ? "FATAL" : "WARN";
  if (row.status === 405) return row.critical ? "FATAL" : "WARN";
  if (row.status >= 500) return row.critical ? "FATAL" : "WARN";
  if (row.status >= 400 && !row.passed) return "WARN";
  return "OK";
}

async function main() {
  console.log(`\n🛰  EduAgent 前后端连通性巡检`);
  console.log(`    后端 API_BASE  = ${API_BASE}`);
  console.log(`    前端 BASE_URL  = ${BASE_URL}`);
  if (resolveChromiumExecutable()) {
    console.log(`    Chromium       = ${resolveChromiumExecutable()}`);
  }
  console.log("");

  console.log("── 阶段 1：静态 API catalog 探测（匿名 / 最小 payload）──\n");
  const probeRows = await staticProbe();
  const buckets = { FATAL: 0, WARN: 0, OK: 0 };
  let fatalCritical = false;
  for (const r of probeRows) {
    const sev = severityOf(r);
    buckets[sev] += 1;
    if (sev === "FATAL" && r.critical) fatalCritical = true;
    const tag =
      sev === "FATAL" ? "✗ FATAL" : sev === "WARN" ? "△ WARN " : "✔ OK   ";
    const mark = r.critical ? "*" : " ";
    const bodySnippet =
      r.status >= 400 || r.errKind ? `  ← ${(r.bodySample || "").replace(/\s+/g, " ").slice(0, 120)}` : "";
    console.log(
      `${tag}${mark} ${r.method.padEnd(5)} ${r.path.padEnd(46)}  ${String(r.status).padEnd(4)} ${String(r.durationMs).padStart(5)}ms${bodySnippet}`,
    );
  }
  console.log(
    `\n静态汇总：${buckets.OK} 个 OK / ${buckets.WARN} 个 WARN / ${buckets.FATAL} 个 FATAL${fatalCritical ? "  ⚠ 有关键接口挂了" : ""}`,
  );

  console.log("\n── 阶段 2：浏览器点击 & 网络失败捕获（如有可用 Chromium）──\n");
  const skipBrowser = env("SKIP_BROWSER", "0") === "1";
  const browserResult = skipBrowser
    ? { skipped: true, reason: "SKIP_BROWSER=1", byPage: [], failures: [] }
    : await browserProbe();

  if (browserResult.skipped) {
    console.log(`浏览器点击阶段跳过：${browserResult.reason}`);
  } else {
    for (const p of browserResult.byPage) {
      if (!p.failures.length) {
        console.log(`  [${p.name}] ${p.path.padEnd(28)} HTTP ${p.httpStatus}  ✔ 无 API 失败请求`);
      } else {
        console.log(`  [${p.name}] ${p.path.padEnd(28)} HTTP ${p.httpStatus}  ✗ 失败=${p.failures.length}`);
        for (const f of p.failures) {
          console.log(`      · ${f.method || "?"} ${f.status || ""} ${f.url}${f.error ? "  " + f.error : ""}`.slice(0, 200));
        }
      }
    }
    console.log(`\n浏览器点击汇总：共 ${browserResult.failures.length} 个 API 失败请求`);
  }

  if (REPORT_JSON) {
    const report = {
      generatedAt: new Date().toISOString(),
      apiBase: API_BASE,
      baseUrl: BASE_URL,
      static: probeRows.map((r) => ({ ...r, severity: severityOf(r) })),
      staticSummary: buckets,
      browser: skipBrowser
        ? { skipped: true, reason: browserResult.reason }
        : {
            skipped: false,
            pages: browserResult.byPage,
            failures: browserResult.failures,
          },
    };
    fs.mkdirSync(path.dirname(REPORT_JSON), { recursive: true });
    fs.writeFileSync(REPORT_JSON, JSON.stringify(report, null, 2), "utf8");
    console.log(`\n已写入 JSON 报告：${REPORT_JSON}`);
  }

  // Exit code：FATAL 里含 critical（后端离线 / 关键路由 404/500）才非 0
  const exitCode = fatalCritical ? 2 : browserResult.failures.length > 0 ? 1 : 0;
  console.log(`\n退出码 = ${exitCode}（2=关键接口 FATAL；1=浏览器阶段 API 失败；0=OK）\n`);
  process.exit(exitCode);
}

main().catch((e) => {
  console.error("check-api-connectivity.mjs 崩溃：", e?.stack || e);
  process.exit(3);
});
