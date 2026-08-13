/**
 * task03 浏览器验证脚本（Playwright）
 *  - 注入真实 admin JWT（localStorage）→ 访问 6 个管理端页面
 *  - 断言：dashboard 6 指标卡、courses 系列列表、系列详情模块树、questions 列表、题目编辑、users 表格
 * 用法：node scripts/verify-task03-admin-ui.mjs <token>
 */
import { chromium } from "playwright";

const token = process.argv[2]?.trim();
if (!token) {
  console.error("usage: node scripts/verify-task03-admin-ui.mjs <jwt>");
  process.exit(1);
}

const BASE = "http://localhost:3000";
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// 注入登录态：token + me（roles 含 admin）
await page.addInitScript(({ token }) => {
  localStorage.setItem("edu:auth:token", token);
  localStorage.setItem(
    "edu:auth:me",
    JSON.stringify({ id: 850, nickname: "验证管理员", email: "admv@example.com", roles: ["admin"] }),
  );
  localStorage.setItem("edu:auth:tenant", "1");
}, { token });

page.on("pageerror", (err) => console.error("  [pageerror]", err.message));
page.on("console", (msg) => {
  if (msg.type() === "error" && !msg.text().includes("favicon")) {
    console.error("  [console.error]", msg.text().slice(0, 160));
  }
});

try {
  /* ============ 1. /admin/dashboard：6 指标卡 ============ */
  await page.goto(`${BASE}/admin/dashboard`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[data-testid="metric-cards"]', { timeout: 15000 });
  check("dashboard 指标卡渲染", true);
  for (const label of ["用户总数", "7d 活跃用户", "禁用账号", "7d 新增注册", "30d 人均登录（天）"]) {
    const el = page.locator(`[data-testid="metric-${label}"]`).first();
    const visible = await el.isVisible().catch(() => false);
    check(`dashboard 指标「${label}」有值`, visible, visible ? (await el.textContent()) : "");
  }
  // 角色分布卡（子项 testid：metric-role-{role}）
  const roleCards = [];
  for (const role of ["admin", "manager", "teacher", "student"]) {
    roleCards.push(await page.locator(`[data-testid="metric-role-${role}"]`).count());
  }
  check("dashboard 角色分布渲染（4 角色）", roleCards.every((c) => c > 0), roleCards.join("/"));

  /* ============ 2. /admin/courses：系列列表 ============ */
  await page.goto(`${BASE}/admin/courses`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[data-testid="series-list"]', { timeout: 15000 });
  const seriesCount = await page.locator('[data-testid="series-row"]').count();
  check("courses 系列列表渲染", seriesCount > 0, `${seriesCount} 行`);

  /* ============ 3. /admin/courses/[seriesId]：模块/课次/视频 ============ */
  await page.goto(`${BASE}/admin/courses/21`, { waitUntil: "networkidle", timeout: 30000 });
  // 等待模块树真实渲染（tree 是独立 useQuery，需等待其 resolve）
  await page.waitForSelector("text=验证模块", { timeout: 15000 });
  const hasModule = await page.locator("text=验证模块").count();
  const hasSession = await page.locator("text=验证课次").count();
  const hasVideoBtn = await page.locator("button:has-text('上传视频')").count();
  check("系列详情页渲染（模块树）", hasModule > 0, `模块=${hasModule}`);
  check("课次渲染", hasSession > 0, `课次=${hasSession}`);
  check("课次「上传视频」入口存在", hasVideoBtn > 0, `${hasVideoBtn} 个按钮`);

  /* ============ 4. /admin/questions：题目列表 ============ */
  await page.goto(`${BASE}/admin/questions`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[data-testid="question-list"]', { timeout: 15000 });
  const qCount = await page.locator('[data-testid="question-row"]').count();
  check("questions 题目列表渲染", qCount > 0, `${qCount} 行`);
  const hasImportBtn = await page.locator("button:has-text('批量导入')").count();
  const hasComposeBtn = await page.locator("button:has-text('自动组卷')").count();
  check("批量导入/自动组卷按钮存在", hasImportBtn > 0 && hasComposeBtn > 0, "");

  /* ============ 5. /admin/questions/[id]：题目编辑页 ============ */
  await page.goto(`${BASE}/admin/questions/4`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[data-testid="question-form"]', { timeout: 15000 });
  const codeInput = await page.locator('input[value="Q-20260812194829"]').count();
  check("题目编辑页回填题目编码", codeInput > 0, "");
  const hasSave = await page.locator('[data-testid="embedded-save"]').count();
  check("题目编辑页「保存修改」存在", hasSave > 0, "");

  /* ============ 6. /admin/users：用户表格 ============ */
  await page.goto(`${BASE}/admin/users`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector('[data-testid="user-table"]', { timeout: 15000 });
  const userRows = await page.locator('[data-testid="user-row"]').count();
  check("users 用户表格渲染", userRows > 0, `${userRows} 行`);
  const roleSelect = await page.locator('[data-testid^="role-select-"]').first().inputValue();
  check("角色下拉有值", roleSelect.length > 0, `首行角色=${roleSelect}`);

  /* ============ 7. RBAC：student 访问 /admin/courses 被守卫拦截 ============ */
  const page2 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page2.addInitScript(({ token }) => {
    localStorage.setItem("edu:auth:token", token);
    localStorage.setItem(
      "edu:auth:me",
      JSON.stringify({ id: 999, nickname: "学生甲", email: "s@example.com", roles: ["student"] }),
    );
  }, { token });
  await page2.goto(`${BASE}/admin/courses`, { waitUntil: "networkidle", timeout: 30000 });
  await page2.waitForTimeout(1500);
  const redirected = !page2.url().includes("/admin/courses") || page2.url().includes("/dashboard");
  check("student 访问管理端被守卫拦截重定向", redirected, page2.url());
  await page2.close();
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task03 浏览器验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
