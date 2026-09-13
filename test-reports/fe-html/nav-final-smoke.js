/* task-NAV 全量烟测：13 页结构完整性 + JS 报错 + 导航项/激活/溢出/控制器 */
const { chromium } = require("../../edu-frontend/node_modules/playwright");
const path = require("path");
const root = __dirname;

const pages = [
  ["courses.html", "user", 8, "课程中心"],
  ["course-detail.html", "user", 8, "课程中心"],
  ["achievements.html", "user", 8, "成就中心"],
  ["community.html", "user", 8, "社区"],
  ["community-post.html", "user", 8, "社区"],
  ["practice.html", "user", 8, "错题/单词本"],
  ["admin-courses.html", "admin", 6, "课程管理"],
  ["admin-course-detail.html", "admin", 6, "课程管理"],
  ["admin-questions.html", "admin", 6, "题库管理"],
  ["admin-question-detail.html", "admin", 6, "题库管理"],
  ["admin-dashboard.html", "admin", 6, "仪表盘"],
  ["admin-users.html", "admin", 6, "用户管理"],
  ["admin-rag-upload.html", "admin", 6, "RAG知识库"],
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const out = [];
  for (const [file, kind, expected, actTitle] of pages) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));
    const url = `file://${path.join(root, file).replace(/\\/g, "/")}`;
    try {
      await page.goto(url, { waitUntil: "load", timeout: 20000 });
      await page.waitForTimeout(600);
      const m = await page.evaluate(() => {
        const navs = [...document.querySelectorAll(".gnav-list .gnav-item")].map(a => a.textContent.trim());
        const active = document.querySelector(".gnav-list .gnav-item.active")?.textContent.trim() || "NONE";
        const ariaC = document.querySelector(".gnav-list .gnav-item.active")?.getAttribute("aria-current") || "NULL";
        // 状态演示器按钮：各页属性名不一（data-s/data-st/data-state/data-v/data-vbk/data-vq），
        // 但状态令牌值统一为 success/loading/error/empty/none；按「值∈令牌」判别，天然排除视口/Tab/对话框按钮。
        const ctrlCount = [...document.querySelectorAll("button")].filter(b =>
          Object.values(b.dataset).some(v => ["success", "loading", "error", "empty", "none"].includes(v))
        ).length;
        const hamb = getComputedStyle(document.querySelector("#gnavToggle")).display;
        const overflowX = document.documentElement.scrollWidth > window.innerWidth;
        const hasMCP = [...document.querySelectorAll(".gnav-list .gnav-item")].some(a => a.textContent.includes("MCP"));
        const bodyLen = document.body.innerText.length;
        return { navs, active, ariaC, ctrlCount, hamb, overflowX, hasMCP, bodyLen };
      });
      out.push({ file, kind, pass: m.navs.length === expected && m.active === actTitle && m.ariaC === "page" && m.bodyLen > 200, itemCount: m.navs.length, active: m.active, ariaC: m.ariaC, ctrlStates: m.ctrlCount, hamb: m.hamb, overflowX: m.overflowX, hasMCP: m.hasMCP, jsErrors: errors.length, errSamples: errors.slice(0, 2) });
    } catch (e) {
      out.push({ file, kind, pass: false, error: String(e.message || e), jsErrors: errors.length });
    }
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out, null, 2));
})();