import { test, expect } from "@playwright/test";
import { login, ADMIN } from "./helpers";

test("探针：浏览器内 admin token 调用题型枚举", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, ADMIN.account, ADMIN.password, "/dashboard");
  const token = await page.evaluate(() => localStorage.getItem("edu:auth:token") || localStorage.getItem("tok") || "");
  console.log("TOKEN head:", token.slice(0, 20), "len=", token.length);
  const result = await page.evaluate(async (tok) => {
    const out: Record<string, unknown> = {};
    for (const path of ["/api/admin/questions/types", "/api/admin/questions/questions/1"]) {
      const t0 = Date.now();
      try {
        const r = await fetch(`http://127.0.0.1:8000${path}`, {
          headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        });
        const text = await r.text();
        let parsed: { code?: unknown } | null = null;
        try { parsed = JSON.parse(text) as { code?: unknown } | null; } catch {}
        out[path] = { status: r.status, ms: Date.now() - t0, code: parsed?.code ?? null, hasData: parsed ? "data" in parsed : false, bodyHead: text.slice(0, 60) };
      } catch (e: unknown) {
        out[path] = { ms: Date.now() - t0, err: e instanceof Error ? e.message : String(e) };
      }
    }
    return out;
  }, token);
  console.log("RESULT:", JSON.stringify(result, null, 2));
  expect(true).toBeTruthy();
});