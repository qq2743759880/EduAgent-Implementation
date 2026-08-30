/**
 * task03 浏览器 UI 全链路验证（Playwright，真实 UI 写操作）
 * 创建系列 → 创建模块 → 创建课次 → 校验回显（中文名）
 */
import { chromium } from "playwright";
import fs from "node:fs";

const token = process.argv[2];
const BASE = "http://localhost:3000";
const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1440, height: 1000 } });
await pg.addInitScript(
  ({ token }) => {
    localStorage.setItem("edu:auth:token", token);
    localStorage.setItem(
      "edu:auth:me",
      JSON.stringify({ id: 850, nickname: "验证管理员", email: "a@example.com", roles: ["admin"] }),
    );
  },
  { token },
);
pg.on("pageerror", (e) => console.error("  [pageerror]", e.message));
pg.on("console", (m) => {
  if (m.type() === "error") console.error("  [console.error]", m.text().slice(0, 200));
});
pg.on("response", (r) => {
  if (r.url().includes("/api/admin/courses/series") && r.request().method() === "POST") {
    console.log("  [POST /series]", r.status(), JSON.stringify(r.request().postData()).slice(0, 300));
  }
});
pg.on("requestfailed", (r) => console.error("  [reqfail]", r.url().slice(0, 140), r.failure()?.errorText));

const seriesCode = `UI-${stamp}`;
const seriesName = `界面验证系列${stamp}`;
const moduleName = `界面验证模块${stamp}`;
const sessionName = `界面验证课次${stamp}`;

try {
  /* ===== 1. 创建系列（SeriesForm 对话框） ===== */
  await pg.goto(`${BASE}/admin/courses`, { waitUntil: "networkidle", timeout: 30000 });
  // 等待列表真实渲染 + 水合稳定（避免 networkidle 早于 hydration 触发点击竞态）
  await pg.waitForSelector('[data-testid="series-list"]', { timeout: 15000 });
  await pg.waitForTimeout(800);
  await pg.click("button:has-text('创建系列') >> nth=0");
  await pg.waitForSelector("text=系列名称", { timeout: 10000 });
  // 注意：页面筛选栏也有 data-slot="native-select"，必须限定在 dialog-content 内
  await pg.fill("[data-slot='dialog-content'] input[placeholder='2-64 字符']", seriesCode);
  await pg.fill("[data-slot='dialog-content'] input[placeholder='如：雅思基础入门系列']", seriesName);
  await pg.selectOption("[data-slot='dialog-content'] [data-slot='native-select'] >> nth=0", "english");
  await pg.selectOption("[data-slot='dialog-content'] [data-slot='native-select'] >> nth=1", "L2");
  await pg.fill("[data-slot='dialog-content'] input[placeholder='如：入门']", "基础");
  await pg.click("button:has-text('创建系列') >> nth=-1");
  await pg.waitForSelector(`text=${seriesName}`, { timeout: 15000 });
  check("UI 创建系列 → 列表回显", true, seriesName);

  /* ===== 2. 进入详情 → 创建模块 ===== */
  await pg.click(`text=${seriesName}`);
  await pg.waitForSelector("button:has-text('新增模块')", { timeout: 15000 });
  await pg.click("button:has-text('新增模块')");
  await pg.waitForSelector("text=模块名称", { timeout: 10000 });
  await pg.fill("input[placeholder='如：词汇基础']", moduleName);
  await pg.fill("input[placeholder='如：MOD-01']", `M-${stamp}`);
  await pg.click("button:has-text('创建模块')");
  await pg.waitForSelector(`text=${moduleName}`, { timeout: 15000 });
  check("UI 创建模块 → 树内回显", true, moduleName);

  /* ===== 3. 创建课次 ===== */
  // 精确匹配「课次」动作按钮（模块卡折叠按钮含「0 课次」文本会误命中）
  await pg.getByRole("button", { name: "课次", exact: true }).click();
  await pg.waitForSelector("text=课次标题", { timeout: 10000 });
  await pg.fill("input[placeholder='如：第 1 讲 词汇导学']", sessionName);
  await pg.click("button:has-text('创建课次') >> nth=-1");
  await pg.waitForSelector(`text=${sessionName}`, { timeout: 15000 });
  check("UI 创建课次 → 树内回显", true, sessionName);

  /* ===== 4. 课次出现「上传视频」按钮 ===== */
  const uploadBtns = await pg.locator("button:has-text('上传视频')").count();
  check("课次「上传视频」按钮", uploadBtns > 0, `${uploadBtns} 个`);

  /* ===== 5. 视频四步流 UI 冒烟：打开 → Init → 绑定 ===== */
  await pg.click("button:has-text('上传视频') >> nth=0");
  await pg.waitForSelector("text=视频文件名", { timeout: 10000 });
  await pg.fill("input[placeholder='如：lesson-01-intro.mp4']", `ui-${stamp}.mp4`);
  await pg.click("button:has-text('发起上传')");
  // 等待模拟上传 + Finalize + Bind（约 3-5s），出现「完成」按钮即走完
  await pg.waitForSelector("button:has-text('绑定到本课次')", { timeout: 20000 });
  await pg.click("button:has-text('绑定到本课次')");
  await pg.waitForSelector("button:has-text('完成')", { timeout: 15000 });
  check("UI 视频 Init→Finalize→Bind 全链路", true, "");
  await pg.click("button:has-text('完成')");
  // 绑定后课次显示「已绑视频」
  await pg.waitForSelector("text=已绑视频", { timeout: 10000 });
  check("绑定后课次显示「已绑视频」", true, "");
} catch (err) {
  console.error("脚本异常:", err.message);
  try {
    const dump = await pg.evaluate(() => ({
      url: location.href,
      bodyText: document.body.innerText.slice(0, 1500),
      toasts: [...document.querySelectorAll("[data-sonner-toast]")].map((t) => t.textContent.slice(0, 120)),
    }));
    fs.writeFileSync("C:/Users/Administrator/AppData/Local/Temp/opencode/ui-chain-fail.txt", JSON.stringify(dump, null, 2), "utf8");
    await pg.screenshot({ path: "C:/Users/Administrator/AppData/Local/Temp/opencode/ui-chain-fail.png" }).catch(() => undefined);
  } catch {
    /* ignore */
  }
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task03 UI 全链路：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
