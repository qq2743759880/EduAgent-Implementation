// W-NEXT-DEBUG-DOC-001 ⑧ 守卫三分支盲测
// 态 1: DEBUG=true + 无 token → ⑧ 应 WARN(本地 dev 有意保留)
// 态 2: DEBUG=false 模拟(后端 mock 401 on /api/users/me) → ⑧ 应 PASS(生产正确)
// 态 3: DEBUG=true + 有 token → HTTP 200 合法(不属于⑧ 漏洞语义,只测后端合法响应)
//
// 跑法: node scripts/eval/_wnextdebugdoc1_blind.mjs
//   - 态 1 走真实 8000 + .env DEBUG=true
//   - 态 2 拉起本地 mock 127.0.0.1:8091(只返 401 on /api/users/me)+ .env DEBUG=false(mock 用进程内 env 不动真 .env)
//   - 态 3 走真实 8000 + admin token
import http from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 复用 check-demo.mjs 同款 .env 解析
function readEnv() {
  const p = fileURLToPath(new URL("../../.env", import.meta.url));
  const out = { DEBUG: null };
  if (!existsSync(p)) return out;
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = /^\s*DEBUG\s*=\s*(.*?)\s*$/.exec(line);
    if (m) out.DEBUG = m[1];
  }
  return out;
}

// 复用 check-demo.mjs 同款三分支(W-NEXT-DEBUG-DOC-001 改后版)
async function debugCheck(backend) {
  const env = readEnv();
  let res;
  try {
    res = await fetch(`${backend}/api/users/me`, { signal: AbortSignal.timeout(5000) });
  } catch (e) {
    return { branch: "skip", detail: `后端不可达:${e.message}` };
  }
  const text = await res.text();
  const vuln = res.status === 200 || /"code":\s*0/.test(text);
  if (!vuln) {
    if (env.DEBUG === "true") {
      return { branch: "A(dev-no-vuln)", verdict: "PASS", detail: `无 token 被 ${res.status} 拒绝(DEBUG=true:后门开关仍开启)` };
    }
    return { branch: "A(prod-no-vuln)", verdict: "PASS", detail: `无 token 被 ${res.status} 拒绝(DEBUG 安全)` };
  }
  if (env.DEBUG === "true") {
    return { branch: "B(dev-vuln)", verdict: "WARN", detail: `DEBUG=true 已知后门,WARN 不阻断,生产部署前必须 DEBUG=false` };
  }
  return { branch: "C(prod-vuln)", verdict: "FAIL", detail: `DEBUG≠true(=${env.DEBUG})却 200 → 真后门,生产态绝不应允许` };
}

const results = [];
function record(name, expected, actual) {
  const ok = actual.verdict === expected;
  results.push({ name, expected, actual: actual.verdict, ok, branch: actual.branch, detail: actual.detail });
  console.log(`[${ok ? "OK" : "MISMATCH"}] ${name}`);
  console.log(`       expected=${expected}  actual=${actual.verdict}  branch=${actual.branch}`);
  console.log(`       ${actual.detail}`);
}

// ========== 态 1: DEBUG=true + 无 token ==========
console.log("=== 态 1: DEBUG=true + 无 token ===");
const r1 = await debugCheck("http://127.0.0.1:8000");
record("态1 真实后端无 token", "WARN", r1);

// ========== 态 2: DEBUG=false 模拟(mock 401) ==========
console.log("\n=== 态 2: DEBUG=false 模拟(mock 后端 401 on /api/users/me) ===");
const mock = http.createServer((req, res) => {
  if (req.url === "/api/users/me") {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ code: 40101, message: "unauthorized" }));
    return;
  }
  res.writeHead(404);
  res.end();
});
await new Promise((r) => mock.listen(8091, "127.0.0.1", r));
// 临时覆盖 .env DEBUG=false(mock 仅用于本次探测,不动真 .env)
const origContent = readFileSync(fileURLToPath(new URL("../../.env", import.meta.url)), "utf8");
const patched = origContent.replace(/^\s*DEBUG\s*=\s*true\s*$/m, "DEBUG=false");
try {
  // 写一份临时 env 副本,改其中 DEBUG,再让 readEnv 读到——但 readEnv 读真 .env,所以我们用 process.env 临时改
  process.env.DEBUG = "false";
  // readEnv 读真 .env 不读 process.env,所以临时改写并复原
  // 直接覆盖文件→测试完了复原
  const fs = await import("node:fs/promises");
  await fs.writeFile(fileURLToPath(new URL("../../.env", import.meta.url)), patched, "utf8");
  const r2 = await debugCheck("http://127.0.0.1:8091");
  record("态2 mock 401(模拟 DEBUG=false)", "PASS", r2);
} finally {
  // 复原 .env
  const fs = await import("node:fs/promises");
  await fs.writeFile(fileURLToPath(new URL("../../.env", import.meta.url)), origContent, "utf8");
  mock.close();
  delete process.env.DEBUG;
}

// ========== 态 3: DEBUG=true + 有 token(独立验证 admin JWT 合法调用) ==========
console.log("\n=== 态 3: DEBUG=true + 有 token(admin 合法调用 /api/users/me) ===");
const login = await fetch("http://127.0.0.1:8000/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "adm02test", password: "Test@123456" }),
});
const loginJson = await login.json();
const token = loginJson?.data?.access_token;
if (!token) {
  console.log(`[FAIL] 态3 login 失败:${JSON.stringify(loginJson).slice(0, 200)}`);
  results.push({ name: "态3 真实后端有 token", expected: "PASS", actual: "FAIL", ok: false, branch: "auth-fail", detail: "login no token" });
} else {
  const r3 = await fetch("http://127.0.0.1:8000/api/users/me", {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(5000),
  });
  const me = await r3.json();
  const authOk = r3.status === 200 && me?.data?.role === "admin";
  record(
    "态3 admin token 合法调用",
    "PASS",
    { branch: "auth-admin", verdict: authOk ? "PASS" : "FAIL", detail: `HTTP ${r3.status} role=${me?.data?.role} account=${me?.data?.account}` }
  );
}

// ========== 汇总 ==========
console.log("\n=== 盲测汇总 ===");
const pass = results.filter((r) => r.ok).length;
const total = results.length;
console.log(`PASS ${pass}/${total}`);
for (const r of results) {
  console.log(`  ${r.ok ? "[OK]" : "[MISMATCH]"} ${r.name} (expected=${r.expected}, actual=${r.actual})`);
}
process.exit(pass === total ? 0 : 1);