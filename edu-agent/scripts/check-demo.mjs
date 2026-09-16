// EduAgent 演示前检查单(task18 七件套 + DEBUG advisory)
// 用法: node scripts/check-demo.mjs [--fail-drill] [--no-color]
// 零新依赖:Node >= 18(fetch / net / child_process 均内置)。
// 检查项:① Milvus socket ② Redis(docker exec redis-cli ping)③ MongoDB socket
//         ④ 后端 8000 /health ⑤ 前端 3000 /login-register.html + 前端形态判别(dev/prod,T5-C2)
//         ⑥ 登录链路(admin+student 各一次 login + /api/auth/me)
//         ⑦ 8 个核心 html 页 200  ⑧ advisory:DEBUG 虚拟管理员漏洞探测(教训 6,三分支语义)
// ⑨ 抽验页 /admin-users-refine-proto.html 200(C5-D2 扩清单)  ⑩ 契约对账门 febe_contract_check.py
// ⑪ VEC-LOCK embed 一致性健康门（edu_knowledge 元数据全=锁定 BGE-M3 revision）
// 共 11 项检查。全绿才 exit 0;FAIL 时逐项给一句话处置指引;--fail-drill 用假端口验证失败路径(不动真实服务)。
import net from "node:net";
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// ---------- 配置(按演示机实际环境修改这里) ----------
const VMX_PATH = "E:\\tt\\CentOS 7 64 位 的克隆 docker\\CentOS 7 64 位 的克隆 docker.vmx";
const MILVUS = { host: "192.168.85.101", port: 19530 };
const MONGO = { host: "192.168.85.101", port: 27017 };
const REDIS_CONTAINER = "edu-redis-standalone";
const BACKEND = process.env.CHECK_DEMO_BACKEND || "http://127.0.0.1:8000"; // env 覆盖仅用于 ⑧ WARN 分支自测
const FRONTEND = "http://127.0.0.1:3000";
const ADMIN = { account: "adm02test", password: "Test@123456" };
const STUDENT = { account: "user000001", password: "Test@123456" };
// 关键页 8 个(核心故事线页面)
const PAGES = [
  "login-register.html",
  "courses.html",
  "course-detail.html?id=1",
  "dashboard.html",
  "learning.html",
  "admin-dashboard.html",
  "admin-mcp.html",
  "admin-rag-upload.html",
];
const SOCKET_TIMEOUT_MS = 3000; // 控制总耗时 <1 分钟(GWT 指标)的关键
const HTTP_TIMEOUT_MS = 5000;
const DOCKER_TIMEOUT_MS = 8000;

// ---------- 参数 ----------
const args = process.argv.slice(2);
const DRILL = args.includes("--fail-drill");
const NOCOLOR = args.includes("--no-color") || !process.stdout.isTTY;
const C = NOCOLOR
  ? { g: "", r: "", y: "", b: "", dim: "", x: "" }
  : { g: "\x1b[32m", r: "\x1b[31m", y: "\x1b[33m", b: "\x1b[36m", dim: "\x1b[2m", x: "\x1b[0m" };

// ---------- 工具 ----------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 读 edu-agent/.env 判 DEBUG/ENV_NAME(A-G4 三分支判据):缺文件/缺值按安全缺省
// ENV_NAME 缺省 = null(非 local)——T5-C1 修:原默认 "local" 会把「未声明环境」误判为安全开发态
function readDevEnv() {
  const envPath = new URL("../.env", import.meta.url);
  const out = { DEBUG: null, ENV_NAME: null };
  if (!existsSync(envPath)) return out;
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m) continue;
    if (m[1] === "DEBUG") out.DEBUG = m[2];
    if (m[1] === "ENV_NAME") out.ENV_NAME = m[2] || null; // 空值同样视为未确证 local
  }
  return out;
}

async function timed(fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    return { ok: true, ms: Date.now() - t0, detail: detail || "" };
  } catch (e) {
    return { ok: false, ms: Date.now() - t0, detail: String(e?.message || e).slice(0, 160), err: e };
  }
}

// socket 探活(带超时;VM 关机时 SYN 无响应,靠超时兜底防止卡满 Windows 默认 21s)
function socketProbe(host, port, timeoutMs = SOCKET_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const s = net.connect({ host, port });
    let done = false;
    const finish = (err) => {
      if (done) return;
      done = true;
      s.destroy();
      err ? reject(err) : resolve();
    };
    s.setTimeout(timeoutMs, () => finish(new Error(`连接超时(>${timeoutMs}ms),主机不可达`)));
    s.on("connect", () => finish(null));
    s.on("error", (e) => {
      const m = { ECONNREFUSED: "连接被拒绝", EHOSTUNREACH: "主机不可达", ENETUNREACH: "网络不可达" }[e.code] || e.message;
      finish(new Error(m));
    });
  });
}

async function httpProbe(url, { method = "GET", headers = {}, body, expect = 200, mustJson } = {}) {
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  const text = await res.text();
  if (res.status !== expect) throw new Error(`HTTP ${res.status}(期望 ${expect})`);
  if (mustJson) {
    let j;
    try { j = JSON.parse(text); } catch { throw new Error("响应非 JSON"); }
    if (mustJson.code !== undefined && j.code !== mustJson.code) {
      throw new Error(`code=${j.code} ${j.message || ""}`.trim());
    }
    return j;
  }
  return undefined;
}

// 运行本机命令(docker exec 等),带超时,非零退出码抛错
function runCmd(cmd, cargs, timeoutMs = DOCKER_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let stdout = "", stderr = "", settled = false;
    const child = spawn(cmd, cargs); // 不用 shell:true:避免 DEP0190,且 docker.exe 可经 PATH 解析
    const timer = setTimeout(() => {
      if (!settled) { settled = true; child.kill(); reject(new Error(`命令超时(>${timeoutMs}ms)`)); }
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error(e.code === "ENOENT" ? "命令不存在" : e.message)); } });
    child.on("close", (code) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      const out = (stdout + stderr).trim();
      if (code !== 0) {
        const msg = /pipe\/docker_engine|cannot find the file specified/i.test(out)
          ? "docker 引擎未运行(Docker Desktop 未启动)"
          : out.split("\n")[0].slice(0, 120) || `退出码 ${code}`;
        reject(new Error(msg));
      } else resolve(out);
    });
  });
}

// ---------- 契约对账（FE-BE-CONTRACT 三方对账门）----------
// 跑 edu-agent/scripts/eval/febe_contract_check.py，解析 [SUMMARY] 行判定：
//   断点 >0  -> FAIL（前端调用了后端不存在的路由）
//   待接/未冻结 >0 -> WARN（不阻断）
//   exit 2 = 后端不可达（以④红项为准，此处降级为 WARN，避免重复误报）
const FEBE_SCRIPT = fileURLToPath(new URL("../scripts/eval/febe_contract_check.py", import.meta.url));

async function resolvePython() {
  for (const c of ["python3", "python"]) {
    try {
      await runCmd(c, ["--version"], 5000);
      return c;
    } catch { /* try next */ }
  }
  // 末位兜底：本机托管 python（Git Bash 下 PATH 通常有，但保险起见）
  const fallback = "C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe";
  if (existsSync(fallback)) return fallback;
  throw new Error("未找到 python 解释器（需 python3/python 在 PATH）");
}

function runPy(python, args) {
  return new Promise((resolve, reject) => {
    let stdout = "", stderr = "", settled = false;
    const child = spawn(python, args, { windowsHide: true });
    const timer = setTimeout(() => {
      if (!settled) { settled = true; child.kill(); reject(new Error("契约对账超时(>60s)")); }
    }, 60000);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(e); } });
    child.on("close", (code) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
}

// ---------- 结果收集 ----------
const results = [];
async function check(no, name, fn) {
  const r = await timed(fn);
  // advisory 项走 WARN(软,不阻断 exit)而非 FAIL:检查函数静态 __warn 或按结果动态 e.__warn
  // (T5-C1:⑧ 分支 C 必须真红,故 ⑧ 不再静态 __warn,改由分支 B 抛 e.__warn 标 WARN)
  const isWarn = !r.ok && (fn.__warn === true || r.err?.__warn === true);
  results.push({ no, name, ...r, warn: isWarn });
  if (r.ok) {
    console.log(`${C.g}[PASS]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}${r.detail ? C.dim + "  " + r.detail + C.x : ""}`);
  } else if (isWarn) {
    console.log(`${C.y}[WARN]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}`);
    console.log(`       ${C.y}-> ${fn.__fix ? fn.__fix(r.detail) : r.detail}${C.x}`);
  } else {
    console.log(`${C.r}[FAIL]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}`);
    console.log(`       ${C.y}-> ${fn.__fix ? fn.__fix(r.detail) : r.detail}${C.x}`);
  }
  return r.ok;
}

// 处置指引(FAIL 时一句话)
const FIX = {
  vm: (d) => `开启 VMware 虚拟机: vmrun start "${VMX_PATH}" nogui,等 60s${existsSync(VMX_PATH) ? "" : `(注意:配置的 vmx 路径不存在,请确认虚拟机实际路径)`} [${d}]`,
  redis: (d) => `docker start ${REDIS_CONTAINER}(若 docker 引擎未运行,先启动 Docker Desktop)[${d}]`,
  backend: (d) => `cd edu-agent && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 [${d}]`,
  frontend: (d) => `cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000 [${d}]`,
  debug: (d) => `DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端) [${d}]`,
};

// ---------- 主流程 ----------
console.log(`${C.b}=== EduAgent 演示前检查单 check-demo.mjs ===${C.x}`);
console.log(`${C.dim}模式: ${DRILL ? "fail-drill(假端口演练,结果仅验证失败路径)" : "normal"}  时间: ${new Date().toLocaleString()}${C.x}\n`);
if (DRILL) {
  console.log(`${C.y}${C.dim}--fail-drill:① Milvus→127.0.0.1:19531 ② Redis→容器内 6380 假端口 ③ Mongo→127.0.0.1:27018(必然失败,验证 FAIL 输出与指引)${C.x}\n`);
}

const milvusTarget = DRILL ? { host: "127.0.0.1", port: 19531 } : MILVUS;
const mongoTarget = DRILL ? { host: "127.0.0.1", port: 27018 } : MONGO;
const redisArgs = DRILL
  ? ["exec", REDIS_CONTAINER, "redis-cli", "-p", "6380", "ping"]
  : ["exec", REDIS_CONTAINER, "redis-cli", "ping"];

// ① Milvus
await check("①", `Milvus 连通 ${milvusTarget.host}:${milvusTarget.port}`, Object.assign(
  () => socketProbe(milvusTarget.host, milvusTarget.port),
  { __fix: FIX.vm }));

// ② Redis
await check("②", `Redis(docker exec ${REDIS_CONTAINER} redis-cli ping)`, Object.assign(
  async () => {
    const out = await runCmd("docker", redisArgs);
    if (!/PONG/i.test(out)) throw new Error(`ping 返回异常: ${out.slice(0, 80)}`);
    return "PONG";
  },
  { __fix: FIX.redis }));

// ③ MongoDB
await check("③", `MongoDB 连通 ${mongoTarget.host}:${mongoTarget.port}`, Object.assign(
  () => socketProbe(mongoTarget.host, mongoTarget.port),
  { __fix: FIX.vm }));

// ④ 后端 /health
await check("④", `后端 8000 /health`, Object.assign(
  async () => {
    const j = await httpProbe(`${BACKEND}/health`, { mustJson: {} });
    if (j?.status !== "ok") throw new Error(`status=${j?.status}`);
    return `status=ok v${j.version || "?"}`;
  },
  { __fix: FIX.backend }));

// ⑤ 前端登录页 + 前端形态判别(T5-C2:dev 开发形态从未被验收门覆盖的假绿)
// 判别法:next dev 会暴露 /_next/static/development/_buildManifest.js(200),生产 build 无此路径(404)
await check("⑤", `前端 3000 /login-register.html(+生产形态判别)`, Object.assign(
  async () => {
    await httpProbe(`${FRONTEND}/login-register.html`);
    let devForm = false;
    try {
      await httpProbe(`${FRONTEND}/_next/static/development/_buildManifest.js`);
      devForm = true;
    } catch {
      devForm = false; // 404 = 生产 build 形态
    }
    if (devForm) {
      const e = new Error("前端为 next dev 开发形态(_buildManifest dev 探针 200),非生产 build,生产形态未验收");
      e.__warn = true;
      throw e;
    }
    return "生产 build 形态(_buildManifest dev 探针 404)";
  },
  { __fix: (d) => `cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000(验生产形态:deploy.mjs stop 后 start,先 build 再起)[${d}]` }));

// ⑥ 登录链路(admin + student 各一次 login + /api/auth/me)
await check("⑥", `登录链路 login×2 + /api/auth/me×2`, Object.assign(
  async () => {
    const who = async (acc, expectRole) => {
      const j = await httpProbe(`${BACKEND}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: { account: acc.account, password: acc.password },
        mustJson: { code: 0 },
      });
      const tok = j?.data?.access_token;
      if (!tok) throw new Error(`${acc.account}: 无 access_token`);
      const me = await httpProbe(`${BACKEND}/api/auth/me`, {
        headers: { Authorization: `Bearer ${tok}` },
        mustJson: { code: 0 },
      });
      const role = me?.data?.role;
      if (role !== expectRole) throw new Error(`${acc.account}: role=${role} 期望 ${expectRole}`);
      return `${acc.account}(role=${role},user_id=${me?.data?.user_id})`;
    };
    const a = await who(ADMIN, "admin");
    const s = await who(STUDENT, "student");
    return `${a} + ${s}`;
  },
  { __fix: (d) => `先过 ④ 后端: cd edu-agent && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000(若账号失效查 DB 种子) [${d}]` }));

// ⑦ 关键页 200(8 个核心 html)
await check("⑦", `关键页 200 × ${PAGES.length}`, Object.assign(
  async () => {
    const bad = [];
    for (const p of PAGES) {
      try { await httpProbe(`${FRONTEND}/${p}`); } catch (e) { bad.push(`${p}(${e.message})`); }
    }
    if (bad.length) throw new Error(`${bad.length}/${PAGES.length} 页异常: ${bad.join(", ")}`);
    return `${PAGES.length}/${PAGES.length} 全 200`;
  },
  { __fix: FIX.frontend }));

// ⑧ advisory:DEBUG 虚拟管理员漏洞(教训 6,A-G4 改探真后门 + 三分支语义)
// 分支:
//   A) 无 token GET /api/users/me 被 401/403 拒绝 → PASS(文案按 DEBUG 动态:DEBUG=true 时不自称「安全」)
//   B) 返回 200/有数据(后门存在)且 DEBUG=true 且 ENV_NAME==='local'(确证读到) → WARN 不阻断 exit 0(本机开发态预期)
//   C) 返回 200/有数据但 DEBUG≠true 或 ENV_NAME 缺省/≠'local' → 红,阻断 exit 1(安全缺省=非 local)
// ENV_NAME 从 edu-agent/.env 读(grep ^ENV_NAME=),缺省=null 即非 local(T5-C1:不再默认 local);
// fail-drill 行为不变(①②③红,④-⑨按假端口语义)。
const debugCheck = Object.assign(
  async () => {
    const env = readDevEnv();
    let res;
    try {
      res = await fetch(`${BACKEND}/api/users/me`, { signal: AbortSignal.timeout(HTTP_TIMEOUT_MS) });
    } catch (e) {
      // 后端不可达:本项无法探测,④ 已红,不重复误报 DEBUG 漏洞
      return `跳过:后端不可达(以④红项为准),DEBUG 漏洞未探测`;
    }
    const text = await res.text();
    const vuln = res.status === 200 || /"code":\s*0/.test(text);
    if (!vuln) {
      // 分支 A:被拒即 PASS;DEBUG=true 时只说明「.env 后门开关开着」,不得自称 DEBUG 安全(T5-C6)
      return env.DEBUG === "true"
        ? `无 token 被 ${res.status} 拒绝(DEBUG=true:.env 后门开关仍开启,按分支 B/C 语义判定)`
        : `无 token 被 ${res.status} 拒绝(DEBUG 安全)`;
    }
    const isLocalDev = env.DEBUG === "true" && env.ENV_NAME === "local";
    if (isLocalDev) {
      // 分支 B:开发态已知后门,ENV_NAME 确证 local → WARN(软)不阻断,避免永久红=狼来了
      const e = new Error(`WARN 开发态虚拟管理员后门存在(DEBUG=${env.DEBUG},ENV_NAME=${env.ENV_NAME});部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门`);
      e.__warn = true;
      throw e;
    }
    // 分支 C:DEBUG 未开却 200(真后门),或 ENV_NAME 未确证 local(缺省/其它环境)→ 红,阻断 exit 1
    throw new Error(`无 token 返回 HTTP ${res.status} 有数据(DEBUG=${env.DEBUG},ENV_NAME=${env.ENV_NAME === null ? "缺省(≠local)" : env.ENV_NAME});未确证本地开发态即危险,上线前必须 DEBUG=false`);
  },
  { __fix: FIX.debug });
await check("⑧", `advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支)`, debugCheck);

// ⑨ 抽验页 /admin-users-refine-proto.html 200(C5-D2 扩清单)
await check("⑨", `抽验页 200 /admin-users-refine-proto.html(C5-D2)`, Object.assign(
  () => httpProbe(`${FRONTEND}/admin-users-refine-proto.html`),
  { __fix: FIX.frontend }));

// ⑩ 契约对账（FE-BE-CONTRACT 四方对账门）：跑 febe_contract_check.py（W-NEXT-FE-001 四档）
//   断点(bp) >0                         -> FAIL 红（前端调用了后端不存在的路由）
//   在用未冻结(in_use_unfrozen) >0        -> FAIL 红（前端实际在用但无冻结契约 = 治理压力核心，CI 阻断）
//   未冻结仅后端(unfrozen_only) >0        -> WARN（后端有、前端未用、无契约，不阻断）
//   待接(to_connect) >0                  -> WARN（后端有、前端未接，不阻断）
//   后端不可达(exit 2)                   -> WARN（以④为准）
const contractGate = Object.assign(
  async () => {
    const py = await resolvePython();
    const { code, stdout, stderr } = await runPy(py, [FEBE_SCRIPT]);
    const summary = /\[SUMMARY\]\s*breakpoints=(\d+)\s+in_use_unfrozen=(\d+)\s+unfrozen_only=(\d+)\s+to_connect=(\d+)/
      .exec(stdout || "");
    if (!summary) {
      throw new Error(`未解析到 [SUMMARY]（exit=${code}）；stderr=${(stderr || "").slice(0, 200)}`);
    }
    const bp = +summary[1], iu = +summary[2], uo = +summary[3], tc = +summary[4];
    if (code === 2) {
      const e = new Error(`后端不可达，契约对账跳过（以④红项为准）：断点=${bp} 在用未冻结=${iu} 未冻结仅后端=${uo} 待接=${tc}`);
      e.__warn = true;
      throw e;
    }
    // 红/阻断：断点>0 或 前端在用却无契约>0
    if (bp > 0) {
      throw new Error(`断点 ${bp} 条（前端调用了后端不存在的路由），见 febe_contract_check.py ① 段`);
    }
    if (iu > 0) {
      throw new Error(`在用未冻结 ${iu} 条（前端实际在用的接口无冻结契约，CI 红/阻断；详见 febe_contract_check.py ② 段，清单移交 W-NEXT-CONTRACT-001）`);
    }
    // WARN，不阻断：后端有前端未接 / 后端有契约无（前端未用）
    if (tc > 0 || uo > 0) {
      const e = new Error(`待接 ${tc} / 未冻结仅后端 ${uo} 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）`);
      e.__warn = true;
      throw e;
    }
    return `断点0 在用未冻结0 未冻结仅后端0 待接0`;
  },
  { __fix: (d) => `python edu-agent/scripts/eval/febe_contract_check.py 查看四方差异清单（断点·在用未冻结 红 / 待接·未冻结 WARN） [${d}]` });
await check("⑩", `契约对账门 febe_contract_check.py（断点·在用未冻结 红 / 待接·未冻结 WARN）`, contractGate);

// ⑪ VEC-LOCK：embed 一致性健康门（VEC-G5）——edu_knowledge 元数据全 = 锁定 BGE-M3 revision，
//    无 fallback 混写/未归一化/空文本。走 venv python 探针（查 Milvus），PASS 才算绿。
const VECLOCK_PROBE = new URL("../veclock_health_probe.py", import.meta.url).pathname;
const EDU_PY = new URL("../.venv/Scripts/python.exe", import.meta.url).pathname;
await check("⑪", `VEC-LOCK embed 一致性(edu_knowledge 元数据)`, Object.assign(
  async () => runCmd(EDU_PY, [VECLOCK_PROBE], 60000),
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\veclock_health_probe.py 排查 embed 元数据/索引状态 [${d}]` }));

// ⑬ W-NEXT-MCP-001「MCP 三态」健康门（能力对账 + 内置工具落审计 + 字段级脱敏）
//   打 live 8000 + MySQL，真实调 calculator（内置）验证审计落库(server_id=0)与字段脱敏；
//   探针末行输出 [TRISTATE] <json>，env_blocked→WARN（不阻断，仅环境未就绪），其余失败→红。
const TRISTATE_PROBE = new URL("../scripts/eval/mcp_tristate_probe.py", import.meta.url).pathname;
await check("⑬", `MCP 三态门（能力对账+内置落审计+脱敏）`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [TRISTATE_PROBE], 60000);
    const m = /\[TRISTATE\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      if (code === 2) {
        const e = new Error(`环境阻塞（后端/DB 不可达，以④红项为准）: ${(stdout || "").slice(0, 200)}`);
        e.__warn = true; throw e;
      }
      throw new Error(`探针未输出 [TRISTATE]（exit=${code}）: ${(stdout || "").slice(0, 200)}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/DB 不可达，跳过）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if (!j.audit_ok) throw new Error(`能力对账未通过: ${j.detail || ""}`);
    if (!j.builtin_logged) throw new Error(`内置工具未落审计: ${j.detail || ""}`);
    if (!j.redacted) throw new Error(`字段脱敏未生效: ${j.detail || ""}`);
    return `审计checked=${j.audit_checked} 内置落库✔ 脱敏✔`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\mcp_tristate_probe.py 排查（需 8000 在线 + MySQL 可达） [${d}]` }));

// ⑫ HITL 真实性健康门（SURFACED-1 闭环实证，P0）：/health 200 + chat 流式 knowledge_import
//    HITL confirm → 续流执行，**不再出现** 42200「必须提供 tool_id」症状（回归红线 =
//    HITL-FIX 后 admin confirm 写类工具零落库的根因）。走 venv python 探针（真实 HTTP + 只读
//    SQL 取证），PASS 才算绿；模型本轮未触发 knowledge_import 时观测返回（单测已覆盖 tool_name 修复），不阻断 exit。
const HITL_PROBE = new URL("../hitl_realness_probe.py", import.meta.url).pathname;
await check("⑫", `HITL 真实性(confirm 续流不再 42200)`, Object.assign(
  async () => {
    const out = await runCmd(EDU_PY, [HITL_PROBE], 90000);
    let j;
    try { j = JSON.parse(out); } catch { throw new Error(`探针输出非 JSON: ${String(out).slice(0, 200)}`); }
    if (j.error) throw new Error(j.error);
    if (j.regression) throw new Error(j.regression);
    if (!j.health_ok) throw new Error("后端 /health 非 ok");
    if (j.pending_confirm_seen && j.confirm_resumed && !j.symptom_in_confirm_pass)
      return `pending_confirm→confirm 真可达,42200 症状消失(task ${j.task_before}→${j.task_after})`;
    if (!j.pending_confirm_seen) return `模型未触发 knowledge_import,跳过(单测已覆盖): ${j.note || ""}`;
    return `confirm 续流无 42200 症状`;
  },
  { __fix: (d) => `确认 HITL_ENABLED=True 且后端可达;SURFACED-1 修复见 tests/test_chat_tool_calling.py [${d}]` }));

// ⑭ W-NEXT-INT-001A 内部可见性健康门：student 检索内部关键词 0 命中 + admin 命中 > 0（T14 S6 修复）
//    走 wnextint1a_visibility_probe.py 探针（真实 HTTP login + /api/chat/search + format_docs=False），
//    末行输出 [WINT1A] {student_hits:0, admin_hits:>0, ...}；env_blocked→WARN（不阻断，仅环境未就绪）。
const WINT1A_PROBE = new URL("../scripts/eval/wnextint1a_visibility_probe.py", import.meta.url).pathname;
await check("⑭", `内部可见性(student 0 内部命中 / admin >0)`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [WINT1A_PROBE, "--base", BACKEND], 90000);
    const m = /\[WINT1A\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      if (code === 2) {
        const e = new Error(`环境阻塞（后端不可达，以④红项为准）: ${(stdout || "").slice(0, 200)}`);
        e.__warn = true; throw e;
      }
      throw new Error(`探针未输出 [WINT1A]（exit=${code}）: ${(stdout || "").slice(0, 200)}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/DB 不可达，跳过）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if (!j.student_hits_zero) throw new Error(`student 内部关键词命中 ${j.student_hits_total} 条（S6 回归保护 FAIL）`);
    if (!(j.admin_hits_total > 0)) throw new Error(`admin 内部关键词 0 命中（admin 不被 internal 过滤失效）`);
    return `student=${j.student_hits_total} admin=${j.admin_hits_total}（5 query 全过）`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\wnextint1a_visibility_probe.py --base ${BACKEND} 排查 [${d}]` }));

// ---------- 汇总 ----------
// warn 条目(软)不阻断:绿 = ok 或 warn;仅真正 FAIL(非 ok 且非 warn)计入红项、触发 exit 1
const pass = results.filter((r) => r.ok).length;
const warn = results.filter((r) => !r.ok && r.warn).map((r) => r.no);
const red = results.filter((r) => !r.ok && !r.warn).map((r) => r.no);
const totalMs = results.reduce((a, r) => a + r.ms, 0);
console.log("");
if (red.length === 0) {
  const warnNote = warn.length ? `,WARN ${warn.join("、")}` : "";
  console.log(`${C.g}汇总: 绿 ${pass + warn.length}/${results.length}${warnNote} —— 演示环境就绪${C.x} ${C.dim}(检查耗时 ${totalMs}ms)${C.x}`);
} else {
  const warnNote = warn.length ? `,WARN ${warn.join("、")}` : "";
  console.log(`${C.r}汇总: 绿 ${pass}/${results.length},红项 ${red.join("、")}${warnNote} —— 请按上方指引处置后重跑${C.x} ${C.dim}(检查耗时 ${totalMs}ms)${C.x}`);
}
process.exit(red.length === 0 ? 0 : 1);
