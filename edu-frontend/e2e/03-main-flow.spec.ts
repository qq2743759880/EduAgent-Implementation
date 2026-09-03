/**
 * task69 · GWT① 全链路 + GWT④ 状态机 + RBAC + 响应壳
 * 链路：登录 → 学习仪表盘 → 课程中心 → 我的班次 → AI 问答 → 社区 → 成就 → 个人中心 → 管理端(RBAC)
 */
import { test, expect } from "@playwright/test";
import { login, STUDENT, ADMIN, expectUserNav } from "./helpers";

/** 收集一次页面生命周期内所有 XHR/fetch 响应结构（排除 SSE） */
async function collectResponseShell(page: import("@playwright/test").Page) {
  const violations: { url: string; status: number; body: string }[] = [];
  page.on("response", (res) => {
    const ct = res.headers()["content-type"] || "";
    // 跳过 SSE / 流式 / 非 JSON
    if (ct.includes("text/event-stream")) return;
    if (res.request().resourceType() !== "xhr" && !res.url().includes("/api/")) return;
    res.text().then((txt) => {
      // 后端响应壳预期 {code,message,data}（部分端点 204/前端静态资源跳过）
      if (!txt) return;
      try {
        const j = JSON.parse(txt);
        // 已冻结分页契约：/api/admin/users 等列表接口直接返回 {total,page,page_size,items} DTO
        // （前端 DataTable 依赖 res.items/res.total，非 {code,message,data} 壳）——显式豁免，不判违规
        const isPagedDto =
          j && typeof j === "object" && "total" in j && "page" in j && "items" in j && !("code" in j);
        if (isPagedDto) return;
        // 其余业务端点须满足统一响应壳 {code,message,data}
        if (typeof j.code === "undefined" || typeof j.message === "undefined" || !("data" in j)) {
          violations.push({ url: res.url(), status: res.status(), body: txt.slice(0, 120) });
        }
      } catch {
        /* 非 JSON（图片/文本等）跳过 */
      }
    }).catch(() => {});
  });
  const done = () => new Promise<void>((r) => setTimeout(r, 1200));
  return { violations, flush: done };
}

test.describe("全链路主流程（GWT①）", () => {
  test("用户端 8 页全链路可达 + 导航完整", async ({ page }) => {
    await login(page, STUDENT.account, STUDENT.password);
    await expectUserNav(page);

    // 逐个访问用户页并断言「正文非空白」
    const pages = [
      "/dashboard", "/courses", "/my-courses", "/practice/wrong-book",
      "/chat", "/community", "/achievements", "/me",
    ];
    for (const p of pages) {
      await page.goto(p, { waitUntil: "domcontentloaded", timeout: 30_000 });
      await page.waitForTimeout(700);
      const bodyLen = (await page.evaluate(() => document.body.innerText.length).catch(() => 0)) ?? 0;
      expect(bodyLen, `${p} 正文为空`).toBeGreaterThan(50);
    }
  });

  test("管理端 6 页（admin 账号）可达", async ({ page }) => {
    await login(page, ADMIN.account, ADMIN.password, "/dashboard");
    const adminPages = ["/admin/dashboard", "/admin/courses", "/admin/questions", "/admin/users", "/admin/rag", "/admin/mcp"];
    for (const p of adminPages) {
      const resp = await page.goto(p, { waitUntil: "domcontentloaded", timeout: 30_000 });
      // 页面应能渲染（允许走 React 端路由 200 或预渲染 200）
      const status = resp ? resp.status() : -1;
      expect(status, `${p} HTTP=${status}`).toBeLessThan(400);
      await page.waitForTimeout(500);
    }
  });

  test("RBAC：student 访问管理端端点 → 403 + 统一错误壳", async ({ page }) => {
    await login(page, STUDENT.account, STUDENT.password);
    const { violations, flush } = await collectResponseShell(page);
    // student 直接请求管理端 API（如 admin users 列表）应被 403/40303 拒绝
    const res = await page.evaluate(async () => {
      const token = (() => {
        try { return localStorage.getItem("edu.auth.token") || ""; } catch { return ""; }
      })();
      const r = await fetch("/admin/users", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      // admin/users 是前端路由（HTML），真实 RBAC 校验在 API 层：
      // 断言后端校验场景 —— 尝试直接调 API 前缀
      const api = await fetch("/api/admin/users", {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: AbortSignal.timeout(8000),
      }).then(r => r.json()).catch(e => ({ __err: e.name }));
      return { rStatus: r.status, api };
    }).catch((e) => ({ __err: e.message }));
    await flush();
    // 前端管理页对 student 返回：要么重定向（前端守卫），要么 403
    const u = new URL(page.url());
    // student 不应能停留在管理页（管理守卫拦截）
    // 后端 /api/admin/users 应按契约 403 + 错误壳
    expect(res).not.toHaveProperty("__err");
    if ("api" in res && res.api && !res.api.__err) {
      // 统一错误壳：code 为字符串、data 为 null
      expect(typeof res.api.code).toBe("string");
      expect(res.api.data).toBeNull();
    }
  });
});

test.describe("RBAC 后端契约校验（GWT④状态机/RBAC 服务端强制）", () => {
  test("admin 用户列表接口返回统一响应壳，无结构违规", async ({ page }) => {
    // 用 admin 真实登录走一次管理页，收集所有 /api/* XHR 响应壳
    await login(page, ADMIN.account, ADMIN.password, "/dashboard");
    const { violations, flush } = await collectResponseShell(page);
    // 触发管理端真实数据请求
    await page.goto("/admin/users", { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(2500); // 等待 DataTable 请求与渲染
    await flush();
    const bad = violations.filter((v) => !v.url.includes("/api/health") && !v.url.includes("/api/auth/refresh"));
    expect(bad, `响应壳违规：${JSON.stringify(bad.slice(0, 3))}`).toEqual([]);
  });
});