/**
 * task04 RBAC 验证：student 访问 /admin/rag 与 /admin/mcp
 *  - 前端 AdminGuard 拦截（守卫重定向/提示）
 *  - 后端 API 403（X-Force-Role: student）
 */
import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
await pg.addInitScript(() => {
  localStorage.setItem("edu:auth:token", "debug-force-token");
  localStorage.setItem("edu:auth:me", JSON.stringify({ id: 802, nickname: "学员小明", email: "s@x.com", roles: ["student"] }));
});
await pg.route("http://127.0.0.1:8000/**", async (route) => {
  const req = route.request();
  const headers = {};
  for (const [k, v] of Object.entries(req.headers())) {
    if (/^content-length$/i.test(k) || /^authorization$/i.test(k)) continue;
    headers[k] = String(v);
  }
  headers["X-Force-Role"] = "student";
  headers["X-Force-User-Id"] = "802";
  const method = req.method();
  const body = req.postDataBuffer();
  try {
    const resp = await fetch(req.url(), { method, headers, body: body ?? undefined });
    const buf = Buffer.from(await resp.arrayBuffer());
    const outHeaders = {};
    resp.headers.forEach((v, k) => {
      if (/^content-encoding$/i.test(k) || /^content-length$/i.test(k)) return;
      outHeaders[k] = v;
    });
    await route.fulfill({ status: resp.status, headers: outHeaders, body: buf });
  } catch {
    await route.abort();
  }
});

const api403s = [];
pg.on("response", (r) => {
  if ((r.url().includes("/api/admin/rag") || r.url().includes("/api/mcp/")) && r.status() === 403) {
    api403s.push(r.url().split("/api/")[1]);
  }
});
void api403s; // 保留响应监听（诊断用途）

try {
  // student 直连 /admin/rag → 守卫拦截（重定向到 /dashboard 或显示无权限）
  await pg.goto(`${BASE}/admin/rag`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.waitForTimeout(6000); // 首次冷加载水合慢
  const url = pg.url();
  check("student 访问 /admin/rag 被守卫拦截（重定向）", !url.includes("/admin/rag"), url);

  // 后端 API 403（前端守卫早于 API 拦截，故此处直连后端验证双保险）
  const student403 = await fetch("http://127.0.0.1:8000/api/admin/rag/collections", {
    headers: { "X-Force-Role": "student", "X-Force-User-Id": "802" },
  });
  check("student 直连 rag API 返回 403", student403.status === 403, `status=${student403.status}`);

  // student 直连 /admin/mcp
  await pg.goto(`${BASE}/admin/mcp`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.waitForTimeout(6000);
  const url2 = pg.url();
  check("student 访问 /admin/mcp 被守卫拦截（重定向）", !url2.includes("/admin/mcp"), url2);
  const studentMcp403 = await fetch("http://127.0.0.1:8000/api/mcp/servers", {
    headers: { "X-Force-Role": "student", "X-Force-User-Id": "802" },
  });
  check("student 直连 mcp API 返回 403", studentMcp403.status === 403, `status=${studentMcp403.status}`);
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task04 RBAC：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
