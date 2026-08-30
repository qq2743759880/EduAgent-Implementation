// 探测主链路可达性：登录→导航8项→各用户页 HTTP 状态（供 E2E 套件适配 selector）
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:3000";
const userNav = [
  ["/dashboard", "学习仪表盘"],
  ["/courses", "课程中心"],
  ["/my-courses", "我的班次"],
  ["/practice/wrong-book", "错题 / 单词本"],
  ["/chat", "AI 学习问答"],
  ["/community", "社区"],
  ["/achievements", "成就中心"],
  ["/me", "个人中心"],
];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const out = [];

// 1. 登录
await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.getByPlaceholder(/账号|邮箱/).first().fill("stu01test");
await page.getByPlaceholder(/密码|6 位以上/).first().fill("Test@123456");
await page.getByRole("button", { name: "登录" }).first().click();
await page.waitForURL(/\/dashboard/, { timeout: 15000 }).catch(()=>{});
out.push({ step: "login", url: page.url() });

// 2. 导航项可见性（桌面 1280）
await page.setViewportSize({ width: 1280, height: 800 });
for (const [href, label] of userNav) {
  const link = page.locator(`aside a[href="${href}"]`).first();
  const visible = await link.isVisible().catch(() => false);
  out.push({ step: `nav:${label}`, href, visible });
}

// 3. 逐个访问用户页，抓页面标题与 body 文本长度
for (const [href] of userNav) {
  const status = await page.goto(`${BASE}${href}`, { waitUntil: "domcontentloaded", timeout: 20000 })
    .then(r => r && r.status())
    .catch(e => `ERR:${e.name}`);
  await page.waitForTimeout(800);
  const h1 = await page.locator("h1").first().textContent().catch(() => "");
  const bodyLen = (await page.evaluate(() => document.body.innerText.length).catch(() => 0)) ?? 0;
  out.push({ step: `page:${href}`, http: status, h1: (h1||"").trim().slice(0, 30), bodyLen });
}

console.log(JSON.stringify(out, null, 2));
await browser.close();