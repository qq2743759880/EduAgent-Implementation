// EduAgent 演示前检查单(task18 七件套 + DEBUG advisory)
// 用法: node scripts/check-demo.mjs [--fail-drill] [--no-color]
// 零新依赖:Node >= 18(fetch / net / child_process 均内置)。
// 检查项:① Milvus socket ② Redis(docker exec redis-cli ping)③ MongoDB socket
//         ④ 后端 8000 /health ⑤ 前端 3000 /login-register.html
//         ⑥ 登录链路(admin+student 各一次 login + /api/auth/me)
//         ⑦ 8 个核心 html 页 200  ⑧ advisory:DEBUG 虚拟管理员漏洞探测(教训 6,三分支语义)
//         ⑨ 抽验页 /admin-users-refine-proto.html 200(C5-D2 扩清单)
// 共 9 项检查。全绿才 exit 0;FAIL 时逐项给一句话处置指引;--fail-drill 用假端口验证失败路径(不动真实服务)。
import net from "node:net";
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

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

// 读 edu-agent/.env 判 DEBUG/ENV_NAME(A-G4 三分支判据):缺文件/缺值按安全缺省(ENV_NAME 缺省=local)
function readDevEnv() {
  const envPath = new URL("../.env", import.meta.url);
  const out = { DEBUG: null, ENV_NAME: "local" }; // ENV_NAME 缺省视为 local(D-04 本机正是缺省态)
  if (!existsSync(envPath)) return out;
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m) continue;
    if (m[1] === "DEBUG") out.DEBUG = m[2];
    if (m[1] === "ENV_NAME") out.ENV_NAME = m[2] || "local";
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

// ---------- 结果收集 ----------
const results = [];
async function check(no, name, fn) {
  const r = await timed(fn);
  const isWarn = fn.__warn && !r.ok; // advisory 项走 WARN(软,不阻断 exit)而非 FAIL
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

// ⑤ 前端登录页
await check("⑤", `前端 3000 /login-register.html`, Object.assign(
  () => httpProbe(`${FRONTEND}/login-register.html`),
  { __fix: FIX.frontend }));

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
//   A) 无 token GET /api/users/me 被 401/403 拒绝 → 安全 PASS「DEBUG 安全」
//   B) 返回 200/有数据(后门存在)且 DEBUG=true + ENV_NAME=local → WARN「开发态虚拟管理员后门存在(已知;部署前必须 DEBUG=false)」——不阻断 exit 0(本机开发态预期)
//   C) 返回 200/有数据且 DEBUG=true + ENV_NAME≠local → 红,阻断 exit 1(真后门/非本地即危险)
// ENV_NAME 从 edu-agent/.env 读(grep ^ENV_NAME=,缺省视为 local);fail-drill 行为不变(①②③红,④-⑨按假端口语义)。
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
    if (!vuln) return `无 token 被 ${res.status} 拒绝(DEBUG 安全)`;
    const isLocalDev = env.DEBUG === "true" && env.ENV_NAME === "local";
    if (isLocalDev) {
      // 开发态已知后门:WARN(软)不阻断,避免永久红=狼来了
      const e = new Error(`WARN 开发态虚拟管理员后门存在(DEBUG=${env.DEBUG},ENV_NAME=${env.ENV_NAME});部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门`);
      e.__warn = true;
      throw e;
    }
    throw new Error(`无 token 返回 HTTP ${res.status} 有数据(DEBUG=${env.DEBUG},ENV_NAME=${env.ENV_NAME});上线前必须 DEBUG=false`);
  },
  { __warn: true, __fix: FIX.debug });
await check("⑧", `advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支)`, debugCheck);

// ⑨ 抽验页(C5-D2 扩清单):admin-users-refine-proto.html 单列第 9 项,
// 不并入 ⑦ 核心故事线(核心页 8 个口径不变);FAIL 指引同前端。
await check("⑨", `抽验页 200 /admin-users-refine-proto.html(C5-D2)`, Object.assign(
  () => httpProbe(`${FRONTEND}/admin-users-refine-proto.html`),
  { __fix: FIX.frontend }));

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
