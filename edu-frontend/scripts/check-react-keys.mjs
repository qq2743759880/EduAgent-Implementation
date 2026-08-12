/**
 * scripts/check-react-keys.mjs
 *
 * 用途：用 Playwright 打开 EduAgent 前端的若干页面，抓取浏览器 console 中的
 *       warning / error，重点筛查 React 19 的「重复 key / 缺失 key」告警。
 *
 * 使用方法：
 *   1) 先确保 dev server 已在运行（默认 http://localhost:3000）：
 *        npm run dev
 *   2) 首次使用需安装 Playwright + Chromium（仅此一次）：
 *        npm i -D playwright
 *        npx playwright install chromium
 *   3) 跑检查：
 *        npm run check:keys
 *        # 或指定自定义地址
 *        BASE_URL=http://localhost:3001 npm run check:keys
 *        # 输出 JSON 报告到文件
 *        REPORT_JSON=./key-report.json npm run check:keys
 *        # 使用你自己手动下载的 Chrome / Chromium（离线包）
 *        PLAYWRIGHT_CHROMIUM_DIR=D:\tool\chrome-win64 npm run check:keys
 *        PLAYWRIGHT_CHROMIUM_EXECUTABLE=D:\tool\chrome-win64\chrome.exe npm run check:keys
 *
 * 退出码：
 *   0 — 未命中任何 same-key / unique-key 的告警
 *   1 — 命中了 React key 告警（或有页面加载异常）
 *   2 — Playwright / 环境未配置 / 访问地址不通
 */
import { chromium } from "playwright";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const BASE_URL = (process.env.BASE_URL || "http://localhost:3000").replace(/\/+$/, "");
const DEFAULT_TIMEOUT_MS = 20_000;
const PAGE_IDLE_MS = 2_000;
const REPORT_JSON = process.env.REPORT_JSON || null;

/** 页面配置：包含路径、显示名和（可选的）页面内交互步骤 */
const PAGES = [
  {
    path: "/",
    name: "首页",
    async interact(page) {
      await gentleScroll(page);
    },
  },
  {
    path: "/login",
    name: "登录页",
    async interact(page) {
      await gentleScroll(page);
    },
  },
  {
    path: "/register",
    name: "注册页",
    async interact(page) {
      await gentleScroll(page);
    },
  },
  {
    path: "/courses",
    name: "课程大厅",
    async interact(page) {
      // 尝试点一下第一个学科标签（如果有），触发列表渲染
      const firstChip = page
        .locator("[data-subject-code]")
        .or(page.locator("button:has-text('语文')"))
        .or(page.locator("button:has-text('数学')"))
        .first();
      if (await firstChip.isVisible({ timeout: 1500 }).catch(() => false)) {
        await firstChip.click({ force: true, timeout: 3000 }).catch(() => {});
        await waitForIdle(page, 1500);
      }
      await gentleScroll(page);
    },
  },
  {
    path: "/courses/search",
    name: "课程搜索",
    async interact(page) {
      const search = page
        .locator('input[type="search"]')
        .or(page.locator('input[placeholder*="搜索"]'))
        .first();
      if (await search.isVisible({ timeout: 1500 }).catch(() => false)) {
        await search.fill("数学", { timeout: 3000 }).catch(() => {});
        await search.press("Enter", { timeout: 3000 }).catch(() => {});
        await waitForIdle(page, 1500);
      }
      await gentleScroll(page);
    },
  },
  {
    // 用 ID=1 作为样例；若后端没有该数据只要能安全兜底 404 即可
    path: "/courses/1",
    name: "课程详情(样例)",
    async interact(page) {
      // 尝试切到评价 Tab（若有）触发评价列表渲染
      const reviewTab = page
        .getByRole("tab", { name: /评价|评论/iu })
        .first();
      if (await reviewTab.isVisible({ timeout: 1500 }).catch(() => false)) {
        await reviewTab.click({ force: true, timeout: 3000 }).catch(() => {});
        await waitForIdle(page, 1500);
      }
      await gentleScroll(page);
    },
  },
  {
    path: "/chat",
    name: "AI 问答",
    async interact(page) {
      await gentleScroll(page);
      const input = page
        .locator("textarea")
        .or(page.locator('div[contenteditable="true"]'))
        .first();
      if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
        await input.fill("你好，帮我介绍一下小学一年级数学", { timeout: 4000 }).catch(() => {});
        const sendBtn = page
          .getByRole("button", { name: /发送|send/iu })
          .or(page.locator('button[type="submit"]'))
          .first();
        if (await sendBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
          await sendBtn.click({ force: true, timeout: 3000 }).catch(() => {});
          await waitForIdle(page, 3500);
        }
      }
    },
  },
  {
    path: "/dashboard",
    name: "学习仪表盘（未登录会跳/login）",
    requireAuth: true,
    async interact(page) {
      await gentleScroll(page);
    },
  },
  {
    path: "/me",
    name: "个人中心（未登录会跳/login）",
    requireAuth: true,
    async interact(page) {
      await gentleScroll(page);
    },
  },
  {
    path: "/my-courses",
    name: "我的课程（未登录会跳/login）",
    requireAuth: true,
    async interact(page) {
      // 尝试切 Tab：进行中 / 已完成 / 已收藏
      for (const name of ["进行中", "已完成", "已收藏"]) {
        const tab = page.getByRole("tab", { name, exact: false }).first();
        if (await tab.isVisible({ timeout: 1200 }).catch(() => false)) {
          await tab.click({ force: true, timeout: 2500 }).catch(() => {});
          await waitForIdle(page, 800);
        }
      }
      await gentleScroll(page);
    },
  },
];

const KEY_WARN_RE =
  /same\s*key|key.*undefined|unique\s*["']?key["']?\s*prop|duplicate\s*key|children.*should.*have.*a.*unique.*key|each\s+child\s+in\s+a\s+list\s+should\s+have\s+a\s+unique\s+"?key"?\s+prop/i;

const LEVEL_COLOR = {
  info: "\x1b[90m",
  warn: "\x1b[33m",
  error: "\x1b[31m",
  pageerror: "\x1b[35m",
  hit: "\x1b[41m\x1b[37m",
};
const RESET = "\x1b[0m";

const perPage = new Map();
const globalCounts = { info: 0, warn: 0, error: 0, pageerror: 0, keyHits: 0 };

main().then((code) => process.exit(code));

async function main() {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: resolveChromiumExecutable(),
    });
  } catch (e) {
    console.error(
      `${LEVEL_COLOR.error}[FATAL]${RESET} 无法启动 Playwright Chromium：`,
      e?.message || String(e),
    );
    const hint = resolveChromiumExecutable()
      ? `  当前使用的自定义 Chromium 路径：${resolveChromiumExecutable()}\n  若路径不正确请调整 PLAYWRIGHT_CHROMIUM_EXECUTABLE / PLAYWRIGHT_CHROMIUM_DIR。\n`
      : "";
    console.error(
      `${hint}  如需使用系统自动安装请执行：\n  npm i -D playwright\n  npx playwright install chromium\n  如使用离线包可设置：\n  PLAYWRIGHT_CHROMIUM_DIR=D:\\tool\\chrome-win64  或  PLAYWRIGHT_CHROMIUM_EXECUTABLE=D:\\tool\\chrome-win64\\chrome.exe`,
    );
    return 2;
  }

  const ctx = await browser.newContext({
    locale: "zh-CN",
    viewport: { width: 1280, height: 820 },
    ignoreHTTPSErrors: true,
  });
  ctx.setDefaultTimeout(DEFAULT_TIMEOUT_MS);

  // 先 ping 一下服务，避免在后续每个页面才报通用错误
  try {
    const resp = await fetch(BASE_URL + "/", { method: "HEAD" }).catch(
      () => fetch(BASE_URL + "/"),
    );
    if (!resp || resp.status >= 500) {
      console.error(
        `${LEVEL_COLOR.error}[FATAL]${RESET} 无法访问 BASE_URL=${BASE_URL} （status=${
          resp?.status ?? "unknown"
        }）。请先执行 npm run dev 启动前端。`,
      );
      await browser.close();
      return 2;
    }
  } catch (e) {
    console.error(
      `${LEVEL_COLOR.error}[FATAL]${RESET} 无法访问 BASE_URL=${BASE_URL}：`,
      e?.message || String(e),
    );
    console.error("请先执行 npm run dev 启动前端。");
    await browser.close();
    return 2;
  }

  console.log(`\n🚀 EduAgent React Key 巡检 · 目标：${BASE_URL}\n`);

  for (const conf of PAGES) {
    const { path, name, requireAuth, interact } = conf;
    const url = BASE_URL + path;
    const page = await ctx.newPage();

    const record = {
      name,
      path,
      finalUrl: url,
      redirected: false,
      requireAuth,
      authBlocked: false,
      httpStatus: null,
      counts: { info: 0, warn: 0, error: 0, pageerror: 0 },
      console: [],
      keyHits: [],
      errors: [],
    };

    page.on("console", (msg) => {
      const type = msg.type(); // log / info / warning / error ...
      const norm = type === "warning" ? "warn" : type;
      const text = msg.text();
      if (!["info", "warn", "error", "pageerror"].includes(norm)) return;
      record.counts[norm] = (record.counts[norm] || 0) + 1;
      globalCounts[norm]++;
      record.console.push({ level: norm, text });
      if (KEY_WARN_RE.test(text)) {
        record.keyHits.push({ level: norm, text });
        globalCounts.keyHits++;
      }
    });

    page.on("pageerror", (err) => {
      record.counts.pageerror = (record.counts.pageerror || 0) + 1;
      globalCounts.pageerror++;
      const text = err?.stack || err?.message || String(err);
      record.errors.push(text);
      if (KEY_WARN_RE.test(text)) {
        record.keyHits.push({ level: "pageerror", text });
        globalCounts.keyHits++;
      }
    });

    try {
      const resp = await page.goto(url, {
        waitUntil: "domcontentloaded",
        timeout: DEFAULT_TIMEOUT_MS,
      });
      record.httpStatus = resp?.status() ?? null;
      await waitForIdle(page, PAGE_IDLE_MS);
      record.finalUrl = page.url();
      record.redirected = new URL(record.finalUrl).pathname !== path;
      if (requireAuth && record.redirected && /\/login($|\?)/i.test(record.finalUrl)) {
        record.authBlocked = true;
      }
      await interact?.(page);
    } catch (err) {
      record.errors.push(`page.goto / interact 失败：${err?.message || String(err)}`);
    }

    perPage.set(path, record);
    await page.close().catch(() => {});
    printPageSummary(record);
  }

  await ctx.close().catch(() => {});
  await browser.close().catch(() => {});

  console.log("\n────────────── 全局汇总 ──────────────");
  console.log(
    `info=${globalCounts.info}  warn=${globalCounts.warn}  error=${globalCounts.error}  pageerror=${globalCounts.pageerror}`,
  );
  const exitCode = globalCounts.keyHits > 0 || anyFatal(perPage) ? 1 : 0;
  if (globalCounts.keyHits > 0) {
    console.log(
      `${LEVEL_COLOR.hit}[命中 React key 告警] ${RESET} 共 ${globalCounts.keyHits} 条，详情见上方每个页面的 Hits 列表。`,
    );
  } else {
    console.log(
      `\x1b[32m✔${RESET} 未命中 React 的 same-key / unique-key 告警（控制台里出现的普通 warn/error 也会在上面列出）。`,
    );
  }

  if (REPORT_JSON) {
    const abs = path.isAbsolute(REPORT_JSON)
      ? REPORT_JSON
      : path.resolve(process.cwd(), REPORT_JSON);
    mkdirSync(path.dirname(abs), { recursive: true });
    const payload = {
      baseUrl: BASE_URL,
      generatedAt: new Date().toISOString(),
      globalCounts,
      exitCode,
      pages: [...perPage.values()],
    };
    writeFileSync(abs, JSON.stringify(payload, null, 2), "utf-8");
    console.log(`\n已写入 JSON 报告：${abs}`);
  }

  return exitCode;
}

/* ----------------------------- 辅助函数 ----------------------------- */

function resolveChromiumExecutable() {
  // 优先：直接指定可执行文件路径
  const explicit = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  if (explicit) {
    const abs = path.isAbsolute(explicit) ? explicit : path.resolve(process.cwd(), explicit);
    return abs;
  }
  // 次选：指定 Chromium / Chrome 所在目录，自动拼接 chrome.exe 或 chrome-headless-shell.exe
  const dir = process.env.PLAYWRIGHT_CHROMIUM_DIR;
  if (dir) {
    const absDir = path.isAbsolute(dir) ? dir : path.resolve(process.cwd(), dir);
    const candidates = [
      path.join(absDir, "chrome.exe"),
      path.join(absDir, "chrome-headless-shell.exe"),
      path.join(absDir, "bin", "chrome.exe"),
      path.join(absDir, "bin", "chrome-headless-shell.exe"),
    ];
    // 不用做 fs.exists，Playwright 自己启动失败时会给出更准确的报错；这里只做路径拼接
    return candidates[0];
  }
  // 未指定：走 Playwright 默认缓存（ms-playwright/* 下的 chromium_headless_shell）
  return undefined;
}

async function waitForIdle(page, ms = PAGE_IDLE_MS) {
  await page.waitForTimeout(ms);
}

async function gentleScroll(page) {
  try {
    await page.evaluate(async () => {
      const total = document.body.scrollHeight || document.documentElement.scrollHeight || 0;
      const steps = Math.max(2, Math.min(6, Math.round(total / 600)));
      for (let i = 1; i <= steps; i++) {
        window.scrollTo(0, Math.round((total * i) / steps));
        await new Promise((r) => setTimeout(r, 250));
      }
      window.scrollTo(0, 0);
    });
    await waitForIdle(page, 400);
  } catch {
    /* ignore: some pages use strict CSP or have detached frames */
  }
}

function printPageSummary(r) {
  const tag = r.authBlocked
    ? `${LEVEL_COLOR.warn}🔒 auth${RESET}`
    : r.redirected
      ? `${LEVEL_COLOR.warn}↩ redirect${RESET}`
      : `${LEVEL_COLOR.info}✔${RESET}`;
  console.log(
    `[${r.name}] ${r.path}  →  HTTP ${r.httpStatus ?? "??"}  ${tag}`,
  );
  console.log(
    `    counts: info=${r.counts.info}  warn=${r.counts.warn}  error=${r.counts.error}  pageerror=${r.counts.pageerror}`,
  );
  if (r.keyHits.length > 0) {
    console.log(
      `    ${LEVEL_COLOR.hit} Hits×${r.keyHits.length}${RESET} React key 告警：`,
    );
    for (const h of r.keyHits.slice(0, 5)) {
      const snippet = h.text.replace(/\s+/g, " ").slice(0, 220);
      console.log(`      · [${h.level}] ${snippet}`);
    }
    if (r.keyHits.length > 5) {
      console.log(`      · ... 其余 ${r.keyHits.length - 5} 条省略，见 REPORT_JSON`);
    }
  }
  if (r.errors.length > 0 && r.keyHits.length === 0) {
    console.log(`    pageerror×${r.errors.length}:`);
    for (const e of r.errors.slice(0, 2)) {
      console.log(`      · ${String(e).replace(/\s+/g, " ").slice(0, 180)}`);
    }
  }
  console.log("");
}

function anyFatal(map) {
  for (const r of map.values()) {
    if (!r.httpStatus) return true;
    if (r.httpStatus >= 500) return true;
  }
  return false;
}
